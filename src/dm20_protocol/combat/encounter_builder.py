"""
Encounter Builder for D&D 5e.

Implements CR-based encounter building using the standard 5e encounter
building rules (DMG Chapter 3). Calculates XP budgets, selects monsters
from loaded rulebooks, applies group multipliers, and suggests balanced
encounter compositions.

The builder works in two modes:
- With loaded rulebooks: full encounter suggestions with monster selections
- Without rulebooks: XP budget and threshold calculations only
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("dm20-protocol.combat")


# =============================================================================
# Constants: XP Thresholds per Character Level (DMG p.82)
# =============================================================================

class Difficulty(str, Enum):
    """Encounter difficulty levels."""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    DEADLY = "deadly"


# XP thresholds per character level for each difficulty tier.
# Key: character level (1-20), Value: dict of difficulty -> XP threshold
XP_THRESHOLDS: dict[int, dict[str, int]] = {
    1:  {"easy": 25,   "medium": 50,   "hard": 75,    "deadly": 100},
    2:  {"easy": 50,   "medium": 100,  "hard": 150,   "deadly": 200},
    3:  {"easy": 75,   "medium": 150,  "hard": 225,   "deadly": 400},
    4:  {"easy": 125,  "medium": 250,  "hard": 375,   "deadly": 500},
    5:  {"easy": 250,  "medium": 500,  "hard": 750,   "deadly": 1100},
    6:  {"easy": 300,  "medium": 600,  "hard": 900,   "deadly": 1400},
    7:  {"easy": 350,  "medium": 750,  "hard": 1100,  "deadly": 1700},
    8:  {"easy": 450,  "medium": 900,  "hard": 1400,  "deadly": 2100},
    9:  {"easy": 550,  "medium": 1100, "hard": 1600,  "deadly": 2400},
    10: {"easy": 600,  "medium": 1200, "hard": 1900,  "deadly": 2800},
    11: {"easy": 800,  "medium": 1600, "hard": 2400,  "deadly": 3600},
    12: {"easy": 1000, "medium": 2000, "hard": 3000,  "deadly": 4500},
    13: {"easy": 1100, "medium": 2200, "hard": 3400,  "deadly": 5100},
    14: {"easy": 1250, "medium": 2500, "hard": 3800,  "deadly": 5700},
    15: {"easy": 1400, "medium": 2800, "hard": 4300,  "deadly": 6400},
    16: {"easy": 1600, "medium": 3200, "hard": 4800,  "deadly": 7200},
    17: {"easy": 2000, "medium": 3900, "hard": 5900,  "deadly": 8800},
    18: {"easy": 2100, "medium": 4200, "hard": 6300,  "deadly": 9500},
    19: {"easy": 2400, "medium": 4900, "hard": 7300,  "deadly": 10900},
    20: {"easy": 2800, "medium": 5700, "hard": 8500,  "deadly": 12700},
}


# =============================================================================
# Constants: Challenge Rating to XP (DMG p.274)
# =============================================================================

CR_TO_XP: dict[float, int] = {
    0:    10,
    0.125: 25,
    0.25: 50,
    0.5:  100,
    1:    200,
    2:    450,
    3:    700,
    4:    1100,
    5:    1800,
    6:    2300,
    7:    2900,
    8:    3900,
    9:    5000,
    10:   5900,
    11:   7200,
    12:   8400,
    13:   10000,
    14:   11500,
    15:   13000,
    16:   15000,
    17:   18000,
    18:   20000,
    19:   22000,
    20:   25000,
    21:   33000,
    22:   41000,
    23:   50000,
    24:   62000,
    25:   75000,
    26:   90000,
    27:   105000,
    28:   120000,
    29:   135000,
    30:   155000,
}


# =============================================================================
# Constants: Encounter Multipliers (DMG p.82)
# =============================================================================

# Ordered list of (monster_count_threshold, multiplier).
# For a given number of monsters, use the multiplier of the last entry
# whose threshold is <= monster_count.
ENCOUNTER_MULTIPLIERS: list[tuple[int, float]] = [
    (1,  1.0),
    (2,  1.5),
    (3,  2.0),
    (7,  2.5),
    (11, 3.0),
    (15, 4.0),
]

# The full ordered list of multiplier values for step adjustments
_MULTIPLIER_STEPS: list[float] = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]


# =============================================================================
# Pydantic Models
# =============================================================================

class MonsterGroup(BaseModel):
    """A group of identical monsters in an encounter composition."""
    monster_name: str = Field(description="Monster name from the rulebook")
    monster_index: str = Field(description="Monster index/ID in the rulebook")
    count: int = Field(ge=1, description="Number of this monster in the encounter")
    challenge_rating: float = Field(ge=0, description="Individual monster CR")
    xp_per_monster: int = Field(ge=0, description="XP value per individual monster")
    creature_type: str | None = Field(default=None, description="Creature type (e.g., undead, beast)")


class EncounterComposition(BaseModel):
    """A single encounter composition suggestion."""
    strategy: str = Field(description="Composition strategy name (e.g., 'single_powerful', 'mixed_group', 'swarm')")
    strategy_description: str = Field(description="Human-readable description of the strategy")
    monster_groups: list[MonsterGroup] = Field(default_factory=list, description="Monster groups in this composition")
    total_monsters: int = Field(ge=0, description="Total number of monsters")
    base_xp: int = Field(ge=0, description="Sum of individual monster XP values")
    encounter_multiplier: float = Field(ge=0, description="Group size multiplier applied")
    adjusted_xp: int = Field(ge=0, description="XP after applying encounter multiplier")
    actual_difficulty: str = Field(description="Resulting difficulty classification")


class EncounterSuggestion(BaseModel):
    """Complete encounter building result."""
    party_levels: list[int] = Field(description="Individual character levels in the party")
    party_size: int = Field(ge=1, description="Number of characters in the party")
    requested_difficulty: str = Field(description="Requested difficulty level")
    xp_budget: int = Field(ge=0, description="Total XP budget for the encounter")
    thresholds: dict[str, int] = Field(description="XP thresholds for each difficulty tier")
    compositions: list[EncounterComposition] = Field(
        default_factory=list,
        description="Suggested encounter compositions (up to 3 strategies)"
    )
    rulebooks_loaded: bool = Field(description="Whether rulebooks were available for monster selection")
    notes: list[str] = Field(default_factory=list, description="Additional notes or warnings")


# =============================================================================
# Core Functions
# =============================================================================

def get_xp_thresholds(party_levels: list[int]) -> dict[str, int]:
    """Calculate total XP thresholds for a party.

    Sums the individual XP thresholds for each character's level across
    all four difficulty tiers.

    Args:
        party_levels: List of character levels (e.g., [5, 5, 4, 3]).

    Returns:
        Dict with keys 'easy', 'medium', 'hard', 'deadly' and total XP values.

    Raises:
        ValueError: If party_levels is empty or contains invalid levels.
    """
    if not party_levels:
        raise ValueError("party_levels must not be empty")

    thresholds = {"easy": 0, "medium": 0, "hard": 0, "deadly": 0}

    for level in party_levels:
        if level < 1 or level > 20:
            raise ValueError(f"Character level must be between 1 and 20, got {level}")
        level_thresholds = XP_THRESHOLDS[level]
        for difficulty in thresholds:
            thresholds[difficulty] += level_thresholds[difficulty]

    return thresholds


def calculate_xp_budget(party_levels: list[int], difficulty: str) -> int:
    """Calculate the XP budget for an encounter.

    Args:
        party_levels: List of character levels (e.g., [5, 5, 4, 3]).
        difficulty: Difficulty level ('easy', 'medium', 'hard', 'deadly').

    Returns:
        Total XP budget for the requested difficulty.

    Raises:
        ValueError: If difficulty is invalid or party_levels is empty/invalid.
    """
    difficulty_lower = difficulty.lower()
    if difficulty_lower not in ("easy", "medium", "hard", "deadly"):
        raise ValueError(f"Invalid difficulty: '{difficulty}'. Must be one of: easy, medium, hard, deadly")

    thresholds = get_xp_thresholds(party_levels)
    return thresholds[difficulty_lower]


def get_encounter_multiplier(
    monster_count: int,
    party_size: int = 4,
) -> float:
    """Get the encounter multiplier for a given number of monsters.

    Applies the standard DMG encounter multiplier table with party size
    adjustments:
    - Party of 1-2: increase multiplier by one step
    - Party of 3-5: standard multiplier (no adjustment)
    - Party of 6+: decrease multiplier by one step

    Args:
        monster_count: Total number of monsters in the encounter.
        party_size: Number of characters in the party.

    Returns:
        The encounter multiplier as a float.

    Raises:
        ValueError: If monster_count < 1 or party_size < 1.
    """
    if monster_count < 1:
        raise ValueError(f"monster_count must be >= 1, got {monster_count}")
    if party_size < 1:
        raise ValueError(f"party_size must be >= 1, got {party_size}")

    # Find base multiplier from the table
    base_multiplier = ENCOUNTER_MULTIPLIERS[0][1]  # default to first entry
    for threshold, multiplier in ENCOUNTER_MULTIPLIERS:
        if monster_count >= threshold:
            base_multiplier = multiplier

    # Find the index of base_multiplier in the step list
    try:
        step_index = _MULTIPLIER_STEPS.index(base_multiplier)
    except ValueError:
        # If exact value not found, find closest
        step_index = min(
            range(len(_MULTIPLIER_STEPS)),
            key=lambda i: abs(_MULTIPLIER_STEPS[i] - base_multiplier),
        )

    # Apply party size adjustment
    if party_size <= 2:
        step_index = min(step_index + 1, len(_MULTIPLIER_STEPS) - 1)
    elif party_size >= 6:
        step_index = max(step_index - 1, 0)

    return _MULTIPLIER_STEPS[step_index]


def classify_difficulty(adjusted_xp: int, thresholds: dict[str, int]) -> str:
    """Classify an encounter's difficulty based on adjusted XP vs thresholds.

    Args:
        adjusted_xp: The encounter's adjusted XP (base XP * multiplier).
        thresholds: Party XP thresholds dict with keys 'easy', 'medium', 'hard', 'deadly'.

    Returns:
        Difficulty classification string: 'trivial', 'easy', 'medium', 'hard', or 'deadly'.
    """
    if adjusted_xp >= thresholds["deadly"]:
        return "deadly"
    elif adjusted_xp >= thresholds["hard"]:
        return "hard"
    elif adjusted_xp >= thresholds["medium"]:
        return "medium"
    elif adjusted_xp >= thresholds["easy"]:
        return "easy"
    else:
        return "trivial"


def _cr_to_xp(cr: float) -> int:
    """Convert a challenge rating to its XP value.

    Args:
        cr: Challenge rating (0 to 30, including fractional values 0.125, 0.25, 0.5).

    Returns:
        XP value for the given CR.

    Raises:
        ValueError: If CR is not a recognized value.
    """
    if cr in CR_TO_XP:
        return CR_TO_XP[cr]
    raise ValueError(f"Unknown challenge rating: {cr}. Valid CRs: {sorted(CR_TO_XP.keys())}")


def _find_cr_for_budget(
    xp_budget: int,
    party_size: int,
    min_cr: float = 0,
    max_cr: float = 30,
) -> list[tuple[float, int]]:
    """Find CRs that fit within an XP budget as a single monster.

    Returns CRs sorted by XP value descending (strongest first) that
    don't exceed the budget when used as a single monster.

    Args:
        xp_budget: Available XP budget.
        party_size: Party size (for multiplier calculation).
        min_cr: Minimum CR to consider.
        max_cr: Maximum CR to consider.

    Returns:
        List of (cr, xp_value) tuples, sorted by xp descending.
    """
    candidates = []
    for cr, xp in sorted(CR_TO_XP.items()):
        if cr < min_cr or cr > max_cr:
            continue
        multiplier = get_encounter_multiplier(1, party_size)
        adjusted = int(xp * multiplier)
        if adjusted <= xp_budget:
            candidates.append((cr, xp))

    # Sort by XP descending (best fit = highest XP without exceeding budget)
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates


def _build_single_powerful(
    xp_budget: int,
    party_size: int,
    thresholds: dict[str, int],
    available_monsters: list[dict[str, Any]] | None,
    min_cr: float = 0,
    max_cr: float = 30,
    creature_type: str | None = None,
) -> EncounterComposition | None:
    """Build a single powerful monster encounter.

    Strategy: One monster whose adjusted XP is closest to the budget
    without exceeding it.

    Args:
        xp_budget: Target XP budget.
        party_size: Number of party members.
        thresholds: Party XP thresholds.
        available_monsters: List of monster dicts from rulebook search, or None.
        min_cr: Minimum CR filter.
        max_cr: Maximum CR filter.
        creature_type: Optional creature type filter.

    Returns:
        EncounterComposition or None if no suitable monster found.
    """
    multiplier = get_encounter_multiplier(1, party_size)

    if available_monsters:
        # Filter and find best fit from actual monsters
        best_monster = None
        best_adjusted = 0

        for monster in available_monsters:
            cr = monster.get("challenge_rating", 0)
            xp = monster.get("xp", 0)

            if cr < min_cr or cr > max_cr:
                continue
            if creature_type and monster.get("type", "").lower() != creature_type.lower():
                continue

            adjusted = int(xp * multiplier)
            if adjusted <= xp_budget and adjusted > best_adjusted:
                best_monster = monster
                best_adjusted = adjusted

        if not best_monster:
            return None

        group = MonsterGroup(
            monster_name=best_monster["name"],
            monster_index=best_monster["index"],
            count=1,
            challenge_rating=best_monster["challenge_rating"],
            xp_per_monster=best_monster["xp"],
            creature_type=best_monster.get("type"),
        )
        base_xp = best_monster["xp"]
    else:
        # No rulebooks: use CR table to find best fit
        candidates = _find_cr_for_budget(xp_budget, party_size, min_cr, max_cr)
        if not candidates:
            return None

        best_cr, best_xp = candidates[0]
        group = MonsterGroup(
            monster_name=f"CR {_format_cr(best_cr)} Monster",
            monster_index=f"cr-{best_cr}",
            count=1,
            challenge_rating=best_cr,
            xp_per_monster=best_xp,
        )
        base_xp = best_xp

    adjusted_xp = int(base_xp * multiplier)
    actual_difficulty = classify_difficulty(adjusted_xp, thresholds)

    return EncounterComposition(
        strategy="single_powerful",
        strategy_description="A single powerful monster as the sole threat",
        monster_groups=[group],
        total_monsters=1,
        base_xp=base_xp,
        encounter_multiplier=multiplier,
        adjusted_xp=adjusted_xp,
        actual_difficulty=actual_difficulty,
    )


def _build_mixed_group(
    xp_budget: int,
    party_size: int,
    thresholds: dict[str, int],
    available_monsters: list[dict[str, Any]] | None,
    min_cr: float = 0,
    max_cr: float = 30,
    creature_type: str | None = None,
) -> EncounterComposition | None:
    """Build a mixed group encounter (leader + minions).

    Strategy: One stronger monster (leader) taking ~60% of budget,
    with 2-4 weaker monsters (minions) using the remaining budget.

    Args:
        xp_budget: Target XP budget.
        party_size: Number of party members.
        thresholds: Party XP thresholds.
        available_monsters: List of monster dicts from rulebook search, or None.
        min_cr: Minimum CR filter.
        max_cr: Maximum CR filter.
        creature_type: Optional creature type filter.

    Returns:
        EncounterComposition or None if no suitable composition found.
    """
    # Estimate leader budget as ~60% of total, solve for base XP
    # We'll iterate to find a good combination
    leader_budget_fraction = 0.6

    if available_monsters:
        # Filter monsters by type if specified
        filtered = available_monsters
        if creature_type:
            filtered = [m for m in available_monsters if m.get("type", "").lower() == creature_type.lower()]
            if not filtered:
                filtered = available_monsters

        # Sort by XP descending
        sorted_monsters = sorted(
            [m for m in filtered if min_cr <= m.get("challenge_rating", 0) <= max_cr],
            key=lambda m: m.get("xp", 0),
            reverse=True,
        )

        if not sorted_monsters:
            return None

        # Try to find a leader + minion combination
        for leader in sorted_monsters:
            leader_xp = leader.get("xp", 0)
            if leader_xp == 0:
                continue

            # Try different minion counts (2-4)
            for minion_count in range(2, 5):
                total_count = 1 + minion_count
                multiplier = get_encounter_multiplier(total_count, party_size)
                remaining_xp_budget = xp_budget / multiplier - leader_xp

                if remaining_xp_budget <= 0:
                    continue

                target_minion_xp = remaining_xp_budget / minion_count

                # Find best minion (lower CR than leader)
                best_minion = None
                best_diff = float("inf")
                for m in sorted_monsters:
                    m_xp = m.get("xp", 0)
                    if m_xp >= leader_xp or m_xp == 0:
                        continue
                    diff = abs(m_xp - target_minion_xp)
                    if diff < best_diff:
                        best_minion = m
                        best_diff = diff

                if not best_minion:
                    continue

                minion_xp = best_minion.get("xp", 0)
                base_xp = leader_xp + (minion_xp * minion_count)
                adjusted_xp = int(base_xp * multiplier)

                if adjusted_xp <= xp_budget:
                    groups = [
                        MonsterGroup(
                            monster_name=leader["name"],
                            monster_index=leader["index"],
                            count=1,
                            challenge_rating=leader["challenge_rating"],
                            xp_per_monster=leader_xp,
                            creature_type=leader.get("type"),
                        ),
                        MonsterGroup(
                            monster_name=best_minion["name"],
                            monster_index=best_minion["index"],
                            count=minion_count,
                            challenge_rating=best_minion["challenge_rating"],
                            xp_per_monster=minion_xp,
                            creature_type=best_minion.get("type"),
                        ),
                    ]
                    actual_difficulty = classify_difficulty(adjusted_xp, thresholds)
                    return EncounterComposition(
                        strategy="mixed_group",
                        strategy_description="A leader monster with a group of weaker minions",
                        monster_groups=groups,
                        total_monsters=total_count,
                        base_xp=base_xp,
                        encounter_multiplier=multiplier,
                        adjusted_xp=adjusted_xp,
                        actual_difficulty=actual_difficulty,
                    )

        return None
    else:
        # No rulebooks: use CR table
        sorted_crs = sorted(CR_TO_XP.items(), key=lambda x: x[1], reverse=True)

        for leader_cr, leader_xp in sorted_crs:
            if leader_cr < min_cr or leader_cr > max_cr:
                continue

            for minion_count in range(2, 5):
                total_count = 1 + minion_count
                multiplier = get_encounter_multiplier(total_count, party_size)
                remaining_xp_budget = xp_budget / multiplier - leader_xp

                if remaining_xp_budget <= 0:
                    continue

                target_minion_xp = remaining_xp_budget / minion_count

                # Find best minion CR
                best_minion_cr = None
                best_minion_xp = 0
                best_diff = float("inf")
                for m_cr, m_xp in sorted_crs:
                    if m_cr >= leader_cr or m_cr < min_cr or m_cr > max_cr:
                        continue
                    diff = abs(m_xp - target_minion_xp)
                    if diff < best_diff:
                        best_minion_cr = m_cr
                        best_minion_xp = m_xp
                        best_diff = diff

                if best_minion_cr is None:
                    continue

                base_xp = leader_xp + (best_minion_xp * minion_count)
                adjusted_xp = int(base_xp * multiplier)

                if adjusted_xp <= xp_budget:
                    groups = [
                        MonsterGroup(
                            monster_name=f"CR {_format_cr(leader_cr)} Leader",
                            monster_index=f"cr-{leader_cr}",
                            count=1,
                            challenge_rating=leader_cr,
                            xp_per_monster=leader_xp,
                        ),
                        MonsterGroup(
                            monster_name=f"CR {_format_cr(best_minion_cr)} Minion",
                            monster_index=f"cr-{best_minion_cr}",
                            count=minion_count,
                            challenge_rating=best_minion_cr,
                            xp_per_monster=best_minion_xp,
                        ),
                    ]
                    actual_difficulty = classify_difficulty(adjusted_xp, thresholds)
                    return EncounterComposition(
                        strategy="mixed_group",
                        strategy_description="A leader monster with a group of weaker minions",
                        monster_groups=groups,
                        total_monsters=total_count,
                        base_xp=base_xp,
                        encounter_multiplier=multiplier,
                        adjusted_xp=adjusted_xp,
                        actual_difficulty=actual_difficulty,
                    )

        return None


def _build_swarm(
    xp_budget: int,
    party_size: int,
    thresholds: dict[str, int],
    available_monsters: list[dict[str, Any]] | None,
    min_cr: float = 0,
    max_cr: float = 30,
    creature_type: str | None = None,
) -> EncounterComposition | None:
    """Build a swarm encounter (many weaker creatures).

    Strategy: 4-8 identical weaker monsters whose adjusted XP is
    closest to the budget without exceeding it.

    Args:
        xp_budget: Target XP budget.
        party_size: Number of party members.
        thresholds: Party XP thresholds.
        available_monsters: List of monster dicts from rulebook search, or None.
        min_cr: Minimum CR filter.
        max_cr: Maximum CR filter.
        creature_type: Optional creature type filter.

    Returns:
        EncounterComposition or None if no suitable composition found.
    """
    best_composition = None
    best_adjusted = 0

    if available_monsters:
        filtered = available_monsters
        if creature_type:
            filtered = [m for m in available_monsters if m.get("type", "").lower() == creature_type.lower()]
            if not filtered:
                filtered = available_monsters

        for monster in filtered:
            cr = monster.get("challenge_rating", 0)
            xp = monster.get("xp", 0)

            if cr < min_cr or cr > max_cr or xp == 0:
                continue

            # Try swarm sizes from 4 to 8
            for count in range(4, 9):
                multiplier = get_encounter_multiplier(count, party_size)
                base_xp = xp * count
                adjusted_xp = int(base_xp * multiplier)

                if adjusted_xp <= xp_budget and adjusted_xp > best_adjusted:
                    group = MonsterGroup(
                        monster_name=monster["name"],
                        monster_index=monster["index"],
                        count=count,
                        challenge_rating=cr,
                        xp_per_monster=xp,
                        creature_type=monster.get("type"),
                    )
                    actual_difficulty = classify_difficulty(adjusted_xp, thresholds)
                    best_composition = EncounterComposition(
                        strategy="swarm",
                        strategy_description="A swarm of weaker creatures overwhelming through numbers",
                        monster_groups=[group],
                        total_monsters=count,
                        base_xp=base_xp,
                        encounter_multiplier=multiplier,
                        adjusted_xp=adjusted_xp,
                        actual_difficulty=actual_difficulty,
                    )
                    best_adjusted = adjusted_xp
    else:
        # No rulebooks: use CR table
        for cr, xp in CR_TO_XP.items():
            if cr < min_cr or cr > max_cr or xp == 0:
                continue

            for count in range(4, 9):
                multiplier = get_encounter_multiplier(count, party_size)
                base_xp = xp * count
                adjusted_xp = int(base_xp * multiplier)

                if adjusted_xp <= xp_budget and adjusted_xp > best_adjusted:
                    group = MonsterGroup(
                        monster_name=f"CR {_format_cr(cr)} Creature",
                        monster_index=f"cr-{cr}",
                        count=count,
                        challenge_rating=cr,
                        xp_per_monster=xp,
                    )
                    actual_difficulty = classify_difficulty(adjusted_xp, thresholds)
                    best_composition = EncounterComposition(
                        strategy="swarm",
                        strategy_description="A swarm of weaker creatures overwhelming through numbers",
                        monster_groups=[group],
                        total_monsters=count,
                        base_xp=base_xp,
                        encounter_multiplier=multiplier,
                        adjusted_xp=adjusted_xp,
                        actual_difficulty=actual_difficulty,
                    )
                    best_adjusted = adjusted_xp

    return best_composition


def _format_cr(cr: float) -> str:
    """Format a CR value for display.

    Args:
        cr: Challenge rating value.

    Returns:
        Formatted string (e.g., '1/8', '1/4', '1/2', '1', '5').
    """
    if cr == 0.125:
        return "1/8"
    elif cr == 0.25:
        return "1/4"
    elif cr == 0.5:
        return "1/2"
    elif cr == int(cr):
        return str(int(cr))
    else:
        return str(cr)


def _fetch_monsters_from_rulebooks(
    rulebook_manager: Any,
    min_cr: float = 0,
    max_cr: float = 30,
    creature_type: str | None = None,
    environment: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch and filter monsters from loaded rulebooks.

    Uses the RulebookManager search and get_monster infrastructure to
    retrieve monster data suitable for encounter building.

    Args:
        rulebook_manager: A RulebookManager instance (or None).
        min_cr: Minimum challenge rating.
        max_cr: Maximum challenge rating.
        creature_type: Filter by creature type (e.g., 'undead', 'beast').
        environment: Filter by environment/terrain (if data available).

    Returns:
        List of monster dicts with keys: name, index, challenge_rating, xp, type.
    """
    if rulebook_manager is None:
        return []

    monsters: list[dict[str, Any]] = []

    # Search for all monsters (empty query with category filter)
    # We use a broad search to get as many candidates as possible
    try:
        search_results = rulebook_manager.search(
            query="",
            categories=["monster"],
            limit=50,
        )
    except Exception as e:
        logger.warning(f"Failed to search monsters from rulebooks: {e}")
        return []

    for result in search_results:
        try:
            monster_def = rulebook_manager.get_monster(result.index)
            if monster_def is None:
                continue

            cr = monster_def.challenge_rating
            if cr < min_cr or cr > max_cr:
                continue

            m_type = getattr(monster_def, "type", "")
            if creature_type and m_type.lower() != creature_type.lower():
                continue

            monsters.append({
                "name": monster_def.name,
                "index": monster_def.index,
                "challenge_rating": cr,
                "xp": monster_def.xp,
                "type": m_type,
            })
        except Exception as e:
            logger.debug(f"Skipping monster {result.index}: {e}")
            continue

    return monsters


