"""Tests for sheets/parser.py — YAML frontmatter extraction and validation."""

import pytest
from pathlib import Path

from dm20_protocol.sheets.parser import CharacterSheetParser, ParseError


VALID_SHEET = """---
# System
dm20_id: testID01
dm20_version: 1
dm20_last_sync: "2026-02-17T14:30:00"

# Identity
name: Aldric Stormwind
player: Marco
class: Ranger
level: 5
subclass: Hunter
race: Wood Elf
alignment: Neutral Good

# Abilities
strength: 12
dexterity: 18
constitution: 14
intelligence: 10
wisdom: 16
charisma: 8

# Combat
hit_points_current: 35
hit_points_max: 42
inspiration: false

# Text
notes: Tracking a group of gnolls.
---

# Aldric Stormwind

> *Level 5 Wood Elf Ranger (Hunter)*

This is the body content.
"""


class TestParseString:

    def test_valid_sheet(self) -> None:
        data = CharacterSheetParser.parse_string(VALID_SHEET)
        assert data["name"] == "Aldric Stormwind"
        assert data["level"] == 5
        assert data["strength"] == 12
        assert data["dm20_id"] == "testID01"

    def test_boolean_fields(self) -> None:
        data = CharacterSheetParser.parse_string(VALID_SHEET)
        assert data["inspiration"] is False

    def test_missing_opening_delimiter(self) -> None:
        content = "name: Test\n---\nBody"
        with pytest.raises(ParseError, match="Missing opening"):
            CharacterSheetParser.parse_string(content)

    def test_missing_closing_delimiter(self) -> None:
        content = "---\nname: Test\nNo closing"
        with pytest.raises(ParseError, match="Missing closing"):
            CharacterSheetParser.parse_string(content)

    def test_invalid_yaml(self) -> None:
        content = "---\n: invalid: yaml: [broken\n---\nBody"
        with pytest.raises(ParseError, match="Invalid YAML"):
            CharacterSheetParser.parse_string(content)

    def test_non_dict_frontmatter(self) -> None:
        content = "---\n- item1\n- item2\n---\nBody"
        with pytest.raises(ParseError, match="must be a mapping"):
            CharacterSheetParser.parse_string(content)

    def test_leading_whitespace(self) -> None:
        content = "  \n---\nname: Test\n---\nBody"
        data = CharacterSheetParser.parse_string(content)
        assert data["name"] == "Test"

    def test_complex_values(self) -> None:
        content = """---
name: Test
skill_proficiencies: [Perception, Stealth]
spell_slots: {'1': 4, '2': 3}
inventory:
  - {name: Sword, quantity: 1, type: weapon}
---
Body
"""
        data = CharacterSheetParser.parse_string(content)
        assert data["skill_proficiencies"] == ["Perception", "Stealth"]
        assert data["inventory"][0]["name"] == "Sword"


class TestParseFile:

    def test_parse_file(self, tmp_path: Path) -> None:
        sheet = tmp_path / "test.md"
        sheet.write_text(VALID_SHEET, encoding="utf-8")
        data = CharacterSheetParser.parse_file(sheet)
        assert data["name"] == "Aldric Stormwind"

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(ParseError, match="Cannot read file"):
            CharacterSheetParser.parse_file(tmp_path / "nonexistent.md")


class TestFrontmatterHash:

    def test_hash_deterministic(self) -> None:
        h1 = CharacterSheetParser.frontmatter_hash(VALID_SHEET)
        h2 = CharacterSheetParser.frontmatter_hash(VALID_SHEET)
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_changes_with_content(self) -> None:
        modified = VALID_SHEET.replace("level: 5", "level: 6")
        h1 = CharacterSheetParser.frontmatter_hash(VALID_SHEET)
        h2 = CharacterSheetParser.frontmatter_hash(modified)
        assert h1 != h2

    def test_hash_ignores_body(self) -> None:
        modified = VALID_SHEET.replace("This is the body content.", "Totally different body.")
        h1 = CharacterSheetParser.frontmatter_hash(VALID_SHEET)
        h2 = CharacterSheetParser.frontmatter_hash(modified)
        assert h1 == h2


class TestValidation:

    def test_valid_data_no_warnings(self) -> None:
        data = CharacterSheetParser.parse_string(VALID_SHEET)
        warnings = CharacterSheetParser.validate_frontmatter(data)
        assert warnings == []

    def test_ability_score_out_of_range(self) -> None:
        data = {"dm20_id": "x", "strength": 0, "dexterity": 31}
        warnings = CharacterSheetParser.validate_frontmatter(data)
        assert any("strength" in w for w in warnings)
        assert any("dexterity" in w for w in warnings)

    def test_level_out_of_range(self) -> None:
        data = {"dm20_id": "x", "level": 21}
        warnings = CharacterSheetParser.validate_frontmatter(data)
        assert any("level" in w for w in warnings)

    def test_negative_hp(self) -> None:
        data = {"dm20_id": "x", "hit_points_current": -5}
        warnings = CharacterSheetParser.validate_frontmatter(data)
        assert any("hit_points_current" in w for w in warnings)

    def test_missing_dm20_id(self) -> None:
        data = {"name": "Test"}
        warnings = CharacterSheetParser.validate_frontmatter(data)
        assert any("dm20_id" in w for w in warnings)


class TestExtractSyncMetadata:

    def test_extract_all_fields(self) -> None:
        data = CharacterSheetParser.parse_string(VALID_SHEET)
        dm20_id, version, last_sync = CharacterSheetParser.extract_sync_metadata(data)
        assert dm20_id == "testID01"
        assert version == 1
        assert last_sync == "2026-02-17T14:30:00"

    def test_missing_fields_default(self) -> None:
        dm20_id, version, last_sync = CharacterSheetParser.extract_sync_metadata({})
        assert dm20_id == ""
        assert version == 0
        assert last_sync == ""
