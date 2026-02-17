"""
Discovery context builder for the Narrator agent.

Builds structured discovery context that the Narrator uses to filter scene
descriptions based on what the party has actually discovered. Undiscovered
features produce sensory hints rather than explicit descriptions; GLIMPSED
features get vague descriptions; EXPLORED features get full descriptions;
FULLY_MAPPED features include DM-level detail.

Key components:
- DiscoveryContext: Structured discovery data for a single location
- FeatureView: A single feature with its description tier
- build_discovery_context(): Main entry point for building narrator context
- format_discovery_prompt_section(): Formats context into LLM prompt text
"""

import logging
from typing import Optional

from ..models import Location
from .discovery import (
    DiscoveryLevel,
    DiscoveryTracker,
    FeatureDiscovery,
    LocationDiscovery,
)

logger = logging.getLogger("dm20-protocol")


# ------------------------------------------------------------------
# Sensory hint templates for undiscovered features
# ------------------------------------------------------------------
# These templates produce atmospheric hints that suggest hidden features
# without revealing them. The narrator weaves these into the scene.
SENSORY_HINTS = [
    "You notice a cold draft from the {direction} wall...",
    "A faint {sense} catches your attention, though you can't quite place its source...",
    "Something about this area feels... off. The shadows seem to gather in unexpected places.",
    "There's an almost imperceptible {sense} that nags at the edge of your awareness...",
    "Your instincts tell you there's more here than meets the eye...",
]

# Direction and sense words for hint variation
DIRECTIONS = ["north", "south", "east", "west"]
SENSES = [
    "sound", "smell", "vibration", "shimmer", "echo",
    "breeze", "warmth", "chill", "hum", "flicker",
]


class FeatureView:
    """A single location feature as seen at a specific discovery level.

    Provides the appropriate description tier based on the party's
    discovery level for this feature.

    Attributes:
        feature_name: The name of the feature.
        discovery_level: The party's current discovery level for this feature.
        description_tier: One of 'hidden', 'hint', 'vague', 'full', 'complete'.
        display_text: The text to show in the narrator prompt.
    """

    def __init__(
        self,
        feature_name: str,
        discovery_level: DiscoveryLevel,
        hint_text: str = "",
    ) -> None:
        self.feature_name = feature_name
        self.discovery_level = discovery_level
        self.hint_text = hint_text

        # Map discovery level to description tier
        tier_map = {
            DiscoveryLevel.UNDISCOVERED: "hidden",
            DiscoveryLevel.GLIMPSED: "vague",
            DiscoveryLevel.EXPLORED: "full",
            DiscoveryLevel.FULLY_MAPPED: "complete",
        }
        self.description_tier = tier_map.get(discovery_level, "hidden")

    @property
    def display_text(self) -> str:
        """Get the display text appropriate for this discovery level."""
        if self.description_tier == "hidden":
            return self.hint_text or ""
        elif self.description_tier == "vague":
            return f"[Vaguely perceived] {self.feature_name}"
        elif self.description_tier == "full":
            return f"{self.feature_name}"
        elif self.description_tier == "complete":
            return f"{self.feature_name} [fully mapped — include DM-level detail]"
        return ""


class DiscoveryContext:
    """Structured discovery data for a single location.

    Contains the overall discovery level and per-feature views,
    ready for injection into the narrator's prompt.

    Attributes:
        location_name: Name of the location.
        overall_level: Overall discovery level for the location.
        visible_features: Features at GLIMPSED or above.
        hidden_feature_hints: Sensory hints for UNDISCOVERED features.
        total_features: Total number of features in the location.
    """

    def __init__(
        self,
        location_name: str,
        overall_level: DiscoveryLevel,
        feature_views: list[FeatureView],
        hidden_hint_count: int = 0,
    ) -> None:
        self.location_name = location_name
        self.overall_level = overall_level
        self.feature_views = feature_views
        self.hidden_hint_count = hidden_hint_count

    @property
    def visible_features(self) -> list[FeatureView]:
        """Features the party can see (GLIMPSED or above)."""
        return [fv for fv in self.feature_views if fv.description_tier != "hidden"]

    @property
    def hidden_features(self) -> list[FeatureView]:
        """Features that are still hidden (UNDISCOVERED)."""
        return [fv for fv in self.feature_views if fv.description_tier == "hidden"]

    @property
    def total_features(self) -> int:
        """Total number of features tracked."""
        return len(self.feature_views)


