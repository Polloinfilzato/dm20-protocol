"""
Automatic session state preservation for the Claudmaster AI DM system.

This module provides the AutoSaveManager, which handles periodic session saves
to prevent data loss from crashes or interruptions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dm20_protocol.claudmaster.session import ClaudmasterSession
    from dm20_protocol.claudmaster.persistence.session_serializer import SessionSerializer

logger = logging.getLogger("dm20-protocol")


class AutoSaveManager:
    """
    Manages automatic session state preservation.

    The AutoSaveManager tracks when sessions were last saved and triggers
    periodic saves based on a configurable interval. It also supports
    named checkpoints for significant events and immediate saves on interruption.

    Attributes:
        session: The session being managed
        serializer: Serializer for persisting session state
        save_interval: Minutes between auto-saves
        last_save: Timestamp of the last successful save
        checkpoints: List of named checkpoint metadata
    """

    MAX_CHECKPOINTS = 10

    def __init__(
        self,
        session: ClaudmasterSession,
        serializer: SessionSerializer,
        save_interval_minutes: int = 5
    ) -> None:
        """
        Initialize the auto-save manager.

        Args:
            session: The session to manage
            serializer: Serializer for session persistence
            save_interval_minutes: Minutes between auto-saves (default: 5)
        """
        self.session = session
        self.serializer = serializer
        self.save_interval = save_interval_minutes
        self.last_save: datetime | None = None
        self.checkpoints: list[dict] = []

    def should_save(self) -> bool:
        """
        Check if enough time has passed since last save.

        Returns:
            True if save interval has elapsed, False otherwise
        """
        if self.last_save is None:
            return True

        now = datetime.now(timezone.utc)
        elapsed = now - self.last_save
        return elapsed >= timedelta(minutes=self.save_interval)

    async def trigger_autosave(self) -> bool:
        """
        Save if interval has passed.

        Checks if the save interval has elapsed and performs a save if needed.
        Updates the last_save timestamp on successful save.

        Returns:
            True if save was performed, False if skipped
        """
        if not self.should_save():
            return False

        try:
            # Prepare session data for serialization
            session_data = {
                "session_id": self.session.session_id,
                "campaign_id": self.session.campaign_id,
                "config": self.session.config.model_dump(),
                "started_at": self.session.started_at.isoformat(),
                "turn_count": self.session.turn_count,
                "conversation_history": self.session.conversation_history,
                "active_agents": self.session.active_agents,
                "metadata": self.session.metadata,
            }

            # Save with autosave mode
            self.serializer.save_session(
                session_data=session_data,
                mode="pause",
                summary_notes="Automatic save"
            )

            self.last_save = datetime.now(timezone.utc)
            logger.info(
                f"Auto-saved session {self.session.session_id} at turn {self.session.turn_count}"
            )
            return True

        except Exception as e:
            logger.error(f"Auto-save failed for session {self.session.session_id}: {e}")
            return False

    async def save_on_interrupt(self) -> None:
        """
        Immediate save when session is interrupted.

        Performs an immediate save regardless of interval, useful for
        handling unexpected terminations or user interruptions.
        """
        try:
            # Prepare session data
            session_data = {
                "session_id": self.session.session_id,
                "campaign_id": self.session.campaign_id,
                "config": self.session.config.model_dump(),
                "started_at": self.session.started_at.isoformat(),
                "turn_count": self.session.turn_count,
                "conversation_history": self.session.conversation_history,
                "active_agents": self.session.active_agents,
                "metadata": self.session.metadata,
            }

            # Save with interrupt description
            now = datetime.now(timezone.utc).isoformat()
            self.serializer.save_session(
                session_data=session_data,
                mode="pause",
                summary_notes=f"Session interrupted at {now}"
            )

            self.last_save = datetime.now(timezone.utc)
            logger.info(f"Interrupt save completed for session {self.session.session_id}")

        except Exception as e:
            logger.error(
                f"Interrupt save failed for session {self.session.session_id}: {e}"
            )
            raise

    def mark_checkpoint(self, description: str) -> None:
        """
        Create named checkpoint for significant events.

        Checkpoints are stored in memory and provide markers for important
        moments in the session. The checkpoint list is limited to MAX_CHECKPOINTS
        entries (FIFO when limit is reached).

        Args:
            description: Human-readable description of the checkpoint
        """
        checkpoint = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "turn_count": self.session.turn_count,
            "description": description,
        }

        self.checkpoints.append(checkpoint)

        # Limit checkpoint history (FIFO)
        if len(self.checkpoints) > self.MAX_CHECKPOINTS:
            removed = self.checkpoints.pop(0)
            logger.debug(
                f"Removed oldest checkpoint: {removed['description']} "
                f"(limit: {self.MAX_CHECKPOINTS})"
            )

        logger.info(
            f"Checkpoint marked at turn {self.session.turn_count}: {description}"
        )

    def get_checkpoints(self) -> list[dict]:
        """
        Get all checkpoints for this session.

        Returns:
            List of checkpoint dictionaries with timestamp, turn_count, and description
        """
        return list(self.checkpoints)


__all__ = ["AutoSaveManager"]
