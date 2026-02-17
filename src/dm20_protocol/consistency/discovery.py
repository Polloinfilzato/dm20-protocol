"""
Discovery tracking for locations and their features.

This module tracks what the party has discovered about locations and their
notable features. It supports granular discovery levels per feature and
enforces that discovery can only be upgraded, never downgraded.

Key components:
- DiscoveryLevel: Enum for discovery progression (UNDISCOVERED -> FULLY_MAPPED)
- FeatureDiscovery: Discovery state for a single location feature
- LocationDiscovery: Discovery state for a location and its features
- DiscoveryTracker: Manager class for all discovery state in a campaign
"""

import json
import logging
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("dm20-protocol")


class DiscoveryLevel(IntEnum):
    """
    Discovery levels for locations and features.

    Levels are ordered so that comparisons work naturally:
    UNDISCOVERED < GLIMPSED < EXPLORED < FULLY_MAPPED.

    Discovery can only be upgraded, never downgraded.
    """
    UNDISCOVERED = 0
    GLIMPSED = 1
    EXPLORED = 2
    FULLY_MAPPED = 3


class FeatureDiscovery(BaseModel):
    """
    Discovery state for a single notable feature of a location.

    Tracks who discovered the feature, when, and how. The discovery_level
    can only be upgraded (enforced by DiscoveryTracker, not the model itself).

    Attributes:
        feature_name: Name of the notable feature (matches Location.notable_features)
        discovery_level: Current discovery level for this feature
        discovered_by: Name of the character who discovered it (optional)
        discovered_session: Session number when it was discovered (optional)
        discovery_method: How it was discovered (e.g., "perception check", "told by NPC")
    """
    feature_name: str
    discovery_level: int = Field(
        default=DiscoveryLevel.UNDISCOVERED,
        description="Discovery level (0=undiscovered, 1=glimpsed, 2=explored, 3=fully_mapped)"
    )
    discovered_by: Optional[str] = Field(
        default=None,
        description="Character who discovered this feature"
    )
    discovered_session: Optional[int] = Field(
        default=None,
        ge=1,
        description="Session number when feature was discovered"
    )
    discovery_method: Optional[str] = Field(
        default=None,
        description="How the feature was discovered (e.g., 'perception check', 'investigation', 'told by NPC')"
    )


class LocationDiscovery(BaseModel):
    """
    Discovery state for a single location.

    Tracks the overall discovery level and per-feature discovery. The
    overall_level represents the party's general knowledge of the location,
    while feature_discoveries provides granular detail.

    Attributes:
        location_id: Unique identifier matching the location name/ID
        overall_level: Overall discovery level for the location
        feature_discoveries: Per-feature discovery states
        first_visited: ISO timestamp of first visit (optional)
        last_visited: ISO timestamp of most recent visit (optional)
    """
    location_id: str
    overall_level: int = Field(
        default=DiscoveryLevel.UNDISCOVERED,
        description="Overall discovery level (0=undiscovered, 1=glimpsed, 2=explored, 3=fully_mapped)"
    )
    feature_discoveries: list[FeatureDiscovery] = Field(default_factory=list)
    first_visited: Optional[str] = Field(
        default=None,
        description="ISO timestamp of first visit"
    )
    last_visited: Optional[str] = Field(
        default=None,
        description="ISO timestamp of most recent visit"
    )


