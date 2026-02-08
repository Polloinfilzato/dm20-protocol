"""
Location state management for the Claudmaster AI DM system.

This module tracks persistent state changes in locations, such as opened doors,
disarmed traps, collected loot, and defeated enemies. It ensures that the world
state remains consistent across sessions.

Key components:
- StateChangeType: Enumeration of state change types
- StateChange: A single state change with time and reversibility tracking
- LocationState: State tracker for a single location
- LocationStateManager: Manager for all location states in a campaign
"""

import json
import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4
from enum import Enum

from pydantic import BaseModel, Field

from .timeline import GameTime

logger = logging.getLogger("dm20-protocol")


class StateChangeType(str, Enum):
    """Types of state changes that can occur in a location."""
    DOOR_OPENED = "door_opened"
    DOOR_LOCKED = "door_locked"
    DOOR_BROKEN = "door_broken"
    TRAP_TRIGGERED = "trap_triggered"
    TRAP_DISARMED = "trap_disarmed"
    LOOT_COLLECTED = "loot_collected"
    ENEMY_DEFEATED = "enemy_defeated"
    OBJECT_MOVED = "object_moved"
    OBJECT_DESTROYED = "object_destroyed"
    ENVIRONMENTAL = "environmental"
    CUSTOM = "custom"


class StateChange(BaseModel):
    """
    A state change that occurred in a location.

    Tracks what changed, when it changed, and whether it can be reverted.
    This enables consistent location state tracking across sessions.

    Attributes:
        id: Unique identifier, auto-generated if empty
        change_type: Type of state change
        description: Human-readable description
        game_time: When the change occurred
        session_number: Session when the change occurred
        target_object: ID/name of the object affected (optional)
        reversible: Whether the change can be undone
        reverted: Whether this change has been reverted
    """
    id: str = Field(default="", description="Change ID, auto-generated if empty")
    change_type: StateChangeType
    description: str
    game_time: GameTime
    session_number: int = Field(ge=1)
    target_object: Optional[str] = None
    reversible: bool = False
    reverted: bool = False


class LocationState(BaseModel):
    """
    State tracker for a single location.

    Maintains the history of all state changes in a location, along with
    visit tracking for first/last visit times.

    Attributes:
        location_id: Unique identifier for the location
        room_id: Specific room within the location (optional)
        state_changes: List of all state changes
        visited: Whether the location has been visited
        first_visited: When first visited (optional)
        last_visited: When last visited (optional)
    """
    location_id: str
    room_id: Optional[str] = None
    state_changes: list[StateChange] = Field(default_factory=list)
    visited: bool = False
    first_visited: Optional[GameTime] = None
    last_visited: Optional[GameTime] = None


