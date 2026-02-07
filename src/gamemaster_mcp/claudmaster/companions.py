"""
Companion NPC Profiles system for the Claudmaster multi-agent framework.

This module extends the NPC framework to support AI-controlled companion characters
with distinct personalities, combat styles, loyalty mechanics, and campaign persistence.

Companions are NPCs that join the player party and can be controlled by AI agents
during combat and exploration. They have personality traits that affect their behavior,
loyalty scores that determine their willingness to follow orders, and combat preferences.
"""

from enum import Enum
from pydantic import BaseModel, Field


class CombatStyle(str, Enum):
    """Combat behavior preferences for companions."""
    AGGRESSIVE = "aggressive"
    DEFENSIVE = "defensive"
    SUPPORTIVE = "supportive"
    BALANCED = "balanced"


class CompanionArchetype(str, Enum):
    """Role archetypes for companions that define their default behavior."""
    TANK = "tank"
    HEALER = "healer"
    STRIKER = "striker"
    SUPPORT = "support"


class PersonalityTraits(BaseModel):
    """
    Numeric personality traits that influence companion behavior and dialogue.

    All traits are on a 0-100 scale where:
    - 0-20: Very low
    - 21-40: Low
    - 41-60: Moderate
    - 61-80: High
    - 81-100: Very high
    """
    bravery: int = Field(default=50, ge=0, le=100, description="Willingness to take risks")
    loyalty: int = Field(default=50, ge=0, le=100, description="Dedication to the party")
    aggression: int = Field(default=50, ge=0, le=100, description="Tendency to attack vs defend")
    caution: int = Field(default=50, ge=0, le=100, description="Tendency to avoid danger")
    compassion: int = Field(default=50, ge=0, le=100, description="Concern for others' wellbeing")


class CompanionProfile(BaseModel):
    """
    Full profile for an AI-controlled companion character.

    Companions are NPCs that join the party and are controlled by AI agents.
    They have personalities, combat preferences, and loyalty mechanics.
    """
    npc_id: str = Field(description="Reference to the base NPC in the campaign NPCs dict")
    name: str = Field(description="Display name for the companion")
    archetype: CompanionArchetype = Field(description="Role archetype defining behavior")
    combat_style: CombatStyle = Field(description="Preferred combat behavior")
    personality: PersonalityTraits = Field(
        default_factory=PersonalityTraits,
        description="Personality trait scores"
    )
    loyalty_score: int = Field(
        default=50,
        ge=0,
        le=100,
        description="Current loyalty to the party (affects willingness)"
    )
    max_loyalty: int = Field(
        default=100,
        ge=0,
        le=100,
        description="Maximum possible loyalty for this companion"
    )
    active: bool = Field(default=True, description="Whether companion is in active party")
    preferred_targets: list[str] = Field(
        default_factory=list,
        description="List of enemy types this companion prefers to target"
    )
    avoided_targets: list[str] = Field(
        default_factory=list,
        description="List of enemy types this companion tries to avoid"
    )
    preferred_abilities: list[str] = Field(
        default_factory=list,
        description="List of ability/spell names this companion prefers to use"
    )


# Archetype templates define default values for creating companions
ARCHETYPE_TEMPLATES: dict[CompanionArchetype, dict] = {
    CompanionArchetype.TANK: {
        "combat_style": CombatStyle.DEFENSIVE,
        "personality": PersonalityTraits(bravery=80, aggression=40, caution=30),
        "preferred_abilities": ["shield", "taunt", "protect"],
    },
    CompanionArchetype.HEALER: {
        "combat_style": CombatStyle.SUPPORTIVE,
        "personality": PersonalityTraits(compassion=90, caution=70, aggression=20),
        "preferred_abilities": ["heal", "cure", "bless"],
    },
    CompanionArchetype.STRIKER: {
        "combat_style": CombatStyle.AGGRESSIVE,
        "personality": PersonalityTraits(bravery=70, aggression=80, caution=20),
        "preferred_abilities": ["sneak_attack", "strike", "flurry"],
    },
    CompanionArchetype.SUPPORT: {
        "combat_style": CombatStyle.SUPPORTIVE,
        "personality": PersonalityTraits(compassion=70, caution=60, aggression=30),
        "preferred_abilities": ["buff", "debuff", "inspire"],
    },
}


