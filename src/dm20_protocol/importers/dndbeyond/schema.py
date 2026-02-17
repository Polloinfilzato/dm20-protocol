"""
D&D Beyond JSON schema constants and lookup tables.

These map DDB's internal IDs and field names to dm20 equivalents.
Based on community reverse-engineering of the v5 character-service endpoint.
"""

import re

# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------

DDB_API_BASE_URL = "https://character-service.dndbeyond.com/character/v5/character"

# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

# Matches: https://www.dndbeyond.com/characters/12345678[/anything]
DDB_CHARACTER_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?dndbeyond\.com/characters/(\d+)"
)

# ---------------------------------------------------------------------------
# Ability score stat IDs
# ---------------------------------------------------------------------------

STAT_ID_MAP: dict[int, str] = {
    1: "strength",
    2: "dexterity",
    3: "constitution",
    4: "intelligence",
    5: "wisdom",
    6: "charisma",
}

# Reverse lookup: ability name → DDB stat ID
STAT_NAME_TO_ID: dict[str, int] = {v: k for k, v in STAT_ID_MAP.items()}

# ---------------------------------------------------------------------------
# Alignment IDs
# ---------------------------------------------------------------------------

ALIGNMENT_MAP: dict[int, str] = {
    1: "Lawful Good",
    2: "Neutral Good",
    3: "Chaotic Good",
    4: "Lawful Neutral",
    5: "True Neutral",
    6: "Chaotic Neutral",
    7: "Lawful Evil",
    8: "Neutral Evil",
    9: "Chaotic Evil",
}

# ---------------------------------------------------------------------------
# Item filter types → dm20 item_type
# ---------------------------------------------------------------------------

ITEM_FILTER_TYPE_MAP: dict[str, str] = {
    "Weapon": "weapon",
    "Armor": "armor",
    "Potion": "consumable",
    "Scroll": "consumable",
    "Wondrous Item": "misc",
    "Ring": "misc",
    "Rod": "misc",
    "Staff": "weapon",
    "Wand": "misc",
    "Ammunition": "consumable",
    "Holy Symbol": "misc",
    "Adventuring Gear": "misc",
    "Tool": "misc",
    "Shield": "armor",
    "Other Gear": "misc",
}

# ---------------------------------------------------------------------------
# Spell school mapping (DDB name → dm20 name)
# ---------------------------------------------------------------------------

SPELL_SCHOOL_MAP: dict[str, str] = {
    "Abjuration": "Abjuration",
    "Conjuration": "Conjuration",
    "Divination": "Divination",
    "Enchantment": "Enchantment",
    "Evocation": "Evocation",
    "Illusion": "Illusion",
    "Necromancy": "Necromancy",
    "Transmutation": "Transmutation",
}

# ---------------------------------------------------------------------------
# Modifier types used in DDB's modifiers sections
# ---------------------------------------------------------------------------

# DDB modifier "type" values we care about
MODIFIER_TYPE_BONUS = "bonus"
MODIFIER_TYPE_PROFICIENCY = "proficiency"
MODIFIER_TYPE_LANGUAGE = "language"
MODIFIER_TYPE_SET = "set"  # used for stat overrides (e.g., headband of intellect)

# DDB modifier "subType" values for ability scores
ABILITY_SCORE_SUBTYPES: dict[str, str] = {
    "strength-score": "strength",
    "dexterity-score": "dexterity",
    "constitution-score": "constitution",
    "intelligence-score": "intelligence",
    "wisdom-score": "wisdom",
    "charisma-score": "charisma",
}

# DDB modifier "subType" values for saving throws
SAVING_THROW_SUBTYPES: dict[str, str] = {
    "strength-saving-throws": "strength",
    "dexterity-saving-throws": "dexterity",
    "constitution-saving-throws": "constitution",
    "intelligence-saving-throws": "intelligence",
    "wisdom-saving-throws": "wisdom",
    "charisma-saving-throws": "charisma",
}

# DDB modifier "subType" values for skill proficiencies
SKILL_SUBTYPES: dict[str, str] = {
    "acrobatics": "acrobatics",
    "animal-handling": "animal handling",
    "arcana": "arcana",
    "athletics": "athletics",
    "deception": "deception",
    "history": "history",
    "insight": "insight",
    "intimidation": "intimidation",
    "investigation": "investigation",
    "medicine": "medicine",
    "nature": "nature",
    "perception": "perception",
    "performance": "performance",
    "persuasion": "persuasion",
    "religion": "religion",
    "sleight-of-hand": "sleight of hand",
    "stealth": "stealth",
    "survival": "survival",
}

# ---------------------------------------------------------------------------
# Hit dice by class name
# ---------------------------------------------------------------------------

CLASS_HIT_DICE: dict[str, str] = {
    "Barbarian": "d12",
    "Bard": "d8",
    "Cleric": "d8",
    "Druid": "d8",
    "Fighter": "d10",
    "Monk": "d8",
    "Paladin": "d10",
    "Ranger": "d10",
    "Rogue": "d8",
    "Sorcerer": "d6",
    "Warlock": "d8",
    "Wizard": "d6",
    "Artificer": "d8",
    "Blood Hunter": "d10",
}

# ---------------------------------------------------------------------------
# Spellcasting ability by class name
# ---------------------------------------------------------------------------

CLASS_SPELLCASTING_ABILITY: dict[str, str] = {
    "Bard": "charisma",
    "Cleric": "wisdom",
    "Druid": "wisdom",
    "Paladin": "charisma",
    "Ranger": "wisdom",
    "Sorcerer": "charisma",
    "Warlock": "charisma",
    "Wizard": "intelligence",
    "Artificer": "intelligence",
}

# ---------------------------------------------------------------------------
# Modifier source sections in DDB JSON
# ---------------------------------------------------------------------------

MODIFIER_SECTIONS = ("race", "class", "background", "item", "feat", "condition")
