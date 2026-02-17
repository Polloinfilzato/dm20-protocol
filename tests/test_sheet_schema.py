"""Tests for sheets/schema.py — bidirectional Character ↔ frontmatter mapping."""

import pytest

from dm20_protocol.models import (
    AbilityScore,
    Character,
    CharacterClass,
    Feature,
    Item,
    Race,
    Spell,
)
from dm20_protocol.sheets.schema import (
    EditTier,
    SheetSchema,
    _resolve_model_path,
    _serialize_value,
    _set_model_path,
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
        race=Race(name="Wood Elf", subrace="Wood", traits=["Darkvision", "Fey Ancestry"]),
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
        skill_proficiencies=["Animal Handling", "Nature", "Perception", "Stealth", "Survival"],
        saving_throw_proficiencies=["strength", "dexterity"],
        tool_proficiencies=["Herbalism Kit"],
        languages=["Common", "Elvish", "Sylvan"],
        spellcasting_ability="wisdom",
        spell_slots={1: 4, 2: 3},
        spell_slots_used={1: 1, 2: 0},
        spells_known=[
            Spell(
                id="sp01",
                name="Cure Wounds",
                level=1,
                school="evocation",
                casting_time="1 action",
                range=5,
                duration="instantaneous",
                components=["V", "S"],
                description="Heal a creature.",
                prepared=True,
            ),
        ],
        inventory=[
            Item(id="it01", name="Longbow", quantity=1, item_type="weapon"),
            Item(id="it02", name="Healing Potion", quantity=3, item_type="consumable"),
        ],
        equipment={
            "weapon_main": Item(id="eq01", name="Longbow", item_type="weapon"),
            "weapon_off": None,
            "armor": Item(id="eq02", name="Studded Leather", item_type="armor"),
            "shield": None,
        },
        features=[
            Feature(name="Favored Enemy", source="Ranger 1", description="Advantage on tracking.", level_gained=1),
        ],
        features_and_traits=["Natural Explorer"],
        conditions=[],
        notes="Tracking a group of gnolls.",
    )