class CompanionManager:
    """
    Manages companion lifecycle, persistence, and loyalty mechanics.

    The manager maintains a registry of all companions in the campaign,
    tracks which are active in the party, handles loyalty adjustments,
    and provides save/load functionality for campaign persistence.
    """

    def __init__(self) -> None:
        """Initialize an empty companion registry."""
        self._companions: dict[str, CompanionProfile] = {}

    def create_from_archetype(
        self,
        npc_id: str,
        name: str,
        archetype: CompanionArchetype,
        **overrides
    ) -> CompanionProfile:
        """
        Create a companion from an archetype template.

        Args:
            npc_id: ID of the NPC this companion references
            name: Display name for the companion
            archetype: Role archetype to use as template
            **overrides: Optional field overrides (combat_style, personality, etc.)

        Returns:
            The created CompanionProfile

        Raises:
            ValueError: If companion with this npc_id already exists
        """
        if npc_id in self._companions:
            raise ValueError(f"Companion with npc_id '{npc_id}' already exists")

        template = ARCHETYPE_TEMPLATES[archetype]

        # Start with template defaults
        profile_data = {
            "npc_id": npc_id,
            "name": name,
            "archetype": archetype,
            "combat_style": template["combat_style"],
            "personality": template["personality"],
            "preferred_abilities": template["preferred_abilities"].copy(),
        }

        # Apply overrides
        profile_data.update(overrides)

        companion = CompanionProfile(**profile_data)
        self._companions[npc_id] = companion
        return companion

    def create_custom(
        self,
        npc_id: str,
        name: str,
        archetype: CompanionArchetype,
        combat_style: CombatStyle,
        personality: PersonalityTraits,
        **kwargs
    ) -> CompanionProfile:
        """
        Create a fully custom companion without using archetype defaults.

        Args:
            npc_id: ID of the NPC this companion references
            name: Display name for the companion
            archetype: Role archetype (for categorization)
            combat_style: Combat behavior preference
            personality: Full personality trait configuration
            **kwargs: Additional optional fields

        Returns:
            The created CompanionProfile

        Raises:
            ValueError: If companion with this npc_id already exists
        """
        if npc_id in self._companions:
            raise ValueError(f"Companion with npc_id '{npc_id}' already exists")

        companion = CompanionProfile(
            npc_id=npc_id,
            name=name,
            archetype=archetype,
            combat_style=combat_style,
            personality=personality,
            **kwargs
        )
        self._companions[npc_id] = companion
        return companion

    def get(self, npc_id: str) -> CompanionProfile | None:
        """
        Get a companion by NPC ID.

        Args:
            npc_id: The NPC ID to look up

        Returns:
            The companion profile if found, None otherwise
        """
        return self._companions.get(npc_id)

    def get_active(self) -> list[CompanionProfile]:
        """
        Get all companions currently active in the party.

        Returns:
            List of active companion profiles, ordered by NPC ID
        """
        return [
            companion
            for companion in self._companions.values()
            if companion.active
        ]

    def activate(self, npc_id: str) -> bool:
        """
        Add a companion to the active party.

        Args:
            npc_id: The NPC ID of the companion to activate

        Returns:
            True if activated, False if companion not found
        """
        companion = self._companions.get(npc_id)
        if companion is None:
            return False
        companion.active = True
        return True

    def deactivate(self, npc_id: str) -> bool:
        """
        Remove a companion from the active party.

        The companion remains in the registry but is no longer active.

        Args:
            npc_id: The NPC ID of the companion to deactivate

        Returns:
            True if deactivated, False if companion not found
        """
        companion = self._companions.get(npc_id)
        if companion is None:
            return False
        companion.active = False
        return True

    def remove(self, npc_id: str) -> bool:
        """
        Permanently remove a companion from the registry.

        Args:
            npc_id: The NPC ID of the companion to remove

        Returns:
            True if removed, False if companion not found
        """
        if npc_id not in self._companions:
            return False
        del self._companions[npc_id]
        return True

    def adjust_loyalty(self, npc_id: str, delta: int, reason: str = "") -> int:
        """
        Adjust a companion's loyalty score.

        The loyalty score is clamped to [0, max_loyalty] to prevent overflow.

        Args:
            npc_id: The NPC ID of the companion
            delta: Amount to adjust loyalty (positive or negative)
            reason: Optional explanation for the adjustment (for audit/logging)

        Returns:
            The new loyalty score after adjustment

        Raises:
            ValueError: If companion not found
        """
        companion = self._companions.get(npc_id)
        if companion is None:
            raise ValueError(f"Companion with npc_id '{npc_id}' not found")

        new_loyalty = companion.loyalty_score + delta
        companion.loyalty_score = max(0, min(new_loyalty, companion.max_loyalty))

        # Reason is provided for future audit/logging features
        # For now, we just return the new value
        return companion.loyalty_score

    def check_loyalty_threshold(self, npc_id: str, required: int) -> bool:
        """
        Check if a companion's loyalty meets a threshold.

        Useful for determining if a companion will follow dangerous orders or
        perform certain actions.

        Loyalty thresholds guide:
        - 0-20: May abandon party
        - 21-40: Reluctant
        - 41-60: Cooperative
        - 61-80: Loyal
        - 81-100: Devoted

        Args:
            npc_id: The NPC ID of the companion
            required: Minimum loyalty required

        Returns:
            True if loyalty >= required, False otherwise

        Raises:
            ValueError: If companion not found
        """
        companion = self._companions.get(npc_id)
        if companion is None:
            raise ValueError(f"Companion with npc_id '{npc_id}' not found")

        return companion.loyalty_score >= required

    def save_state(self) -> dict:
        """
        Serialize all companions for campaign persistence.

        Returns:
            Dictionary mapping npc_id to serialized companion data
        """
        return {
            npc_id: companion.model_dump()
            for npc_id, companion in self._companions.items()
        }

    def load_state(self, data: dict) -> None:
        """
        Restore companions from saved campaign data.

        Args:
            data: Dictionary from save_state() containing companion data
        """
        self._companions.clear()
        for npc_id, companion_data in data.items():
            self._companions[npc_id] = CompanionProfile(**companion_data)


__all__ = [
    "CombatStyle",
    "CompanionArchetype",
    "PersonalityTraits",
    "CompanionProfile",
    "CompanionManager",
    "ARCHETYPE_TEMPLATES",
]
