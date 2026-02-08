"""
Session state serialization for Claudmaster AI DM system.

Handles saving and loading complete session state to/from disk,
enabling session pause/resume across process restarts.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("dm20-protocol")


class SessionMetadata(BaseModel):
    """Metadata about a persisted session."""

    session_id: str = Field(description="Unique session identifier")
    campaign_id: str = Field(description="Campaign this session belongs to")
    status: str = Field(description="Session status: active, paused, ended")
    created_at: str = Field(description="ISO timestamp of session creation")
    last_active: str = Field(description="ISO timestamp of last activity")
    total_duration_minutes: int = Field(default=0, description="Total session duration in minutes")
    action_count: int = Field(default=0, description="Number of player actions in this session")
    save_notes: Optional[str] = Field(default=None, description="DM notes saved with the session")


class SessionSerializer:
    """
    Handles session state persistence to disk.

    Sessions are saved as a directory of JSON files under the campaign path:
    {campaign_path}/claudmaster_sessions/{session_id}/
        session_meta.json      - Session metadata
        state_snapshot.json    - Full session state at save time
        action_history.json    - Conversation/action history
    """

    VERSION = "1.0"

    def __init__(self, campaign_path: Path) -> None:
        """
        Initialize the serializer.

        Args:
            campaign_path: Root path for the campaign directory
        """
        self.campaign_path = Path(campaign_path)
        self._sessions_dir = self.campaign_path / "claudmaster_sessions"

    def _session_dir(self, session_id: str) -> Path:
        """Get the directory for a specific session."""
        return self._sessions_dir / session_id

    def save_session(
        self,
        session_data: dict,
        mode: str = "pause",
        summary_notes: Optional[str] = None,
    ) -> Path:
        """
        Serialize and save complete session state.

        Args:
            session_data: Dictionary of session state from SessionManager.save_session
            mode: "pause" (resumable) or "end" (final)
            summary_notes: Optional DM notes to store

        Returns:
            Path to the saved session directory
        """
        session_id = session_data["session_id"]
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now().isoformat()

        # Calculate duration from started_at
        started_at = session_data.get("started_at", now)
        try:
            start_dt = datetime.fromisoformat(started_at)
            duration_minutes = int((datetime.now() - start_dt).total_seconds() / 60)
        except (ValueError, TypeError):
            duration_minutes = 0

        # Build metadata
        status = "paused" if mode == "pause" else "ended"
        action_count = session_data.get("turn_count", 0)
        metadata = SessionMetadata(
            session_id=session_id,
            campaign_id=session_data.get("campaign_id", ""),
            status=status,
            created_at=started_at,
            last_active=now,
            total_duration_minutes=duration_minutes,
            action_count=action_count,
            save_notes=summary_notes,
        )

        # Write metadata
        meta_path = session_dir / "session_meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {"version": self.VERSION, **metadata.model_dump(mode="json")},
                f,
                indent=2,
                ensure_ascii=False,
            )

        # Write state snapshot (config, agents, metadata)
        state_snapshot = {
            "version": self.VERSION,
            "session_id": session_id,
            "campaign_id": session_data.get("campaign_id", ""),
            "config": session_data.get("config", {}),
            "started_at": started_at,
            "turn_count": session_data.get("turn_count", 0),
            "active_agents": session_data.get("active_agents", {}),
            "metadata": session_data.get("metadata", {}),
        }
        state_path = session_dir / "state_snapshot.json"
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state_snapshot, f, indent=2, ensure_ascii=False)

        # Write action history separately (can be large)
        history = session_data.get("conversation_history", [])
        history_path = session_dir / "action_history.json"
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(
                {"version": self.VERSION, "actions": history},
                f,
                indent=2,
                ensure_ascii=False,
            )

        logger.info(
            f"Saved session {session_id} to {session_dir} "
            f"(mode={mode}, actions={action_count})"
        )
        return session_dir

    def load_session(self, session_id: str) -> Optional[dict]:
        """
        Load session state from disk.

        Args:
            session_id: The session ID to load

        Returns:
            Dictionary of session state (compatible with SessionManager),
            or None if session not found
        """
        session_dir = self._session_dir(session_id)

        if not session_dir.exists():
            logger.debug(f"No saved session found at {session_dir}")
            return None

        try:
            # Load state snapshot
            state_path = session_dir / "state_snapshot.json"
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)

            # Load action history
            history_path = session_dir / "action_history.json"
            if history_path.exists():
                with open(history_path, "r", encoding="utf-8") as f:
                    history_data = json.load(f)
                state["conversation_history"] = history_data.get("actions", [])
            else:
                state["conversation_history"] = []

            logger.info(f"Loaded session {session_id} from {session_dir}")
            return state

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None

    def load_metadata(self, session_id: str) -> Optional[SessionMetadata]:
        """
        Load only session metadata (lightweight, no history).

        Args:
            session_id: The session ID to query

        Returns:
            SessionMetadata or None if not found
        """
        session_dir = self._session_dir(session_id)
        meta_path = session_dir / "session_meta.json"

        if not meta_path.exists():
            return None

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Remove version key before constructing model
            data.pop("version", None)
            return SessionMetadata(**data)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"Failed to load metadata for session {session_id}: {e}")
            return None

    def list_sessions(self) -> list[SessionMetadata]:
        """
        List all saved sessions for this campaign.

        Returns:
            List of SessionMetadata, sorted by last_active descending
        """
        if not self._sessions_dir.exists():
            return []

        sessions: list[SessionMetadata] = []
        for session_dir in self._sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
            meta = self.load_metadata(session_dir.name)
            if meta:
                sessions.append(meta)

        # Sort by last_active descending (most recent first)
        sessions.sort(key=lambda s: s.last_active, reverse=True)
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a saved session from disk.

        Args:
            session_id: The session ID to delete

        Returns:
            True if session was deleted, False if not found
        """
        session_dir = self._session_dir(session_id)
        if not session_dir.exists():
            return False

        import shutil
        shutil.rmtree(session_dir)
        logger.info(f"Deleted saved session {session_id}")
        return True


__all__ = [
    "SessionSerializer",
    "SessionMetadata",
]
