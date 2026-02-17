"""
Core mapper functions for translating D&D Beyond JSON to dm20 Character model.

This module contains the mapping logic that converts DDB's nested JSON structure
into dm20's flat, normalized Character model. Each mapper function returns a
(result, warnings) tuple to enable graceful degradation.
"""

from __future__ import annotations

from dm20_protocol.models import Character, CharacterClass, Race, AbilityScore

from ..base import ImportResult
from .schema import (
    ABILITY_SCORE_SUBTYPES,
    ALIGNMENT_MAP,
    CLASS_HIT_DICE,
    CLASS_SPELLCASTING_ABILITY,
    MODIFIER_SECTIONS,
    SAVING_THROW_SUBTYPES,
    SKILL_SUBTYPES,
    STAT_ID_MAP,
)


def map_identity(ddb: dict) -> tuple[dict, list[str]]:
    """Map basic identity fields from DDB character.

    Args:
        ddb: Raw D&D Beyond character JSON.

    Returns:
        Tuple of (identity_fields_dict, warnings).
        identity_fields_dict contains: name, race, character_class, background, alignment
    """
    warnings: list[str] = []
    result: dict = {}

    # Name
    result["name"] = ddb.get("name", "Unknown Character")

    # Race
    race_data = ddb.get("race", {})
    race_name = race_data.get("fullName") or race_data.get("baseName", "Unknown")
    race_subrace = race_data.get("subRaceShortName")
    # Only set subrace if it's present and non-empty
    if race_subrace and race_subrace.strip():
        result["race"] = Race(name=race_name, subrace=race_subrace)
    else:
        result["race"] = Race(name=race_name)

    # Character class: pick highest-level class
    classes = ddb.get("classes", [])
    if classes:
        # Sort by level descending, take first
        primary_class = max(classes, key=lambda c: c.get("level", 0))
        class_def = primary_class.get("definition", {})
        class_name = class_def.get("name", "Unknown")
        class_level = primary_class.get("level", 1)
        subclass_def = primary_class.get("subclassDefinition")
        subclass_name = subclass_def.get("name") if subclass_def else None

        # Get hit dice type from schema
        hit_dice_type = CLASS_HIT_DICE.get(class_name, "d8")

        result["character_class"] = CharacterClass(
            name=class_name,
            level=class_level,
            hit_dice=hit_dice_type,
            subclass=subclass_name,
        )

        # Set spellcasting ability if applicable
        if class_name in CLASS_SPELLCASTING_ABILITY:
            result["spellcasting_ability"] = CLASS_SPELLCASTING_ABILITY[class_name]
    else:
        warnings.append("No classes found, defaulting to Fighter level 1")
        result["character_class"] = CharacterClass(name="Fighter", level=1, hit_dice="d10")

    # Background
    background_data = ddb.get("background", {})
    background_def = background_data.get("definition", {})
    result["background"] = background_def.get("name")

    # Alignment
    alignment_id = ddb.get("alignmentId")
    if alignment_id:
        result["alignment"] = ALIGNMENT_MAP.get(alignment_id, "True Neutral")
    else:
        result["alignment"] = None

    return result, warnings


def map_abilities(ddb: dict) -> tuple[dict[str, AbilityScore], list[str]]:
    """Map ability scores from DDB character.

    This is the most complex mapping function because DDB scatters ability scores
    across multiple locations: base stats, bonus stats, override stats, and modifiers
    from race/class/items/feats.

    Args:
        ddb: Raw D&D Beyond character JSON.

    Returns:
        Tuple of (abilities_dict, warnings).
        abilities_dict maps ability name → AbilityScore.
    """
    warnings: list[str] = []
    abilities: dict[str, AbilityScore] = {}

    # Extract all stat arrays
    base_stats = {s["id"]: s["value"] for s in ddb.get("stats", [])}
    bonus_stats = {s["id"]: s.get("value", 0) or 0 for s in ddb.get("bonusStats", [])}
    override_stats = {
        s["id"]: s.get("value") for s in ddb.get("overrideStats", []) if s.get("value") is not None
    }

    # Collect ability score bonuses from modifiers
    # Structure: modifiers = {"race": [...], "class": [...], "item": [...], ...}
    modifiers_dict = ddb.get("modifiers", {})
    ability_bonuses: dict[str, int] = {ability: 0 for ability in STAT_ID_MAP.values()}

    for section_name in MODIFIER_SECTIONS:
        section = modifiers_dict.get(section_name, [])
        for mod in section:
            if mod.get("type") == "bonus" and mod.get("subType") in ABILITY_SCORE_SUBTYPES:
                ability_name = ABILITY_SCORE_SUBTYPES[mod["subType"]]
                mod_value = mod.get("value", 0)
                if mod_value:
                    ability_bonuses[ability_name] += mod_value

    # Calculate final scores
    for stat_id, ability_name in STAT_ID_MAP.items():
        # Check for override first
        if stat_id in override_stats:
            final_score = override_stats[stat_id]
        else:
            # Standard calculation: base + bonus + modifiers
            base = base_stats.get(stat_id, 10)
            bonus = bonus_stats.get(stat_id, 0)
            modifier_bonus = ability_bonuses.get(ability_name, 0)
            final_score = base + bonus + modifier_bonus

        abilities[ability_name] = AbilityScore(score=final_score)

    return abilities, warnings