class LocationStateManager:
    """
    Manages persistent state changes for locations.

    The LocationStateManager tracks the state of all locations in a campaign,
    maintaining a history of changes like opened doors, disarmed traps, and
    collected loot. This ensures consistency across sessions and prevents
    contradictions like encountering the same loot twice.

    Attributes:
        campaign_path: Path to campaign directory for persistence
        _locations: Dictionary mapping location IDs to LocationState objects
    """

    def __init__(self, campaign_path: Path):
        """
        Initialize the location state manager.

        Args:
            campaign_path: Path to the campaign directory
        """
        self.campaign_path = Path(campaign_path)
        self._locations: dict[str, LocationState] = {}
        self.campaign_path.mkdir(parents=True, exist_ok=True)
        self.load()

    def _ensure_location(self, location_id: str) -> LocationState:
        """
        Ensure a location exists in the manager.

        Creates a new LocationState if one doesn't exist.

        Args:
            location_id: ID of the location

        Returns:
            LocationState for the location
        """
        if location_id not in self._locations:
            self._locations[location_id] = LocationState(location_id=location_id)
        return self._locations[location_id]

    def get_location_state(self, location_id: str) -> LocationState:
        """
        Get the state of a location.

        Args:
            location_id: ID of the location

        Returns:
            LocationState for the location
        """
        return self._ensure_location(location_id)

    def record_state_change(self, location_id: str, change: StateChange) -> str:
        """
        Record a state change in a location.

        Args:
            location_id: ID of the location
            change: The state change to record

        Returns:
            The change's ID (auto-generated if not provided)
        """
        loc = self._ensure_location(location_id)
        if not change.id:
            change.id = f"sc_{uuid4().hex[:8]}"
        loc.state_changes.append(change)
        logger.debug(f"Recorded {change.change_type} in {location_id}: {change.description}")
        return change.id

    def is_door_open(self, location_id: str, door_id: str) -> bool:
        """
        Check if a door is currently open.

        Checks the most recent non-reverted state change for the door.

        Args:
            location_id: ID of the location
            door_id: ID of the door

        Returns:
            True if door is open, False otherwise (default: closed)
        """
        loc = self._ensure_location(location_id)
        # Find the latest door state change for this door
        for change in reversed(loc.state_changes):
            if change.target_object == door_id and not change.reverted:
                if change.change_type in (StateChangeType.DOOR_OPENED, StateChangeType.DOOR_BROKEN):
                    return True
                if change.change_type == StateChangeType.DOOR_LOCKED:
                    return False
        return False  # Default: doors are closed

    def is_trap_active(self, location_id: str, trap_id: str) -> bool:
        """
        Check if a trap is currently active.

        Args:
            location_id: ID of the location
            trap_id: ID of the trap

        Returns:
            True if trap is active, False if triggered/disarmed (default: active)
        """
        loc = self._ensure_location(location_id)
        for change in reversed(loc.state_changes):
            if change.target_object == trap_id and not change.reverted:
                if change.change_type in (StateChangeType.TRAP_TRIGGERED, StateChangeType.TRAP_DISARMED):
                    return False
        return True  # Default: traps are active

    def is_loot_collected(self, location_id: str, loot_id: str) -> bool:
        """
        Check if loot has been collected.

        Args:
            location_id: ID of the location
            loot_id: ID of the loot

        Returns:
            True if loot has been collected, False otherwise
        """
        loc = self._ensure_location(location_id)
        for change in loc.state_changes:
            if (change.target_object == loot_id and
                change.change_type == StateChangeType.LOOT_COLLECTED and
                not change.reverted):
                return True
        return False

    def get_changes_since(self, location_id: str, game_time: GameTime) -> list[StateChange]:
        """
        Get all state changes since a specific game time.

        Args:
            location_id: ID of the location
            game_time: Threshold time

        Returns:
            List of state changes at or after the threshold
        """
        loc = self._ensure_location(location_id)
        threshold = game_time._to_total_minutes()
        return [c for c in loc.state_changes if c.game_time._to_total_minutes() >= threshold]

    def revert_change(self, location_id: str, change_id: str) -> bool:
        """
        Revert a state change.

        Only reversible changes can be reverted.

        Args:
            location_id: ID of the location
            change_id: ID of the change to revert

        Returns:
            True if successfully reverted, False if not found or irreversible
        """
        loc = self._ensure_location(location_id)
        for change in loc.state_changes:
            if change.id == change_id:
                if not change.reversible:
                    logger.warning(f"Cannot revert irreversible change {change_id}")
                    return False
                change.reverted = True
                logger.info(f"Reverted change {change_id} in {location_id}")
                return True
        logger.warning(f"Change {change_id} not found in {location_id}")
        return False

    def mark_visited(self, location_id: str, game_time: GameTime) -> None:
        """
        Mark a location as visited.

        Updates first_visited on first visit, always updates last_visited.

        Args:
            location_id: ID of the location
            game_time: When the visit occurred
        """
        loc = self._ensure_location(location_id)
        loc.visited = True
        if loc.first_visited is None:
            loc.first_visited = game_time
        loc.last_visited = game_time
        logger.debug(f"Marked {location_id} as visited at {game_time.to_string('short')}")

    def get_location_summary(self, location_id: str) -> dict:
        """
        Get a summary of a location's state.

        Args:
            location_id: ID of the location

        Returns:
            Dictionary with location summary information
        """
        loc = self._ensure_location(location_id)
        active_changes = [c for c in loc.state_changes if not c.reverted]
        return {
            "location_id": loc.location_id,
            "visited": loc.visited,
            "total_changes": len(loc.state_changes),
            "active_changes": len(active_changes),
            "first_visited": loc.first_visited.to_string() if loc.first_visited else None,
            "last_visited": loc.last_visited.to_string() if loc.last_visited else None,
        }

    @property
    def location_count(self) -> int:
        """
        Get the total number of tracked locations.

        Returns:
            Number of locations
        """
        return len(self._locations)

    def save(self) -> None:
        """Persist location states to location_state.json."""
        data = {
            "version": "1.0",
            "locations": {
                lid: loc.model_dump() for lid, loc in self._locations.items()
            },
        }
        path = self.campaign_path / "location_state.json"
        path.write_text(json.dumps(data, indent=2, default=str))
        logger.info(f"Saved state for {len(self._locations)} locations to {path}")

    def load(self) -> None:
        """
        Load location states from location_state.json.

        If the file doesn't exist, initializes with no locations.
        If the file is corrupt, logs a warning and starts fresh.
        """
        path = self.campaign_path / "location_state.json"
        if not path.exists():
            logger.debug(f"No existing location state at {path}, starting fresh")
            return
        try:
            data = json.loads(path.read_text())
            for lid, loc_data in data.get("locations", {}).items():
                self._locations[lid] = LocationState(**loc_data)
            logger.info(f"Loaded state for {len(self._locations)} locations from {path}")
        except Exception as e:
            logger.warning(f"Failed to load location state: {e}")


__all__ = [
    "StateChangeType",
    "StateChange",
    "LocationState",
    "LocationStateManager",
]
