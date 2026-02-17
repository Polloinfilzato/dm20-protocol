"""Tests for sheets/diff.py — change detection and editability classification."""

import pytest

from dm20_protocol.models import (
    AbilityScore,
    Character,
    CharacterClass,
    Item,
    Race,
    Spell,
)
from dm20_protocol.sheets.diff import SheetDiffEngine, _values_equal
from dm20_protocol.sheets.schema import EditTier, SheetSchema


@pytest.fixture
def sample_character() -> Character:
    return Character(
        id="testID01",
        name="Aldric Stormwind",
        player_name="Marco",
        character_class=CharacterClass(name="Ranger", level=5, hit_dice="1d10", subclass="Hunter"),
        race=Race(name="Wood Elf"),
        background="Outlander",
        alignment="Neutral Good",
        description="A tall elf.",
        bio="Raised in the forest.",
        abilities={
            "strength": AbilityScore(score=12),
            "dexterity": AbilityScore(score=18),
            "constitution": AbilityScore(score=14),
            "intelligence": AbilityScore(score=10),
            "wisdom": AbilityScore(score=16),
            "charisma": AbilityScore(score=8),
        },
        armor_class=16,
        hit_points_max=42,
        hit_points_current=35,
        temporary_hit_points=0,
        speed=35,
        inspiration=False,
        skill_proficiencies=["Perception", "Stealth"],
        saving_throw_proficiencies=["strength", "dexterity"],
        languages=["Common", "Elvish"],
        notes="Tracking gnolls.",
    )


class TestComputeDiff:

    def test_no_changes(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        diff = SheetDiffEngine.compute_diff(sample_character, fm)
        assert not diff.has_changes
        assert diff.changes == []

    def test_player_free_change_detected(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        fm["hit_points_current"] = 20  # player_free
        diff = SheetDiffEngine.compute_diff(sample_character, fm)
        assert diff.has_changes
        assert len(diff.free_changes) == 1
        assert diff.free_changes[0].field == "hit_points_current"
        assert diff.free_changes[0].old_value == 35
        assert diff.free_changes[0].new_value == 20

    def test_player_approval_change_detected(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        fm["strength"] = 14  # player_approval
        diff = SheetDiffEngine.compute_diff(sample_character, fm)
        assert diff.has_changes
        assert len(diff.approval_changes) == 1
        assert diff.approval_changes[0].field == "strength"
        assert diff.needs_approval

    def test_dm_only_change_rejected(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        fm["armor_class"] = 20  # dm_only
        diff = SheetDiffEngine.compute_diff(sample_character, fm)
        assert diff.has_changes
        assert len(diff.rejected_changes) == 1
        assert diff.rejected_changes[0].field == "armor_class"

    def test_mixed_changes_categorized(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        fm["notes"] = "New notes"  # player_free
        fm["name"] = "Aldric the Great"  # player_approval
        fm["armor_class"] = 20  # dm_only
        diff = SheetDiffEngine.compute_diff(sample_character, fm)
        assert len(diff.free_changes) == 1
        assert len(diff.approval_changes) == 1
        assert len(diff.rejected_changes) == 1
        assert len(diff.changes) == 3

    def test_text_fields_are_player_free(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        fm["description"] = "New description"
        fm["bio"] = "New bio"
        fm["notes"] = "New notes"
        diff = SheetDiffEngine.compute_diff(sample_character, fm)
        assert len(diff.free_changes) == 3
        assert all(c.tier == EditTier.PLAYER_FREE.value for c in diff.free_changes)

    def test_inspiration_is_player_free(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        fm["inspiration"] = True
        diff = SheetDiffEngine.compute_diff(sample_character, fm)
        assert len(diff.free_changes) == 1
        assert diff.free_changes[0].field == "inspiration"

    def test_missing_frontmatter_key_skipped(self, sample_character: Character) -> None:
        """If a key is absent from frontmatter, no change is reported."""
        fm = {"dm20_id": "testID01", "name": "Aldric Stormwind"}
        diff = SheetDiffEngine.compute_diff(sample_character, fm)
        # Only keys present in fm are checked; missing keys don't count
        assert not diff.has_changes

    def test_spell_slots_used_player_free(self, sample_character: Character) -> None:
        sample_character.spell_slots = {1: 4, 2: 3}
        sample_character.spell_slots_used = {1: 0, 2: 0}
        fm = SheetSchema.character_to_frontmatter(sample_character)
        # Simulate player using a spell slot by editing the sheet
        fm["spell_slots_used"] = {"1": 1, "2": 0}
        diff = SheetDiffEngine.compute_diff(sample_character, fm)
        assert len(diff.free_changes) == 1
        assert diff.free_changes[0].field == "spell_slots_used"


class TestDiffReport:

    def test_no_changes_report(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        diff = SheetDiffEngine.compute_diff(sample_character, fm)
        report = SheetDiffEngine.format_diff_report(diff)
        assert "No changes detected" in report

    def test_report_sections(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        fm["notes"] = "Changed"
        fm["strength"] = 14
        fm["armor_class"] = 20
        diff = SheetDiffEngine.compute_diff(sample_character, fm)
        report = SheetDiffEngine.format_diff_report(diff)
        assert "Auto-Applied" in report
        assert "Pending DM Approval" in report
        assert "Rejected" in report

    def test_display_format(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        fm["hit_points_current"] = 20
        diff = SheetDiffEngine.compute_diff(sample_character, fm)
        change = diff.free_changes[0]
        assert "hit_points_current" in change.display
        assert "35" in change.display
        assert "20" in change.display


class TestValuesEqual:

    def test_same_primitives(self) -> None:
        assert _values_equal(42, 42)
        assert _values_equal("hello", "hello")
        assert _values_equal(True, True)

    def test_different_primitives(self) -> None:
        assert not _values_equal(42, 43)
        assert not _values_equal("a", "b")

    def test_none_handling(self) -> None:
        assert _values_equal(None, None)
        assert not _values_equal(None, 42)
        assert not _values_equal(42, None)

    def test_none_empty_string_equivalent(self) -> None:
        assert _values_equal(None, "")
        assert _values_equal("", None)

    def test_dict_key_normalization(self) -> None:
        """YAML parses {1: 4} and {'1': 4} differently — both should match."""
        assert _values_equal({1: 4, 2: 3}, {"1": 4, "2": 3})
        assert _values_equal({"1": 4}, {1: 4})

    def test_lists_compared_directly(self) -> None:
        assert _values_equal([1, 2, 3], [1, 2, 3])
        assert not _values_equal([1, 2], [1, 2, 3])
