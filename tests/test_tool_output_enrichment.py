"""
Tests for Issue #67: Tool Output Audit & Enrichment.

Tests verify that the enriched output from get_character, get_npc,
get_game_state, start_combat, next_turn, and end_combat contains
the new structured data fields.
"""

import pytest
from pathlib import Path

from dm20_protocol.storage import DnDStorage
from dm20_protocol.models import (
    Character, NPC, Location, Quest, Item, Spell,
    CharacterClass, Race, AbilityScore, GameState,
)


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def temp_storage_dir(tmp_path: Path) -> Path:
    """Create a temporary storage directory for tests."""
    storage_dir = tmp_path / "test_storage"
    storage_dir.mkdir()
    return storage_dir


@pytest.fixture
def storage(temp_storage_dir: Path) -> DnDStorage:
    """Create a storage instance with a test campaign and rich data."""
    s = DnDStorage(data_dir=temp_storage_dir)
    s.create_campaign(
        name="Enrichment Test",
        description="Campaign for output enrichment tests",
        dm_name="Test DM",
    )

    # Character with full data
    char = Character(
        name="Thalion",
        player_name="Alice",
        character_class=CharacterClass(name="Wizard", level=5, hit_dice="1d6"),
        race=Race(name="Elf", subrace="High Elf"),
        background="Sage",
        alignment="Neutral Good",
        abilities={
            "strength": AbilityScore(score=8),
            "dexterity": AbilityScore(score=14),
            "constitution": AbilityScore(score=12),
            "intelligence": AbilityScore(score=18),
            "wisdom": AbilityScore(score=13),
            "charisma": AbilityScore(score=10),
        },
        armor_class=12,
        hit_points_max=28,
        hit_points_current=28,
        temporary_hit_points=5,
        proficiency_bonus=3,
        hit_dice_remaining="5d6",
        death_saves_success=1,
        death_saves_failure=0,
        skill_proficiencies=["Arcana", "History", "Investigation"],
        saving_throw_proficiencies=["Intelligence", "Wisdom"],
        languages=["Common", "Elvish", "Draconic"],
        features_and_traits=["Darkvision", "Fey Ancestry", "Arcane Recovery"],
        inspiration=True,
        inventory=[
            Item(name="Quarterstaff", item_type="weapon", quantity=1, weight=4.0, value="2 sp"),
            Item(name="Potion of Healing", item_type="consumable", quantity=3, value="50 gp", description="Heals 2d4+2 HP"),
        ],
        equipment={
            "weapon_main": Item(name="Quarterstaff", item_type="weapon"),
            "weapon_off": None,
            "armor": Item(name="Mage Armor", item_type="armor"),
            "shield": None,
        },
        spell_slots={1: 4, 2: 3, 3: 2},
        spell_slots_used={1: 1, 2: 0},
        spells_known=[
            Spell(name="Fireball", level=3, school="Evocation", casting_time="1 action",
                  range=150, duration="Instantaneous", components=["V", "S", "M"],
                  description="A bright streak flashes...", prepared=True),
            Spell(name="Shield", level=1, school="Abjuration", casting_time="1 reaction",
                  range=0, duration="1 round", components=["V", "S"],
                  description="An invisible barrier...", prepared=False),
        ],
        notes="Seeking ancient tomes",
    )
    s.add_character(char)

    # Second character for combat tests (will be set to 0 HP)
    char2 = Character(
        name="Bruenor",
        player_name="Bob",
        character_class=CharacterClass(name="Fighter", level=5),
        race=Race(name="Dwarf"),
        hit_points_max=45,
        hit_points_current=0,  # Dead/incapacitated
    )
    s.add_character(char2)

    # NPC with stats and relationships
    npc = NPC(
        name="Elara",
        race="Human",
        occupation="Innkeeper",
        location="Greenfield",
        attitude="friendly",
        description="A warm-hearted innkeeper",
        bio="Secretly a retired adventurer",
        stats={"AC": 12, "HP": 22, "STR": 14, "DEX": 10},
        relationships={"Thalion": "trusted ally", "Bruenor": "regular customer"},
        notes="Knows about the hidden passage",
    )
    s.add_npc(npc)

    # NPC without stats/relationships (for negative case)
    npc2 = NPC(
        name="Mysterious Stranger",
        race="Unknown",
        occupation="Unknown",
        attitude="unknown",
    )
    s.add_npc(npc2)

    return s


