"""
Web server for Party Mode player UI.

Runs a Starlette/Uvicorn server in a background thread with its own asyncio
event loop. The server MUST NOT block the main thread (which runs the MCP
stdio transport).

Key components:
- Starlette app with routes for player UI and WebSocket connections
- Background thread lifecycle management (start/stop)
- WebSocket connection manager for real-time updates
- Token-based authentication middleware
- Integration with PCRegistry, PermissionResolver, and StorageManager

Routes:
- GET /play?token=xxx - Serve player UI (static HTML)
- POST /action - Submit player action
- GET /character/{player_id} - Get character data (with permission check)
- GET /status - Server health and connected players
- WS /ws?token=xxx - WebSocket connection for real-time updates
"""

import asyncio
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from dm20_protocol.claudmaster.pc_tracking import PCRegistry
from dm20_protocol.permissions import PermissionResolver
from dm20_protocol.storage import DnDStorage

from .auth import TokenManager, detect_host_ip
from .queue import ActionQueue

logger = logging.getLogger("dm20-protocol.party")


# Global server state
_server_thread: Optional[threading.Thread] = None
_server_instance: Optional["PartyServer"] = None
_stop_event: Optional[threading.Event] = None


class ConnectionManager:
    """
    Manages WebSocket connections for Party Mode.

    Tracks active connections per player_id. A player may have multiple
    tabs open, so we store a set of WebSocket connections per player.

    Attributes:
        _connections: Dict mapping player_id -> set of WebSocket connections
    """

    def __init__(self) -> None:
        """Initialize an empty ConnectionManager."""
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = threading.Lock()

    async def connect(self, player_id: str, websocket: WebSocket) -> None:
        """
        Register a new WebSocket connection for a player.

        Args:
            player_id: The player's identifier
            websocket: The WebSocket connection
        """
        await websocket.accept()
        with self._lock:
            if player_id not in self._connections:
                self._connections[player_id] = set()
            self._connections[player_id].add(websocket)
        logger.info(f"WebSocket connected: player_id={player_id} "
                   f"({len(self._connections[player_id])} total connections)")

    def disconnect(self, player_id: str, websocket: WebSocket) -> None:
        """
        Unregister a WebSocket connection for a player.

        Args:
            player_id: The player's identifier
            websocket: The WebSocket connection to remove
        """
        with self._lock:
            if player_id in self._connections:
                self._connections[player_id].discard(websocket)
                if not self._connections[player_id]:
                    del self._connections[player_id]
        logger.info(f"WebSocket disconnected: player_id={player_id}")

    async def send_to_player(self, player_id: str, message: dict) -> int:
        """
        Send a JSON message to all connections for a specific player.

        Args:
            player_id: The player to send to
            message: The JSON-serializable message dict

        Returns:
            Number of connections the message was sent to
        """
        with self._lock:
            connections = self._connections.get(player_id, set()).copy()

        sent = 0
        for ws in connections:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to send message to {player_id}: {e}")
        return sent

    async def broadcast(self, message: dict) -> int:
        """
        Broadcast a JSON message to all connected players.

        Args:
            message: The JSON-serializable message dict

        Returns:
            Number of connections the message was sent to
        """
        with self._lock:
            all_connections = []
            for conns in self._connections.values():
                all_connections.extend(conns)

        sent = 0
        for ws in all_connections:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception as e:
                logger.warning(f"Failed to broadcast message: {e}")
        return sent

    def get_connected_players(self) -> list[str]:
        """
        Get a list of all currently connected player IDs.

        Returns:
            List of player_id strings
        """
        with self._lock:
            return list(self._connections.keys())

    def connection_count(self, player_id: Optional[str] = None) -> int:
        """
        Get the number of connections for a player, or total if player_id is None.

        Args:
            player_id: The player to count connections for, or None for total

        Returns:
            Number of connections
        """
        with self._lock:
            if player_id is not None:
                return len(self._connections.get(player_id, set()))
            return sum(len(conns) for conns in self._connections.values())

    async def close_all(self) -> None:
        """Close all WebSocket connections gracefully."""
        with self._lock:
            all_connections = []
            for conns in self._connections.values():
                all_connections.extend(conns)
            self._connections.clear()

        for ws in all_connections:
            try:
                await ws.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket: {e}")
        logger.info(f"Closed {len(all_connections)} WebSocket connections")


