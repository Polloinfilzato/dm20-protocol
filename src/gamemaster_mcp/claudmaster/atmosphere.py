"""
Scene Atmosphere and Pacing system for Claudmaster.

Manages tone detection, pacing adjustment, tension building, and smooth
transitions between different atmospheric states during gameplay.
"""

import logging
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field

logger = logging.getLogger("gamemaster-mcp")


# ------------------------------------------------------------------
# Protocol for LLM client
# ------------------------------------------------------------------

class LLMClient(Protocol):
    """Protocol for LLM interaction, enabling easy mocking in tests."""

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """Generate text from a prompt.

        Args:
            prompt: The full prompt to send to the LLM.
            max_tokens: Maximum tokens in the response.

        Returns:
            The generated text.
        """
        ...


# ------------------------------------------------------------------
# Enumerations
# ------------------------------------------------------------------

class Tone(str, Enum):
    """Atmospheric tones for narrative scenes."""
    NEUTRAL = "neutral"
    HEROIC = "heroic"
    HORROR = "horror"
    MYSTERIOUS = "mysterious"
    COMEDIC = "comedic"
    TRAGIC = "tragic"
    TENSE = "tense"
    PEACEFUL = "peaceful"
    OMINOUS = "ominous"
    TRIUMPHANT = "triumphant"
    DESPERATE = "desperate"
    WONDER = "wonder"


class Pacing(str, Enum):
    """Narrative pacing speeds."""
    SLOW = "slow"
    NORMAL = "normal"
    FAST = "fast"
    FRANTIC = "frantic"
    DELIBERATE = "deliberate"


class SceneType(str, Enum):
    """Types of game scenes."""
    COMBAT = "combat"
    EXPLORATION = "exploration"
    SOCIAL = "social"
    PUZZLE = "puzzle"
    REST = "rest"
    TRANSITION = "transition"


# ------------------------------------------------------------------
# Configuration dictionaries
# ------------------------------------------------------------------

TONE_INDICATORS: dict[Tone, dict[str, list[str]]] = {
    Tone.HORROR: {
        "keywords": ["dark", "creeping", "dread", "undead", "corruption", "shadow", "blood", "decay", "rot", "scream", "fear", "terror"],
        "creature_types": ["undead", "aberration", "fiend", "zombie", "skeleton", "vampire", "ghost"],
        "environment": ["dungeon", "crypt", "swamp", "ruins", "cave", "tomb", "graveyard", "abandoned"],
    },
    Tone.HEROIC: {
        "keywords": ["glory", "honor", "battle", "champion", "brave", "valor", "courage", "legendary", "epic", "triumph"],
        "creature_types": ["dragon", "giant", "titan"],
        "environment": ["battlefield", "castle", "arena", "throne", "fortress", "mountain peak"],
    },
    Tone.MYSTERIOUS: {
        "keywords": ["strange", "arcane", "mysterious", "enigmatic", "puzzle", "riddle", "ancient", "hidden", "secret", "unknown"],
        "creature_types": ["fey", "aberration", "construct"],
        "environment": ["ruins", "library", "temple", "shrine", "labyrinth", "ancient"],
    },
    Tone.PEACEFUL: {
        "keywords": ["calm", "serene", "gentle", "quiet", "tranquil", "peaceful", "rest", "safe", "haven", "sanctuary"],
        "creature_types": ["beast", "fey"],
        "environment": ["village", "inn", "meadow", "grove", "garden", "sanctuary", "temple"],
    },
    Tone.OMINOUS: {
        "keywords": ["foreboding", "threatening", "dark", "ominous", "warning", "danger", "lurking", "watching", "approaching"],
        "creature_types": ["fiend", "undead", "aberration", "demon"],
        "environment": ["ruins", "cave", "forest", "mist", "fog", "swamp", "abandoned"],
    },
    Tone.TRIUMPHANT: {
        "keywords": ["victory", "triumph", "success", "celebration", "glory", "achievement", "conquered", "defeated"],
        "creature_types": [],
        "environment": ["throne room", "hall", "arena", "battlefield"],
    },
    Tone.TENSE: {
        "keywords": ["danger", "threat", "ambush", "trap", "stalking", "pursued", "hunted", "countdown", "ticking"],
        "creature_types": ["predator", "assassin", "hunter"],
        "environment": ["narrow passage", "ambush point", "trapped", "surrounded"],
    },
    Tone.DESPERATE: {
        "keywords": ["desperate", "hopeless", "dire", "last stand", "fleeing", "overwhelmed", "outnumbered", "dying"],
        "creature_types": ["horde", "swarm"],
        "environment": ["collapsing", "burning", "sinking", "surrounded"],
    },
    Tone.WONDER: {
        "keywords": ["wonder", "awe", "magnificent", "beautiful", "breathtaking", "magical", "ethereal", "celestial", "majestic"],
        "creature_types": ["celestial", "fey", "elemental"],
        "environment": ["palace", "garden", "crystal", "floating", "skybound", "paradise"],
    },
    Tone.COMEDIC: {
        "keywords": ["funny", "absurd", "ridiculous", "bumbling", "chaotic", "slapstick", "silly", "mishap"],
        "creature_types": ["goblin", "kobold"],
        "environment": ["tavern", "market", "fair"],
    },
    Tone.TRAGIC: {
        "keywords": ["tragic", "sorrow", "loss", "grief", "mourning", "fallen", "sacrifice", "betrayal", "ruins"],
        "creature_types": [],
        "environment": ["ruins", "graveyard", "battlefield", "memorial"],
    },
}