class DiscoveryTracker:
    """
    Manages discovery state for all locations in a campaign.

    The DiscoveryTracker persists discovery data to discovery_state.json
    in the campaign's split-storage directory. It follows the same pattern
    as LocationStateManager: load on init, save explicitly.

    Discovery levels can only be upgraded (UNDISCOVERED -> GLIMPSED ->
    EXPLORED -> FULLY_MAPPED). Attempts to downgrade are silently ignored.

    For backward compatibility, locations without discovery data are treated
    as EXPLORED (level 2), since existing locations were already accessible
    to the party before the discovery system was introduced.

    Attributes:
        campaign_path: Path to the campaign directory for persistence
        _locations: Dictionary mapping location IDs to LocationDiscovery objects
    """

    # Default level for locations without explicit discovery data.
    # This ensures backward compatibility: existing campaigns treat all
    # previously created locations as already explored by the party.
    DEFAULT_LEVEL = DiscoveryLevel.EXPLORED

    def __init__(self, campaign_path: Path):
        """
        Initialize the discovery tracker.

        Args:
            campaign_path: Path to the campaign directory
        """
        self.campaign_path = Path(campaign_path)
        self._locations: dict[str, LocationDiscovery] = {}
        self.campaign_path.mkdir(parents=True, exist_ok=True)
        self.load()

    @property
    def _state_path(self) -> Path:
        """Path to the discovery state JSON file."""
        return self.campaign_path / "discovery_state.json"

    @property
    def location_count(self) -> int:
        """Get the number of tracked locations."""
        return len(self._locations)

    def _ensure_location(self, location_id: str) -> LocationDiscovery:
        """
        Ensure a location exists in the tracker.

        Creates a new LocationDiscovery if one doesn't exist. New entries
        start at UNDISCOVERED (not the backward-compatible default), since
        explicitly creating a discovery entry means the system is actively
        tracking this location.

        Args:
            location_id: ID/name of the location

        Returns:
            LocationDiscovery for the location
        """
        if location_id not in self._locations:
            self._locations[location_id] = LocationDiscovery(location_id=location_id)
        return self._locations[location_id]

    def discover_location(
        self,
        location_id: str,
        level: DiscoveryLevel,
    ) -> LocationDiscovery:
        """
        Set or upgrade the overall discovery level for a location.

        Discovery can only be upgraded. If the requested level is lower than
        the current level, the request is silently ignored.

        Args:
            location_id: ID/name of the location
            level: Desired discovery level

        Returns:
            Updated LocationDiscovery object
        """
        loc = self._ensure_location(location_id)
        current = DiscoveryLevel(loc.overall_level)

        if level > current:
            loc.overall_level = level
            logger.debug(
                f"Discovery upgraded for '{location_id}': "
                f"{current.name} -> {level.name}"
            )
        else:
            logger.debug(
                f"Discovery for '{location_id}' not upgraded: "
                f"requested {level.name} <= current {current.name}"
            )

        # Update visit timestamps
        now = datetime.now().isoformat()
        if loc.first_visited is None:
            loc.first_visited = now
        loc.last_visited = now

        return loc

    def discover_feature(
        self,
        location_id: str,
        feature_name: str,
        level: DiscoveryLevel,
        method: Optional[str] = None,
        discovered_by: Optional[str] = None,
        session: Optional[int] = None,
    ) -> FeatureDiscovery:
        """
        Reveal or upgrade a specific feature of a location.

        Discovery can only be upgraded. If the feature doesn't exist in
        the tracker yet, it is created. If the requested level is lower
        than the current level, the request is silently ignored.

        Args:
            location_id: ID/name of the location
            feature_name: Name of the notable feature
            level: Desired discovery level for the feature
            method: How it was discovered (e.g., "perception check")
            discovered_by: Character who discovered it
            session: Session number when discovered

        Returns:
            Updated FeatureDiscovery object
        """
        loc = self._ensure_location(location_id)

        # Find existing feature discovery or create one
        feature_disc = None
        for fd in loc.feature_discoveries:
            if fd.feature_name == feature_name:
                feature_disc = fd
                break

        if feature_disc is None:
            feature_disc = FeatureDiscovery(feature_name=feature_name)
            loc.feature_discoveries.append(feature_disc)

        current = DiscoveryLevel(feature_disc.discovery_level)

        if level > current:
            feature_disc.discovery_level = level
            # Update metadata only when level actually changes
            if discovered_by is not None:
                feature_disc.discovered_by = discovered_by
            if session is not None:
                feature_disc.discovered_session = session
            if method is not None:
                feature_disc.discovery_method = method
            logger.debug(
                f"Feature '{feature_name}' in '{location_id}' upgraded: "
                f"{current.name} -> {level.name}"
            )
        else:
            logger.debug(
                f"Feature '{feature_name}' in '{location_id}' not upgraded: "
                f"requested {level.name} <= current {current.name}"
            )

        return feature_disc

    def get_discovery_state(self, location_id: str) -> LocationDiscovery:
        """
        Get the current discovery state for a location.

        If the location has no explicit discovery data, returns a default
        LocationDiscovery with overall_level = DEFAULT_LEVEL (EXPLORED)
        for backward compatibility. This default entry is NOT persisted
        to avoid polluting the discovery state file.

        Args:
            location_id: ID/name of the location

        Returns:
            LocationDiscovery for the location
        """
        if location_id in self._locations:
            return self._locations[location_id]

        # Backward compatibility: return default without persisting
        return LocationDiscovery(
            location_id=location_id,
            overall_level=self.DEFAULT_LEVEL,
        )

    def get_visible_features(self, location_id: str) -> list[FeatureDiscovery]:
        """
        Return only features that are at GLIMPSED level or above.

        Features at UNDISCOVERED level are hidden from the party.

        Args:
            location_id: ID/name of the location

        Returns:
            List of FeatureDiscovery objects at GLIMPSED or above
        """
        if location_id not in self._locations:
            return []

        loc = self._locations[location_id]
        return [
            fd for fd in loc.feature_discoveries
            if DiscoveryLevel(fd.discovery_level) >= DiscoveryLevel.GLIMPSED
        ]

    def is_fully_explored(self, location_id: str) -> bool:
        """
        Check if all features of a location are FULLY_MAPPED.

        A location is considered fully explored when:
        1. The overall level is FULLY_MAPPED, AND
        2. ALL tracked features are at FULLY_MAPPED level.

        If the location has no tracked features, only the overall level
        is checked. If the location has no discovery data at all, returns
        False (even though the backward-compatible default is EXPLORED,
        EXPLORED != FULLY_MAPPED).

        Args:
            location_id: ID/name of the location

        Returns:
            True if fully explored, False otherwise
        """
        if location_id not in self._locations:
            return False

        loc = self._locations[location_id]

        # Overall level must be FULLY_MAPPED
        if DiscoveryLevel(loc.overall_level) != DiscoveryLevel.FULLY_MAPPED:
            return False

        # All features must be FULLY_MAPPED
        for fd in loc.feature_discoveries:
            if DiscoveryLevel(fd.discovery_level) != DiscoveryLevel.FULLY_MAPPED:
                return False

        return True

    def save(self) -> None:
        """Persist discovery state to discovery_state.json."""
        data = {
            "version": "1.0",
            "locations": {
                lid: loc.model_dump(mode="json")
                for lid, loc in self._locations.items()
            },
        }
        self._state_path.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info(
            f"Saved discovery state for {len(self._locations)} locations "
            f"to {self._state_path}"
        )

    def load(self) -> None:
        """
        Load discovery state from discovery_state.json.

        If the file doesn't exist, initializes with no locations.
        If the file is corrupt, logs a warning and starts fresh.
        """
        if not self._state_path.exists():
            logger.debug(
                f"No existing discovery state at {self._state_path}, starting fresh"
            )
            return

        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            for lid, loc_data in data.get("locations", {}).items():
                self._locations[lid] = LocationDiscovery.model_validate(loc_data)
            logger.info(
                f"Loaded discovery state for {len(self._locations)} locations "
                f"from {self._state_path}"
            )
        except Exception as e:
            logger.warning(f"Failed to load discovery state: {e}")


__all__ = [
    "DiscoveryLevel",
    "FeatureDiscovery",
    "LocationDiscovery",
    "DiscoveryTracker",
]
