"""
Crash recovery manager for the Claudmaster AI DM system.

Detects and recovers from unexpected process termination by using
recovery markers and persisted session state.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from dm20_protocol.claudmaster.exceptions import RecoveryError, SessionError
from dm20_protocol.claudmaster.recovery import RecoveryResult

if TYPE_CHECKING:
    from dm20_protocol.claudmaster.persistence.session_serializer import SessionSerializer

logger = logging.getLogger("dm20-protocol")


class CrashRecoveryManager:
    """Manages crash detection and recovery for sessions.

    Uses a recovery marker file to detect when a session terminated
    unexpectedly. The marker is written when a session starts and
    removed on clean shutdown.

    Attributes:
        campaign_path: Path to the campaign directory
        marker_file: Path to the recovery marker file
        serializer: Session serializer for loading crashed sessions
    """

    def __init__(self, campaign_path: Path, serializer: SessionSerializer):
        """Initialize the crash recovery manager.

        Args:
            campaign_path: Path to the campaign directory
            serializer: Session serializer for loading sessions
        """
        self.campaign_path = Path(campaign_path)
        self.marker_file = self.campaign_path / ".claudmaster_recovery"
        self.serializer = serializer

    def write_recovery_marker(self, session_id: str) -> None:
        """Write a recovery marker indicating an active session.

        The marker file contains the session ID, timestamp, and process ID.
        If the process terminates unexpectedly, this marker will remain
        and can be used to detect and recover the session.

        Args:
            session_id: ID of the active session
        """
        marker_data = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "pid": os.getpid(),
        }

        try:
            self.campaign_path.mkdir(parents=True, exist_ok=True)
            with open(self.marker_file, "w", encoding="utf-8") as f:
                json.dump(marker_data, f, indent=2)
            logger.debug(f"Wrote recovery marker for session {session_id}")
        except (OSError, IOError) as e:
            logger.warning(f"Failed to write recovery marker: {e}")

    def check_for_crash(self) -> str | None:
        """Check if a previous session crashed unexpectedly.

        Returns:
            Session ID of crashed session if found, None otherwise
        """
        if not self.marker_file.exists():
            return None

        try:
            with open(self.marker_file, "r", encoding="utf-8") as f:
                marker_data = json.load(f)

            session_id = marker_data.get("session_id")
            timestamp = marker_data.get("timestamp")
            pid = marker_data.get("pid")

            logger.warning(
                f"Found recovery marker for session {session_id} "
                f"(timestamp: {timestamp}, pid: {pid})"
            )

            return session_id

        except (json.JSONDecodeError, OSError, IOError) as e:
            logger.error(f"Failed to read recovery marker: {e}")
            # Remove corrupt marker
            try:
                self.marker_file.unlink()
            except OSError:
                pass
            return None

    def recover_session(self, session_id: str) -> RecoveryResult:
        """Recover a crashed session by loading its persisted state.

        Args:
            session_id: ID of the session to recover

        Returns:
            RecoveryResult indicating success or failure
        """
        logger.info(f"Attempting to recover crashed session {session_id}")

        try:
            # Try to load the session state
            session_data = self.serializer.load_session(session_id)

            if session_data is None:
                raise RecoveryError(
                    f"Could not load session data for {session_id}",
                    details={"session_id": session_id},
                )

            # Successfully loaded - clean up marker
            self.clean_recovery_marker()

            turn_count = session_data.get("turn_count", 0)
            logger.info(
                f"Successfully recovered session {session_id} "
                f"(turn count: {turn_count})"
            )

            return RecoveryResult(
                success=True,
                strategy_used="crash_recovery",
                message=f"Recovered session {session_id} from unexpected termination "
                f"at turn {turn_count}",
            )

        except Exception as e:
            logger.error(f"Failed to recover session {session_id}: {e}")
            return RecoveryResult(
                success=False,
                strategy_used="crash_recovery",
                message=f"Could not recover session {session_id}: {e}",
            )

    def clean_recovery_marker(self) -> None:
        """Remove the recovery marker file on clean shutdown.

        Should be called when a session ends normally to prevent
        false crash detection on next startup.
        """
        if self.marker_file.exists():
            try:
                self.marker_file.unlink()
                logger.debug("Cleaned recovery marker (normal shutdown)")
            except OSError as e:
                logger.warning(f"Failed to clean recovery marker: {e}")

    def has_crashed_session(self) -> bool:
        """Check if there is evidence of a crashed session.

        Convenience method for simple crash detection.

        Returns:
            True if a crashed session is detected, False otherwise
        """
        return self.check_for_crash() is not None


__all__ = ["CrashRecoveryManager"]