PACING_BY_SCENE: dict[SceneType, Pacing] = {
    SceneType.COMBAT: Pacing.FAST,
    SceneType.EXPLORATION: Pacing.DELIBERATE,
    SceneType.SOCIAL: Pacing.NORMAL,
    SceneType.PUZZLE: Pacing.SLOW,
    SceneType.REST: Pacing.SLOW,
    SceneType.TRANSITION: Pacing.NORMAL,
}


TONE_MODIFIERS: dict[Tone, dict[str, Any]] = {
    Tone.HORROR: {
        "verbs": ["creeps", "lurks", "slithers", "whispers", "echoes", "drips"],
        "adjectives": ["cold", "damp", "rotting", "unseen", "shadowy", "putrid"],
        "sentence_style": "short, punchy sentences building dread",
        "sensory_focus": ["sound", "smell", "touch"],
    },
    Tone.HEROIC: {
        "verbs": ["charges", "stands", "rallies", "strikes", "commands", "blazes"],
        "adjectives": ["gleaming", "mighty", "towering", "unyielding", "radiant"],
        "sentence_style": "bold, sweeping sentences with action",
        "sensory_focus": ["sight", "sound"],
    },
    Tone.MYSTERIOUS: {
        "verbs": ["shifts", "shimmers", "conceals", "beckons", "hints", "eludes"],
        "adjectives": ["arcane", "cryptic", "enigmatic", "veiled", "strange"],
        "sentence_style": "layered, questioning sentences",
        "sensory_focus": ["sight", "intuition"],
    },
    Tone.PEACEFUL: {
        "verbs": ["flows", "drifts", "settles", "soothes", "rests", "breathes"],
        "adjectives": ["gentle", "warm", "soft", "calm", "tranquil"],
        "sentence_style": "flowing, relaxed sentences",
        "sensory_focus": ["sound", "touch", "smell"],
    },
    Tone.OMINOUS: {
        "verbs": ["looms", "gathers", "darkens", "threatens", "watches", "waits"],
        "adjectives": ["dark", "heavy", "oppressive", "silent", "watchful"],
        "sentence_style": "building, foreboding sentences",
        "sensory_focus": ["sight", "sound", "intuition"],
    },
    Tone.TRIUMPHANT: {
        "verbs": ["rings", "soars", "celebrates", "proclaims", "shines"],
        "adjectives": ["glorious", "victorious", "jubilant", "shining", "exultant"],
        "sentence_style": "sweeping, celebratory sentences",
        "sensory_focus": ["sight", "sound"],
    },
    Tone.TENSE: {
        "verbs": ["waits", "tightens", "poises", "holds", "watches", "readies"],
        "adjectives": ["taut", "coiled", "ready", "electric", "breathless"],
        "sentence_style": "terse, tight sentences",
        "sensory_focus": ["sound", "touch", "sight"],
    },
}


# ------------------------------------------------------------------
# LLM Prompts
# ------------------------------------------------------------------

ATMOSPHERE_PROMPT = """\
You are enhancing a D&D narrative with atmospheric tone.

Current tone: {tone}
Intensity level: {intensity:.1f} (0.0 = subtle, 1.0 = extreme)
Application strength: {intensity_description}

Original narrative:
{narrative}

Rewrite the narrative to emphasize the {tone} tone. Use the following guidance:
- Verbs: {verbs}
- Adjectives: {adjectives}
- Sentence style: {sentence_style}
- Focus on these senses: {sensory_focus}

Keep the same events and information, but adjust the language, rhythm, and sensory \
details to match the tone at the specified intensity level.

Enhanced narrative:"""

