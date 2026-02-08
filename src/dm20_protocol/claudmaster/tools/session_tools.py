"""
Session management tools for Claudmaster AI DM system.

This module provides MCP tools for starting and resuming Claudmaster sessions,
managing session state, and coordinating multi-agent gameplay.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from dm20_protocol.models import Campaign
from ..orchestrator import Orchestrator
from ..session import ClaudmasterSession
from ..config import ClaudmasterConfig
from ..base import AgentRole
from ..persistence import SessionSerializer, SessionMetadata

logger = logging.getLogger("dm20-protocol")


# ============================================================================
# Session State Models
# ============================================================================

class CampaignSummary(BaseModel):
    """Summary of campaign information for session state."""
    campaign_id: str = Field(description="Campaign unique identifier")
    campaign_name: str = Field(description="Campaign name")
    character_count: int = Field(description="Number of player characters in the party")
    npc_count: int = Field(description="Number of NPCs in the campaign")


class ModuleSummary(BaseModel):
    """Summary of loaded module information."""
    module_id: Optional[str] = Field(default=None, description="Module unique identifier")
    module_name: Optional[str] = Field(default=None, description="Module name")
    is_loaded: bool = Field(description="Whether a module is currently loaded")


class GameStateSummary(BaseModel):
    """Summary of current game state."""
    current_location: Optional[str] = Field(default=None, description="Current location of the party")
    in_combat: bool = Field(description="Whether the party is currently in combat")
    turn_count: int = Field(description="Number of turns in the current session")


class CharacterSummary(BaseModel):
    """Summary of a player character."""
    character_id: str = Field(description="Character unique identifier")
    character_name: str = Field(description="Character name")
    character_class: Optional[str] = Field(default=None, description="Character class")
    level: Optional[int] = Field(default=None, description="Character level")


class SessionState(BaseModel):
    """Complete state representation of a Claudmaster session."""
    session_id: str = Field(description="Unique session identifier")
    status: str = Field(description="Session status: active, paused, error")
    campaign_info: CampaignSummary = Field(description="Campaign summary information")
    module_info: ModuleSummary = Field(description="Module summary information")
    game_state: GameStateSummary = Field(description="Game state summary")
    party_info: list[CharacterSummary] = Field(description="Party members summary")
    last_events: list[str] = Field(description="Recent game events")
    context_budget: int = Field(description="Remaining context budget for LLM calls")
    error_message: Optional[str] = Field(default=None, description="Error message if status is error")


# ============================================================================
# Session Manager
# ============================================================================

class SessionManager:
    """
    Manages the lifecycle of Claudmaster AI DM sessions.

    This class handles session creation, persistence, resumption, and state tracking
    for the multi-agent AI Game Master system.
    """

    def __init__(self) -> None:
        """Initialize the SessionManager."""
        self._active_sessions: dict[str, tuple[Orchestrator, ClaudmasterSession]] = {}
        self._saved_sessions: dict[str, dict] = {}
        logger.info("SessionManager initialized")

    async def start_session(
        self,
        campaign: Campaign,
        config: Optional[ClaudmasterConfig] = None,
        module_id: Optional[str] = None
    ) -> SessionState:
        """
        Start a new Claudmaster AI DM session.

        Args:
            campaign: The campaign to run
            config: Configuration for the session (uses defaults if not provided)
            module_id: Optional module ID to load

        Returns:
            SessionState representing the newly created session

        Raises:
            ValueError: If campaign is invalid
        """
        if not campaign:
            raise ValueError("Campaign cannot be None")

        # Use provided config or create default
        session_config = config or ClaudmasterConfig()

        # Create orchestrator
        orchestrator = Orchestrator(campaign=campaign, config=session_config)

        # TODO: Register agents once agent implementations are available
        # For now, we'll create a session without agents

        # Start the session
        session = orchestrator.start_session()

        # Store in active sessions
        self._active_sessions[session.session_id] = (orchestrator, session)

        logger.info(
            f"Started new session {session.session_id} for campaign '{campaign.name}' "
            f"(module_id: {module_id or 'none'})"
        )

        # Build and return session state
        return self._build_session_state(
            orchestrator=orchestrator,
            session=session,
            status="active",
            module_id=module_id
        )

    async def resume_session(
        self,
        session_id: str,
        campaign: Campaign
    ) -> SessionState:
        """
        Resume a previously saved session.

        Args:
            session_id: The session ID to resume
            campaign: The campaign associated with the session

        Returns:
            SessionState representing the resumed session

        Raises:
            ValueError: If session_id is not found in saved sessions
            ValueError: If campaign is invalid
        """
        if session_id not in self._saved_sessions:
            raise ValueError(f"Session {session_id} not found in saved sessions")

        if not campaign:
            raise ValueError("Campaign cannot be None")

        # Load saved session data
        saved_data = self._saved_sessions[session_id]

        # Recreate config from saved data
        config = ClaudmasterConfig(**saved_data.get("config", {}))

        # Create new orchestrator
        orchestrator = Orchestrator(campaign=campaign, config=config)

        # Recreate session with saved state
        session = ClaudmasterSession(
            session_id=session_id,
            campaign_id=campaign.id,
            config=config,
            started_at=datetime.fromisoformat(saved_data["started_at"]),
            turn_count=saved_data.get("turn_count", 0),
            conversation_history=saved_data.get("conversation_history", []),
            active_agents=saved_data.get("active_agents", {}),
            metadata=saved_data.get("metadata", {})
        )

        # Manually assign the session to orchestrator
        orchestrator.session = session

        # Store in active sessions
        self._active_sessions[session_id] = (orchestrator, session)

        logger.info(
            f"Resumed session {session_id} for campaign '{campaign.name}' "
            f"(turn count: {session.turn_count})"
        )

        # Build and return session state
        return self._build_session_state(
            orchestrator=orchestrator,
            session=session,
            status="active"
        )

    def save_session(self, session_id: str) -> bool:
        """
        Save a session for later resumption.

        Args:
            session_id: The session ID to save

        Returns:
            True if session was successfully saved, False otherwise
        """
        if session_id not in self._active_sessions:
            logger.warning(f"Cannot save session {session_id}: not found in active sessions")
            return False

        orchestrator, session = self._active_sessions[session_id]

        # Save session data
        self._saved_sessions[session_id] = {
            "session_id": session.session_id,
            "campaign_id": session.campaign_id,
            "config": session.config.model_dump(),
            "started_at": session.started_at.isoformat(),
            "turn_count": session.turn_count,
            "conversation_history": session.conversation_history,
            "active_agents": dict(session.active_agents),
            "metadata": dict(session.metadata)
        }

        logger.info(f"Saved session {session_id} (turn count: {session.turn_count})")
        return True

    def end_session(self, session_id: str) -> bool:
        """
        End an active session.

        Args:
            session_id: The session ID to end

        Returns:
            True if session was successfully ended, False otherwise
        """
        if session_id not in self._active_sessions:
            logger.warning(f"Cannot end session {session_id}: not found in active sessions")
            return False

        orchestrator, session = self._active_sessions[session_id]

        # End session via orchestrator
        try:
            orchestrator.end_session()
        except Exception as e:
            logger.error(f"Error ending session {session_id}: {e}")
            return False

        # Remove from active sessions
        del self._active_sessions[session_id]

        logger.info(f"Ended session {session_id} (final turn count: {session.turn_count})")
        return True

    def get_session_state(self, session_id: str) -> Optional[SessionState]:
        """
        Get the current state of an active session.

        Args:
            session_id: The session ID to query

        Returns:
            SessionState if session is active, None otherwise
        """
        if session_id not in self._active_sessions:
            return None

        orchestrator, session = self._active_sessions[session_id]

        return self._build_session_state(
            orchestrator=orchestrator,
            session=session,
            status="active"
        )

    def _build_session_state(
        self,
        orchestrator: Orchestrator,
        session: ClaudmasterSession,
        status: str = "active",
        module_id: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> SessionState:
        """
        Build a SessionState object from orchestrator and session.

        Args:
            orchestrator: The orchestrator managing the session
            session: The session object
            status: Session status (active, paused, error)
            module_id: Optional module ID if a module is loaded
            error_message: Optional error message if status is error

        Returns:
            Complete SessionState object
        """
        campaign = orchestrator.campaign

        # Build campaign summary
        campaign_info = CampaignSummary(
            campaign_id=campaign.id,
            campaign_name=campaign.name,
            character_count=len(campaign.characters),
            npc_count=len(campaign.npcs)
        )

        # Build module summary
        module_info = ModuleSummary(
            module_id=module_id,
            module_name=None,  # TODO: Lookup module name from module_id once module system is integrated
            is_loaded=module_id is not None
        )

        # Build game state summary
        game_state = GameStateSummary(
            current_location=campaign.game_state.current_location,
            in_combat=campaign.game_state.in_combat,
            turn_count=session.turn_count
        )

        # Build party info
        party_info: list[CharacterSummary] = []
        for char_id, character in campaign.characters.items():
            party_info.append(
                CharacterSummary(
                    character_id=char_id,
                    character_name=character.name,
                    character_class=character.character_class.name,
                    level=character.character_class.level
                )
            )

        # Extract last events from conversation history
        last_events: list[str] = []
        for msg in session.conversation_history[-5:]:  # Last 5 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # Truncate long messages
            if len(content) > 100:
                content = content[:97] + "..."
            last_events.append(f"[{role}] {content}")

        # Calculate context budget (simplified - assumes 4096 max tokens)
        # This is a rough estimate based on conversation history length
        used_tokens = sum(len(msg.get("content", "").split()) * 1.3 for msg in session.conversation_history)
        context_budget = max(0, int(session.config.max_tokens - used_tokens))

        return SessionState(
            session_id=session.session_id,
            status=status,
            campaign_info=campaign_info,
            module_info=module_info,
            game_state=game_state,
            party_info=party_info,
            last_events=last_events,
            context_budget=context_budget,
            error_message=error_message
        )


# Module-level singleton
_session_manager = SessionManager()


# ============================================================================
# MCP Tool Function
# ============================================================================

async def start_claudmaster_session(
    campaign_name: str,
    module_id: Optional[str] = None,
    session_id: Optional[str] = None,
    resume: bool = False,
) -> dict:
    """
    Start or resume a Claudmaster AI DM session.

    This is the main MCP tool for initiating gameplay sessions with the
    multi-agent AI Game Master system.

    Args:
        campaign_name: Name of the campaign to play
        module_id: Optional D&D module to load (e.g., "lost-mine-of-phandelver")
        session_id: Session ID to resume (required if resume=True)
        resume: Whether to resume an existing session (default: False)

    Returns:
        Dictionary representation of SessionState with the following keys:
            - session_id: Unique session identifier
            - status: "active", "paused", or "error"
            - campaign_info: Campaign summary (id, name, character_count, npc_count)
            - module_info: Module summary (module_id, module_name, is_loaded)
            - game_state: Game state summary (current_location, in_combat, turn_count)
            - party_info: List of character summaries
            - last_events: Recent game events
            - context_budget: Remaining context budget
            - error_message: Error description if status is "error"

    Examples:
        Start a new session:
        >>> result = await start_claudmaster_session(campaign_name="Dragon Heist")

        Resume an existing session:
        >>> result = await start_claudmaster_session(
        ...     campaign_name="Dragon Heist",
        ...     session_id="abc123",
        ...     resume=True
        ... )

        Start with a specific module:
        >>> result = await start_claudmaster_session(
        ...     campaign_name="Starter Set",
        ...     module_id="lost-mine-of-phandelver"
        ... )
    """
    try:
        # Validate inputs
        if not campaign_name or not campaign_name.strip():
            return {
                "session_id": "",
                "status": "error",
                "error_message": "campaign_name cannot be empty"
            }

        if resume and not session_id:
            return {
                "session_id": "",
                "status": "error",
                "error_message": "session_id is required when resume=True"
            }

        # TODO: Load campaign from storage
        # For now, we'll need to create a mock campaign or load from a campaign manager
        # This will be implemented once the campaign loading system is in place

        # Placeholder error for missing campaign loading integration
        return {
            "session_id": session_id or "",
            "status": "error",
            "error_message": (
                f"Campaign loading not yet integrated. "
                f"Cannot load campaign '{campaign_name}'. "
                f"This tool requires integration with campaign storage."
            )
        }

        # The actual implementation would be:
        # if resume:
        #     state = await _session_manager.resume_session(session_id, campaign)
        # else:
        #     state = await _session_manager.start_session(campaign, module_id=module_id)
        # return state.model_dump()

    except ValueError as e:
        logger.error(f"Validation error in start_claudmaster_session: {e}")
        return {
            "session_id": session_id or "",
            "status": "error",
            "error_message": str(e)
        }
    except Exception as e:
        logger.error(f"Unexpected error in start_claudmaster_session: {e}", exc_info=True)
        return {
            "session_id": session_id or "",
            "status": "error",
            "error_message": f"Unexpected error: {type(e).__name__}: {str(e)}"
        }


async def end_session(
    session_id: str,
    mode: str = "pause",
    summary_notes: Optional[str] = None,
    campaign_path: Optional[str] = None,
) -> dict:
    """
    End or pause a Claudmaster session, saving all state.

    This MCP tool cleanly terminates or pauses a Claudmaster session.
    In "pause" mode, all state is persisted to disk so the session can
    be resumed later. In "end" mode, state is saved as a final snapshot
    and the session is terminated.

    Args:
        session_id: The session ID to end or pause
        mode: "pause" (save for later resumption) or "end" (final termination)
        summary_notes: Optional DM notes to save with the session snapshot
        campaign_path: Optional path for disk persistence.
            If provided, session state is written to disk under this path.

    Returns:
        Dictionary with the following keys:
            - status: "paused" or "ended" on success, "error" on failure
            - session_id: The session ID that was ended
            - session_summary: Brief summary of the session
            - save_path: Where state was persisted (if campaign_path provided)
            - stats: Session statistics (duration, turn count, etc.)
            - error_message: Error description if status is "error"

    Examples:
        Pause a session for later:
        >>> result = await end_session(
        ...     session_id="abc123",
        ...     mode="pause",
        ...     summary_notes="Party just entered the dungeon"
        ... )

        End a session permanently:
        >>> result = await end_session(session_id="abc123", mode="end")

        Pause with disk persistence:
        >>> result = await end_session(
        ...     session_id="abc123",
        ...     mode="pause",
        ...     campaign_path="/data/campaigns/my-campaign"
        ... )
    """
    try:
        # Validate mode
        if mode not in ("pause", "end"):
            return {
                "status": "error",
                "session_id": session_id,
                "error_message": f"Invalid mode '{mode}'. Must be 'pause' or 'end'.",
            }

        # Check session exists
        if session_id not in _session_manager._active_sessions:
            return {
                "status": "error",
                "session_id": session_id,
                "error_message": f"Session {session_id} not found in active sessions.",
            }

        # Get session info before ending
        orchestrator, session = _session_manager._active_sessions[session_id]
        turn_count = session.turn_count
        started_at = session.started_at
        campaign_id = session.campaign_id

        # Calculate duration
        duration_minutes = int((datetime.now() - started_at).total_seconds() / 60)

        # Build stats
        stats = {
            "turn_count": turn_count,
            "duration_minutes": duration_minutes,
            "started_at": started_at.isoformat(),
            "ended_at": datetime.now().isoformat(),
        }

        # Save to memory first (for resume capability)
        _session_manager.save_session(session_id)

        # Persist to disk if campaign_path provided
        save_path = None
        if campaign_path:
            serializer = SessionSerializer(Path(campaign_path))
            saved_data = _session_manager._saved_sessions.get(session_id, {})
            save_dir = serializer.save_session(
                session_data=saved_data,
                mode=mode,
                summary_notes=summary_notes,
            )
            save_path = str(save_dir)

        # End the session (removes from active)
        result_status = "paused" if mode == "pause" else "ended"
        _session_manager.end_session(session_id)

        # Build summary
        session_summary = (
            f"Session {session_id} for campaign '{campaign_id}': "
            f"{turn_count} turns over {duration_minutes} minutes."
        )

        logger.info(f"MCP end_session: {result_status} session {session_id}")

        return {
            "status": result_status,
            "session_id": session_id,
            "session_summary": session_summary,
            "save_path": save_path,
            "stats": stats,
        }

    except Exception as e:
        logger.error(f"Error in end_session for {session_id}: {e}", exc_info=True)
        return {
            "status": "error",
            "session_id": session_id,
            "error_message": f"Unexpected error: {type(e).__name__}: {str(e)}",
        }


async def get_session_state(
    session_id: str,
    detail_level: str = "standard",
    include_history: bool = True,
    history_limit: int = 10,
) -> dict:
    """
    Get the current state of a Claudmaster session.

    This MCP tool queries the state of an active session, returning
    information about the game state, party, recent history, and
    session metadata. Supports multiple detail levels.

    Args:
        session_id: The session ID to query
        detail_level: How much detail to include:
            - "minimal": Basic session info and status only
            - "standard": Session info, game state, party status, recent history
            - "full": Everything including complete context budget analysis
        include_history: Whether to include action history in the response
        history_limit: Maximum number of history entries to return (default: 10)

    Returns:
        Dictionary with the following keys:
            - session_info: Basic session metadata (id, status, campaign, duration)
            - game_state: Current game state (location, combat, turn count)
            - party_status: List of character summaries with status
            - recent_history: Last N actions (if include_history=True)
            - active_quests: Current quest status (placeholder)
            - context_usage: Context window utilization info
            - error_message: Error description if session not found

    Examples:
        Get standard session state:
        >>> result = await get_session_state(session_id="abc123")

        Get minimal info (fast):
        >>> result = await get_session_state(
        ...     session_id="abc123",
        ...     detail_level="minimal"
        ... )

        Get full state with extended history:
        >>> result = await get_session_state(
        ...     session_id="abc123",
        ...     detail_level="full",
        ...     history_limit=50
        ... )
    """
    try:
        # Validate detail level
        valid_levels = ("minimal", "standard", "full")
        if detail_level not in valid_levels:
            return {
                "error_message": (
                    f"Invalid detail_level '{detail_level}'. "
                    f"Must be one of: {', '.join(valid_levels)}"
                )
            }

        # Get session state from manager
        state = _session_manager.get_session_state(session_id)

        if state is None:
            return {
                "error_message": (
                    f"Session {session_id} not found. "
                    f"It may have been ended or never started."
                )
            }

        # Get raw session for additional details
        orchestrator, session = _session_manager._active_sessions[session_id]

        # Calculate duration
        duration_minutes = int((datetime.now() - session.started_at).total_seconds() / 60)

        # Build session_info (always included)
        session_info = {
            "session_id": state.session_id,
            "status": state.status,
            "campaign_id": state.campaign_info.campaign_id,
            "campaign_name": state.campaign_info.campaign_name,
            "duration_minutes": duration_minutes,
            "turn_count": session.turn_count,
        }

        # Minimal level: just session info
        if detail_level == "minimal":
            return {"session_info": session_info}

        # Standard and full: add game state and party
        game_state = state.game_state.model_dump()
        party_status = [char.model_dump() for char in state.party_info]

        # Build history if requested
        recent_history: list[dict] = []
        if include_history:
            limit = history_limit if detail_level == "standard" else max(history_limit, 50)
            for msg in session.conversation_history[-limit:]:
                recent_history.append(msg)

        # Context usage
        context_usage = {
            "context_budget_remaining": state.context_budget,
            "max_tokens": session.config.max_tokens,
        }

        # Full level: add extra detail
        if detail_level == "full":
            context_usage["conversation_length"] = len(session.conversation_history)
            context_usage["active_agents"] = dict(session.active_agents)

        return {
            "session_info": session_info,
            "game_state": game_state,
            "party_status": party_status,
            "recent_history": recent_history,
            "active_quests": [],  # Placeholder for quest system integration
            "context_usage": context_usage,
        }

    except Exception as e:
        logger.error(f"Error in get_session_state for {session_id}: {e}", exc_info=True)
        return {
            "error_message": f"Unexpected error: {type(e).__name__}: {str(e)}"
        }


__all__ = [
    "CampaignSummary",
    "ModuleSummary",
    "GameStateSummary",
    "CharacterSummary",
    "SessionState",
    "SessionManager",
    "SessionMetadata",
    "start_claudmaster_session",
    "end_session",
    "get_session_state",
]
