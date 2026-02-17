"""Integration tests for the full character sheet sync pipeline.

End-to-end: create char → MD generated → edit MD → diff detected →
approve → JSON updated.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from dm20_protocol.models import (
    AbilityScore,
    Character,
    CharacterClass,
    Item,
    Race,
    Spell,
)
from dm20_protocol.sheets.diff import SheetDiffEngine
from dm20_protocol.sheets.parser import CharacterSheetParser
from dm20_protocol.sheets.renderer import CharacterSheetRenderer
from dm20_protocol.sheets.schema import SheetSchema
from dm20_protocol.sheets.sync import SheetSyncManager


@pytest.fixture
def full_character() -> Character:
    """A fully-populated character for integration testing."""
    return Character(
        id="intTest1",
        name="Elara Moonwhisper",
        player_name="Sofia",
        character_class=CharacterClass(name="Wizard", level=7, hit_dice="1d6", subclass="Evocation"),
        race=Race(name="High Elf", subrace="High"),
        background="Sage",
        alignment="Chaotic Good",
        description="A silver-haired elf with piercing blue eyes.",
        bio="Once a librarian in Candlekeep, now seeking lost arcane knowledge.",
        abilities={
            "strength": AbilityScore(score=8),
            "dexterity": AbilityScore(score=14),
            "constitution": AbilityScore(score=13),
            "intelligence": AbilityScore(score=20),
            "wisdom": AbilityScore(score=12),
            "charisma": AbilityScore(score=10),
        },
        experience_points=23000,
        armor_class=12,
        hit_points_max=38,
        hit_points_current=25,
        temporary_hit_points=5,
        speed=30,
        hit_dice_type="d6",
        hit_dice_remaining="7d6",
        inspiration=True,
        skill_proficiencies=["Arcana", "History", "Investigation"],
        saving_throw_proficiencies=["intelligence", "wisdom"],
        tool_proficiencies=[],
        languages=["Common", "Elvish", "Draconic", "Celestial"],
        spellcasting_ability="intelligence",
        spell_slots={1: 4, 2: 3, 3: 3, 4: 1},
        spell_slots_used={1: 2, 2: 1, 3: 0, 4: 0},
        spells_known=[
            Spell(
                id="sp01", name="Magic Missile", level=1, school="evocation",
                casting_time="1 action", range=120, duration="instantaneous",
                components=["V", "S"], description="Three darts of magical force.", prepared=True,
            ),
            Spell(
                id="sp02", name="Fireball", level=3, school="evocation",
                casting_time="1 action", range=150, duration="instantaneous",
                components=["V", "S", "M"], description="A ball of fire.", prepared=True,
            ),
            Spell(
                id="sp03", name="Shield", level=1, school="abjuration",
                casting_time="1 reaction", range=0, duration="1 round",
                components=["V", "S"], description="An invisible barrier of magical force.", prepared=True,
            ),
        ],
        inventory=[
            Item(id="it01", name="Spellbook", quantity=1, item_type="misc", weight=3.0),
            Item(id="it02", name="Component Pouch", quantity=1, item_type="misc"),
            Item(id="it03", name="Healing Potion", quantity=2, item_type="consumable", value="50 gp"),
        ],
        equipment={
            "weapon_main": Item(id="eq01", name="Quarterstaff", item_type="weapon"),
            "weapon_off": None,
            "armor": None,
            "shield": None,
        },
        features_and_traits=["Arcane Recovery"],
        conditions=[],
        notes="Looking for the Tome of the Stilled Tongue.",
    )


@pytest.fixture
def mock_storage(full_character: Character) -> MagicMock:
    storage = MagicMock()
    campaign = MagicMock()
    campaign.name = "Integration Test"
    campaign.characters = {full_character.name: full_character}
    storage.get_current_campaign.return_value = campaign
    storage.find_character.return_value = full_character
    return storage


class TestEndToEndRoundtrip:
    """Full pipeline: Character → MD → parse → verify roundtrip."""

    def test_render_parse_roundtrip(self, full_character: Character, tmp_path: Path) -> None:
        """Render a character, parse it back, verify data integrity."""
        renderer = CharacterSheetRenderer(tmp_path)
        path, _ = renderer.write(full_character, sync_version=1, sync_time="2026-02-17T14:30:00")

        # Parse it back
        fm = CharacterSheetParser.parse_file(path)

        # Verify all key fields roundtrip
        assert fm["dm20_id"] == "intTest1"
        assert fm["name"] == "Elara Moonwhisper"
        assert fm["player"] == "Sofia"
        assert fm["class"] == "Wizard"
        assert fm["level"] == 7
        assert fm["subclass"] == "Evocation"
        assert fm["race"] == "High Elf"
        assert fm["intelligence"] == 20
        assert fm["hit_points_current"] == 25
        assert fm["hit_points_max"] == 38
        assert fm["temporary_hit_points"] == 5
        assert fm["inspiration"] is True
        assert len(fm["spells_known"]) == 3
        assert len(fm["inventory"]) == 3
        assert "Arcana" in fm["skill_proficiencies"]
        assert "Elvish" in fm["languages"]

    def test_no_diff_after_render(self, full_character: Character, tmp_path: Path) -> None:
        """A freshly rendered sheet should produce zero diff."""
        renderer = CharacterSheetRenderer(tmp_path)
        path, _ = renderer.write(full_character)
        fm = CharacterSheetParser.parse_file(path)
        diff = SheetDiffEngine.compute_diff(full_character, fm)
        assert not diff.has_changes, f"Unexpected changes: {[c.display for c in diff.changes]}"


class TestEditApproveFlow:
    """Simulate player editing the sheet and DM approving."""

    def test_player_edits_free_fields(
        self, full_character: Character, mock_storage: MagicMock, tmp_path: Path
    ) -> None:
        """Player changes HP, notes, and bio — auto-applied."""
        sm = SheetSyncManager()
        sm.wire_storage(mock_storage)
        sm.start(tmp_path / "sheets", enable_watcher=False)

        path = sm.render_character(full_character)

        # Player edits the file
        content = path.read_text()
        content = content.replace("hit_points_current: 25", "hit_points_current: 30")
        content = content.replace("notes: Looking for the Tome", "notes: Found a clue about the Tome")
        path.write_text(content)

        diff = sm.process_file_change(path)
        assert diff.has_changes
        # Free changes auto-applied
        assert full_character.hit_points_current == 30
        assert "Found a clue" in full_character.notes

    def test_player_edits_approval_fields(
        self, full_character: Character, mock_storage: MagicMock, tmp_path: Path
    ) -> None:
        """Player changes ability scores — queued for approval."""
        sm = SheetSyncManager()
        sm.wire_storage(mock_storage)
        sm.start(tmp_path / "sheets", enable_watcher=False)

        path = sm.render_character(full_character)

        content = path.read_text()
        content = content.replace("intelligence: 20", "intelligence: 22")
        path.write_text(content)

        diff = sm.process_file_change(path)
        assert len(diff.approval_changes) == 1

        # Intelligence should NOT change yet
        assert full_character.abilities["intelligence"].score == 20

        # DM approves
        result = sm.approve_changes("Elara Moonwhisper")
        assert "Approved" in result
        assert full_character.abilities["intelligence"].score == 22

    def test_player_edits_dm_only_fields(
        self, full_character: Character, mock_storage: MagicMock, tmp_path: Path
    ) -> None:
        """Player tries to change AC — silently rejected."""
        sm = SheetSyncManager()
        sm.wire_storage(mock_storage)
        sm.start(tmp_path / "sheets", enable_watcher=False)

        path = sm.render_character(full_character)

        content = path.read_text()
        content = content.replace("armor_class: 12", "armor_class: 18")
        path.write_text(content)

        diff = sm.process_file_change(path)
        assert len(diff.rejected_changes) == 1
        assert full_character.armor_class == 12

    def test_dm_rejects_changes(
        self, full_character: Character, mock_storage: MagicMock, tmp_path: Path
    ) -> None:
        """DM rejects player changes — sheet regenerated from JSON."""
        sm = SheetSyncManager()
        sm.wire_storage(mock_storage)
        sm.start(tmp_path / "sheets", enable_watcher=False)

        path = sm.render_character(full_character)

        content = path.read_text()
        content = content.replace("intelligence: 20", "intelligence: 22")
        path.write_text(content)

        sm.process_file_change(path)
        result = sm.reject_changes("Elara Moonwhisper")
        assert "Rejected" in result

        # Intelligence unchanged
        assert full_character.abilities["intelligence"].score == 20

        # Sheet should be regenerated with original data
        new_fm = CharacterSheetParser.parse_file(path)
        assert new_fm["intelligence"] == 20


class TestMixedEdits:
    """Player edits multiple fields from different tiers simultaneously."""

    def test_mixed_tier_edits(
        self, full_character: Character, mock_storage: MagicMock, tmp_path: Path
    ) -> None:
        sm = SheetSyncManager()
        sm.wire_storage(mock_storage)
        sm.start(tmp_path / "sheets", enable_watcher=False)

        path = sm.render_character(full_character)

        content = path.read_text()
        # Player free: change HP and notes
        content = content.replace("hit_points_current: 25", "hit_points_current: 15")
        content = content.replace("inspiration: true", "inspiration: false")
        # Player approval: change name
        content = content.replace("name: Elara Moonwhisper", "name: Elara the Wise")
        # DM only: change AC
        content = content.replace("armor_class: 12", "armor_class: 20")
        path.write_text(content)

        diff = sm.process_file_change(path)

        # Free changes auto-applied
        assert full_character.hit_points_current == 15
        assert full_character.inspiration is False

        # Approval changes queued
        assert len(diff.approval_changes) >= 1

        # DM only rejected
        assert full_character.armor_class == 12


class TestEdgeCases:

    def test_empty_character(self, tmp_path: Path) -> None:
        """Minimal character renders and parses without errors."""
        char = Character(
            id="empty01",
            name="Nobody",
            character_class=CharacterClass(name="Fighter", level=1, hit_dice="1d10"),
            race=Race(name="Human"),
        )
        renderer = CharacterSheetRenderer(tmp_path)
        path, _ = renderer.write(char)
        fm = CharacterSheetParser.parse_file(path)
        diff = SheetDiffEngine.compute_diff(char, fm)
        assert not diff.has_changes

    def test_character_with_special_chars_in_name(self, tmp_path: Path) -> None:
        """Characters with special characters in names."""
        char = Character(
            id="spec01",
            name="Thog the Mighty",
            character_class=CharacterClass(name="Barbarian", level=3, hit_dice="1d12"),
            race=Race(name="Half-Orc"),
        )
        renderer = CharacterSheetRenderer(tmp_path)
        path, _ = renderer.write(char)
        assert path.exists()
        fm = CharacterSheetParser.parse_file(path)
        assert fm["name"] == "Thog the Mighty"
