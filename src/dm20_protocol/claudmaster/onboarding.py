"""
Guided onboarding flow for new Claudmaster users.

Provides a first-session experience that detects new users (no existing
campaigns) and walks them through campaign creation, character setup
suggestions, and an engaging first scene — all within 5 minutes.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("dm20-protocol")


# ============================================================================
# Default Campaign Settings
# ============================================================================

DEFAULT_CAMPAIGN_NAME = "The Forgotten Realms"
DEFAULT_CAMPAIGN_DESCRIPTION = (
    "A classic Forgotten Realms adventure. The Sword Coast beckons "
    "with tales of ancient ruins, lurking dangers, and untold treasures."
)
DEFAULT_CAMPAIGN_SETTING = "Sword Coast, Forgotten Realms"
DEFAULT_DIFFICULTY = "balanced"


# ============================================================================
# Onboarding Prompt Templates
# ============================================================================

CHARACTER_SUGGESTIONS_TEMPLATE = """\
You are the Narrator of a D&D campaign, helping a brand-new player create their first character.

Generate a warm, in-character welcome followed by 3 character suggestions. Each suggestion should:
1. Have a name, race, and class
2. Include a one-sentence personality hook
3. Feel distinct and appealing to different play styles

Format exactly as:
---
*Welcome message (2-3 sentences, warm and inviting)*

**Choose your hero:**

1. **[Name]** — [Race] [Class]
   [Personality hook]

2. **[Name]** — [Race] [Class]
   [Personality hook]

3. **[Name]** — [Race] [Class]
   [Personality hook]

*Or describe your own character — any race, class, or concept you can imagine.*
---

Keep suggestions beginner-friendly (Fighter, Rogue, Cleric). Vary races (Human, Elf, Dwarf/Halfling).
"""

FIRST_SCENE_TEMPLATE = """\
You are the Narrator of a D&D campaign. Generate the opening scene for a new adventure.

Character: {character_name}, a level 1 {character_class} ({character_race})
Setting: The Sword Coast, Forgotten Realms
Location: A cozy tavern called The Yawning Portal in Waterdeep

Generate an atmospheric opening (2-3 paragraphs) that:
1. Sets the scene with vivid sensory details
2. Introduces the character in the environment
3. Presents a hook — something interesting happening that invites interaction
4. Ends with an implicit prompt for the player to act

