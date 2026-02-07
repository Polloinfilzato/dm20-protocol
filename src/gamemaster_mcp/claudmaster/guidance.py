"""
Player Guidance System for AI Companions in Claudmaster.

This module implements natural language command parsing for player guidance to AI companions,
allowing players to give tactical instructions during combat (e.g., "stay back", "focus on
the healer", "protect Gandalf", "be aggressive").

The guidance system parses commands into structured guidance that modifies companion behavior
in the TacticsEngine. Guidance can be temporary (N rounds) or permanent (until cleared).

Key Components:
- GuidanceParser: Parses natural language commands into ParsedGuidance
- CompanionGuidance: Manages active guidance for a single companion
- GuidanceManager: Manages guidance across combat rounds for all companions

Example:
    >>> manager = GuidanceManager()
    >>> guidance, ack = manager.apply_guidance("companion_1", "stay back and heal")
    >>> print(ack)  # "Got it, moving back."
    >>> active = manager.get_active_guidance("companion_1")
    >>> manager.tick_round()  # Expire temporary guidance
"""

import re
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class GuidanceType(str, Enum):
    """Types of tactical guidance that can be given to companions."""
    POSITIONING = "positioning"
    TARGET_FOCUS = "target_focus"
    TARGET_AVOID = "target_avoid"
    ABILITY_USE = "ability_use"
    PROTECTION = "protection"
    AGGRESSION = "aggression"
    GENERAL = "general"


class ParsedGuidance(BaseModel):
    """Structured representation of a parsed guidance command."""
    guidance_type: GuidanceType
    target: Optional[str] = None
    modifier: Optional[str] = None
    priority: int = Field(default=1, ge=1, le=10)
    duration: Optional[int] = Field(default=None, ge=1, description="Rounds, None=permanent")


class CompanionGuidance(BaseModel):
    """Manages active guidance for a single companion."""
    companion_id: str
    active_guidance: list[ParsedGuidance] = Field(default_factory=list)

    def add_guidance(self, guidance: ParsedGuidance) -> None:
        """Add guidance, replacing conflicting guidance of same type."""
        # Remove existing guidance of same type
        self.active_guidance = [
            g for g in self.active_guidance if g.guidance_type != guidance.guidance_type
        ]
        self.active_guidance.append(guidance)

    def clear_guidance(self, guidance_type: Optional[GuidanceType] = None) -> int:
        """Clear guidance. Returns count removed."""
        if guidance_type is None:
            count = len(self.active_guidance)
            self.active_guidance = []
            return count
        before = len(self.active_guidance)
        self.active_guidance = [
            g for g in self.active_guidance if g.guidance_type != guidance_type
        ]
        return before - len(self.active_guidance)

    def get_by_type(self, guidance_type: GuidanceType) -> Optional[ParsedGuidance]:
        """Get active guidance of a specific type."""
        for g in self.active_guidance:
            if g.guidance_type == guidance_type:
                return g
        return None


# Pattern definitions: (regex, modifier)
POSITIONING_PATTERNS: list[tuple[str, str]] = [
    (r"stay\s+(back|behind)", "back"),
    (r"(?:go|move|get)\s+(?:to\s+the\s+)?(front|forward)", "front"),
    (r"flank", "flank"),
    (r"stay\s+(close|near)", "close"),
    (r"(?:go|move)\s+(?:to\s+the\s+)?(middle|center|mid)", "middle"),
]

TARGET_FOCUS_PATTERNS: list[str] = [
    r"(?:focus|target|attack|kill)\s+(?:on\s+)?(?:the\s+)?(.+)",
]

TARGET_AVOID_PATTERNS: list[str] = [
    r"(?:ignore|avoid|don'?t\s+attack)\s+(?:the\s+)?(.+)",
]

PROTECTION_PATTERNS: list[str] = [
    r"protect\s+(?:the\s+)?(.+)",
    r"guard\s+(?:the\s+)?(.+)",
    r"keep\s+(.+?)\s+safe",
    r"defend\s+(?:the\s+)?(.+)",
]

ABILITY_PATTERNS: list[tuple[str, str]] = [
    (r"(?:use|cast)\s+(?:only\s+)?healing(?:\s+spells)?", "healing_only"),
    (r"save\s+(?:your\s+)?(?:big\s+)?(?:spells|attacks|abilities)", "conserve"),
    (r"(?:use|go)\s+(?:all\s+out|nova)", "nova"),
    (r"(?:use|cast)\s+(?:only\s+)?(?:ranged|range)", "ranged_only"),
    (r"(?:use|cast)\s+(?:only\s+)?(?:melee)", "melee_only"),
]

AGGRESSION_PATTERNS: list[tuple[str, str]] = [
    (r"(?:be|go)\s+aggressive", "aggressive"),
    (r"play\s+(?:it\s+)?safe", "safe"),
    (r"(?:be|stay)\s+(?:cautious|careful)", "cautious"),
    (r"(?:be|go)\s+(?:reckless|bold)", "reckless"),
]

GENERAL_PATTERNS: list[tuple[str, str]] = [
    (r"do\s+your\s+(?:thing|best)", "autonomous"),
    (r"follow\s+my\s+lead", "follow"),
    (r"(?:as\s+you\s+wish|do\s+as\s+I\s+say)", "obedient"),
]