TENSION_PROMPT = """\
You are building tension in a D&D scene.

Target tension level: {target_level:.1f} (0.0 = calm, 1.0 = maximum tension)

Current description:
{description}

Add tension-building elements to increase the sense of danger, urgency, or unease. \
Depending on the target level:
- Low (< 0.3): Subtle hints, distant sounds, minor oddities
- Medium (0.3-0.6): Clear warnings, growing threats, time pressure
- High (0.6-0.9): Immediate danger, countdown elements, escalating threats
- Maximum (0.9+): Life-or-death urgency, overwhelming odds, desperate situation

Enhanced description with tension level {target_level:.1f}:"""

TRANSITION_PROMPT = """\
You are smoothly transitioning between two atmospheric tones in a D&D narrative.

From: {from_tone}
To: {to_tone}
Trigger: {trigger}

Generate a brief narrative passage (2-4 sentences) that smoothly transitions \
from the {from_tone} atmosphere to the {to_tone} atmosphere. The transition \
should feel natural and be triggered by: {trigger}

Use sensory details and pacing to bridge the tonal shift.

Transition passage:"""


# ------------------------------------------------------------------
# Data models
# ------------------------------------------------------------------

class TensionState(BaseModel):
    """Tracks tension buildup and release."""
    level: float = 0.5  # 0.0 to 1.0
    build_rate: float = 0.1
    release_rate: float = 0.15
    peak_threshold: float = 0.9


class SceneContext(BaseModel):
    """Context information for a scene."""
    scene_type: SceneType = SceneType.EXPLORATION
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    creature_types: list[str] = Field(default_factory=list)
    environment: str = ""
    time_of_day: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------------
# AtmosphereManager
# ------------------------------------------------------------------