def map_combat(
    ddb: dict, abilities: dict[str, AbilityScore], level: int
) -> tuple[dict, list[str]]:
    """Map combat-related stats from DDB character.

    Args:
        ddb: Raw D&D Beyond character JSON.
        abilities: Already-computed ability scores (needed for HP calculation).
        level: Character level (needed for HP calculation).

    Returns:
        Tuple of (combat_fields_dict, warnings).
        combat_fields_dict contains: hit_points_max, hit_points_current,
        temporary_hit_points, armor_class, speed, hit_dice_type,
        hit_dice_remaining, experience_points
    """
    warnings: list[str] = []
    result: dict = {}

    # Hit points
    override_hp = ddb.get("overrideHitPoints")
    if override_hp is not None:
        hp_max = override_hp
    else:
        base_hp = ddb.get("baseHitPoints", 0)
        bonus_hp = ddb.get("bonusHitPoints", 0)
        con_mod = abilities.get("constitution", AbilityScore(score=10)).mod
        hp_max = base_hp + bonus_hp + (con_mod * level)

    result["hit_points_max"] = max(1, hp_max)  # Minimum 1 HP
    result["hit_points_current"] = max(0, hp_max - ddb.get("removedHitPoints", 0))
    result["temporary_hit_points"] = ddb.get("temporaryHitPoints", 0)

    # Armor class
    result["armor_class"] = ddb.get("armorClass", 10)

    # Speed
    try:
        speed = ddb.get("race", {}).get("weightSpeeds", {}).get("normal", {}).get("walk", 30)
        result["speed"] = speed
    except (AttributeError, TypeError):
        result["speed"] = 30
        warnings.append("Could not parse race speed, defaulting to 30")

    # Hit dice - already set in character_class during map_identity, but we return type/remaining
    # Get class name from the already-mapped character class (caller will merge these)
    # For now, we'll just use a placeholder since the caller has the class info
    # The caller should merge this properly
    result["hit_dice_type"] = "d8"  # Placeholder, overridden by class hit_dice
    result["hit_dice_remaining"] = f"{level}d8"  # Placeholder

    # Experience points
    result["experience_points"] = ddb.get("currentXp", 0)

    return result, warnings


def map_proficiencies(ddb: dict) -> tuple[dict, list[str]]:
    """Map proficiencies and languages from DDB character.

    Scans all modifier sections for proficiency and language modifiers.

    Args:
        ddb: Raw D&D Beyond character JSON.

    Returns:
        Tuple of (proficiency_fields_dict, warnings).
        proficiency_fields_dict contains: skill_proficiencies,
        saving_throw_proficiencies, tool_proficiencies, languages
    """
    warnings: list[str] = []
    result: dict = {
        "skill_proficiencies": [],
        "saving_throw_proficiencies": [],
        "tool_proficiencies": [],
        "languages": [],
    }

    modifiers_dict = ddb.get("modifiers", {})

    for section_name in MODIFIER_SECTIONS:
        section = modifiers_dict.get(section_name, [])
        for mod in section:
            mod_type = mod.get("type")
            sub_type = mod.get("subType", "")
            friendly_name = mod.get("friendlySubtypeName", sub_type)

            # Skills
            if mod_type == "proficiency" and sub_type in SKILL_SUBTYPES:
                skill_name = SKILL_SUBTYPES[sub_type]
                if skill_name not in result["skill_proficiencies"]:
                    result["skill_proficiencies"].append(skill_name)

            # Saving throws
            elif mod_type == "proficiency" and sub_type in SAVING_THROW_SUBTYPES:
                save_name = SAVING_THROW_SUBTYPES[sub_type]
                if save_name not in result["saving_throw_proficiencies"]:
                    result["saving_throw_proficiencies"].append(save_name)

            # Tools (proficiency type but not skill/save)
            elif mod_type == "proficiency" and sub_type not in SKILL_SUBTYPES and sub_type not in SAVING_THROW_SUBTYPES:
                if friendly_name and friendly_name not in result["tool_proficiencies"]:
                    result["tool_proficiencies"].append(friendly_name)

            # Languages
            elif mod_type == "language":
                if friendly_name and friendly_name not in result["languages"]:
                    result["languages"].append(friendly_name)

    return result, warnings


