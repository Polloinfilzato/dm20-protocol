"""Tests for D&D Beyond character mapper."""

import pytest
import json
from pathlib import Path

from dm20_protocol.importers.dndbeyond.mapper import (
    map_identity,
    map_abilities,
    map_combat,
    map_proficiencies,
    map_inventory,
    map_equipment,
    map_spells,
    map_features,
    map_notes,
    map_currency,
    map_ddb_to_character,
)
from dm20_protocol.models import AbilityScore


@pytest.fixture
def ddb_sample():
    """Load the sample DDB character JSON."""
    path = Path(__file__).parent / "fixtures" / "ddb_character_sample.json"
    with open(path) as f:
        return json.load(f)


class TestMapIdentity:
    """Test identity field mapping."""

    def test_map_identity(self, ddb_sample):
        """Map basic identity fields from sample character."""
        result, warnings = map_identity(ddb_sample)

        assert result["name"] == "Thalion Nightbreeze"
        assert result["race"].name == "Wood Elf"
        assert result["race"].subrace == "Wood"
        assert result["character_class"].name == "Ranger"
        assert result["character_class"].level == 7
        assert result["character_class"].subclass == "Gloom Stalker"
        assert result["character_class"].hit_dice == "d10"
        assert result["background"] == "Outlander"
        assert result["alignment"] == "Chaotic Good"
        assert result["spellcasting_ability"] == "wisdom"

    def test_map_identity_no_classes(self):
        """Handle missing classes with default."""
        ddb = {
            "name": "Classless Character",
            "race": {"fullName": "Human"},
            "classes": [],
        }

        result, warnings = map_identity(ddb)

        assert result["character_class"].name == "Fighter"
        assert result["character_class"].level == 1
        assert len(warnings) > 0
        assert "Fighter" in warnings[0]

    def test_map_identity_no_subclass(self):
        """Handle character without subclass."""
        ddb = {
            "name": "Low Level Fighter",
            "race": {"fullName": "Human"},
            "classes": [
                {
                    "level": 2,
                    "definition": {"name": "Fighter"},
                    "subclassDefinition": None,
                }
            ],
        }

        result, warnings = map_identity(ddb)

        assert result["character_class"].subclass is None

    def test_map_identity_multiclass(self):
        """Pick highest level class for multiclass character."""
        ddb = {
            "name": "Multiclass Character",
            "race": {"fullName": "Half-Elf"},
            "classes": [
                {"level": 3, "definition": {"name": "Rogue"}},
                {"level": 5, "definition": {"name": "Fighter"}},
            ],
        }

        result, warnings = map_identity(ddb)

        # Should pick Fighter (level 5)
        assert result["character_class"].name == "Fighter"
        assert result["character_class"].level == 5


class TestMapAbilities:
    """Test ability score mapping."""

    def test_map_abilities(self, ddb_sample):
        """Map ability scores with racial bonuses."""
        result, warnings = map_abilities(ddb_sample)

        # DEX: base 14 + racial 2 = 16
        assert result["dexterity"].score == 16
        # WIS: base 15 + racial 1 = 16
        assert result["wisdom"].score == 16
        # STR: base 10, no bonuses
        assert result["strength"].score == 10
        # CON: base 14, no bonuses
        assert result["constitution"].score == 14
        # INT: base 12, no bonuses
        assert result["intelligence"].score == 12
        # CHA: base 8, no bonuses
        assert result["charisma"].score == 8

    def test_map_abilities_with_override(self):
        """Handle override stats (e.g., magic items setting stats)."""
        ddb = {
            "stats": [
                {"id": 1, "value": 10},
                {"id": 2, "value": 12},
                {"id": 3, "value": 14},
                {"id": 4, "value": 8},
                {"id": 5, "value": 13},
                {"id": 6, "value": 10},
            ],
            "bonusStats": [
                {"id": i, "value": 0} for i in range(1, 7)
            ],
            "overrideStats": [
                {"id": 1, "value": None},
                {"id": 2, "value": None},
                {"id": 3, "value": None},
                {"id": 4, "value": 19},  # Headband of Intellect
                {"id": 5, "value": None},
                {"id": 6, "value": None},
            ],
            "modifiers": {},
        }

        result, warnings = map_abilities(ddb)

        # INT should use override value
        assert result["intelligence"].score == 19
        # Others should use base
        assert result["strength"].score == 10
        assert result["dexterity"].score == 12

    def test_map_abilities_base_only(self):
        """Map abilities with no modifiers."""
        ddb = {
            "stats": [
                {"id": 1, "value": 15},
                {"id": 2, "value": 14},
                {"id": 3, "value": 13},
                {"id": 4, "value": 12},
                {"id": 5, "value": 10},
                {"id": 6, "value": 8},
            ],
            "bonusStats": [],
            "overrideStats": [],
            "modifiers": {},
        }

        result, warnings = map_abilities(ddb)

        assert result["strength"].score == 15
        assert result["dexterity"].score == 14
        assert result["constitution"].score == 13