class TestCharacterToFrontmatter:
    """Test Character → frontmatter conversion."""

    def test_basic_fields(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character, sync_version=1)
        assert fm["dm20_id"] == "testID01"
        assert fm["name"] == "Aldric Stormwind"
        assert fm["player"] == "Marco"
        assert fm["class"] == "Ranger"
        assert fm["level"] == 5
        assert fm["subclass"] == "Hunter"
        assert fm["race"] == "Wood Elf"
        assert fm["background"] == "Outlander"
        assert fm["alignment"] == "Neutral Good"
        assert fm["experience_points"] == 6500

    def test_ability_scores(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        assert fm["strength"] == 12
        assert fm["dexterity"] == 18
        assert fm["constitution"] == 14
        assert fm["intelligence"] == 10
        assert fm["wisdom"] == 16
        assert fm["charisma"] == 8

    def test_combat_fields(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        assert fm["armor_class"] == 16
        assert fm["hit_points_max"] == 42
        assert fm["hit_points_current"] == 35
        assert fm["temporary_hit_points"] == 0
        assert fm["speed"] == 35
        assert fm["inspiration"] is False

    def test_proficiencies_are_lists(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        assert isinstance(fm["skill_proficiencies"], list)
        assert "Perception" in fm["skill_proficiencies"]
        assert isinstance(fm["languages"], list)
        assert "Elvish" in fm["languages"]

    def test_spells_serialized(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        assert len(fm["spells_known"]) == 1
        spell = fm["spells_known"][0]
        assert isinstance(spell, dict)
        assert spell["name"] == "Cure Wounds"
        assert spell["prepared"] is True

    def test_inventory_serialized(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        assert len(fm["inventory"]) == 2
        assert fm["inventory"][0]["name"] == "Longbow"

    def test_equipment_serialized(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        eq = fm["equipment"]
        assert isinstance(eq, dict)
        assert eq["weapon_main"]["name"] == "Longbow"
        assert eq["weapon_off"] is None

    def test_sync_metadata(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(
            sample_character, sync_version=3, sync_time="2026-02-17T14:30:00"
        )
        assert fm["dm20_version"] == 3
        assert fm["dm20_last_sync"] == "2026-02-17T14:30:00"

    def test_empty_spells(self) -> None:
        char = Character(
            name="Fighter",
            character_class=CharacterClass(name="Fighter", level=1, hit_dice="1d10"),
            race=Race(name="Human"),
        )
        fm = SheetSchema.character_to_frontmatter(char)
        assert fm["spells_known"] == []
        assert fm["spell_slots"] == {}
        assert fm["spellcasting_ability"] is None


class TestFrontmatterToUpdates:
    """Test frontmatter → updates dict conversion."""

    def test_basic_roundtrip_keys(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        updates = SheetSchema.frontmatter_to_updates(fm)
        # Should have model paths, not frontmatter keys
        assert "name" in updates
        assert "character_class.name" in updates
        assert "abilities.strength.score" in updates

    def test_sync_keys_excluded(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        updates = SheetSchema.frontmatter_to_updates(fm)
        assert "_sync.dm20_version" not in updates
        assert "_sync.last_sync" not in updates

    def test_unknown_keys_ignored(self) -> None:
        fm = {"name": "Test", "totally_unknown_key": "value"}
        updates = SheetSchema.frontmatter_to_updates(fm)
        assert "name" in updates
        assert "totally_unknown_key" not in updates


class TestRoundtrip:
    """Test complete roundtrip: Character → frontmatter → apply → Character matches."""

    def test_scalar_roundtrip(self, sample_character: Character) -> None:
        fm = SheetSchema.character_to_frontmatter(sample_character)
        updates = SheetSchema.frontmatter_to_updates(fm)

        # Verify ability scores round-trip
        assert updates["abilities.strength.score"] == 12
        assert updates["abilities.dexterity.score"] == 18

    def test_apply_updates_changes_character(self, sample_character: Character) -> None:
        updates = {
            "hit_points_current": 20,
            "notes": "Updated notes",
            "inspiration": True,
        }
        changed = SheetSchema.apply_updates_to_character(sample_character, updates)
        assert "hit_points_current" in changed
        assert "notes" in changed
        assert "inspiration" in changed
        assert sample_character.hit_points_current == 20
        assert sample_character.notes == "Updated notes"
        assert sample_character.inspiration is True

    def test_apply_no_change_returns_empty(self, sample_character: Character) -> None:
        updates = {
            "name": "Aldric Stormwind",  # Same as current
            "hit_points_current": 35,  # Same as current
        }
        changed = SheetSchema.apply_updates_to_character(sample_character, updates)
        assert changed == []

    def test_ability_score_update(self, sample_character: Character) -> None:
        updates = {"abilities.strength.score": 14}
        changed = SheetSchema.apply_updates_to_character(sample_character, updates)
        assert "abilities.strength.score" in changed
        assert sample_character.abilities["strength"].score == 14


class TestEditTiers:
    """Test editability tier lookups."""

    def test_player_free_fields(self) -> None:
        assert SheetSchema.get_tier("hit_points_current") == EditTier.PLAYER_FREE
        assert SheetSchema.get_tier("temporary_hit_points") == EditTier.PLAYER_FREE
        assert SheetSchema.get_tier("inspiration") == EditTier.PLAYER_FREE
        assert SheetSchema.get_tier("notes") == EditTier.PLAYER_FREE
        assert SheetSchema.get_tier("bio") == EditTier.PLAYER_FREE
        assert SheetSchema.get_tier("description") == EditTier.PLAYER_FREE

    def test_player_approval_fields(self) -> None:
        assert SheetSchema.get_tier("name") == EditTier.PLAYER_APPROVAL
        assert SheetSchema.get_tier("strength") == EditTier.PLAYER_APPROVAL
        assert SheetSchema.get_tier("class") == EditTier.PLAYER_APPROVAL
        assert SheetSchema.get_tier("inventory") == EditTier.PLAYER_APPROVAL

    def test_dm_only_fields(self) -> None:
        assert SheetSchema.get_tier("dm20_id") == EditTier.DM_ONLY
        assert SheetSchema.get_tier("armor_class") == EditTier.DM_ONLY
        assert SheetSchema.get_tier("features") == EditTier.DM_ONLY
        assert SheetSchema.get_tier("conditions") == EditTier.DM_ONLY

    def test_unknown_field_defaults_to_dm_only(self) -> None:
        assert SheetSchema.get_tier("nonexistent_field") == EditTier.DM_ONLY


class TestHelpers:
    """Test internal helper functions."""

    def test_resolve_model_path_simple(self, sample_character: Character) -> None:
        assert _resolve_model_path(sample_character, "name") == "Aldric Stormwind"

    def test_resolve_model_path_nested(self, sample_character: Character) -> None:
        assert _resolve_model_path(sample_character, "character_class.name") == "Ranger"
        assert _resolve_model_path(sample_character, "character_class.level") == 5

    def test_resolve_model_path_deep(self, sample_character: Character) -> None:
        assert _resolve_model_path(sample_character, "abilities.strength.score") == 12

    def test_resolve_model_path_none(self, sample_character: Character) -> None:
        result = _resolve_model_path(sample_character, "nonexistent.path")
        assert result is None

    def test_set_model_path_simple(self, sample_character: Character) -> None:
        _set_model_path(sample_character, "notes", "New notes")
        assert sample_character.notes == "New notes"

    def test_set_model_path_nested(self, sample_character: Character) -> None:
        _set_model_path(sample_character, "abilities.strength.score", 20)
        assert sample_character.abilities["strength"].score == 20

    def test_serialize_value_model(self) -> None:
        item = Item(id="x", name="Sword", quantity=1, item_type="weapon")
        result = _serialize_value(item)
        assert isinstance(result, dict)
        assert result["name"] == "Sword"

    def test_serialize_value_list_of_models(self) -> None:
        items = [Item(id="x", name="Sword"), Item(id="y", name="Shield")]
        result = _serialize_value(items)
        assert len(result) == 2
        assert all(isinstance(r, dict) for r in result)

    def test_serialize_value_primitives(self) -> None:
        assert _serialize_value(42) == 42
        assert _serialize_value("hello") == "hello"
        assert _serialize_value(True) is True
        assert _serialize_value(None) is None
