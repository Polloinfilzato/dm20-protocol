"""
Party Mode: Multi-player web UI for D&D sessions.

This package provides a web server that allows multiple players to connect
to a shared D&D session via their browsers. Each player gets a personalized
UI for their character, with real-time updates via WebSocket.

The server runs in a background thread with its own asyncio event loop,
separate from the main MCP stdio transport, ensuring no interference.

Key components:
- auth: Token generation, validation, and QR code creation
- server: Starlette web app, WebSocket connections, and background thread lifecycle
- static: HTML/CSS/JS for the player UI (built in Task 3)

Public API:
- start_party_server(): Start the web server in a background thread
- stop_party_server(): Gracefully stop the web server
- get_server_instance(): Get the current PartyServer instance
"""

from .auth import (
    TokenManager,
    QRCodeGenerator,
    detect_host_ip,
)
from .queue import (
    ActionQueue,
    ResponseQueue,
)
from .server import (
    PartyServer,
    ConnectionManager,
    start_party_server,
    stop_party_server,
    get_server_instance,
)

__all__ = [
    # Auth
    "TokenManager",
    "QRCodeGenerator",
    "detect_host_ip",
    # Queue
    "ActionQueue",
    "ResponseQueue",
    # Server
    "PartyServer",
    "ConnectionManager",
    "start_party_server",
    "stop_party_server",
    "get_server_instance",
]
