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
- DiscoveryContext: Structured discovery data for narrator integration
- build_discovery_context: Builds narrator-ready discovery context
- format_discovery_prompt_section: Formats context into LLM prompt text
- filter_location_by_discovery: Filters location data by discovery state
- PartyKnowledge: Tracks what the party collectively knows about the world
- AcquisitionMethod: How the party acquired knowledge
- KnowledgeRecord: Metadata about a party-known fact
"""

from .discovery import (
    DiscoveryLevel,
    DiscoveryTracker,
    FeatureDiscovery,
    LocationDiscovery,
)
from .narrator_discovery import (
    DiscoveryContext,
    FeatureView,
    build_discovery_context,
    filter_location_by_discovery,
    format_discovery_prompt_section,
)
from .party_knowledge import (
    PARTY_KNOWN_TAG,
    AcquisitionMethod,
    KnowledgeRecord,
    PartyKnowledge,
)

__all__ = [
    "DiscoveryLevel",
    "DiscoveryTracker",
    "FeatureDiscovery",
    "LocationDiscovery",
    "DiscoveryContext",
    "FeatureView",
    "build_discovery_context",
    "filter_location_by_discovery",
    "format_discovery_prompt_section",
    "PARTY_KNOWN_TAG",
    "AcquisitionMethod",
    "KnowledgeRecord",
    "PartyKnowledge",
]