def map_ddb_to_character(ddb: dict, player_name: str | None = None) -> ImportResult:
    """Orchestrate full DDB → Character mapping.

    Calls all mapper functions, collects warnings, and builds the final Character.
    Always returns a valid Character even if some sections fail.

    Args:
        ddb: Raw D&D Beyond character JSON.
        player_name: Optional player name to attach to the character.

    Returns:
        ImportResult with the created Character, mapped/unmapped fields, and warnings.
    """
    all_warnings: list[str] = []
    mapped_fields: list[str] = []
    unmapped_fields: list[str] = []

    # Initialize with defaults
    character_data: dict = {
        "name": "Unknown Character",
        "race": Race(name="Unknown"),
        "character_class": CharacterClass(name="Fighter", level=1, hit_dice="d10"),
        "abilities": {
            "strength": AbilityScore(score=10),
            "dexterity": AbilityScore(score=10),
            "constitution": AbilityScore(score=10),
            "intelligence": AbilityScore(score=10),
            "wisdom": AbilityScore(score=10),
            "charisma": AbilityScore(score=10),
        },
        "hit_points_max": 1,
        "hit_points_current": 1,
        "armor_class": 10,
        "speed": 30,
    }

    # Map identity
    try:
        identity, warnings = map_identity(ddb)
        character_data.update(identity)
        all_warnings.extend(warnings)
        mapped_fields.extend(["name", "race", "character_class", "background", "alignment"])
    except Exception as e:
        all_warnings.append(f"Failed to map identity: {e}")
        unmapped_fields.extend(["name", "race", "character_class", "background", "alignment"])

    # Map abilities
    try:
        abilities, warnings = map_abilities(ddb)
        character_data["abilities"] = abilities
        all_warnings.extend(warnings)
        mapped_fields.extend(["abilities"])
    except Exception as e:
        all_warnings.append(f"Failed to map abilities: {e}")
        unmapped_fields.append("abilities")

    # Map combat stats (requires abilities and level)
    try:
        level = character_data.get("character_class", CharacterClass(name="Fighter", level=1)).level
        combat, warnings = map_combat(ddb, character_data["abilities"], level)

        # Update hit_dice fields from character_class
        class_obj = character_data.get("character_class")
        if class_obj:
            combat["hit_dice_type"] = class_obj.hit_dice
            combat["hit_dice_remaining"] = f"{level}{class_obj.hit_dice}"

        character_data.update(combat)
        all_warnings.extend(warnings)
        mapped_fields.extend([
            "hit_points_max",
            "hit_points_current",
            "temporary_hit_points",
            "armor_class",
            "speed",
            "experience_points",
        ])
    except Exception as e:
        all_warnings.append(f"Failed to map combat stats: {e}")
        unmapped_fields.extend([
            "hit_points_max",
            "hit_points_current",
            "armor_class",
            "speed",
            "experience_points",
        ])

    # Map proficiencies
    try:
        profs, warnings = map_proficiencies(ddb)
        character_data.update(profs)
        all_warnings.extend(warnings)
        mapped_fields.extend([
            "skill_proficiencies",
            "saving_throw_proficiencies",
            "tool_proficiencies",
            "languages",
        ])
    except Exception as e:
        all_warnings.append(f"Failed to map proficiencies: {e}")
        unmapped_fields.extend([
            "skill_proficiencies",
            "saving_throw_proficiencies",
            "tool_proficiencies",
            "languages",
        ])

    # Add player name if provided
    if player_name:
        character_data["player_name"] = player_name

    # Build Character model
    character = Character(**character_data)

    # Return ImportResult
    return ImportResult(
        character=character,
        mapped_fields=mapped_fields,
        unmapped_fields=unmapped_fields,
        warnings=all_warnings,
        source="url",  # Caller can override if importing from file
        source_id=ddb.get("id"),
    )
