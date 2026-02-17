"""Tests for sheets/renderer.py — Character → Markdown rendering."""

import tempfile
from pathlib import Path

import pytest
import yaml

from dm20_protocol.models import (
    AbilityScore,
    Character,
    CharacterClass,
    Feature,
    Item,
    Race,
    Spell,
)
from dm20_protocol.sheets.parser import CharacterSheetParser
from dm20_protocol.sheets.renderer import (
    CharacterSheetRenderer,
    _render_body,
    _safe_filename,
)


@pytest.fixture
def sample_character() -> Character:
    """A fully-populated character for testing."""
    return Character(
        id="testID01",
        name="Aldric Stormwind",
        player_name="Marco",
        character_class=CharacterClass(
            name="Ranger", level=5, hit_dice="1d10", subclass="Hunter"
        ),
        race=Race(name="Wood Elf", subrace="Wood", traits=["Darkvision"]),
        background="Outlander",
        alignment="Neutral Good",
        description="A tall elf with weathered features.",
        bio="Raised in the Silverwood forest.",
        abilities={
            "strength": AbilityScore(score=12),
            "dexterity": AbilityScore(score=18),
            "constitution": AbilityScore(score=14),
            "intelligence": AbilityScore(score=10),
            "wisdom": AbilityScore(score=16),
            "charisma": AbilityScore(score=8),
        },
        experience_points=6500,
        armor_class=16,
        hit_points_max=42,
        hit_points_current=35,
        temporary_hit_points=0,
        speed=35,
        hit_dice_type="d10",
        hit_dice_remaining="5d10",
        inspiration=False,
        skill_proficiencies=["Perception", "Stealth", "Survival"],
        saving_throw_proficiencies=["strength", "dexterity"],
        tool_proficiencies=["Herbalism Kit"],
        languages=["Common", "Elvish"],
        spellcasting_ability="wisdom",
        spell_slots={1: 4, 2: 3},
        spell_slots_used={1: 1, 2: 0},
        spells_known=[
            Spell(
                id="sp01", name="Cure Wounds", level=1, school="evocation",
                casting_time="1 action", range=5, duration="instantaneous",
                components=["V", "S"], description="Heal a creature.", prepared=True,
            ),
            Spell(
                id="sp02", name="Hunter's Mark", level=1, school="divination",
                casting_time="1 bonus action", range=90, duration="concentration, up to 1 hour",
                components=["V"], description="Mark a target.", prepared=True,
            ),
        ],
        inventory=[
            Item(id="it01", name="Longbow", quantity=1, item_type="weapon", weight=2.0, value="50 gp"),
            Item(id="it02", name="Healing Potion", quantity=3, item_type="consumable"),
        ],
        equipment={
            "weapon_main": Item(id="eq01", name="Longbow", item_type="weapon"),
            "weapon_off": None,
            "armor": Item(id="eq02", name="Studded Leather", item_type="armor"),
            "shield": None,
        },
        features=[
            Feature(name="Favored Enemy", source="Ranger 1", description="Advantage on Wisdom (Survival) checks to track favored enemies.", level_gained=1),
        ],
        features_and_traits=["Natural Explorer"],
        notes="Tracking a group of gnolls.",
    )


@pytest.fixture
def minimal_character() -> Character:
    """A minimal character with no spells, equipment, or features."""
    return Character(
        name="Thog",
        character_class=CharacterClass(name="Barbarian", level=1, hit_dice="1d12"),
        race=Race(name="Half-Orc"),
        hit_points_max=14,
        hit_points_current=14,
    )


@pytest.fixture
def sheets_dir(tmp_path: Path) -> Path:
    return tmp_path / "sheets"