# ── get_character tests ───────────────────────────────────────────

class TestGetCharacterEnriched:
    """Tests for enriched get_character output."""

    def _build_output(self, storage: DnDStorage, name: str) -> str:
        """Call get_character tool's underlying function with swapped storage."""
        from dm20_protocol import main as m

        # Temporarily swap the module-level storage
        original_storage = m.storage
        m.storage = storage
        try:
            # .fn accesses the original function wrapped by @mcp.tool
            return m.get_character.fn(name)
        finally:
            m.storage = original_storage

    def test_inventory_details(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Thalion")
        assert "Quarterstaff" in result
        assert "x1" in result
        assert "weapon" in result
        assert "2 sp" in result
        assert "4.0 lb" in result
        assert "Potion of Healing" in result
        assert "x3" in result
        assert "50 gp" in result
        assert "Heals 2d4+2 HP" in result

    def test_equipment_slots(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Thalion")
        assert "Weapon Main" in result
        assert "Quarterstaff" in result
        assert "Mage Armor" in result
        assert "Weapon Off" in result
        assert "(empty)" in result  # weapon_off and shield are empty

    def test_spell_slots(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Thalion")
        assert "Spell Slots:" in result
        assert "Level 1:" in result
        assert "3/4 remaining" in result  # 4 max, 1 used
        assert "Level 2:" in result
        assert "3/3 remaining" in result  # 3 max, 0 used
        assert "Level 3:" in result
        assert "2/2 remaining" in result  # 2 max, 0 used

    def test_spells_known(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Thalion")
        assert "Spells Known:" in result
        assert "Fireball" in result
        assert "Lvl 3" in result
        assert "Evocation" in result
        assert "[PREPARED]" in result
        assert "Shield" in result
        assert "Abjuration" in result

    def test_proficiency_bonus(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Thalion")
        assert "Proficiency Bonus: +3" in result

    def test_skill_proficiencies(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Thalion")
        assert "Skill Proficiencies:" in result
        assert "Arcana" in result
        assert "History" in result
        assert "Investigation" in result

    def test_saving_throw_proficiencies(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Thalion")
        assert "Saving Throw Proficiencies:" in result
        assert "Intelligence" in result
        assert "Wisdom" in result

    def test_death_saves(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Thalion")
        assert "Death Saves:" in result
        assert "1 successes" in result
        assert "0 failures" in result

    def test_hit_dice_remaining(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Thalion")
        assert "Hit Dice Remaining: 5d6" in result

    def test_features_and_traits(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Thalion")
        assert "Features & Traits:" in result
        assert "Darkvision" in result
        assert "Fey Ancestry" in result
        assert "Arcane Recovery" in result

    def test_languages(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Thalion")
        assert "Languages:" in result
        assert "Common" in result
        assert "Elvish" in result
        assert "Draconic" in result

    def test_inspiration(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Thalion")
        assert "Inspiration:" in result
        assert "Yes" in result

    def test_notes(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Thalion")
        assert "Seeking ancient tomes" in result

    def test_empty_fields_show_none(self, storage: DnDStorage) -> None:
        """Character with defaults should show (none)/(empty) placeholders."""
        result = self._build_output(storage, "Bruenor")
        assert "(none)" in result  # No skill profs, no spells, etc.
        assert "(empty)" in result  # Empty inventory


# ── get_npc tests ─────────────────────────────────────────────────

class TestGetNpcEnriched:
    """Tests for enriched get_npc output."""

    def _build_output(self, storage: DnDStorage, name: str) -> str:
        from dm20_protocol import main as m
        original_storage = m.storage
        m.storage = storage
        try:
            return m.get_npc.fn(name)
        finally:
            m.storage = original_storage

    def test_stats_present(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Elara")
        assert "Stats:" in result
        assert "AC" in result
        assert "12" in result
        assert "HP" in result
        assert "22" in result
        assert "STR" in result
        assert "14" in result

    def test_relationships_present(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Elara")
        assert "Relationships:" in result
        assert "Thalion" in result
        assert "trusted ally" in result
        assert "Bruenor" in result
        assert "regular customer" in result

    def test_no_stats_no_section(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Mysterious Stranger")
        assert "**Stats:**" not in result

    def test_no_relationships_no_section(self, storage: DnDStorage) -> None:
        result = self._build_output(storage, "Mysterious Stranger")
        assert "**Relationships:**" not in result


# ── get_game_state tests ──────────────────────────────────────────

class TestGetGameStateEnriched:
    """Tests for enriched get_game_state output."""

    def _build_output(self, storage: DnDStorage) -> str:
        from dm20_protocol import main as m
        original_storage = m.storage
        m.storage = storage
        try:
            return m.get_game_state.fn()
        finally:
            m.storage = original_storage

    def test_active_quest_names_listed(self, storage: DnDStorage) -> None:
        """Active quest names should appear in the output (not just count)."""
        # Add a quest and update game state to track it
        quest = Quest(title="Find the Amulet", description="Locate the lost amulet")
        storage.add_quest(quest)
        storage.update_game_state(active_quests=["Find the Amulet"])

        result = self._build_output(storage)
        assert "Active Quests" in result
        assert "Find the Amulet" in result

    def test_combat_initiative_in_state(self, storage: DnDStorage) -> None:
        """When in combat, initiative order and current turn should appear."""
        storage.update_game_state(
            in_combat=True,
            initiative_order=[
                {"name": "Thalion", "initiative": 18},
                {"name": "Goblin", "initiative": 12},
            ],
            current_turn="Thalion",
        )

        result = self._build_output(storage)
        assert "Initiative Order:" in result
        assert "Thalion" in result
        assert "18" in result
        assert "Goblin" in result
        assert "12" in result
        assert "Current Turn:" in result

    def test_no_combat_no_initiative(self, storage: DnDStorage) -> None:
        """When not in combat, initiative section should not appear."""
        result = self._build_output(storage)
        assert "Initiative Order:" not in result

    def test_no_active_quests(self, storage: DnDStorage) -> None:
        """When no active quests, should show (none)."""
        result = self._build_output(storage)
        assert "(none)" in result


# ── start_combat tests ────────────────────────────────────────────

class TestStartCombatEnriched:
    """Tests for enriched start_combat output."""

    def _run_start_combat(self, storage: DnDStorage, participants: list[dict]) -> str:
        from dm20_protocol import main as m
        original_storage = m.storage
        m.storage = storage
        try:
            return m.start_combat.fn(participants)
        finally:
            m.storage = original_storage

    def test_known_participants_no_warning(self, storage: DnDStorage) -> None:
        """Known characters and NPCs should not trigger warnings."""
        result = self._run_start_combat(storage, [
            {"name": "Thalion", "initiative": 18},
            {"name": "Elara", "initiative": 12},
        ])
        assert "Combat Started!" in result
        assert "Warnings:" not in result

    def test_unknown_participant_warning(self, storage: DnDStorage) -> None:
        """Unknown participants should trigger a warning but not block combat."""
        result = self._run_start_combat(storage, [
            {"name": "Thalion", "initiative": 18},
            {"name": "Mysterious Goblin King", "initiative": 15},
        ])
        assert "Combat Started!" in result
        assert "Warnings:" in result
        assert "Mysterious Goblin King" in result
        assert "not a known character or NPC" in result

    def test_initiative_order_sorted(self, storage: DnDStorage) -> None:
        """Participants should be sorted by initiative (highest first)."""
        result = self._run_start_combat(storage, [
            {"name": "Thalion", "initiative": 10},
            {"name": "Elara", "initiative": 20},
        ])
        # Elara (20) should be listed first
        elara_pos = result.find("Elara")
        thalion_pos = result.find("Thalion")
        assert elara_pos < thalion_pos


# ── end_combat tests ──────────────────────────────────────────────

class TestEndCombatEnriched:
    """Tests for enriched end_combat output."""

    def _run(self, storage: DnDStorage) -> str:
        from dm20_protocol import main as m
        original_storage = m.storage
        m.storage = storage
        try:
            return m.end_combat.fn()
        finally:
            m.storage = original_storage

    def test_combat_summary_participants(self, storage: DnDStorage) -> None:
        """End combat should list participants."""
        storage.update_game_state(
            in_combat=True,
            initiative_order=[
                {"name": "Thalion", "initiative": 18},
                {"name": "Bruenor", "initiative": 14},
            ],
            current_turn="Thalion",
        )

        result = self._run(storage)
        assert "Combat Ended" in result
        assert "Participants" in result
        assert "Thalion" in result
        assert "Bruenor" in result

    def test_combat_summary_casualties(self, storage: DnDStorage) -> None:
        """Bruenor (HP=0) should be listed as a casualty."""
        storage.update_game_state(
            in_combat=True,
            initiative_order=[
                {"name": "Thalion", "initiative": 18},
                {"name": "Bruenor", "initiative": 14},
            ],
            current_turn="Thalion",
        )

        result = self._run(storage)
        assert "Casualties:" in result
        assert "Bruenor" in result

    def test_combat_summary_no_casualties(self, storage: DnDStorage) -> None:
        """When no participants have HP<=0, show 'None' for casualties."""
        storage.update_game_state(
            in_combat=True,
            initiative_order=[
                {"name": "Thalion", "initiative": 18},
            ],
            current_turn="Thalion",
        )

        result = self._run(storage)
        assert "Casualties:** None" in result


# ── next_turn tests ───────────────────────────────────────────────

class TestNextTurnEnriched:
    """Tests for enriched next_turn output."""

    def _run(self, storage: DnDStorage) -> str:
        from dm20_protocol import main as m
        original_storage = m.storage
        m.storage = storage
        try:
            return m.next_turn.fn()
        finally:
            m.storage = original_storage

    def test_skip_dead_participant(self, storage: DnDStorage) -> None:
        """Dead participants (HP <= 0) should be skipped."""
        storage.update_game_state(
            in_combat=True,
            initiative_order=[
                {"name": "Thalion", "initiative": 18},
                {"name": "Bruenor", "initiative": 14},
                {"name": "Elara", "initiative": 10},
            ],
            current_turn="Thalion",
        )

        # Bruenor has HP=0, should be skipped
        result = self._run(storage)
        # Next turn should be Elara (NPC, not checked for HP) not Bruenor
        # Actually Bruenor is a character with HP=0, so he should be skipped.
        # Elara is an NPC, storage.get_character("Elara") returns None, so she's not skipped.
        assert "Elara" in result
        assert "Skipped dead/incapacitated: Bruenor" in result

    def test_all_dead_ends_combat(self, storage: DnDStorage) -> None:
        """If all remaining participants are dead characters, combat should end."""
        # Create a scenario where only dead characters remain
        storage.update_game_state(
            in_combat=True,
            initiative_order=[
                {"name": "Bruenor", "initiative": 14},  # HP=0
            ],
            current_turn="Bruenor",
        )

        result = self._run(storage)
        assert "Combat ended automatically" in result

    def test_normal_turn_advance(self, storage: DnDStorage) -> None:
        """Normal turn advance when next participant is alive."""
        storage.update_game_state(
            in_combat=True,
            initiative_order=[
                {"name": "Thalion", "initiative": 18},
                {"name": "Elara", "initiative": 10},
            ],
            current_turn="Thalion",
        )

        result = self._run(storage)
        assert "Next Turn:" in result
        assert "Elara" in result
        # No skipped participants
        assert "Skipped" not in result

    def test_not_in_combat(self, storage: DnDStorage) -> None:
        """Should return error message when not in combat."""
        result = self._run(storage)
        assert "Not currently in combat" in result