class AtmosphereManager:
    """Manages scene atmosphere, tone, pacing, and tension.

    Detects appropriate tones based on scene context, adjusts narrative
    pacing, builds tension, and handles smooth transitions between tones.

    Args:
        llm: An object implementing the LLMClient protocol.
        max_tokens: Maximum tokens for LLM responses.
    """

    def __init__(self, llm: LLMClient, max_tokens: int = 512) -> None:
        self.llm = llm
        self.max_tokens = max_tokens
        self.current_tone: Tone = Tone.NEUTRAL
        self.tension = TensionState()
        self.pacing: Pacing = Pacing.NORMAL

    def detect_tone(self, scene: SceneContext) -> Tone:
        """Detect the appropriate tone for a scene based on context.

        Analyzes keywords, creature types, and environment to score each
        potential tone. Returns the highest scoring tone, or NEUTRAL if
        no strong match is found.

        Args:
            scene: The scene context to analyze.

        Returns:
            The detected tone.
        """
        # Normalize inputs for matching
        scene_keywords = {kw.lower() for kw in scene.keywords}
        scene_creatures = {ct.lower() for ct in scene.creature_types}
        scene_env = scene.environment.lower()
        scene_desc = scene.description.lower()

        # Score each tone
        tone_scores: dict[Tone, int] = {}

        for tone, indicators in TONE_INDICATORS.items():
            score = 0

            # Score keyword matches
            for keyword in indicators["keywords"]:
                if keyword in scene_keywords:
                    score += 3
                # Also check in description for partial matches
                if keyword in scene_desc:
                    score += 1

            # Score creature type matches
            for creature_type in indicators["creature_types"]:
                if creature_type in scene_creatures:
                    score += 4

            # Score environment matches
            for env in indicators["environment"]:
                if env in scene_env:
                    score += 3
                if env in scene_desc:
                    score += 1

            tone_scores[tone] = score

        # Find the highest scoring tone
        if not tone_scores:
            return Tone.NEUTRAL

        max_score = max(tone_scores.values())

        # Require a minimum score to override NEUTRAL
        if max_score < 3:
            return Tone.NEUTRAL

        # Return the highest scoring tone
        for tone, score in tone_scores.items():
            if score == max_score:
                return tone

        return Tone.NEUTRAL

    def get_pacing(self, scene_type: SceneType) -> Pacing:
        """Get the appropriate pacing for a scene type.

        Args:
            scene_type: The type of scene.

        Returns:
            The recommended pacing.
        """
        return PACING_BY_SCENE.get(scene_type, Pacing.NORMAL)

    def update_tension(self, delta: float) -> float:
        """Update tension level by a delta value.

        Args:
            delta: Amount to change tension (positive or negative).

        Returns:
            The new tension level (clamped to [0.0, 1.0]).
        """
        self.tension.level = max(0.0, min(1.0, self.tension.level + delta))
        return self.tension.level

    def get_tone_modifiers(self, tone: Tone) -> dict[str, Any]:
        """Get the tone modifiers for a specific tone.

        Args:
            tone: The tone to get modifiers for.

        Returns:
            Dictionary of modifiers (verbs, adjectives, etc.) or empty dict.
        """
        return TONE_MODIFIERS.get(tone, {})

    async def apply_atmosphere(self, narrative: str, tone: Tone, intensity: float = 0.5) -> str:
        """Apply atmospheric tone to a narrative using the LLM.

        Args:
            narrative: The original narrative text.
            tone: The tone to apply.
            intensity: How strongly to apply the tone (0.0 to 1.0).

        Returns:
            The enhanced narrative with applied tone.
        """
        # Clamp intensity
        intensity = max(0.0, min(1.0, intensity))

        # Determine intensity description
        if intensity > 0.7:
            intensity_description = "very strongly"
        elif intensity > 0.4:
            intensity_description = "moderately"
        else:
            intensity_description = "subtly"

        # Get tone modifiers
        modifiers = self.get_tone_modifiers(tone)

        # Fallback if no modifiers defined for this tone
        if not modifiers:
            modifiers = {
                "verbs": ["moves", "acts", "exists"],
                "adjectives": ["present", "visible", "notable"],
                "sentence_style": "clear, descriptive sentences",
                "sensory_focus": ["sight"],
            }

        # Build prompt
        verbs_str = ", ".join(modifiers.get("verbs", []))
        adjectives_str = ", ".join(modifiers.get("adjectives", []))
        sentence_style = modifiers.get("sentence_style", "descriptive")
        sensory_focus = ", ".join(modifiers.get("sensory_focus", ["sight"]))

        prompt = ATMOSPHERE_PROMPT.format(
            tone=tone.value,
            intensity=intensity,
            intensity_description=intensity_description,
            narrative=narrative,
            verbs=verbs_str,
            adjectives=adjectives_str,
            sentence_style=sentence_style,
            sensory_focus=sensory_focus,
        )

        # Generate enhanced narrative
        response = await self.llm.generate(prompt, max_tokens=self.max_tokens)
        return response.strip()

    async def build_tension(self, description: str, target_level: float) -> str:
        """Add tension-building elements to a description.

        Args:
            description: The original description.
            target_level: The desired tension level (0.0 to 1.0).

        Returns:
            Enhanced description with tension-building elements.
        """
        # Clamp target level
        target_level = max(0.0, min(1.0, target_level))

        # Build prompt
        prompt = TENSION_PROMPT.format(
            target_level=target_level,
            description=description,
        )

        # Generate tension-enhanced description
        response = await self.llm.generate(prompt, max_tokens=self.max_tokens)
        return response.strip()

    async def transition_tone(self, from_tone: Tone, to_tone: Tone, trigger: str) -> str:
        """Generate a smooth transition passage between two tones.

        Args:
            from_tone: The starting tone.
            to_tone: The ending tone.
            trigger: The event or action that triggers the transition.

        Returns:
            A narrative passage smoothly transitioning between tones.
        """
        # Build prompt
        prompt = TRANSITION_PROMPT.format(
            from_tone=from_tone.value,
            to_tone=to_tone.value,
            trigger=trigger,
        )

        # Generate transition
        response = await self.llm.generate(prompt, max_tokens=self.max_tokens)
        return response.strip()

    def set_scene(self, scene: SceneContext) -> tuple[Tone, Pacing]:
        """Set the scene and update internal atmosphere state.

        Convenience method that detects tone, sets pacing, and updates
        internal state all at once.

        Args:
            scene: The scene context.

        Returns:
            Tuple of (detected tone, recommended pacing).
        """
        # Detect and set tone
        self.current_tone = self.detect_tone(scene)

        # Set pacing
        self.pacing = self.get_pacing(scene.scene_type)

        return (self.current_tone, self.pacing)


__all__ = [
    "LLMClient",
    "Tone",
    "Pacing",
    "SceneType",
    "TONE_INDICATORS",
    "PACING_BY_SCENE",
    "TONE_MODIFIERS",
    "TensionState",
    "SceneContext",
    "AtmosphereManager",
]
