"""Integration tests for D&D Beyond character import pipeline."""

import pytest
import json
from pathlib import Path

from dm20_protocol.importers.dndbeyond.mapper import map_ddb_to_character
from dm20_protocol.importers.dndbeyond.fetcher import read_character_file


@pytest.fixture
def ddb_sample():
    """Load the sample DDB character JSON."""
    path = Path(__file__).parent / "fixtures" / "ddb_character_sample.json"
    with open(path) as f:
        return json.load(f)


class TestFullImportPipeline:
    """Test the complete import pipeline from JSON to Character."""

    def test_full_import_from_fixture(self, ddb_sample):
        """Import complete character from fixture and verify all fields."""
        result = map_ddb_to_character(ddb_sample)

        char = result.character

        # --- Identity ---
        assert char.name == "Thalion Nightbreeze"
        assert char.race.name == "Wood Elf"
        assert char.race.subrace == "Wood"
        assert char.character_class.name == "Ranger"
        assert char.character_class.level == 7
        assert char.character_class.subclass == "Gloom Stalker"
        assert char.background == "Outlander"
        assert char.alignment == "Chaotic Good"

        # --- Abilities ---
        assert char.abilities["strength"].score == 10
        assert char.abilities["dexterity"].score == 16  # 14 + 2 racial
        assert char.abilities["constitution"].score == 14
        assert char.abilities["intelligence"].score == 12
        assert char.abilities["wisdom"].score == 16  # 15 + 1 racial
        assert char.abilities["charisma"].score == 8

        # Verify modifiers are calculated correctly
        assert char.abilities["dexterity"].mod == 3
        assert char.abilities["wisdom"].mod == 3
        assert char.abilities["constitution"].mod == 2

        # --- Combat Stats ---
        assert char.hit_points_max == 59  # 45 + (2 * 7)
        assert char.hit_points_current == 54  # 59 - 5
        assert char.temporary_hit_points == 3
        assert char.armor_class == 15
        assert char.speed == 35
        assert char.experience_points == 23000

        # --- Proficiencies ---
        assert "perception" in char.skill_proficiencies
        assert "stealth" in char.skill_proficiencies
        assert "nature" in char.skill_proficiencies
        assert "survival" in char.skill_proficiencies
        assert "athletics" in char.skill_proficiencies

        assert "strength" in char.saving_throw_proficiencies
        assert "dexterity" in char.saving_throw_proficiencies

        assert "Common" in char.languages
        assert "Elvish" in char.languages
        assert "Sylvan" in char.languages

        # --- Inventory ---
        assert len(char.inventory) == 4
        weapon_names = [i.name for i in char.inventory if i.item_type == "weapon"]
        assert "Longbow" in weapon_names
        assert "Shortsword" in weapon_names

        # --- Equipment ---
        assert char.equipment["weapon_main"] is not None
        assert char.equipment["armor"] is not None
        assert char.equipment["armor"].name == "Studded Leather"

        # --- Spells ---
        assert len(char.spells_known) == 3
        spell_names = [s.name for s in char.spells_known]
        assert "Hunter's Mark" in spell_names
        assert "Cure Wounds" in spell_names
        assert "Pass without Trace" in spell_names

        # Verify spell slots
        assert char.spell_slots[1] == 4
        assert char.spell_slots[2] == 3
        assert char.spellcasting_ability == "wisdom"

        # --- Features ---
        feature_names = [f.name for f in char.features]
        # Class features
        assert "Favored Enemy" in feature_names
        assert "Natural Explorer" in feature_names
        assert "Fighting Style" in feature_names
        assert "Dread Ambusher" in feature_names
        # Racial traits
        assert "Darkvision" in feature_names
        assert "Fey Ancestry" in feature_names
        assert "Mask of the Wild" in feature_names
        # Feats
        assert "Sharpshooter" in feature_names

        # --- Notes ---
        assert "newborn pups" in char.notes
        assert "seasons" in char.notes
        assert "unspoiled wilderness" in char.notes
        assert "slow to trust" in char.notes
        assert "150 gp" in char.notes
        assert "Tracking the shadow beast" in char.notes

    def test_import_result_fields(self, ddb_sample):
        """Verify ImportResult metadata."""
        result = map_ddb_to_character(ddb_sample, player_name="Alice")

        # Should have mapped fields
        assert len(result.mapped_fields) > 0
        assert "name" in result.mapped_fields
        assert "abilities" in result.mapped_fields
        assert "inventory" in result.mapped_fields

        # Warnings should be a list
        assert isinstance(result.warnings, list)

        # Source metadata
        assert result.source == "url"
        assert result.source_id == 98765432

        # Player name should be set
        assert result.character.player_name == "Alice"

    def test_partial_import_missing_inventory(self):
        """Handle character with missing inventory gracefully."""
        ddb = {
            "id": 111,
            "name": "Test Character",
            "race": {"fullName": "Dwarf"},
            "classes": [{"level": 3, "definition": {"name": "Cleric"}}],
            "stats": [{"id": i, "value": 12} for i in range(1, 7)],
            "bonusStats": [],
            "overrideStats": [],
            "modifiers": {},
            "baseHitPoints": 20,
            "removedHitPoints": 0,
            "temporaryHitPoints": 0,
            "armorClass": 16,
            "currentXp": 900,
            # No inventory key
        }

        result = map_ddb_to_character(ddb)

        # Should still create valid character
        assert result.character.name == "Test Character"
        assert result.character.inventory == []
        assert result.character.equipment["weapon_main"] is None

    def test_partial_import_missing_spells(self):
        """Handle non-caster character with missing spells section."""
        ddb = {
            "id": 222,
            "name": "Fighter Bob",
            "race": {"fullName": "Human"},
            "classes": [{"level": 5, "definition": {"name": "Fighter"}}],
            "stats": [{"id": i, "value": 14} for i in range(1, 7)],
            "bonusStats": [],
            "overrideStats": [],
            "modifiers": {},
            "baseHitPoints": 40,
            "removedHitPoints": 0,
            "temporaryHitPoints": 0,
            "armorClass": 18,
            "currentXp": 6500,
            "inventory": [],
            # No classSpells key
        }

        result = map_ddb_to_character(ddb)

        assert result.character.spells_known == []
        assert result.character.spell_slots == {}
        assert result.character.spellcasting_ability is None

    def test_import_from_file(self):
        """Test reading and importing from file."""
        fixture_path = Path(__file__).parent / "fixtures" / "ddb_character_sample.json"
        ddb = read_character_file(str(fixture_path))
        result = map_ddb_to_character(ddb)

        # Should successfully import
        assert result.character.name == "Thalion Nightbreeze"
        assert result.character.character_class.level == 7

    def test_character_validation(self, ddb_sample):
        """Verify character passes Pydantic validation."""
        result = map_ddb_to_character(ddb_sample)

        # Should be valid Pydantic model
        char = result.character
        assert char.model_dump() is not None

        # Proficiency bonus should be auto-calculated
        # Level 7 = proficiency +3
        assert char.proficiency_bonus == 3

    def test_graceful_degradation(self):
        """Verify import succeeds even with minimal data."""
        minimal_ddb = {
            "id": 999,
            "name": "Minimal",
            "race": {},
            "classes": [],
            "stats": [],
            "bonusStats": [],
            "overrideStats": [],
            "modifiers": {},
            "armorClass": 10,
        }

        result = map_ddb_to_character(minimal_ddb)

        # Should create character with defaults
        assert result.character.name == "Minimal"
        assert result.character.character_class.name == "Fighter"  # default
        assert len(result.warnings) > 0  # Should warn about missing data


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_very_high_level_character(self):
        """Import level 20 character."""
        ddb = {
            "id": 333,
            "name": "Epic Hero",
            "race": {"fullName": "Human"},
            "classes": [{"level": 20, "definition": {"name": "Wizard"}}],
            "stats": [{"id": i, "value": 20} for i in range(1, 7)],
            "bonusStats": [],
            "overrideStats": [],
            "modifiers": {},
            "baseHitPoints": 100,
            "removedHitPoints": 0,
            "temporaryHitPoints": 0,
            "armorClass": 15,
            "currentXp": 355000,
        }

        result = map_ddb_to_character(ddb)

        assert result.character.character_class.level == 20
        assert result.character.proficiency_bonus == 6  # Level 20 proficiency

    def test_multiclass_character(self):
        """Import multiclass character (picks highest level class)."""
        ddb = {
            "id": 444,
            "name": "Multiclass Hero",
            "race": {"fullName": "Half-Elf"},
            "classes": [
                {"level": 5, "definition": {"name": "Rogue"}},
                {"level": 3, "definition": {"name": "Fighter"}},
            ],
            "stats": [{"id": i, "value": 14} for i in range(1, 7)],
            "bonusStats": [],
            "overrideStats": [],
            "modifiers": {},
            "baseHitPoints": 50,
            "removedHitPoints": 0,
            "temporaryHitPoints": 0,
            "armorClass": 16,
            "currentXp": 14000,
        }

        result = map_ddb_to_character(ddb)

        # Should pick Rogue (level 5)
        assert result.character.character_class.name == "Rogue"
        assert result.character.character_class.level == 5

    def test_character_with_no_equipment(self, ddb_sample):
        """Character with inventory but nothing equipped."""
        # Modify sample to unequip everything
        ddb_modified = ddb_sample.copy()
        for item in ddb_modified.get("inventory", []):
            item["equipped"] = False

        result = map_ddb_to_character(ddb_modified)

        # Should have inventory but no equipped items
        assert len(result.character.inventory) == 4
        assert result.character.equipment["weapon_main"] is None
        assert result.character.equipment["armor"] is None