class TestMapCombat:
    """Test combat stats mapping."""

    def test_map_combat(self, ddb_sample):
        """Map combat stats from sample character."""
        abilities, _ = map_abilities(ddb_sample)
        level = 7

        result, warnings = map_combat(ddb_sample, abilities, level)

        # HP max = baseHitPoints(45) + bonusHitPoints(0) + (CON_mod(2) * level(7))
        # = 45 + 0 + 14 = 59
        assert result["hit_points_max"] == 59
        # HP current = max - removedHitPoints(5) = 54
        assert result["hit_points_current"] == 54
        # Temp HP
        assert result["temporary_hit_points"] == 3
        # AC
        assert result["armor_class"] == 15
        # Speed
        assert result["speed"] == 35
        # XP
        assert result["experience_points"] == 23000

    def test_map_combat_override_hp(self):
        """Handle overridden HP from manual adjustment."""
        ddb = {
            "baseHitPoints": 50,
            "bonusHitPoints": 10,
            "overrideHitPoints": 100,
            "removedHitPoints": 20,
            "temporaryHitPoints": 5,
            "armorClass": 18,
            "currentXp": 5000,
            "race": {"weightSpeeds": {"normal": {"walk": 30}}},
        }

        abilities = {
            "constitution": AbilityScore(score=14)  # +2 mod
        }

        result, warnings = map_combat(ddb, abilities, level=5)

        # Should use override
        assert result["hit_points_max"] == 100
        assert result["hit_points_current"] == 80  # 100 - 20

    def test_map_combat_minimum_hp(self):
        """Ensure HP never goes below 1."""
        ddb = {
            "baseHitPoints": 0,
            "bonusHitPoints": 0,
            "removedHitPoints": 50,
            "temporaryHitPoints": 0,
            "armorClass": 10,
            "currentXp": 0,
            "race": {"weightSpeeds": {"normal": {"walk": 30}}},
        }

        abilities = {
            "constitution": AbilityScore(score=10)  # +0 mod
        }

        result, warnings = map_combat(ddb, abilities, level=1)

        # HP max should be at least 1
        assert result["hit_points_max"] == 1


class TestMapProficiencies:
    """Test proficiency mapping."""

    def test_map_proficiencies(self, ddb_sample):
        """Map skill, save, and language proficiencies."""
        result, warnings = map_proficiencies(ddb_sample)

        # Skills from class and race
        assert "perception" in result["skill_proficiencies"]
        assert "stealth" in result["skill_proficiencies"]
        assert "nature" in result["skill_proficiencies"]
        assert "survival" in result["skill_proficiencies"]
        assert "athletics" in result["skill_proficiencies"]

        # Saves
        assert "strength" in result["saving_throw_proficiencies"]
        assert "dexterity" in result["saving_throw_proficiencies"]

        # Languages
        assert "Common" in result["languages"]
        assert "Elvish" in result["languages"]
        assert "Sylvan" in result["languages"]

    def test_map_proficiencies_deduplication(self, ddb_sample):
        """Ensure duplicate proficiencies are deduplicated."""
        result, warnings = map_proficiencies(ddb_sample)

        # Athletics appears in both class and background
        # Should only appear once
        athletics_count = result["skill_proficiencies"].count("athletics")
        assert athletics_count == 1