def _generate_hint(feature_name: str, index: int) -> str:
    """Generate a sensory hint for an undiscovered feature.

    Uses the feature name and index to deterministically select
    a hint template, providing variety without randomness (so
    the same feature always produces the same hint).

    Args:
        feature_name: Name of the hidden feature (used for hash).
        index: Index for variation.

    Returns:
        A sensory hint string.
    """
    # Use feature name hash for deterministic but varied hints
    name_hash = sum(ord(c) for c in feature_name)
    template_idx = (name_hash + index) % len(SENSORY_HINTS)
    direction = DIRECTIONS[(name_hash + index) % len(DIRECTIONS)]
    sense = SENSES[(name_hash + index) % len(SENSES)]

    hint = SENSORY_HINTS[template_idx]
    hint = hint.replace("{direction}", direction)
    hint = hint.replace("{sense}", sense)
    return hint


def build_discovery_context(
    location: Location,
    tracker: DiscoveryTracker,
    auto_glimpse_on_visit: bool = True,
) -> DiscoveryContext:
    """Build a DiscoveryContext for a location based on the tracker state.

    This is the main entry point for integrating discovery with the narrator.
    It queries the DiscoveryTracker for the location's discovery state and
    builds feature views appropriate for each discovery level.

    When auto_glimpse_on_visit is True and the location is UNDISCOVERED,
    it auto-upgrades to GLIMPSED and reveals "obvious" features (first half
    of the notable_features list). This simulates first-visit discovery.

    Args:
        location: The Location model with all features.
        tracker: The DiscoveryTracker instance.
        auto_glimpse_on_visit: If True, auto-GLIMPSE on first visit.

    Returns:
        DiscoveryContext with feature views and hints.
    """
    # Check whether this location has explicit discovery tracking.
    # Locations without explicit tracking use backward-compatible EXPLORED default,
    # but for auto-glimpse we need to distinguish "never visited" from "already tracked".
    has_explicit_tracking = location.name in tracker._locations

    loc_state = tracker.get_discovery_state(location.name)
    overall_level = DiscoveryLevel(loc_state.overall_level)

    # Auto-glimpse on first visit: triggers when the location has no explicit
    # tracking data (i.e., it's a brand new location the party is visiting).
    # Locations with existing tracking (even at UNDISCOVERED) are not auto-glimpsed
    # because their state was set intentionally.
    if auto_glimpse_on_visit and not has_explicit_tracking:
        tracker.discover_location(location.name, DiscoveryLevel.GLIMPSED)
        overall_level = DiscoveryLevel.GLIMPSED

        # Reveal "obvious" features (first half of the list)
        if location.notable_features:
            obvious_count = max(1, len(location.notable_features) // 2)
            for feature_name in location.notable_features[:obvious_count]:
                tracker.discover_feature(
                    location.name,
                    feature_name,
                    DiscoveryLevel.GLIMPSED,
                    method="first visit",
                )

        # Re-fetch state after auto-discovery
        loc_state = tracker.get_discovery_state(location.name)
        has_explicit_tracking = True  # We just registered it

    # Build feature discovery map from tracker
    feature_disc_map: dict[str, FeatureDiscovery] = {}
    for fd in loc_state.feature_discoveries:
        feature_disc_map[fd.feature_name] = fd

    # Determine default level for untracked features.
    # For backward-compatible locations (no explicit tracking), features
    # inherit the location's overall level (EXPLORED) so all features
    # are visible. For explicitly tracked locations, untracked features
    # are UNDISCOVERED (the DM hasn't set them up yet).
    if not has_explicit_tracking:
        default_feature_level = DiscoveryLevel(overall_level)
    else:
        default_feature_level = DiscoveryLevel.UNDISCOVERED

    # Build feature views for all notable features
    feature_views: list[FeatureView] = []
    hidden_count = 0

    for idx, feature_name in enumerate(location.notable_features):
        fd = feature_disc_map.get(feature_name)
        if fd is not None:
            level = DiscoveryLevel(fd.discovery_level)
        else:
            level = default_feature_level

        hint = ""
        if level == DiscoveryLevel.UNDISCOVERED:
            hint = _generate_hint(feature_name, idx)
            hidden_count += 1

        feature_views.append(FeatureView(
            feature_name=feature_name,
            discovery_level=level,
            hint_text=hint,
        ))

    return DiscoveryContext(
        location_name=location.name,
        overall_level=overall_level,
        feature_views=feature_views,
        hidden_hint_count=hidden_count,
    )


def format_discovery_prompt_section(context: DiscoveryContext) -> str:
    """Format a DiscoveryContext into a prompt section for the narrator LLM.

    Produces a structured text block that instructs the narrator on what
    to reveal and how to describe each feature based on discovery level.

    Args:
        context: The DiscoveryContext to format.

    Returns:
        A formatted string for injection into the narrator prompt.
        Returns empty string if no discovery context is available.
    """
    if not context:
        return ""

    lines = [
        f"## Discovery State for {context.location_name}",
        f"Overall knowledge: {DiscoveryLevel(context.overall_level).name}",
        "",
    ]

    # Visible features with appropriate detail tiers
    visible = context.visible_features
    if visible:
        lines.append("### Known Features (describe according to tier):")
        for fv in visible:
            if fv.description_tier == "vague":
                lines.append(
                    f"- **{fv.feature_name}** [GLIMPSED]: Describe vaguely. "
                    "The party noticed this but hasn't examined it closely. "
                    "Use uncertain language: 'seems to be', 'appears to', 'you think you see'."
                )
            elif fv.description_tier == "full":
                lines.append(
                    f"- **{fv.feature_name}** [EXPLORED]: Describe fully. "
                    "The party has examined this thoroughly. Provide clear, detailed description."
                )
            elif fv.description_tier == "complete":
                lines.append(
                    f"- **{fv.feature_name}** [FULLY MAPPED]: Include all detail, "
                    "even mechanical information. The party knows this feature inside and out."
                )
        lines.append("")

    # Sensory hints for hidden features
    hidden = context.hidden_features
    if hidden:
        lines.append(
            "### Sensory Hints (weave subtly into the scene, do NOT reveal the features):"
        )
        for fv in hidden:
            if fv.hint_text:
                lines.append(f"- {fv.hint_text}")
        lines.append("")

    # Overall guidance
    if context.overall_level == DiscoveryLevel.GLIMPSED:
        lines.append(
            "**Guidance:** The party has only a first impression of this place. "
            "Keep descriptions atmospheric but incomplete. Suggest there is more to discover."
        )
    elif context.overall_level == DiscoveryLevel.EXPLORED:
        lines.append(
            "**Guidance:** The party is familiar with this location. "
            "Describe it confidently, noting any changes since their last visit."
        )
    elif context.overall_level == DiscoveryLevel.FULLY_MAPPED:
        lines.append(
            "**Guidance:** The party knows this place intimately. "
            "Include tactical and mechanical details freely."
        )

    return "\n".join(lines)


def filter_location_by_discovery(
    location: Location,
    tracker: DiscoveryTracker,
) -> dict:
    """Filter a location's data based on discovery state.

    Returns a dict representation of the location with notable_features
    filtered to only include features the party has discovered (GLIMPSED+).
    Used by the get_location MCP tool when discovery_filter is enabled.

    Args:
        location: The full Location model.
        tracker: The DiscoveryTracker instance.

    Returns:
        Dict with location data, notable_features filtered by discovery.
    """
    loc_state = tracker.get_discovery_state(location.name)
    overall_level = DiscoveryLevel(loc_state.overall_level)

    # Build set of visible feature names
    visible_names: set[str] = set()
    for fd in loc_state.feature_discoveries:
        if DiscoveryLevel(fd.discovery_level) >= DiscoveryLevel.GLIMPSED:
            visible_names.add(fd.feature_name)

    # For backward compatibility (EXPLORED default), show all features
    if (
        location.name not in tracker._locations
        and overall_level >= DiscoveryLevel.EXPLORED
    ):
        visible_names = set(location.notable_features)

    # Filter notable features
    filtered_features = [
        f for f in location.notable_features if f in visible_names
    ]

    return {
        "name": location.name,
        "location_type": location.location_type,
        "description": location.description,
        "population": location.population,
        "government": location.government,
        "notable_features": filtered_features,
        "npcs": location.npcs,
        "connections": location.connections,
        "notes": location.notes,
        "discovery_level": DiscoveryLevel(overall_level).name,
        "hidden_features_count": len(location.notable_features) - len(filtered_features),
    }


__all__ = [
    "DiscoveryContext",
    "FeatureView",
    "build_discovery_context",
    "format_discovery_prompt_section",
    "filter_location_by_discovery",
]