# Acknowledgment templates
ACKNOWLEDGMENTS: dict[GuidanceType, list[str]] = {
    GuidanceType.POSITIONING: [
        "Got it, moving {modifier}.",
        "Repositioning {modifier}.",
    ],
    GuidanceType.TARGET_FOCUS: [
        "Focusing on {target}.",
        "I'll target {target}.",
    ],
    GuidanceType.TARGET_AVOID: [
        "I'll avoid {target}.",
        "Ignoring {target}.",
    ],
    GuidanceType.PROTECTION: [
        "I'll protect {target}.",
        "Guarding {target}.",
    ],
    GuidanceType.ABILITY_USE: [
        "Understood, {modifier}.",
        "Adjusting my approach: {modifier}.",
    ],
    GuidanceType.AGGRESSION: [
        "Going {modifier}.",
        "Adjusting aggression: {modifier}.",
    ],
    GuidanceType.GENERAL: [
        "Understood.",
        "As you wish.",
    ],
}


class GuidanceParser:
    """Parses natural language commands into tactical guidance."""

    def parse(self, command: str) -> Optional[ParsedGuidance]:
        """Parse a natural language command into guidance."""
        cmd = command.strip()
        if not cmd:
            return None

        # Check positioning patterns
        for pattern, modifier in POSITIONING_PATTERNS:
            match = re.search(pattern, cmd, re.IGNORECASE)
            if match:
                return ParsedGuidance(
                    guidance_type=GuidanceType.POSITIONING,
                    modifier=modifier,
                )

        # Check protection patterns (before target focus to avoid "protect X" matching as "target X")
        for pattern in PROTECTION_PATTERNS:
            match = re.search(pattern, cmd, re.IGNORECASE)
            if match:
                return ParsedGuidance(
                    guidance_type=GuidanceType.PROTECTION,
                    target=match.group(1).strip(),
                )

        # Check target avoid patterns (before focus)
        for pattern in TARGET_AVOID_PATTERNS:
            match = re.search(pattern, cmd, re.IGNORECASE)
            if match:
                return ParsedGuidance(
                    guidance_type=GuidanceType.TARGET_AVOID,
                    target=match.group(1).strip(),
                )

        # Check target focus patterns
        for pattern in TARGET_FOCUS_PATTERNS:
            match = re.search(pattern, cmd, re.IGNORECASE)
            if match:
                return ParsedGuidance(
                    guidance_type=GuidanceType.TARGET_FOCUS,
                    target=match.group(1).strip(),
                )

        # Check ability patterns
        for pattern, modifier in ABILITY_PATTERNS:
            match = re.search(pattern, cmd, re.IGNORECASE)
            if match:
                return ParsedGuidance(
                    guidance_type=GuidanceType.ABILITY_USE,
                    modifier=modifier,
                )

        # Check aggression patterns
        for pattern, modifier in AGGRESSION_PATTERNS:
            match = re.search(pattern, cmd, re.IGNORECASE)
            if match:
                return ParsedGuidance(
                    guidance_type=GuidanceType.AGGRESSION,
                    modifier=modifier,
                )

        # Check general patterns
        for pattern, modifier in GENERAL_PATTERNS:
            match = re.search(pattern, cmd, re.IGNORECASE)
            if match:
                return ParsedGuidance(
                    guidance_type=GuidanceType.GENERAL,
                    modifier=modifier,
                )

        return None

    def get_acknowledgment(self, guidance: ParsedGuidance) -> str:
        """Generate companion acknowledgment text for guidance."""
        templates = ACKNOWLEDGMENTS.get(guidance.guidance_type, ["Understood."])
        template = templates[0]  # Use first template for determinism
        return template.format(
            target=guidance.target or "target",
            modifier=guidance.modifier or "acknowledged",
        )


class GuidanceManager:
    """Manages guidance across combat rounds for all companions."""

    def __init__(self):
        self._companions: dict[str, CompanionGuidance] = {}
        self._parser = GuidanceParser()

    def _ensure_companion(self, companion_id: str) -> CompanionGuidance:
        if companion_id not in self._companions:
            self._companions[companion_id] = CompanionGuidance(companion_id=companion_id)
        return self._companions[companion_id]

    def apply_guidance(self, companion_id: str, command: str) -> tuple[Optional[ParsedGuidance], str]:
        """Apply guidance from command. Returns (guidance, acknowledgment)."""
        guidance = self._parser.parse(command)
        if guidance is None:
            return (None, "I don't understand that command.")

        companion = self._ensure_companion(companion_id)
        companion.add_guidance(guidance)
        ack = self._parser.get_acknowledgment(guidance)
        return (guidance, ack)

    def get_active_guidance(self, companion_id: str) -> list[ParsedGuidance]:
        """Get all active guidance for a companion."""
        if companion_id not in self._companions:
            return []
        return self._companions[companion_id].active_guidance

    def tick_round(self) -> None:
        """Advance round counters, expire temporary guidance."""
        for companion in self._companions.values():
            remaining = []
            for g in companion.active_guidance:
                if g.duration is not None:
                    g.duration -= 1
                    if g.duration <= 0:
                        continue
                remaining.append(g)
            companion.active_guidance = remaining

    def reset_combat_end(self) -> None:
        """Clear all combat-specific guidance."""
        self._companions.clear()

    def clear_companion(self, companion_id: str, guidance_type: Optional[GuidanceType] = None) -> int:
        """Clear guidance for a companion. Returns count cleared."""
        if companion_id not in self._companions:
            return 0
        return self._companions[companion_id].clear_guidance(guidance_type)

    @property
    def companion_count(self) -> int:
        """Get the number of companions with active guidance."""
        return len(self._companions)


__all__ = [
    "GuidanceType",
    "ParsedGuidance",
    "CompanionGuidance",
    "GuidanceParser",
    "GuidanceManager",
    "ACKNOWLEDGMENTS",
]