class PartyServer:
    """
    Party Mode web server running in a background thread.

    Manages the Starlette app, Uvicorn server, and integration with
    the MCP server's data layer.

    Attributes:
        token_manager: Token authentication manager
        connection_manager: WebSocket connection manager
        pc_registry: Player character registry
        permission_resolver: Permission validation
        storage: Campaign storage manager
        campaign_dir: Path to the active campaign directory
        host: Server bind address
        port: Server port
        start_time: Server start timestamp
    """

    def __init__(
        self,
        pc_registry: PCRegistry,
        permission_resolver: PermissionResolver,
        storage: DnDStorage,
        campaign_dir: Path,
        host: str = "0.0.0.0",
        port: int = 8080,
    ) -> None:
        """
        Initialize the Party Mode server.

        Args:
            pc_registry: Player character registry
            permission_resolver: Permission validation
            storage: Campaign storage manager
            campaign_dir: Path to the active campaign directory
            host: Server bind address (default: 0.0.0.0)
            port: Server port (default: 8080)
        """
        self.token_manager = TokenManager()
        self.connection_manager = ConnectionManager()
        self.pc_registry = pc_registry
        self.permission_resolver = permission_resolver
        self.storage = storage
        self.campaign_dir = campaign_dir
        self.host = host
        self.port = port
        self.start_time = datetime.now()

        # Initialize action queue
        self.action_queue = ActionQueue(campaign_dir)

        # Detect LAN IP for QR codes
        self.host_ip = detect_host_ip()

        # Build Starlette app
        self.app = self._build_app()

        logger.info(f"PartyServer initialized on {host}:{port}")

    def _build_app(self) -> Starlette:
        """
        Build the Starlette application with routes.

        Returns:
            Configured Starlette app
        """
        routes = [
            Route("/play", self.get_play, methods=["GET"]),
            Route("/action", self.post_action, methods=["POST"]),
            Route("/action/{action_id}/status", self.get_action_status, methods=["GET"]),
            Route("/character/{player_id}", self.get_character, methods=["GET"]),
            Route("/status", self.get_status, methods=["GET"]),
            WebSocketRoute("/ws", self.websocket_endpoint),
        ]

        return Starlette(debug=False, routes=routes)

    async def get_play(self, request: Request) -> Response:
        """
        Serve the player UI HTML page.

        Validates the session token and serves static/index.html with
        the player's name injected.

        Args:
            request: Starlette request object

        Returns:
            HTML response or 401 Unauthorized
        """
        token = request.query_params.get("token")
        if not token:
            return PlainTextResponse("Missing token", status_code=401)

        player_id = self.token_manager.validate_token(token)
        if not player_id:
            return PlainTextResponse("Invalid token", status_code=401)

        # Load static HTML and inject player name
        static_file = Path(__file__).parent / "static" / "index.html"
        if not static_file.exists():
            return PlainTextResponse("UI not available", status_code=503)

        html = static_file.read_text()
        # Simple placeholder replacement (Task 3 will build proper UI)
        html = html.replace("{player_name}", player_id)
        html = html.replace("{token}", token)

        return HTMLResponse(html)

    async def post_action(self, request: Request) -> Response:
        """
        Handle player action submission.

        Validates token and queues the action for host processing.

        Args:
            request: Starlette request object

        Returns:
            JSON response with action_id and status
        """
        # Extract token from Authorization header or query param
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            token = request.query_params.get("token", "")

        player_id = self.token_manager.validate_token(token)
        if not player_id:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        try:
            body = await request.json()
            action_text = body.get("action", "")
        except Exception as e:
            return JSONResponse({"error": f"Invalid request: {e}"}, status_code=400)

        if not action_text.strip():
            return JSONResponse({"error": "Empty action"}, status_code=400)

        action_id = self.action_queue.push(player_id, action_text)
        logger.info(f"Action queued: {action_id} from {player_id}")

        return JSONResponse({
            "success": True,
            "action_id": action_id,
            "player_id": player_id,
            "status": "pending",
        })

    async def get_action_status(self, request: Request) -> Response:
        """
        Get the status of a submitted action.

        Args:
            request: Starlette request object

        Returns:
            JSON response with action status
        """
        action_id = request.path_params.get("action_id")
        if not action_id:
            return JSONResponse({"error": "Missing action_id"}, status_code=400)

        status = self.action_queue.get_status(action_id)
        if status is None:
            return JSONResponse({"error": "Action not found"}, status_code=404)

        return JSONResponse({
            "action_id": action_id,
            "status": status,
        })

    async def get_character(self, request: Request) -> Response:
        """
        Get character data for a specific player.

        Validates token and checks permissions before returning character data.

        Args:
            request: Starlette request object

        Returns:
            JSON response with character data or error
        """
        player_id = request.path_params.get("player_id")
        if not player_id:
            return JSONResponse({"error": "Missing player_id"}, status_code=400)

        # Validate token
        token = request.query_params.get("token", "")
        requesting_player = self.token_manager.validate_token(token)
        if not requesting_player:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        # Check permission
        allowed = self.permission_resolver.check_permission(
            requesting_player,
            "get_character",
            player_id
        )
        if not allowed:
            return JSONResponse(
                {"error": "Permission denied"},
                status_code=403
            )

        # Get character data from storage
        try:
            character = self.storage.get_character(player_id)
            # Use mode='json' to handle datetime and other non-standard types
            return JSONResponse(character.model_dump(mode='json'))
        except Exception as e:
            logger.error(f"Failed to get character {player_id}: {e}")
            return JSONResponse(
                {"error": f"Character not found: {e}"},
                status_code=404
            )

    async def get_status(self, request: Request) -> Response:
        """
        Get server health and status information.

        Returns:
            JSON response with server status
        """
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        connected_players = self.connection_manager.get_connected_players()

        return JSONResponse({
            "status": "running",
            "uptime_seconds": uptime_seconds,
            "connected_players": connected_players,
            "total_connections": self.connection_manager.connection_count(),
            "active_pcs": len(self.pc_registry.get_all_active()),
        })

    async def websocket_endpoint(self, websocket: WebSocket) -> None:
        """
        Handle WebSocket connections for real-time updates.

        Args:
            websocket: WebSocket connection
        """
        # Validate token from query params
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=1008, reason="Missing token")
            return

        player_id = self.token_manager.validate_token(token)
        if not player_id:
            await websocket.close(code=1008, reason="Invalid token")
            return

        # Register connection
        await self.connection_manager.connect(player_id, websocket)

        try:
            # Send initial connection confirmation
            await websocket.send_json({
                "type": "connected",
                "player_id": player_id,
                "timestamp": datetime.now().isoformat(),
            })

            # Keep connection alive and handle incoming messages
            while True:
                message = await websocket.receive_json()
                # Handle client messages (heartbeat, action, etc.)
                await self._handle_ws_message(player_id, message)

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {player_id}")
        except Exception as e:
            logger.error(f"WebSocket error for {player_id}: {e}")
        finally:
            self.connection_manager.disconnect(player_id, websocket)

    async def _handle_ws_message(self, player_id: str, message: dict) -> None:
        """
        Handle incoming WebSocket messages from a player.

        Args:
            player_id: The player who sent the message
            message: The message dict
        """
        msg_type = message.get("type")

        if msg_type == "heartbeat":
            # Update player activity timestamp
            self.pc_registry.heartbeat(player_id)
        elif msg_type == "action":
            action_text = message.get("text", "")
            if action_text.strip():
                action_id = self.action_queue.push(player_id, action_text)
                await self.connection_manager.send_to_player(player_id, {
                    "type": "action_status",
                    "action_id": action_id,
                    "status": "pending",
                })
        else:
            logger.warning(f"Unknown WebSocket message type: {msg_type}")


