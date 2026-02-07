"""
State rollback manager for the Claudmaster AI DM system.

Provides snapshot-based state rollback capabilities, allowing the system
to recover from state corruption by restoring to a previous known-good state.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from gamemaster_mcp.claudmaster.exceptions import RollbackError

if TYPE_CHECKING:
    from gamemaster_mcp.claudmaster.session import ClaudmasterSession

logger = logging.getLogger("gamemaster-mcp")


@dataclass
class StateSnapshot:
    """A snapshot of session state at a point in time.

    Attributes:
        snapshot_id: Unique identifier for this snapshot
        label: Human-readable label for this snapshot
        timestamp: When the snapshot was created
        session_data: Deep copy of the session state
        turn_count: Turn number when snapshot was created
    """

    snapshot_id: str
    label: str
    timestamp: datetime
    session_data: dict
    turn_count: int


class StateRollbackManager:
    """Manages session state snapshots and rollback operations.

    Creates periodic snapshots of session state and allows rolling back
    to previous snapshots when state corruption is detected.

    Attributes:
        session: Reference to the active session
        snapshots: List of state snapshots, ordered by creation time
        max_snapshots: Maximum number of snapshots to keep (FIFO)
    """

    def __init__(self, session: ClaudmasterSession, max_snapshots: int = 10):
        """Initialize the rollback manager.

        Args:
            session: Reference to the active session
            max_snapshots: Maximum number of snapshots to retain
        """
        self.session = session
        self.max_snapshots = max_snapshots
        self.snapshots: list[StateSnapshot] = []

    def create_snapshot(self, label: str = "auto") -> StateSnapshot:
        """Create a snapshot of current session state.

        The snapshot includes a deep copy of all session data to prevent
        unintended modifications to historical state.

        Args:
            label: Human-readable label for this snapshot

        Returns:
            The created StateSnapshot
        """
        snapshot_id = str(uuid4())
        session_data = self.session.model_dump(mode="json")

        # Deep copy to prevent modifications to snapshot
        session_data_copy = copy.deepcopy(session_data)

        snapshot = StateSnapshot(
            snapshot_id=snapshot_id,
            label=label,
            timestamp=datetime.now(),
            session_data=session_data_copy,
            turn_count=self.session.turn_count,
        )

        self.snapshots.append(snapshot)
        logger.info(
            f"Created snapshot {snapshot_id} (label: {label}, turn: {self.session.turn_count})"
        )

        # Clean old snapshots if we exceed max
        self.clear_old_snapshots()

        return snapshot

    def rollback_to(self, snapshot_id: str) -> bool:
        """Rollback session state to a specific snapshot.

        Args:
            snapshot_id: ID of the snapshot to restore

        Returns:
            True if rollback successful

        Raises:
            RollbackError: If snapshot not found or restoration fails
        """
        # Find the snapshot
        snapshot = None
        for snap in self.snapshots:
            if snap.snapshot_id == snapshot_id:
                snapshot = snap
                break

        if snapshot is None:
            raise RollbackError(
                f"Snapshot {snapshot_id} not found",
                details={"available_snapshots": [s.snapshot_id for s in self.snapshots]},
            )

        logger.warning(
            f"Rolling back session to snapshot {snapshot_id} "
            f"(label: {snapshot.label}, turn: {snapshot.turn_count})"
        )

        try:
            # Restore session fields from snapshot
            self.session.turn_count = snapshot.session_data["turn_count"]
            self.session.conversation_history = copy.deepcopy(
                snapshot.session_data["conversation_history"]
            )
            self.session.active_agents = copy.deepcopy(
                snapshot.session_data["active_agents"]
            )
            self.session.metadata = copy.deepcopy(snapshot.session_data["metadata"])

            logger.info(f"Successfully rolled back to snapshot {snapshot_id}")
            return True

        except (KeyError, TypeError, AttributeError) as e:
            raise RollbackError(
                f"Failed to restore snapshot {snapshot_id}: {e}",
                details={"snapshot": snapshot.snapshot_id, "error": str(e)},
            )

    def rollback_last(self) -> bool:
        """Rollback to the most recent snapshot.

        Convenience method for rolling back to the latest snapshot.

        Returns:
            True if rollback successful

        Raises:
            RollbackError: If no snapshots available or restoration fails
        """
        if not self.snapshots:
            raise RollbackError(
                "No snapshots available for rollback",
                details={"snapshot_count": 0},
            )

        latest_snapshot = self.snapshots[-1]
        return self.rollback_to(latest_snapshot.snapshot_id)

    def clear_old_snapshots(self) -> None:
        """Remove old snapshots to maintain max_snapshots limit.

        Uses FIFO strategy - oldest snapshots are removed first.
        """
        if len(self.snapshots) > self.max_snapshots:
            excess = len(self.snapshots) - self.max_snapshots
            removed = self.snapshots[:excess]
            self.snapshots = self.snapshots[excess:]

            logger.debug(
                f"Cleared {excess} old snapshots, {len(self.snapshots)} remaining"
            )
            for snap in removed:
                logger.debug(
                    f"  Removed snapshot {snap.snapshot_id} "
                    f"(label: {snap.label}, turn: {snap.turn_count})"
                )

    def list_snapshots(self) -> list[dict]:
        """Get list of available snapshots with metadata.

        Returns:
            List of snapshot metadata dictionaries
        """
        return [
            {
                "snapshot_id": snap.snapshot_id,
                "label": snap.label,
                "timestamp": snap.timestamp.isoformat(),
                "turn_count": snap.turn_count,
            }
            for snap in self.snapshots
        ]

    def get_snapshot_count(self) -> int:
        """Get current number of snapshots.

        Returns:
            Number of snapshots currently stored
        """
        return len(self.snapshots)


__all__ = [
    "StateSnapshot",
    "StateRollbackManager",
]
