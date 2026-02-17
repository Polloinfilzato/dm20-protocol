"""
Core mapper functions for translating D&D Beyond JSON to dm20 Character model.

This module contains the mapping logic that converts DDB's nested JSON structure
into dm20's flat, normalized Character model. Each mapper function returns a
(result, warnings) tuple to enable graceful degradation.
"""

from __future__ import annotations

from dm20_protocol.models import Character, CharacterClass, Race, AbilityScore, Item, Spell, Feature

from ..base import ImportResult
from .schema import (
    ABILITY_SCORE_SUBTYPES,
    ALIGNMENT_MAP,
    CLASS_HIT_DICE,
    CLASS_SPELLCASTING_ABILITY,
    ITEM_FILTER_TYPE_MAP,
    MODIFIER_SECTIONS,
    SAVING_THROW_SUBTYPES,
    SKILL_SUBTYPES,
    SPELL_SCHOOL_MAP,
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


def map_inventory(ddb: dict) -> tuple[list[Item], list[str]]:
    """Map inventory items from DDB character.

    Args:
        ddb: Raw D&D Beyond character JSON.

    Returns:
        Tuple of (item_list, warnings).
    """
    warnings: list[str] = []
    items: list[Item] = []

    inventory_data = ddb.get("inventory", [])
    for item_data in inventory_data:
        try:
            definition = item_data.get("definition", {})
            name = definition.get("name", "Unknown Item")
            description = definition.get("description", "")

            # Truncate long descriptions
            if description and len(description) > 500:
                description = description[:497] + "..."

            quantity = item_data.get("quantity", 1)
            weight = definition.get("weight")

            # Parse cost/value
            cost = definition.get("cost")
            value = None
            if cost:
                value = f"{cost} gp"

            # Map filter type to item_type
            filter_type = definition.get("filterType", "Other Gear")
            item_type = ITEM_FILTER_TYPE_MAP.get(filter_type, "misc")

            # Build properties dict with damage, AC, etc.
            properties = {}
            if definition.get("damage"):
                damage_data = definition["damage"]
                if damage_data.get("diceString"):
                    properties["damage"] = damage_data["diceString"]
            if definition.get("armorClass") is not None:
                properties["armor_class"] = definition["armorClass"]
            if item_data.get("equipped") is not None:
                properties["equipped"] = item_data["equipped"]

            item = Item(
                name=name,
                description=description,
                quantity=quantity,
                weight=weight,
                value=value,
                item_type=item_type,
                properties=properties,
            )
            items.append(item)
        except Exception as e:
            warnings.append(f"Failed to parse inventory item: {e}")

    return items, warnings


def map_equipment(ddb: dict, items: list[Item]) -> tuple[dict[str, Item | None], list[str]]:
    """Detect equipped items and assign to equipment slots.

    Args:
        ddb: Raw D&D Beyond character JSON.
        items: Already-parsed inventory items.

    Returns:
        Tuple of (equipment_dict, warnings).
    """
    warnings: list[str] = []
    equipment: dict[str, Item | None] = {
        "weapon_main": None,
        "weapon_off": None,
        "armor": None,
        "shield": None,
    }

    # Find equipped items
    equipped_items = [item for item in items if item.properties.get("equipped", False)]

    for item in equipped_items:
        if item.item_type == "weapon":
            if equipment["weapon_main"] is None:
                equipment["weapon_main"] = item
            elif equipment["weapon_off"] is None:
                equipment["weapon_off"] = item
        elif item.item_type == "armor":
            if "shield" in item.name.lower():
                equipment["shield"] = item
            else:
                equipment["armor"] = item

    return equipment, warnings


def map_spells(ddb: dict) -> tuple[dict, list[str]]:
    """Map spells and spell slots from DDB character.

    Args:
        ddb: Raw D&D Beyond character JSON.

    Returns:
        Tuple of (spell_fields_dict, warnings).
        spell_fields_dict contains: spells_known, spell_slots
    """
    warnings: list[str] = []
    result: dict = {
        "spells_known": [],
        "spell_slots": {},
    }

    # Component mapping: DDB uses ints (1=V, 2=S, 3=M)
    component_map = {1: "V", 2: "S", 3: "M"}

    # Parse spells from classSpells array
    class_spells = ddb.get("classSpells", [])
    for class_spell_list in class_spells:
        spells_data = class_spell_list.get("spells", [])
        for spell_data in spells_data:
            try:
                definition = spell_data.get("definition", {})
                name = definition.get("name", "Unknown Spell")
                level = definition.get("level", 0)
                school_raw = definition.get("school", "Abjuration")
                school = SPELL_SCHOOL_MAP.get(school_raw, school_raw)
                # castingTime can be a dict or string in DDB
                casting_time_raw = definition.get("castingTime", "1 action")
                if isinstance(casting_time_raw, dict):
                    casting_time = casting_time_raw.get("castingTimeInterval", "1 action")
                else:
                    casting_time = str(casting_time_raw)

                # Parse range
                range_data = definition.get("range", {})
                if isinstance(range_data, dict):
                    range_value = range_data.get("rangeValue")
                else:
                    range_value = range_data
                if range_value is None:
                    range_value = 5

                # duration can be a dict or string in DDB
                duration_raw = definition.get("duration", "Instantaneous")
                if isinstance(duration_raw, dict):
                    duration = duration_raw.get("durationInterval", "Instantaneous")
                else:
                    duration = str(duration_raw)
                description = definition.get("description", "")

                # Truncate long descriptions
                if description and len(description) > 500:
                    description = description[:497] + "..."

                # Parse components
                components_raw = definition.get("components", [])
                components = [component_map.get(c, str(c)) for c in components_raw]

                # Material components
                material_components = None
                if "M" in components:
                    material_components = definition.get("componentsDescription", "")

                prepared = spell_data.get("prepared", False)

                spell = Spell(
                    name=name,
                    level=level,
                    school=school,
                    casting_time=casting_time,
                    range=range_value,
                    duration=duration,
                    components=components,
                    description=description,
                    material_components=material_components,
                    prepared=prepared,
                )
                result["spells_known"].append(spell)
            except Exception as e:
                warnings.append(f"Failed to parse spell: {e}")

    # Parse spell slots from classes
    classes = ddb.get("classes", [])
    for class_data in classes:
        try:
            spell_rules = class_data.get("definition", {}).get("spellRules")
            if spell_rules:
                level_spell_slots = spell_rules.get("levelSpellSlots", {})
                # levelSpellSlots is a dict like {"1": [2, 0, 0, ...], "2": [2, 3, 0, ...]}
                # where the array index is spell level and value is number of slots
                class_level = class_data.get("level", 1)
                slots_array = level_spell_slots.get(str(class_level), [])
                for spell_level, slot_count in enumerate(slots_array, start=1):
                    if slot_count > 0:
                        # Sum slots if multiclass
                        current = result["spell_slots"].get(spell_level, 0)
                        result["spell_slots"][spell_level] = current + slot_count
        except Exception as e:
            warnings.append(f"Failed to parse spell slots for class: {e}")

    return result, warnings


def map_features(ddb: dict) -> tuple[list[Feature], list[str]]:
    """Map class features, racial traits, and feats from DDB character.

    Args:
        ddb: Raw D&D Beyond character JSON.

    Returns:
        Tuple of (feature_list, warnings).
    """
    warnings: list[str] = []
    features: list[Feature] = []

    # Class features
    classes = ddb.get("classes", [])
    for class_data in classes:
        try:
            class_name = class_data.get("definition", {}).get("name", "Unknown")
            class_level = class_data.get("level", 1)
            class_features = class_data.get("classFeatures", [])

            for feature_data in class_features:
                definition = feature_data.get("definition", {})
                required_level = definition.get("requiredLevel", 1)

                # Only include features the character has access to
                if required_level <= class_level:
                    name = definition.get("name", "Unknown Feature")
                    description = definition.get("description", "")

                    # Truncate long descriptions
                    if description and len(description) > 500:
                        description = description[:497] + "..."

                    feature = Feature(
                        name=name,
                        source=f"{class_name} {required_level}",
                        description=description,
                        level_gained=required_level,
                    )
                    features.append(feature)
        except Exception as e:
            warnings.append(f"Failed to parse class features: {e}")

    # Racial traits
    try:
        race_data = ddb.get("race", {})
        race_name = race_data.get("fullName") or race_data.get("baseName", "Unknown")
        racial_traits = race_data.get("racialTraits", [])

        for trait_data in racial_traits:
            definition = trait_data.get("definition", {})
            name = definition.get("name", "Unknown Trait")
            description = definition.get("description", "")

            # Truncate long descriptions
            if description and len(description) > 500:
                description = description[:497] + "..."

            feature = Feature(
                name=name,
                source=race_name,
                description=description,
                level_gained=1,
            )
            features.append(feature)
    except Exception as e:
        warnings.append(f"Failed to parse racial traits: {e}")

    # Feats
    try:
        feats = ddb.get("feats", [])
        for feat_data in feats:
            definition = feat_data.get("definition", {})
            name = definition.get("name", "Unknown Feat")
            description = definition.get("description", "")

            # Truncate long descriptions
            if description and len(description) > 500:
                description = description[:497] + "..."

            feature = Feature(
                name=name,
                source="Feat",
                description=description,
                level_gained=1,
            )
            features.append(feature)
    except Exception as e:
        warnings.append(f"Failed to parse feats: {e}")

    return features, warnings


def map_notes(ddb: dict) -> tuple[str, list[str]]:
    """Map character traits and notes from DDB character.

    Args:
        ddb: Raw D&D Beyond character JSON.

    Returns:
        Tuple of (notes_string, warnings).
    """
    warnings: list[str] = []
    notes_parts: list[str] = []

    # Parse traits
    traits = ddb.get("traits", {})
    if traits:
        personality = traits.get("personalityTraits")
        if personality:
            notes_parts.append(f"Personality: {personality}")

        ideals = traits.get("ideals")
        if ideals:
            notes_parts.append(f"Ideals: {ideals}")

        bonds = traits.get("bonds")
        if bonds:
            notes_parts.append(f"Bonds: {bonds}")

        flaws = traits.get("flaws")
        if flaws:
            notes_parts.append(f"Flaws: {flaws}")

    # Parse notes
    notes_data = ddb.get("notes", {})
    if notes_data:
        # DDB notes can have various fields, we'll collect any that exist
        for key, value in notes_data.items():
            if value and isinstance(value, str):
                notes_parts.append(f"{key.title()}: {value}")

    notes = "\n\n".join(notes_parts)
    return notes, warnings


def map_currency(ddb: dict) -> tuple[str, list[str]]:
    """Format currency string for notes.

    Args:
        ddb: Raw D&D Beyond character JSON.

    Returns:
        Tuple of (currency_string, warnings).
    """
    warnings: list[str] = []
    currency = ddb.get("currencies", {})

    parts = []
    if currency.get("pp"):
        parts.append(f"{currency['pp']} pp")
    if currency.get("gp"):
        parts.append(f"{currency['gp']} gp")
    if currency.get("ep"):
        parts.append(f"{currency['ep']} ep")
    if currency.get("sp"):
        parts.append(f"{currency['sp']} sp")
    if currency.get("cp"):
        parts.append(f"{currency['cp']} cp")

    currency_str = ", ".join(parts) if parts else ""
    return currency_str, warnings


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

    # Map inventory
    try:
        inventory, warnings = map_inventory(ddb)
        character_data["inventory"] = inventory
        all_warnings.extend(warnings)
        mapped_fields.append("inventory")
    except Exception as e:
        all_warnings.append(f"Failed to map inventory: {e}")
        unmapped_fields.append("inventory")

    # Map equipment (requires inventory)
    try:
        equipment, warnings = map_equipment(ddb, character_data.get("inventory", []))
        character_data["equipment"] = equipment
        all_warnings.extend(warnings)
        mapped_fields.append("equipment")
    except Exception as e:
        all_warnings.append(f"Failed to map equipment: {e}")
        unmapped_fields.append("equipment")

    # Map spells and spell slots
    try:
        spell_data, warnings = map_spells(ddb)
        character_data.update(spell_data)
        all_warnings.extend(warnings)
        mapped_fields.extend(["spells_known", "spell_slots"])
    except Exception as e:
        all_warnings.append(f"Failed to map spells: {e}")
        unmapped_fields.extend(["spells_known", "spell_slots"])

    # Map features and traits
    try:
        features, warnings = map_features(ddb)
        character_data["features"] = features
        all_warnings.extend(warnings)
        mapped_fields.append("features")
    except Exception as e:
        all_warnings.append(f"Failed to map features: {e}")
        unmapped_fields.append("features")

    # Map notes
    try:
        notes, warnings = map_notes(ddb)
        currency, curr_warnings = map_currency(ddb)
        all_warnings.extend(warnings)
        all_warnings.extend(curr_warnings)

        # Combine notes and currency
        notes_parts = []
        if currency:
            notes_parts.append(f"Currency: {currency}")
        if notes:
            notes_parts.append(notes)
        character_data["notes"] = "\n\n".join(notes_parts)
        mapped_fields.append("notes")
    except Exception as e:
        all_warnings.append(f"Failed to map notes: {e}")
        unmapped_fields.append("notes")

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
