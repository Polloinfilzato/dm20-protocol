"""
Campaign-level consistency tracking.

This package provides discovery tracking and other campaign-wide consistency
tools that operate at the storage/campaign level (as opposed to the
Claudmaster-specific consistency tools in claudmaster.consistency).

Key components:
- DiscoveryTracker: Tracks what the party has discovered about locations
- DiscoveryLevel: Enum for discovery progression
- FeatureDiscovery: Per-feature discovery state
- LocationDiscovery: Per-location discovery state
"""

from .discovery import (
    DiscoveryLevel,
    DiscoveryTracker,
    FeatureDiscovery,
    LocationDiscovery,
)

__all__ = [
    "DiscoveryLevel",
    "DiscoveryTracker",
    "FeatureDiscovery",
    "LocationDiscovery",
]