class TestMapInventory:
    """Test inventory item mapping."""

    def test_map_inventory(self, ddb_sample):
        """Map inventory items from sample character."""
        result, warnings = map_inventory(ddb_sample)

        assert len(result) == 4

        # Check Longbow
        longbow = next((i for i in result if i.name == "Longbow"), None)
        assert longbow is not None
        assert longbow.item_type == "weapon"
        assert longbow.properties["damage"] == "1d8"
        assert longbow.properties["equipped"] is True
        assert longbow.weight == 2

        # Check Healing Potion
        potion = next((i for i in result if i.name == "Healing Potion"), None)
        assert potion is not None
        assert potion.item_type == "consumable"
        assert potion.properties["equipped"] is False

    def test_map_inventory_armor(self, ddb_sample):
        """Map armor items with AC."""
        result, warnings = map_inventory(ddb_sample)

        armor = next((i for i in result if i.name == "Studded Leather"), None)
        assert armor is not None
        assert armor.item_type == "armor"
        assert armor.properties["armor_class"] == 12
        assert armor.weight == 13


class TestMapEquipment:
    """Test equipment slot mapping."""

    def test_map_equipment(self, ddb_sample):
        """Detect equipped items and assign to slots."""
        items, _ = map_inventory(ddb_sample)
        result, warnings = map_equipment(ddb_sample, items)

        # Should have weapons equipped
        assert result["weapon_main"] is not None
        assert result["weapon_main"].name in ["Longbow", "Shortsword"]

        # Should have armor equipped
        assert result["armor"] is not None
        assert result["armor"].name == "Studded Leather"

    def test_map_equipment_unequipped(self):
        """Handle character with no equipped items."""
        ddb = {"inventory": []}
        items = []

        result, warnings = map_equipment(ddb, items)

        assert result["weapon_main"] is None
        assert result["weapon_off"] is None
        assert result["armor"] is None
        assert result["shield"] is None


class TestMapSpells:
    """Test spell mapping."""

    def test_map_spells(self, ddb_sample):
        """Map spells and spell slots from sample character."""
        result, warnings = map_spells(ddb_sample)

        # Check spell count
        assert len(result["spells_known"]) == 3

        # Check Hunter's Mark
        hunters_mark = next((s for s in result["spells_known"] if s.name == "Hunter's Mark"), None)
        assert hunters_mark is not None
        assert hunters_mark.level == 1
        assert hunters_mark.school == "Divination"
        assert hunters_mark.range == 90
        assert "V" in hunters_mark.components
        assert "S" in hunters_mark.components
        assert hunters_mark.prepared is True
        assert hunters_mark.casting_time == "1 Bonus Action"
        assert hunters_mark.duration == "1 Hour"

        # Check Pass without Trace (has material component)
        pass_without_trace = next((s for s in result["spells_known"] if s.name == "Pass without Trace"), None)
        assert pass_without_trace is not None
        assert pass_without_trace.level == 2
        assert "M" in pass_without_trace.components

        # Check spell slots (level 7 Ranger)
        assert result["spell_slots"][1] == 4
        assert result["spell_slots"][2] == 3

    def test_map_spells_no_spells(self):
        """Handle non-caster character."""
        ddb = {
            "classSpells": [],
            "classes": [],
        }

        result, warnings = map_spells(ddb)

        assert result["spells_known"] == []
        assert result["spell_slots"] == {}


class TestMapFeatures:
    """Test feature mapping."""

    def test_map_features(self, ddb_sample):
        """Map class features, racial traits, and feats."""
        result, warnings = map_features(ddb_sample)

        # Should have class features
        favored_enemy = next((f for f in result if f.name == "Favored Enemy"), None)
        assert favored_enemy is not None
        assert "Ranger" in favored_enemy.source
        assert favored_enemy.level_gained == 1

        # Should have racial traits
        darkvision = next((f for f in result if f.name == "Darkvision"), None)
        assert darkvision is not None
        assert "Elf" in darkvision.source

        # Should have feats
        sharpshooter = next((f for f in result if f.name == "Sharpshooter"), None)
        assert sharpshooter is not None
        assert sharpshooter.source == "Feat"

    def test_map_features_level_filtering(self):
        """Only include features character has access to."""
        ddb = {
            "classes": [
                {
                    "level": 3,
                    "definition": {
                        "name": "Fighter"
                    },
                    "classFeatures": [
                        {
                            "definition": {
                                "name": "Fighting Style",
                                "description": "Level 1 feature",
                                "requiredLevel": 1
                            }
                        },
                        {
                            "definition": {
                                "name": "Action Surge",
                                "description": "Level 2 feature",
                                "requiredLevel": 2
                            }
                        },
                        {
                            "definition": {
                                "name": "Extra Attack",
                                "description": "Level 5 feature",
                                "requiredLevel": 5
                            }
                        }
                    ]
                }
            ],
            "race": {"racialTraits": []},
            "feats": []
        }

        result, warnings = map_features(ddb)

        feature_names = [f.name for f in result]
        assert "Fighting Style" in feature_names
        assert "Action Surge" in feature_names
        # Extra Attack requires level 5, character is level 3
        assert "Extra Attack" not in feature_names