class TestRendererOutput:
    """Test the full rendered Markdown output."""

    def test_render_contains_frontmatter(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        content = renderer.render(sample_character)
        assert content.startswith("---\n")
        assert "\n---\n" in content  # closing frontmatter

    def test_frontmatter_is_valid_yaml(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        content = renderer.render(sample_character)
        # Extract frontmatter
        parts = content.split("---", 2)
        assert len(parts) >= 3
        fm = yaml.safe_load(parts[1])
        assert isinstance(fm, dict)
        assert fm["name"] == "Aldric Stormwind"
        assert fm["dm20_id"] == "testID01"

    def test_body_contains_title(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        content = renderer.render(sample_character)
        assert "# Aldric Stormwind" in content

    def test_body_contains_ability_table(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        content = renderer.render(sample_character)
        assert "## Ability Scores" in content
        assert "**18** (+4)" in content  # DEX
        assert "**8** (-1)" in content   # CHA

    def test_body_contains_combat_table(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        content = renderer.render(sample_character)
        assert "## Combat" in content
        assert "35/42" in content  # HP
        assert "16" in content     # AC

    def test_body_contains_spellcasting(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        content = renderer.render(sample_character)
        assert "## Spellcasting" in content
        assert "Cure Wounds" in content
        assert "Hunter's Mark" in content

    def test_body_contains_inventory_table(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        content = renderer.render(sample_character)
        assert "### Inventory" in content
        assert "Longbow" in content
        assert "Healing Potion" in content

    def test_body_contains_features(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        content = renderer.render(sample_character)
        assert "## Features & Traits" in content
        assert "Favored Enemy" in content
        assert "Natural Explorer" in content

    def test_body_contains_text_sections(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        content = renderer.render(sample_character)
        assert "## Description" in content
        assert "A tall elf" in content
        assert "## Bio" in content
        assert "## Notes" in content

    def test_body_contains_footer(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        content = renderer.render(sample_character)
        assert "Generated by dm20-protocol" in content


class TestMinimalCharacter:
    """Test rendering with a minimal character (no spells, features, etc.)."""

    def test_no_spellcasting_section(self, minimal_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        content = renderer.render(minimal_character)
        assert "## Spellcasting" not in content

    def test_no_features_section_if_empty(self, sheets_dir: Path) -> None:
        char = Character(
            name="Nobody",
            character_class=CharacterClass(name="Fighter", level=1, hit_dice="1d10"),
            race=Race(name="Human"),
        )
        renderer = CharacterSheetRenderer(sheets_dir)
        content = renderer.render(char)
        assert "## Features & Traits" not in content

    def test_empty_equipment(self, minimal_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        content = renderer.render(minimal_character)
        assert "No items equipped" in content


class TestFileOperations:
    """Test write/delete/rename operations."""

    def test_write_creates_file(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        path, hash_val = renderer.write(sample_character)
        assert path.exists()
        assert path.name == "Aldric Stormwind.md"
        assert len(hash_val) == 64  # SHA-256 hex digest

    def test_write_is_atomic(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        path, _ = renderer.write(sample_character)
        # No .tmp files left behind
        tmp_files = list(sheets_dir.glob(".sheet_*.md.tmp"))
        assert len(tmp_files) == 0

    def test_write_overwrites(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        renderer.write(sample_character)
        sample_character.hit_points_current = 10
        path, _ = renderer.write(sample_character)
        content = path.read_text()
        assert "10/42" in content

    def test_delete_removes_file(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        renderer.write(sample_character)
        assert renderer.delete("Aldric Stormwind") is True
        assert not (sheets_dir / "Aldric Stormwind.md").exists()

    def test_delete_nonexistent_returns_false(self, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        assert renderer.delete("Nobody") is False

    def test_sheet_path(self, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        path = renderer.sheet_path("Aldric Stormwind")
        assert path == sheets_dir / "Aldric Stormwind.md"


class TestSafeFilename:

    def test_normal_name(self) -> None:
        assert _safe_filename("Aldric Stormwind") == "Aldric Stormwind"

    def test_unsafe_chars_stripped(self) -> None:
        assert _safe_filename('Thog "the" Destroyer') == "Thog the Destroyer"
        assert _safe_filename("Path/Name") == "PathName"

    def test_empty_name(self) -> None:
        assert _safe_filename("") == "unnamed"
        assert _safe_filename("   ") == "unnamed"


class TestFrontmatterHash:

    def test_hash_deterministic(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        content = renderer.render(sample_character, sync_time="2026-01-01T00:00:00")
        h1 = CharacterSheetParser.frontmatter_hash(content)
        h2 = CharacterSheetParser.frontmatter_hash(content)
        assert h1 == h2

    def test_hash_changes_with_content(self, sample_character: Character, sheets_dir: Path) -> None:
        renderer = CharacterSheetRenderer(sheets_dir)
        content1 = renderer.render(sample_character, sync_version=1, sync_time="2026-01-01T00:00:00")
        content2 = renderer.render(sample_character, sync_version=2, sync_time="2026-01-01T00:00:00")
        assert CharacterSheetParser.frontmatter_hash(content1) != CharacterSheetParser.frontmatter_hash(content2)
