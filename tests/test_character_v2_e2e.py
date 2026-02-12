"""End-to-end tests for the Character v2 lifecycle (Issue #104).

Tests the full character creation → level-up → inventory → spell → rest pipeline
using mock rulebook data that mirrors SRD structure. Validates that all components
(CharacterBuilder, LevelUpEngine, inventory tools, spell tools, rest tools)
work together as a cohesive system.
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dm20_protocol.character_builder import CharacterBuilder, CharacterBuilderError
from dm20_protocol.level_up_engine import LevelUpEngine
from dm20_protocol.models import Character, CharacterClass, Item, Race, Spell
from dm20_protocol.main import (
    _equip_item_logic,
    _unequip_item_logic,
    _remove_item_logic,
    _use_spell_slot_logic,
    _add_spell_logic,
    _remove_spell_logic,
    _long_rest_logic,
    _short_rest_logic,
    _add_death_save_logic,
    _parse_json_list,
)
from dm20_protocol.rulebooks.models import (
    AbilityBonus,
    BackgroundDefinition,
    BackgroundFeature,
    ClassDefinition,
    ClassLevelInfo,
    RaceDefinition,
    RacialTrait,
    SpellcastingInfo,
)


# ═══════════════════════════════════════════════════════════════════════
# Mock Rulebook Definitions — comprehensive, SRD-like
# ═══════════════════════════════════════════════════════════════════════


def make_fighter_def() -> ClassDefinition:
    return ClassDefinition(
        index="fighter",
        name="Fighter",
        source="srd-2014",
        hit_die=10,
        proficiencies=["All armor", "Shields", "Simple weapons", "Martial weapons"],
        proficiency_choices={
            "desc": "Choose two skills",
            "choose": 2,
            "type": "proficiencies",
            "from": {
                "option_set_type": "options_array",
                "options": [
                    {"option_type": "reference", "item": {"index": "skill-athletics", "name": "Skill: Athletics"}},
                    {"option_type": "reference", "item": {"index": "skill-intimidation", "name": "Skill: Intimidation"}},
                ],
            },
        },
        saving_throws=["STR", "CON"],
        starting_equipment=["Chain mail", "Shield", "Longsword"],
        starting_equipment_options=[],
        spellcasting=None,
        class_levels={
            1: ClassLevelInfo(level=1, proficiency_bonus=2, features=["Fighting Style", "Second Wind"]),
            2: ClassLevelInfo(level=2, proficiency_bonus=2, features=["Action Surge"]),
            3: ClassLevelInfo(level=3, proficiency_bonus=2, features=["Martial Archetype"]),
            4: ClassLevelInfo(level=4, proficiency_bonus=2, features=["Ability Score Improvement"]),
            5: ClassLevelInfo(level=5, proficiency_bonus=3, features=["Extra Attack"]),
        },
        subclasses=["champion"],
        subclass_level=3,
    )


def make_ranger_def() -> ClassDefinition:
    return ClassDefinition(
        index="ranger",
        name="Ranger",
        source="srd-2014",
        hit_die=10,
        proficiencies=["Light armor", "Medium armor", "Shields", "Simple weapons", "Martial weapons"],
        proficiency_choices={
            "desc": "Choose three skills",
            "choose": 3,
            "type": "proficiencies",
            "from": {
                "option_set_type": "options_array",
                "options": [
                    {"option_type": "reference", "item": {"index": "skill-animal-handling", "name": "Skill: Animal Handling"}},
                    {"option_type": "reference", "item": {"index": "skill-athletics", "name": "Skill: Athletics"}},
                    {"option_type": "reference", "item": {"index": "skill-stealth", "name": "Skill: Stealth"}},
                ],
            },
        },
        saving_throws=["DEX", "WIS"],
        starting_equipment=["Longbow", "Quiver", "20 Arrows"],
        starting_equipment_options=[],
        spellcasting=SpellcastingInfo(
            level=2,
            spellcasting_ability="WIS",
            caster_type="half",
            cantrips_known=None,
            spells_known=[0, 2, 3, 3, 4, 4, 5, 5, 6, 6],
            spell_slots={
                2: [2, 0, 0, 0, 0, 0, 0, 0, 0],
                3: [3, 0, 0, 0, 0, 0, 0, 0, 0],
                5: [4, 2, 0, 0, 0, 0, 0, 0, 0],
            },
        ),
        class_levels={
            1: ClassLevelInfo(level=1, proficiency_bonus=2, features=["Favored Enemy", "Natural Explorer"]),
            2: ClassLevelInfo(level=2, proficiency_bonus=2, features=["Fighting Style", "Spellcasting"]),
            3: ClassLevelInfo(level=3, proficiency_bonus=2, features=["Ranger Archetype", "Primeval Awareness"]),
            4: ClassLevelInfo(level=4, proficiency_bonus=2, features=["Ability Score Improvement"]),
            5: ClassLevelInfo(level=5, proficiency_bonus=3, features=["Extra Attack"]),
        },
        subclasses=["hunter"],
        subclass_level=3,
    )


def make_wizard_def() -> ClassDefinition:
    return ClassDefinition(
        index="wizard",
        name="Wizard",
        source="srd-2014",
        hit_die=6,
        proficiencies=["Daggers", "Darts", "Slings", "Quarterstaffs", "Light crossbows"],
        proficiency_choices={
            "desc": "Choose two skills",
            "choose": 2,
            "type": "proficiencies",
            "from": {
                "option_set_type": "options_array",
                "options": [
                    {"option_type": "reference", "item": {"index": "skill-arcana", "name": "Skill: Arcana"}},
                    {"option_type": "reference", "item": {"index": "skill-investigation", "name": "Skill: Investigation"}},
                ],
            },
        },
        saving_throws=["INT", "WIS"],
        starting_equipment=["Spellbook", "Component pouch", "Quarterstaff"],
        starting_equipment_options=[],
        spellcasting=SpellcastingInfo(
            level=1,
            spellcasting_ability="INT",
            caster_type="full",
            cantrips_known=[3, 3, 3, 4, 4, 4, 4, 4, 4, 5],
            spells_known=None,
            spell_slots={
                1: [2, 0, 0, 0, 0, 0, 0, 0, 0],
                2: [3, 0, 0, 0, 0, 0, 0, 0, 0],
                3: [4, 2, 0, 0, 0, 0, 0, 0, 0],
                5: [4, 3, 2, 0, 0, 0, 0, 0, 0],
            },
        ),
        class_levels={
            1: ClassLevelInfo(level=1, proficiency_bonus=2, features=["Spellcasting", "Arcane Recovery"]),
            2: ClassLevelInfo(level=2, proficiency_bonus=2, features=["Arcane Tradition"]),
            3: ClassLevelInfo(level=3, proficiency_bonus=2, features=[]),
            4: ClassLevelInfo(level=4, proficiency_bonus=2, features=["Ability Score Improvement"]),
            5: ClassLevelInfo(level=5, proficiency_bonus=3, features=[]),
        },
        subclasses=["evocation"],
        subclass_level=2,
    )


def make_human_def() -> RaceDefinition:
    return RaceDefinition(
        index="human",
        name="Human",
        source="srd-2014",
        speed=30,
        ability_bonuses=[
            AbilityBonus(ability_score="STR", bonus=1),
            AbilityBonus(ability_score="DEX", bonus=1),
            AbilityBonus(ability_score="CON", bonus=1),
            AbilityBonus(ability_score="INT", bonus=1),
            AbilityBonus(ability_score="WIS", bonus=1),
            AbilityBonus(ability_score="CHA", bonus=1),
        ],
        languages=["Common"],
        traits=[],
    )


def make_wood_elf_def() -> RaceDefinition:
    return RaceDefinition(
        index="elf",
        name="Elf",
        source="srd-2014",
        speed=35,
        ability_bonuses=[AbilityBonus(ability_score="DEX", bonus=2)],
        languages=["Common", "Elvish"],
        traits=[
            RacialTrait(index="darkvision", name="Darkvision", desc=["60 feet"]),
            RacialTrait(index="fey-ancestry", name="Fey Ancestry", desc=["Advantage vs charm"]),
            RacialTrait(index="trance", name="Trance", desc=["Elves don't sleep"]),
            RacialTrait(index="mask-of-the-wild", name="Mask of the Wild", desc=["Hide in light obscurement"]),
        ],
    )


def make_outlander_def() -> BackgroundDefinition:
    return BackgroundDefinition(
        index="outlander",
        name="Outlander",
        source="srd-2014",
        starting_proficiencies=["Skill: Athletics", "Skill: Survival"],
        starting_equipment=["Staff", "Hunting trap", "Traveler's clothes", "10 gp"],
        starting_equipment_options=[],
        feature=BackgroundFeature(
            name="Wanderer",
            desc=["You have an excellent memory for maps and geography."],
        ),
    )


def make_acolyte_def() -> BackgroundDefinition:
    return BackgroundDefinition(
        index="acolyte",
        name="Acolyte",
        source="srd-2014",
        starting_proficiencies=["Skill: Insight", "Skill: Religion"],
        starting_equipment=["Holy symbol", "Prayer book", "5 sticks of incense"],
        starting_equipment_options=[],
        feature=BackgroundFeature(
            name="Shelter of the Faithful",
            desc=["You can find shelter at a temple."],
        ),
    )


def make_mock_manager(
    class_def=None,
    race_def=None,
    bg_def=None,
) -> MagicMock:
    """Create a mock RulebookManager."""
    manager = MagicMock()
    manager.get_class.return_value = class_def
    manager.get_race.return_value = race_def
    manager.get_background.return_value = bg_def
    return manager


# ═══════════════════════════════════════════════════════════════════════
# E2E Test: Fighter Lifecycle (Simple Martial)
# ═══════════════════════════════════════════════════════════════════════


class TestFighterLifecycle:
    """Create level 1 Human Fighter → level up to 5 → verify full progression."""

    def setup_method(self):
        self.manager = make_mock_manager(
            class_def=make_fighter_def(),
            race_def=make_human_def(),
        )
        self.builder = CharacterBuilder(self.manager)
        self.engine = LevelUpEngine(self.manager)

    def test_create_level_1_fighter(self):
        char = self.builder.build(
            "Aldric", "Fighter", "Human", 1,
            strength=16, dexterity=14, constitution=14,
            intelligence=10, wisdom=12, charisma=8,
        )
        # Basic identity
        assert char.name == "Aldric"
        assert char.character_class.name == "Fighter"
        assert char.character_class.level == 1
        assert char.race.name == "Human"

        # Ability scores (base + 1 human racial each)
        assert char.abilities["strength"].score == 17
        assert char.abilities["constitution"].score == 15

        # HP: 10 (hit die max) + CON mod (from 15 → +2)
        assert char.hit_points_max == 12
        assert char.hit_points_current == 12

        # Proficiency bonus
        assert char.proficiency_bonus == 2

        # Saving throws
        assert "STR" in char.saving_throw_proficiencies
        assert "CON" in char.saving_throw_proficiencies

        # Starting equipment
        assert len(char.inventory) >= 2  # Chain mail, Shield, Longsword

        # Features
        assert any("Fighting Style" in f for f in char.features_and_traits)
        assert any("Second Wind" in f for f in char.features_and_traits)

        # No spellcasting
        assert char.spell_slots == {}
        assert char.spellcasting_ability is None

        # Speed
        assert char.speed == 30

        # We should have at least 20 populated fields
        populated = sum(1 for field in [
            char.name, char.character_class, char.race, char.abilities,
            char.hit_points_max, char.hit_points_current, char.armor_class,
            char.proficiency_bonus, char.saving_throw_proficiencies,
            char.inventory, char.equipment, char.features_and_traits,
            char.features, char.speed, char.hit_dice_type,
            char.hit_dice_remaining, char.experience_points,
            char.death_saves_success, char.conditions, char.languages,
        ] if field is not None)
        assert populated >= 20

    def test_fighter_level_1_to_5(self):
        char = self.builder.build(
            "Aldric", "Fighter", "Human", 1,
            strength=16, constitution=14,
        )
        initial_hp = char.hit_points_max

        # Level 2: Action Surge
        result2 = self.engine.level_up(char)
        assert char.character_class.level == 2
        assert char.hit_points_max > initial_hp
        assert any("Action Surge" in f for f in char.features_and_traits)

        # Level 3: Martial Archetype (Champion)
        result3 = self.engine.level_up(char, subclass="champion")
        assert char.character_class.level == 3
        assert char.character_class.subclass == "champion"

        # Level 4: ASI (+2 STR)
        old_str = char.abilities["strength"].score
        result4 = self.engine.level_up(char, asi_choices={"strength": 2})
        assert char.character_class.level == 4
        assert char.abilities["strength"].score == old_str + 2

        # Level 5: Extra Attack, proficiency +3
        result5 = self.engine.level_up(char)
        assert char.character_class.level == 5
        assert char.proficiency_bonus == 3
        assert any("Extra Attack" in f for f in char.features_and_traits)

        # Verify all features accumulated
        traits = char.features_and_traits
        expected_features = ["Fighting Style", "Second Wind", "Action Surge",
                             "Martial Archetype", "Ability Score Improvement", "Extra Attack"]
        for feature in expected_features:
            assert any(feature in t for t in traits), f"Missing feature: {feature}"

        # HP should have increased 4 times
        assert char.hit_points_max > initial_hp

        # Hit dice remaining
        assert "5d10" in char.hit_dice_remaining


# ═══════════════════════════════════════════════════════════════════════
# E2E Test: Ranger Lifecycle (Half-Caster)
# ═══════════════════════════════════════════════════════════════════════


class TestRangerLifecycle:
    """Create level 3 Wood Elf Ranger with Outlander background."""

    def setup_method(self):
        self.manager = make_mock_manager(
            class_def=make_ranger_def(),
            race_def=make_wood_elf_def(),
            bg_def=make_outlander_def(),
        )
        self.builder = CharacterBuilder(self.manager)
        self.engine = LevelUpEngine(self.manager)

    def test_create_level_3_ranger(self):
        char = self.builder.build(
            "Thorn", "Ranger", "Elf", 3,
            background="Outlander",
            subclass="hunter",
            strength=12, dexterity=16, constitution=14,
            intelligence=10, wisdom=14, charisma=8,
        )

        # Class identity
        assert char.character_class.name == "Ranger"
        assert char.character_class.level == 3
        assert char.character_class.subclass == "hunter"

        # Race: Wood Elf
        assert char.race.name == "Elf"
        assert char.speed == 35  # Wood Elf speed

        # DEX bonus from Elf (+2)
        assert char.abilities["dexterity"].score == 18  # 16 + 2

        # Saving throws: DEX + WIS
        assert "DEX" in char.saving_throw_proficiencies
        assert "WIS" in char.saving_throw_proficiencies

        # Racial traits
        race_traits = char.race.traits
        trait_names = [t if isinstance(t, str) else t.name for t in race_traits]
        assert "Darkvision" in trait_names
        assert "Fey Ancestry" in trait_names
        assert "Trance" in trait_names
        assert "Mask of the Wild" in trait_names

        # Languages (Elf base)
        assert "Common" in char.languages
        assert "Elvish" in char.languages

        # Class features accumulated through level 3
        traits = char.features_and_traits
        assert any("Favored Enemy" in t for t in traits)
        assert any("Natural Explorer" in t for t in traits)

        # Half-caster spell slots at level 3
        assert char.spell_slots.get(1, 0) == 3  # 3 first-level slots

        # Outlander background equipment
        assert len(char.inventory) >= 3  # Starting equipment from class + background

        # HP: 3d10 + CON×3 (CON 14 → +2 mod)
        # Level 1: 10 + 2 = 12, Level 2: avg(5.5→6) + 2 = 8, Level 3: 6 + 2 = 8
        assert char.hit_points_max == 28  # 12 + 8 + 8

    def test_ranger_level_up_to_5(self):
        char = self.builder.build(
            "Thorn", "Ranger", "Elf", 3,
            background="Outlander",
            subclass="hunter",
            dexterity=16, constitution=14,
        )

        # Level 4: ASI
        self.engine.level_up(char, asi_choices={"dexterity": 2})
        assert char.character_class.level == 4
        assert char.abilities["dexterity"].score == 20  # 16 + 2 (elf) + 2 (ASI)

        # Level 5: Extra Attack + 2nd-level spell slots
        self.engine.level_up(char)
        assert char.character_class.level == 5
        assert char.proficiency_bonus == 3
        assert any("Extra Attack" in t for t in char.features_and_traits)
        assert char.spell_slots.get(2, 0) == 2  # 2 second-level slots


# ═══════════════════════════════════════════════════════════════════════
# E2E Test: Wizard Lifecycle (Full Caster)
# ═══════════════════════════════════════════════════════════════════════


class TestWizardLifecycle:
    """Create level 5 Wizard → verify spell slots → use spell → rest → verify reset."""

    def setup_method(self):
        self.manager = make_mock_manager(
            class_def=make_wizard_def(),
            race_def=make_human_def(),
            bg_def=make_acolyte_def(),
        )
        self.builder = CharacterBuilder(self.manager)

    def test_create_level_5_wizard(self):
        char = self.builder.build(
            "Elara", "Wizard", "Human", 5,
            background="Acolyte",
            subclass="evocation",
            strength=8, dexterity=14, constitution=12,
            intelligence=16, wisdom=13, charisma=10,
        )

        # Basic
        assert char.character_class.name == "Wizard"
        assert char.character_class.level == 5
        assert char.character_class.subclass == "evocation"

        # INT saves
        assert "INT" in char.saving_throw_proficiencies
        assert "WIS" in char.saving_throw_proficiencies

        # Spell slots: {1: 4, 2: 3, 3: 2}
        assert char.spell_slots[1] == 4
        assert char.spell_slots[2] == 3
        assert char.spell_slots[3] == 2

        # Spellcasting ability (stored as full name by builder)
        assert char.spellcasting_ability == "intelligence"

        # Features
        traits = char.features_and_traits
        assert any("Spellcasting" in t for t in traits)
        assert any("Arcane Recovery" in t for t in traits)
        assert any("Arcane Tradition" in t for t in traits)

    def test_wizard_spell_slot_usage_and_rest(self):
        """Full cycle: use spell slots → long rest → verify reset."""
        char = self.builder.build(
            "Elara", "Wizard", "Human", 5,
            subclass="evocation",
            intelligence=16, constitution=12,
        )

        # Use some spell slots
        assert _use_spell_slot_logic(char, 1).startswith("✅")
        assert _use_spell_slot_logic(char, 1).startswith("✅")
        assert _use_spell_slot_logic(char, 3).startswith("✅")

        assert char.spell_slots_used[1] == 2
        assert char.spell_slots_used[3] == 1

        # Long rest → all slots reset
        result = _long_rest_logic(char)
        assert "Spell slots restored" in result
        assert char.spell_slots_used[1] == 0
        assert char.spell_slots_used[2] == 0
        assert char.spell_slots_used[3] == 0
        assert char.hit_points_current == char.hit_points_max

    def test_wizard_spell_management(self):
        """Add spells, use slots, remove spells."""
        char = self.builder.build(
            "Elara", "Wizard", "Human", 5,
            subclass="evocation",
        )

        # Add spells
        fireball = Spell(
            name="Fireball", level=3, school="evocation",
            casting_time="1 action", range=150,
            duration="instantaneous", components=["V", "S", "M"],
            description="A bright streak flashes.",
        )
        shield = Spell(
            name="Shield", level=1, school="abjuration",
            casting_time="1 reaction", range=0,
            duration="1 round", components=["V", "S"],
            description="An invisible barrier of magical force.",
        )

        assert _add_spell_logic(char, fireball).startswith("✅")
        assert _add_spell_logic(char, shield).startswith("✅")
        assert len(char.spells_known) == 2

        # Duplicate detection
        result = _add_spell_logic(char, fireball)
        assert "already knows" in result
        assert len(char.spells_known) == 2

        # Remove spell
        assert _remove_spell_logic(char, "Shield").startswith("✅")
        assert len(char.spells_known) == 1
        assert char.spells_known[0].name == "Fireball"


# ═══════════════════════════════════════════════════════════════════════
# E2E Test: Full Inventory Cycle
# ═══════════════════════════════════════════════════════════════════════


class TestInventoryCycle:
    """Add items → equip → unequip → remove."""

    def setup_method(self):
        self.manager = make_mock_manager(
            class_def=make_fighter_def(),
            race_def=make_human_def(),
        )
        self.builder = CharacterBuilder(self.manager)

    def test_full_inventory_cycle(self):
        char = self.builder.build("Aldric", "Fighter", "Human", 1, strength=16)

        # Builder may have created starting equipment — add items with unique names
        potion = Item(name="Potion of Healing", item_type="consumable", quantity=1, weight=0.5)
        shield = Item(name="Tower Shield", item_type="armor", quantity=1, weight=6.0)
        arrows = Item(name="Arrow", item_type="misc", quantity=20, weight=0.05)
        char.inventory.extend([potion, shield, arrows])

        initial_count = len(char.inventory)

        # Equip shield → shield slot
        result = _equip_item_logic(char, "Tower Shield", "shield")
        assert "Equipped Tower Shield" in result
        assert char.equipment["shield"] is shield

        # Inventory should have 1 fewer item (shield moved to equipment)
        assert len(char.inventory) == initial_count - 1

        # Unequip shield → back to inventory
        result = _unequip_item_logic(char, "shield")
        assert "Unequipped Tower Shield" in result
        assert char.equipment["shield"] is None
        assert shield in char.inventory

        # Remove some arrows (partial quantity)
        result = _remove_item_logic(char, "Arrow", quantity=5)
        assert "Removed 5x Arrow" in result
        assert arrows.quantity == 15

        # Remove remaining arrows
        result = _remove_item_logic(char, "Arrow", quantity=15)
        assert arrows not in char.inventory


# ═══════════════════════════════════════════════════════════════════════
# E2E Test: Full Rest Cycle
# ═══════════════════════════════════════════════════════════════════════


class TestRestCycle:
    """Use spell slots → take damage → short rest → long rest → verify everything."""

    def setup_method(self):
        self.manager = make_mock_manager(
            class_def=make_wizard_def(),
            race_def=make_human_def(),
        )
        self.builder = CharacterBuilder(self.manager)

    def test_full_rest_cycle(self):
        char = self.builder.build(
            "Elara", "Wizard", "Human", 5,
            subclass="evocation",
            constitution=14,  # +2 mod
        )

        full_hp = char.hit_points_max

        # Take damage
        char.hit_points_current = full_hp - 15

        # Use spell slots
        _use_spell_slot_logic(char, 1)
        _use_spell_slot_logic(char, 1)
        _use_spell_slot_logic(char, 3)

        # Short rest: spend 2 hit dice
        result = _short_rest_logic(char, 2)
        assert "✅" in result
        assert "spent 2d6" in result
        # Should have healed some
        assert char.hit_points_current > full_hp - 15
        # Spell slots NOT restored by short rest
        assert char.spell_slots_used[1] == 2

        # Long rest: everything resets
        result = _long_rest_logic(char)
        assert "✅" in result
        assert "Spell slots restored" in result
        assert "HP restored" in result
        assert char.hit_points_current == full_hp
        assert char.spell_slots_used[1] == 0
        assert char.spell_slots_used[3] == 0


# ═══════════════════════════════════════════════════════════════════════
# E2E Test: Death Save Tracking
# ═══════════════════════════════════════════════════════════════════════


class TestDeathSaveCycle:
    """Full death save scenario: go to 0 HP → death saves → stabilize."""

    def test_stabilize_scenario(self):
        char = Character(
            name="Aldric",
            character_class=CharacterClass(name="Fighter", level=5, hit_dice="5d10"),
            race=Race(name="Human"),
            hit_points_max=44,
            hit_points_current=0,
            conditions=["unconscious"],
        )

        # Fail once, succeed three times
        _add_death_save_logic(char, success=False)
        assert char.death_saves_failure == 1

        _add_death_save_logic(char, success=True)
        _add_death_save_logic(char, success=True)
        result = _add_death_save_logic(char, success=True)

        assert "stabilized" in result
        assert char.hit_points_current == 1
        assert char.death_saves_success == 0
        assert char.death_saves_failure == 0
        assert "unconscious" not in char.conditions

    def test_death_scenario(self):
        char = Character(
            name="Aldric",
            character_class=CharacterClass(name="Fighter", level=5, hit_dice="5d10"),
            race=Race(name="Human"),
            hit_points_max=44,
            hit_points_current=0,
        )

        _add_death_save_logic(char, success=True)
        _add_death_save_logic(char, success=False)
        _add_death_save_logic(char, success=False)
        result = _add_death_save_logic(char, success=False)

        assert "DIED" in result
        assert "💀" in result


# ═══════════════════════════════════════════════════════════════════════
# E2E Test: Backward Compatibility
# ═══════════════════════════════════════════════════════════════════════


class TestBackwardCompatibility:
    """Load v1 character JSON → verify defaults → update → round-trip."""

    @pytest.fixture
    def v1_data(self):
        fixture_path = Path(__file__).parent / "fixtures" / "v1_character.json"
        return json.loads(fixture_path.read_text())

    def test_v1_loads_without_errors(self, v1_data):
        char = Character(**v1_data)
        assert char.name == "Old Gandalf"
        assert char.character_class.name == "Wizard"
        assert char.character_class.level == 5

    def test_v1_new_fields_have_defaults(self, v1_data):
        char = Character(**v1_data)
        # New v2 fields should have correct defaults
        assert char.experience_points == 0
        assert char.speed == 30
        assert char.conditions == []
        assert char.tool_proficiencies == []
        assert char.skill_proficiencies == []
        assert char.saving_throw_proficiencies == []
        assert char.features_and_traits == []
        assert char.features == []
        assert char.languages == []
        assert char.death_saves_success == 0
        assert char.death_saves_failure == 0
        assert char.spell_slots == {}
        assert char.spell_slots_used == {}
        assert char.spells_known == []

    def test_v1_update_with_new_tools(self, v1_data):
        char = Character(**v1_data)

        # Use new utility tools on a v1 character
        char.conditions.append("poisoned")
        char.languages.extend(["Common", "Elvish"])
        char.experience_points = 6500
        char.speed = 30

        assert "poisoned" in char.conditions
        assert char.experience_points == 6500

    def test_v1_serialize_roundtrip(self, v1_data):
        char = Character(**v1_data)
        # Serialize to JSON and back
        json_str = char.model_dump_json()
        char_reloaded = Character.model_validate_json(json_str)

        assert char_reloaded.name == char.name
        assert char_reloaded.experience_points == 0
        assert char_reloaded.speed == 30
        assert char_reloaded.hit_points_current == 22

    def test_v1_preserves_existing_data(self, v1_data):
        char = Character(**v1_data)
        assert char.abilities["intelligence"].score == 18
        assert char.hit_points_current == 22
        assert char.hit_points_max == 28
        assert char.alignment == "Neutral Good"
        assert len(char.inventory) == 1
        assert char.inventory[0].name == "Quarterstaff"


# ═══════════════════════════════════════════════════════════════════════
# E2E Test: No Rulebook Error
# ═══════════════════════════════════════════════════════════════════════


class TestNoRulebookError:

    def test_builder_with_no_class_raises(self):
        manager = make_mock_manager(class_def=None, race_def=make_human_def())
        builder = CharacterBuilder(manager)
        with pytest.raises(CharacterBuilderError, match="[Cc]lass"):
            builder.build("Test", "Fighter", "Human", 1)

    def test_builder_with_no_race_raises(self):
        manager = make_mock_manager(class_def=make_fighter_def(), race_def=None)
        builder = CharacterBuilder(manager)
        with pytest.raises(CharacterBuilderError, match="[Rr]ace"):
            builder.build("Test", "Fighter", "Human", 1)


# ═══════════════════════════════════════════════════════════════════════
# E2E Test: Ability Score Methods
# ═══════════════════════════════════════════════════════════════════════


class TestAbilityScoreMethods:

    def setup_method(self):
        self.manager = make_mock_manager(
            class_def=make_fighter_def(),
            race_def=make_human_def(),
        )
        self.builder = CharacterBuilder(self.manager)

    def test_standard_array(self):
        assignments = {
            "strength": 15, "dexterity": 14, "constitution": 13,
            "intelligence": 12, "wisdom": 10, "charisma": 8,
        }
        char = self.builder.build(
            "Test", "Fighter", "Human", 1,
            ability_method="standard_array",
            ability_assignments=assignments,
        )
        # 15 + 1 (human) = 16 STR
        assert char.abilities["strength"].score == 16
        assert char.abilities["charisma"].score == 9  # 8 + 1

    def test_point_buy(self):
        # Point buy budget = 27. Costs: 15→9, 14→7, 13→5, 12→4, 10→2, 8→0 = 27
        assignments = {
            "strength": 15, "dexterity": 14, "constitution": 13,
            "intelligence": 12, "wisdom": 10, "charisma": 8,
        }
        char = self.builder.build(
            "Test", "Fighter", "Human", 1,
            ability_method="point_buy",
            ability_assignments=assignments,
        )
        # With human: +1 to all
        assert char.abilities["strength"].score == 16
        assert char.abilities["dexterity"].score == 15
        assert char.abilities["charisma"].score == 9

    def test_manual_default_10s(self):
        char = self.builder.build("Test", "Fighter", "Human", 1)
        # All 10 + 1 (human) = 11
        for ability in char.abilities.values():
            assert ability.score == 11


# ═══════════════════════════════════════════════════════════════════════
# E2E Test: Performance Benchmark
# ═══════════════════════════════════════════════════════════════════════


class TestPerformance:

    def test_character_creation_under_2_seconds(self):
        manager = make_mock_manager(
            class_def=make_wizard_def(),
            race_def=make_human_def(),
            bg_def=make_acolyte_def(),
        )
        builder = CharacterBuilder(manager)

        start = time.perf_counter()
        for _ in range(100):
            builder.build(
                "Benchmark", "Wizard", "Human", 5,
                background="Acolyte", subclass="evocation",
            )
        elapsed = time.perf_counter() - start

        # 100 creations should complete well within 2 seconds
        assert elapsed < 2.0, f"100 character creations took {elapsed:.2f}s (budget: 2.0s)"

    def test_level_up_performance(self):
        manager = make_mock_manager(
            class_def=make_fighter_def(),
            race_def=make_human_def(),
        )
        builder = CharacterBuilder(manager)
        engine = LevelUpEngine(manager)

        start = time.perf_counter()
        for _ in range(100):
            char = builder.build("Bench", "Fighter", "Human", 1)
            for _ in range(4):  # Level 1→5
                engine.level_up(char)
        elapsed = time.perf_counter() - start

        # 100 full progressions (1→5) should be fast
        assert elapsed < 2.0, f"100 level-up chains took {elapsed:.2f}s (budget: 2.0s)"