def _run_server(server: PartyServer, stop_event: threading.Event) -> None:
    """
    Run the Uvicorn server in a background thread.

    This function creates a new asyncio event loop and runs the Uvicorn
    server until stop_event is set.

    Args:
        server: The PartyServer instance
        stop_event: Event to signal server shutdown
    """
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    config = uvicorn.Config(
        server.app,
        host=server.host,
        port=server.port,
        log_level="info",
        loop="asyncio",
    )
    uvicorn_server = uvicorn.Server(config)

    async def serve() -> None:
        """Run server until stop_event is set."""
        await uvicorn_server.serve()

    async def shutdown_monitor() -> None:
        """Monitor stop_event and shutdown server when signaled."""
        while not stop_event.is_set():
            await asyncio.sleep(0.1)
        await server.connection_manager.close_all()
        uvicorn_server.should_exit = True

    # Run both tasks
    try:
        loop.run_until_complete(asyncio.gather(
            serve(),
            shutdown_monitor(),
        ))
    except Exception as e:
        logger.error(f"Server thread error: {e}")
    finally:
        loop.close()
        logger.info("Server thread exited")


def start_party_server(
    pc_registry: PCRegistry,
    permission_resolver: PermissionResolver,
    storage: DnDStorage,
    campaign_dir: Path,
    host: str = "0.0.0.0",
    port: int = 8080,
) -> PartyServer:
    """
    Start the Party Mode web server in a background thread.

    This function MUST NOT block. It starts a daemon thread running
    Uvicorn with its own asyncio event loop, separate from the main
    thread (which runs the MCP stdio transport).

    Args:
        pc_registry: Player character registry
        permission_resolver: Permission validation
        storage: Campaign storage manager
        campaign_dir: Path to the active campaign directory
        host: Server bind address (default: 0.0.0.0)
        port: Server port (default: 8080)

    Returns:
        The PartyServer instance

    Raises:
        RuntimeError: If server is already running
    """
    global _server_thread, _server_instance, _stop_event

    if _server_thread is not None and _server_thread.is_alive():
        raise RuntimeError("Party server is already running")

    # Create server instance
    server = PartyServer(
        pc_registry=pc_registry,
        permission_resolver=permission_resolver,
        storage=storage,
        campaign_dir=campaign_dir,
        host=host,
        port=port,
    )

    # Create stop event
    stop_event = threading.Event()

    # Start background thread
    thread = threading.Thread(
        target=_run_server,
        args=(server, stop_event),
        daemon=True,
        name="PartyModeServer",
    )
    thread.start()

    # Store globals
    _server_thread = thread
    _server_instance = server
    _stop_event = stop_event

    # Wait a moment for server to start
    time.sleep(0.5)

    logger.info(f"Party Mode server started on http://{server.host_ip}:{port}")
    return server


def stop_party_server() -> None:
    """
    Stop the Party Mode web server gracefully.

    Closes all WebSocket connections and shuts down the Uvicorn server.
    Waits up to 5 seconds for the server thread to exit.

    Raises:
        RuntimeError: If server is not running
    """
    global _server_thread, _server_instance, _stop_event

    if _server_thread is None or not _server_thread.is_alive():
        raise RuntimeError("Party server is not running")

    logger.info("Stopping Party Mode server...")

    # Signal shutdown
    if _stop_event:
        _stop_event.set()

    # Wait for thread to exit
    _server_thread.join(timeout=5.0)

    if _server_thread.is_alive():
        logger.warning("Server thread did not exit cleanly")
    else:
        logger.info("Party Mode server stopped")

    # Clear globals
    _server_thread = None
    _server_instance = None
    _stop_event = None


def get_server_instance() -> Optional[PartyServer]:
    """
    Get the current PartyServer instance if running.

    Returns:
        The PartyServer instance, or None if not running
    """
    return _server_instance


__all__ = [
    "PartyServer",
    "ConnectionManager",
    "start_party_server",
    "stop_party_server",
    "get_server_instance",
]
