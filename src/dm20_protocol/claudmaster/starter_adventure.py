"""
Built-in starter adventure content for the onboarding flow.

Provides a self-contained tutorial adventure: The Yawning Portal tavern in
Waterdeep, with 2 NPCs and a goblin ambush encounter. Teaches exploration,
dialogue, and combat in a single compact scenario.
"""

from dm20_protocol.models import Location, NPC, Quest, CombatEncounter


# ============================================================================
# Location
# ============================================================================

STARTER_LOCATION = Location(
    id="starter-yawning-portal",
    name="The Yawning Portal",
    location_type="tavern",
    description=(
        "A sprawling, lantern-lit tavern built around a gaping well that "
        "descends into Undermountain — the most infamous dungeon beneath "
        "Waterdeep. The common room is warm with hearth-smoke, crowded with "
        "adventurers swapping tales over tankards of ale. Trophies from past "
        "expeditions line the walls: a rusted shield, a mounted owlbear head, "
        "a cracked crystal orb that glows faintly. The well in the center is "
        "ringed by a low stone wall, and occasionally a cold draft rises from "
        "its depths, carrying the faint echo of something stirring far below."
    ),
    notable_features=[
        "The Well of Undermountain — a 140-foot shaft descending into darkness, "
        "with a pulley system for lowering adventurers",
        "A notice board near the entrance covered in job postings, wanted posters, "
        "and a half-torn treasure map",
        "A private alcove in the back with a curtain — currently occupied by "
        "a hooded figure nursing a single drink",
    ],
    npcs=["Durnan", "Viari"],
    connections=["Castle Ward", "Dock Ward", "Undermountain Entrance"],
)


# ============================================================================
# NPCs
# ============================================================================

STARTER_NPC_DURNAN = NPC(
    id="starter-durnan",
    name="Durnan",
    description=(
        "A broad-shouldered, grey-haired human in his late fifties with "
        "forearms like knotted oak. His face is weathered and scarred, but "
        "his eyes are sharp and miss nothing. He moves behind the bar with "
        "the quiet efficiency of someone who has fought dragons and poured "
        "ale in equal measure."
    ),
    bio=(
        "Durnan is the legendary owner of The Yawning Portal, and a retired "
        "adventurer who once delved deep into Undermountain and returned with "
        "enough treasure to buy the tavern. He speaks little of his past but "
        "knows more about the dungeon below than anyone alive. He is protective "
        "of inexperienced adventurers and will offer practical advice — but "
        "never coddling. He has heard rumors of goblins raiding caravans on "
        "the road north and is looking for someone capable to investigate."
    ),
    race="Human",
    occupation="Tavern Owner / Retired Adventurer",
    location="The Yawning Portal",
    attitude="friendly",
    notes="Quest giver. Knows about the goblin ambush on the Triboar Trail.",
    relationships={"Viari": "Regular patron, trusted acquaintance"},
)

STARTER_NPC_VIARI = NPC(
    id="starter-viari",
    name="Viari",
    description=(
        "A lean half-elf with dark hair and quick, restless eyes. He wears "
        "a travel-stained cloak and keeps one hand near the hilt of a rapier. "
        "A faded tattoo of a compass rose peeks from beneath his collar. He "
        "sits alone in the back alcove, watching the room with the wary "
        "alertness of someone expecting trouble."
    ),
    bio=(
        "Viari is a wandering scout and information broker who trades in "
        "rumors and maps. He recently returned from the Triboar Trail where "
        "he narrowly escaped a goblin ambush. He carries a bloodied map "
        "showing the location of the goblin hideout and will share it — for "
        "a price, or for a promise of a share in whatever treasure is found. "
        "He is charming but evasive about his own past."
    ),
    race="Half-Elf",
    occupation="Scout / Information Broker",
    location="The Yawning Portal",
    attitude="neutral",
    notes="Combat trigger. Has the map to the goblin hideout. Can be convinced to share it.",
    relationships={"Durnan": "Occasional informant, respectful distance"},
)


# ============================================================================
# Quest
# ============================================================================

STARTER_QUEST = Quest(
    id="starter-goblin-trail",
    title="Trouble on the Triboar Trail",
    description=(
        "Goblins have been ambushing travelers on the road north of Waterdeep. "
        "Durnan, the tavern owner, has asked you to investigate and put a stop "
        "to the raids. A half-elf scout named Viari has a map showing where "
        "the goblins are hiding."
    ),
    giver="Durnan",
    status="active",
    objectives=[
        "Speak with Durnan about the goblin problem",
        "Find the scout Viari and obtain the map",
        "Travel to the Triboar Trail and locate the ambush site",
        "Defeat the goblins or find another solution",
    ],
    reward="50 gold pieces and Durnan's gratitude",
)


# ============================================================================
# Encounter
# ============================================================================

STARTER_ENCOUNTER = CombatEncounter(
    id="starter-goblin-ambush",
    name="Goblin Ambush on the Triboar Trail",
    description=(
        "A narrow section of the Triboar Trail where the road winds between "
        "dense undergrowth and a rocky outcrop. Perfect ambush territory. "
        "Three goblins hide in the bushes, waiting for travelers. A crude "
        "rope trap is stretched across the path."
    ),
    enemies=["Goblin x3"],
    difficulty="easy",
    experience_value=150,
    location="Triboar Trail",
    status="planned",
    notes=(
        "Tutorial encounter. Goblins use hit-and-run tactics: one shoots "
        "arrows from the rocks while two charge with scimitars. If reduced "
        "to 1 goblin, the survivor tries to flee toward the hideout. Players "
        "can also try stealth, diplomacy, or intimidation to resolve without "
        "full combat."
    ),
)


# ============================================================================
# Loader
# ============================================================================

def populate_campaign_with_starter_content(campaign) -> None:
    """Add starter adventure content to a newly created campaign.

    Populates the campaign with The Yawning Portal location, 2 NPCs,
    a starter quest, and a goblin encounter. Sets the starting location.

    Args:
        campaign: A Campaign model instance to populate.
    """
    # Add location
    campaign.locations[STARTER_LOCATION.id] = STARTER_LOCATION

    # Add NPCs
    campaign.npcs[STARTER_NPC_DURNAN.id] = STARTER_NPC_DURNAN
    campaign.npcs[STARTER_NPC_VIARI.id] = STARTER_NPC_VIARI

    # Add quest
    campaign.quests[STARTER_QUEST.id] = STARTER_QUEST

    # Add encounter
    campaign.encounters[STARTER_ENCOUNTER.id] = STARTER_ENCOUNTER

    # Set starting location
    campaign.game_state.current_location = STARTER_LOCATION.name


__all__ = [
    "STARTER_LOCATION",
    "STARTER_NPC_DURNAN",
    "STARTER_NPC_VIARI",
    "STARTER_QUEST",
    "STARTER_ENCOUNTER",
    "populate_campaign_with_starter_content",
]