class TestMapNotes:
    """Test notes mapping."""

    def test_map_notes(self, ddb_sample):
        """Map personality traits and notes."""
        result, warnings = map_notes(ddb_sample)

        assert "Personality" in result
        assert "newborn pups" in result
        assert "Ideals" in result
        assert "seasons" in result
        assert "Bonds" in result
        assert "unspoiled wilderness" in result
        assert "Flaws" in result
        assert "slow to trust" in result

    def test_map_notes_empty(self):
        """Handle character with no traits."""
        ddb = {
            "traits": {},
            "notes": {}
        }

        result, warnings = map_notes(ddb)

        assert result == ""


class TestMapCurrency:
    """Test currency formatting."""

    def test_map_currency(self, ddb_sample):
        """Format currency string."""
        result, warnings = map_currency(ddb_sample)

        assert "2 pp" in result
        assert "150 gp" in result
        assert "30 sp" in result
        assert "15 cp" in result

    def test_map_currency_empty(self):
        """Handle character with no money."""
        ddb = {
            "currencies": {}
        }

        result, warnings = map_currency(ddb)

        assert result == ""


class TestMapDdbToCharacter:
    """Test full character mapping orchestration."""

    def test_full_mapping(self, ddb_sample):
        """Map complete character from sample."""
        import_result = map_ddb_to_character(ddb_sample, player_name="Test Player")

        char = import_result.character

        # Verify identity
        assert char.name == "Thalion Nightbreeze"
        assert char.player_name == "Test Player"
        assert char.race.name == "Wood Elf"
        assert char.character_class.name == "Ranger"
        assert char.character_class.level == 7

        # Verify abilities
        assert char.abilities["dexterity"].score == 16
        assert char.abilities["wisdom"].score == 16

        # Verify combat
        assert char.hit_points_max == 59
        assert char.armor_class == 15

        # Verify inventory
        assert len(char.inventory) == 4

        # Verify spells
        assert len(char.spells_known) == 3

        # Verify features
        assert len(char.features) > 0

        # Verify metadata
        assert import_result.source == "url"
        assert import_result.source_id == 98765432
        assert len(import_result.mapped_fields) > 0

    def test_partial_import_missing_inventory(self):
        """Handle character with missing optional sections."""
        ddb = {
            "id": 123,
            "name": "Minimal Character",
            "race": {"fullName": "Human"},
            "classes": [{"level": 1, "definition": {"name": "Fighter"}}],
            "stats": [
                {"id": i, "value": 10} for i in range(1, 7)
            ],
            "bonusStats": [],
            "overrideStats": [],
            "modifiers": {},
            "baseHitPoints": 10,
            "removedHitPoints": 0,
            "temporaryHitPoints": 0,
            "armorClass": 10,
            "currentXp": 0,
            # No inventory
        }

        result = map_ddb_to_character(ddb)

        # Should still create valid character
        assert result.character.name == "Minimal Character"
        assert result.character.inventory == []

    def test_partial_import_missing_spells(self):
        """Handle non-caster character."""
        ddb = {
            "id": 456,
            "name": "Barbarian",
            "race": {"fullName": "Half-Orc"},
            "classes": [{"level": 5, "definition": {"name": "Barbarian"}}],
            "stats": [
                {"id": i, "value": 15} for i in range(1, 7)
            ],
            "bonusStats": [],
            "overrideStats": [],
            "modifiers": {},
            "baseHitPoints": 50,
            "removedHitPoints": 0,
            "temporaryHitPoints": 0,
            "armorClass": 14,
            "currentXp": 6500,
            # No classSpells
        }

        result = map_ddb_to_character(ddb)

        assert result.character.spells_known == []
        assert result.character.spell_slots == {}