def build_encounter(
    party_levels: list[int],
    difficulty: str = "medium",
    rulebook_manager: Any = None,
    min_cr: float = 0,
    max_cr: float = 30,
    creature_type: str | None = None,
    environment: str | None = None,
) -> EncounterSuggestion:
    """Build a balanced encounter for a party.

    Calculates XP budgets and optionally selects monsters from loaded
    rulebooks. Provides up to 3 composition strategies:
    1. Single powerful monster
    2. Mixed group (leader + minions)
    3. Swarm of weaker creatures

    When no rulebooks are loaded, returns XP budget and thresholds only,
    with generic CR-based placeholder suggestions.

    Args:
        party_levels: List of character levels (e.g., [5, 5, 4, 3]).
        difficulty: Target difficulty ('easy', 'medium', 'hard', 'deadly').
        rulebook_manager: Optional RulebookManager instance for monster data.
        min_cr: Minimum challenge rating filter.
        max_cr: Maximum challenge rating filter.
        creature_type: Filter by creature type (e.g., 'undead', 'beast').
        environment: Filter by environment/terrain type.

    Returns:
        EncounterSuggestion with XP budget, thresholds, and compositions.

    Raises:
        ValueError: If party_levels is empty/invalid or difficulty is invalid.
    """
    difficulty_lower = difficulty.lower()
    if difficulty_lower not in ("easy", "medium", "hard", "deadly"):
        raise ValueError(f"Invalid difficulty: '{difficulty}'. Must be one of: easy, medium, hard, deadly")

    party_size = len(party_levels)
    thresholds = get_xp_thresholds(party_levels)
    xp_budget = thresholds[difficulty_lower]

    notes: list[str] = []

    # Attempt to fetch monsters from rulebooks
    available_monsters: list[dict[str, Any]] | None = None
    rulebooks_loaded = False

    if rulebook_manager is not None:
        available_monsters = _fetch_monsters_from_rulebooks(
            rulebook_manager,
            min_cr=min_cr,
            max_cr=max_cr,
            creature_type=creature_type,
            environment=environment,
        )
        if available_monsters:
            rulebooks_loaded = True
        else:
            notes.append("Rulebooks loaded but no matching monsters found for the given filters.")

    if not rulebooks_loaded:
        notes.append(
            "No rulebooks loaded. Showing CR-based placeholder suggestions. "
            "Load a rulebook (e.g., SRD) for specific monster recommendations."
        )

    # Build compositions using the three strategies
    compositions: list[EncounterComposition] = []

    single = _build_single_powerful(
        xp_budget, party_size, thresholds,
        available_monsters, min_cr, max_cr, creature_type,
    )
    if single:
        compositions.append(single)

    mixed = _build_mixed_group(
        xp_budget, party_size, thresholds,
        available_monsters, min_cr, max_cr, creature_type,
    )
    if mixed:
        compositions.append(mixed)

    swarm = _build_swarm(
        xp_budget, party_size, thresholds,
        available_monsters, min_cr, max_cr, creature_type,
    )
    if swarm:
        compositions.append(swarm)

    if not compositions:
        notes.append(
            "No encounter compositions could be generated within the XP budget. "
            "Try adjusting difficulty, CR range, or creature type filters."
        )

    return EncounterSuggestion(
        party_levels=party_levels,
        party_size=party_size,
        requested_difficulty=difficulty_lower,
        xp_budget=xp_budget,
        thresholds=thresholds,
        compositions=compositions,
        rulebooks_loaded=rulebooks_loaded,
        notes=notes,
    )