Write in second person ("You..."). Be vivid but concise (under 200 words).
"""


# ============================================================================
# Onboarding Data Models
# ============================================================================

@dataclass
class OnboardingState:
    """Tracks onboarding progress for resumability.

    Attributes:
        step: Current onboarding step.
        campaign_created: Whether the campaign was auto-created.
        character_created: Whether a character has been created.
        first_scene_delivered: Whether the first scene has been shown.
        campaign_name: Name of the created campaign.
    """
    step: str = "character_creation"  # character_creation, first_scene, complete
    campaign_created: bool = False
    character_created: bool = False
    first_scene_delivered: bool = False
    campaign_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "step": self.step,
            "campaign_created": self.campaign_created,
            "character_created": self.character_created,
            "first_scene_delivered": self.first_scene_delivered,
            "campaign_name": self.campaign_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OnboardingState":
        """Deserialize from a dictionary."""
        return cls(
            step=data.get("step", "character_creation"),
            campaign_created=data.get("campaign_created", False),
            character_created=data.get("character_created", False),
            first_scene_delivered=data.get("first_scene_delivered", False),
            campaign_name=data.get("campaign_name", ""),
        )


@dataclass
class OnboardingResult:
    """Result of an onboarding step.

    Attributes:
        campaign_name: Name of the auto-created campaign.
        character_suggestions: Narrator-generated character options.
        first_scene: Opening scene text (populated after character creation).
        onboarding_state: Current onboarding state for persistence.
    """
    campaign_name: str = ""
    character_suggestions: str = ""
    first_scene: str = ""
    onboarding_state: OnboardingState = field(default_factory=OnboardingState)


# ============================================================================
# Onboarding Logic
# ============================================================================

def detect_new_user(storage: Any) -> bool:
    """Check if this is a new user with no existing campaigns.

    Args:
        storage: The DnDStorage instance.

    Returns:
        True if no campaigns exist (new user), False otherwise.
    """
    if storage is None:
        return False
    campaigns = storage.list_campaigns()
    return len(campaigns) == 0


async def run_onboarding(
    storage: Any,
    campaign_name: str,
    narrator: Any = None,
) -> OnboardingResult:
    """Execute the onboarding flow for a new user.

    Creates a campaign with sensible defaults and generates character
    suggestions through the Narrator agent.

    Args:
        storage: The DnDStorage instance for campaign creation.
        campaign_name: User-provided campaign name (or auto-generated).
        narrator: Optional NarratorAgent for generating suggestions.

    Returns:
        OnboardingResult with campaign name and character suggestions.
    """
    result = OnboardingResult()
    state = OnboardingState()

    # Step 1: Auto-create campaign
    effective_name = campaign_name.strip() if campaign_name.strip() else DEFAULT_CAMPAIGN_NAME
    try:
        storage.create_campaign(
            name=effective_name,
            description=DEFAULT_CAMPAIGN_DESCRIPTION,
        )
        state.campaign_created = True
        state.campaign_name = effective_name
        result.campaign_name = effective_name
        logger.info(f"[Onboarding] Auto-created campaign '{effective_name}'")
    except Exception as e:
        logger.error(f"[Onboarding] Failed to create campaign: {e}")
        raise

    # Step 2: Generate character suggestions via Narrator
    if narrator is not None:
        try:
            suggestions = await narrator.generate(
                CHARACTER_SUGGESTIONS_TEMPLATE, max_tokens=512
            )
            result.character_suggestions = suggestions.strip()
            logger.info("[Onboarding] Generated character suggestions via Narrator")
        except Exception as e:
            logger.warning(f"[Onboarding] Narrator failed, using fallback: {e}")
            result.character_suggestions = _fallback_character_suggestions()
    else:
        result.character_suggestions = _fallback_character_suggestions()

    # Update state
    state.step = "character_creation"
    result.onboarding_state = state

    return result


async def generate_first_scene(
    narrator: Any,
    character_name: str,
    character_class: str,
    character_race: str,
) -> str:
    """Generate the atmospheric first scene after character creation.

    Args:
        narrator: NarratorAgent for scene generation.
        character_name: The player character's name.
        character_class: The character's class.
        character_race: The character's race.

    Returns:
        First scene narrative text.
    """
    prompt = FIRST_SCENE_TEMPLATE.format(
        character_name=character_name,
        character_class=character_class,
        character_race=character_race,
    )
    try:
        scene = await narrator.generate(prompt, max_tokens=512)
        logger.info(f"[Onboarding] Generated first scene for {character_name}")
        return scene.strip()
    except Exception as e:
        logger.warning(f"[Onboarding] First scene generation failed: {e}")
        return _fallback_first_scene(character_name)


def _fallback_character_suggestions() -> str:
    """Static fallback when Narrator is unavailable."""
    return (
        "*The DM smiles warmly and spreads three character sheets across the table.*\n\n"
        "**Choose your hero:**\n\n"
        "1. **Torvin Ironforge** — Dwarf Fighter\n"
        "   A sturdy warrior who solves problems with steel and stubbornness.\n\n"
        "2. **Lyra Nightwhisper** — Elf Rogue\n"
        "   A quick-witted shadow who prefers cunning over brute force.\n\n"
        "3. **Brother Marcus** — Human Cleric\n"
        "   A devoted healer whose faith shields allies from harm.\n\n"
        "*Or describe your own character — any race, class, or concept you can imagine.*"
    )


def _fallback_first_scene(character_name: str) -> str:
    """Static fallback first scene."""
    return (
        f"The Yawning Portal tavern buzzes with the hum of conversation and "
        f"the clink of tankards. You, {character_name}, sit at a corner table, "
        f"nursing a drink and watching the infamous well in the center of the room — "
        f"the entrance to Undermountain, the legendary dungeon beneath Waterdeep.\n\n"
        f"A weathered adventurer stumbles through the door, clutching a bloodied map. "
        f"\"Someone... help,\" they gasp, collapsing at the nearest table. "
        f"The tavern falls silent. All eyes turn to you."
    )


__all__ = [
    "OnboardingState",
    "OnboardingResult",
    "detect_new_user",
    "run_onboarding",
    "generate_first_scene",
]
