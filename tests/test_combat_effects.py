"""
Tests for the Active Effects system.

Covers:
- Modifier and ActiveEffect model creation/serialization
- EffectsEngine: apply/remove effects, effective stat computation,
  advantage/disadvantage resolution, duration ticking, SRD conditions
- Backward compatibility (Character without active_effects)
- Edge cases: stacking, multiple modifiers, set+add ordering, etc.
"""

import pytest

from dm20_protocol.models import (
    ActiveEffect,
    Modifier,
    Character,
    CharacterClass,
    Race,
    AbilityScore,
)
from dm20_protocol.combat.effects import EffectsEngine, SRD_CONDITIONS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fighter() -> Character:
    """A level 5 fighter with reasonable stats."""
    return Character(
        name="Aldric",
        player_name="TestPlayer",
        character_class=CharacterClass(name="Fighter", level=5, hit_dice="1d10"),
        race=Race(name="Human"),
        abilities={
            "strength": AbilityScore(score=16),
            "dexterity": AbilityScore(score=14),
            "constitution": AbilityScore(score=14),
            "intelligence": AbilityScore(score=10),
            "wisdom": AbilityScore(score=12),
            "charisma": AbilityScore(score=8),
        },
        armor_class=18,
        speed=30,
        hit_points_max=44,
        hit_points_current=44,
    )


@pytest.fixture
def wizard() -> Character:
    """A level 3 wizard for spellcasting tests."""
    return Character(
        name="Elara",
        player_name="TestWizard",
        character_class=CharacterClass(name="Wizard", level=3, hit_dice="1d6"),
        race=Race(name="Elf", subrace="High Elf"),
        abilities={
            "strength": AbilityScore(score=8),
            "dexterity": AbilityScore(score=14),
            "constitution": AbilityScore(score=12),
            "intelligence": AbilityScore(score=18),
            "wisdom": AbilityScore(score=13),
            "charisma": AbilityScore(score=10),
        },
        armor_class=12,
        speed=30,
        hit_points_max=18,
        hit_points_current=18,
    )


def make_effect(
    name: str = "Test Effect",
    modifiers: list[Modifier] | None = None,
    duration_type: str = "permanent",
    duration_remaining: int | None = None,
    grants_advantage: list[str] | None = None,
    grants_disadvantage: list[str] | None = None,
    immunities: list[str] | None = None,
    stackable: bool = False,
    source: str = "Test",
) -> ActiveEffect:
    """Helper to create an ActiveEffect with sensible defaults."""
    return ActiveEffect(
        name=name,
        source=source,
        modifiers=modifiers or [],
        duration_type=duration_type,
        duration_remaining=duration_remaining,
        grants_advantage=grants_advantage or [],
        grants_disadvantage=grants_disadvantage or [],
        immunities=immunities or [],
        stackable=stackable,
    )


# ===========================================================================
# Model Tests
# ===========================================================================

class TestModifierModel:
    """Tests for the Modifier Pydantic model."""

    def test_create_add_modifier(self):
        mod = Modifier(stat="attack_roll", operation="add", value=2)
        assert mod.stat == "attack_roll"
        assert mod.operation == "add"
        assert mod.value == 2

    def test_create_set_modifier(self):
        mod = Modifier(stat="speed", operation="set", value=0)
        assert mod.operation == "set"
        assert mod.value == 0

    def test_create_dice_modifier(self):
        mod = Modifier(stat="attack_roll", operation="dice", value="1d4")
        assert mod.operation == "dice"
        assert mod.value == "1d4"

    def test_default_operation_is_add(self):
        mod = Modifier(stat="armor_class", value=1)
        assert mod.operation == "add"

    def test_serialization_roundtrip(self):
        mod = Modifier(stat="attack_roll", operation="dice", value="1d4")
        data = mod.model_dump()
        restored = Modifier.model_validate(data)
        assert restored.stat == mod.stat
        assert restored.operation == mod.operation
        assert restored.value == mod.value


class TestActiveEffectModel:
    """Tests for the ActiveEffect Pydantic model."""

    def test_create_minimal_effect(self):
        effect = ActiveEffect(name="Shield of Faith")
        assert effect.name == "Shield of Faith"
        assert effect.source == ""
        assert effect.modifiers == []
        assert effect.duration_type == "permanent"
        assert effect.duration_remaining is None
        assert effect.grants_advantage == []
        assert effect.grants_disadvantage == []
        assert effect.immunities == []
        assert effect.stackable is False
        assert len(effect.id) == 8

    def test_create_full_effect(self):
        effect = make_effect(
            name="Shield of Faith",
            source="Shield of Faith spell",
            modifiers=[Modifier(stat="armor_class", operation="add", value=2)],
            duration_type="concentration",
            grants_advantage=["saving_throw"],
            immunities=["fire"],
            stackable=False,
        )
        assert effect.name == "Shield of Faith"
        assert len(effect.modifiers) == 1
        assert effect.modifiers[0].stat == "armor_class"
        assert effect.immunities == ["fire"]

    def test_unique_ids(self):
        e1 = ActiveEffect(name="A")
        e2 = ActiveEffect(name="A")
        assert e1.id != e2.id

    def test_serialization_roundtrip(self):
        effect = make_effect(
            name="Bless",
            modifiers=[Modifier(stat="attack_roll", operation="dice", value="1d4")],
            duration_type="concentration",
            grants_advantage=["saving_throw"],
        )
        data = effect.model_dump()
        restored = ActiveEffect.model_validate(data)
        assert restored.name == effect.name
        assert restored.modifiers[0].value == "1d4"
        assert restored.grants_advantage == ["saving_throw"]


# ===========================================================================
# Character Integration Tests
# ===========================================================================

class TestCharacterActiveEffects:
    """Tests for ActiveEffect integration with the Character model."""

    def test_character_has_active_effects_field(self, fighter):
        assert hasattr(fighter, "active_effects")
        assert fighter.active_effects == []

    def test_character_serialization_with_effects(self, fighter):
        effect = make_effect(
            name="Shield of Faith",
            modifiers=[Modifier(stat="armor_class", value=2)],
        )
        fighter.active_effects.append(effect)
        data = fighter.model_dump()
        assert "active_effects" in data
        assert len(data["active_effects"]) == 1
        assert data["active_effects"][0]["name"] == "Shield of Faith"

    def test_character_deserialization_with_effects(self, fighter):
        effect = make_effect(name="Bless")
        fighter.active_effects.append(effect)
        data = fighter.model_dump()
        restored = Character.model_validate(data)
        assert len(restored.active_effects) == 1
        assert restored.active_effects[0].name == "Bless"

    def test_backward_compatibility_no_effects_field(self):
        """Campaigns saved before active_effects was added should load cleanly."""
        data = {
            "name": "OldChar",
            "character_class": {"name": "Rogue", "level": 1},
            "race": {"name": "Halfling"},
        }
        char = Character.model_validate(data)
        assert char.active_effects == []

    def test_conditions_field_still_works(self, fighter):
        """The legacy conditions field must still be functional."""
        fighter.conditions = ["poisoned", "prone"]
        assert "poisoned" in fighter.conditions
        assert "prone" in fighter.conditions
        data = fighter.model_dump()
        assert data["conditions"] == ["poisoned", "prone"]


# ===========================================================================
# EffectsEngine: Apply / Remove
# ===========================================================================

class TestEffectsEngineApplyRemove:
    """Tests for EffectsEngine.apply_effect and remove_effect."""

    def test_apply_effect(self, fighter):
        effect = make_effect(name="Shield of Faith")
        applied = EffectsEngine.apply_effect(fighter, effect)
        assert len(fighter.active_effects) == 1
        assert fighter.active_effects[0].name == "Shield of Faith"
        # Returned effect should be the one added (not the template)
        assert applied.id == fighter.active_effects[0].id

    def test_apply_creates_unique_copy(self, fighter, wizard):
        """Applying the same template to two characters creates independent copies."""
        template = make_effect(name="Bless")
        applied1 = EffectsEngine.apply_effect(fighter, template)
        applied2 = EffectsEngine.apply_effect(wizard, template)
        assert applied1.id != applied2.id
        assert applied1.id != template.id

    def test_non_stackable_prevents_duplicates(self, fighter):
        effect = make_effect(name="Shield of Faith", stackable=False)
        first = EffectsEngine.apply_effect(fighter, effect)
        second = EffectsEngine.apply_effect(fighter, effect)
        assert len(fighter.active_effects) == 1
        # Should return the existing one
        assert second.id == first.id

    def test_stackable_allows_duplicates(self, fighter):
        effect = make_effect(name="Exhaustion", stackable=True)
        EffectsEngine.apply_effect(fighter, effect)
        EffectsEngine.apply_effect(fighter, effect)
        assert len(fighter.active_effects) == 2
        assert all(e.name == "Exhaustion" for e in fighter.active_effects)

    def test_remove_effect_by_id(self, fighter):
        effect = make_effect(name="Bless")
        applied = EffectsEngine.apply_effect(fighter, effect)
        removed = EffectsEngine.remove_effect(fighter, applied.id)
        assert removed is not None
        assert removed.name == "Bless"
        assert len(fighter.active_effects) == 0

    def test_remove_nonexistent_effect(self, fighter):
        result = EffectsEngine.remove_effect(fighter, "nonexistent_id")
        assert result is None

    def test_remove_effects_by_name(self, fighter):
        # Apply two stackable effects
        effect = make_effect(name="Exhaustion", stackable=True)
        EffectsEngine.apply_effect(fighter, effect)
        EffectsEngine.apply_effect(fighter, effect)
        # Also add a different effect
        EffectsEngine.apply_effect(fighter, make_effect(name="Bless"))
        assert len(fighter.active_effects) == 3

        removed = EffectsEngine.remove_effects_by_name(fighter, "Exhaustion")
        assert len(removed) == 2
        assert len(fighter.active_effects) == 1
        assert fighter.active_effects[0].name == "Bless"

    def test_remove_effects_by_name_nonexistent(self, fighter):
        removed = EffectsEngine.remove_effects_by_name(fighter, "Nonexistent")
        assert removed == []


# ===========================================================================
# EffectsEngine: Effective Stat Computation
# ===========================================================================

class TestEffectsEngineEffectiveStat:
    """Tests for EffectsEngine.effective_stat."""

    def test_base_stat_no_effects(self, fighter):
        """Without effects, effective stat equals base stat."""
        assert EffectsEngine.effective_stat(fighter, "armor_class") == 18
        assert EffectsEngine.effective_stat(fighter, "speed") == 30
        assert EffectsEngine.effective_stat(fighter, "strength") == 16

    def test_add_modifier(self, fighter):
        effect = make_effect(
            name="Shield of Faith",
            modifiers=[Modifier(stat="armor_class", operation="add", value=2)],
        )
        EffectsEngine.apply_effect(fighter, effect)
        assert EffectsEngine.effective_stat(fighter, "armor_class") == 20

    def test_multiple_add_modifiers_stack(self, fighter):
        e1 = make_effect(
            name="Shield of Faith",
            modifiers=[Modifier(stat="armor_class", operation="add", value=2)],
        )
        e2 = make_effect(
            name="Haste AC Bonus",
            modifiers=[Modifier(stat="armor_class", operation="add", value=2)],
        )
        EffectsEngine.apply_effect(fighter, e1)
        EffectsEngine.apply_effect(fighter, e2)
        assert EffectsEngine.effective_stat(fighter, "armor_class") == 22

    def test_set_modifier_overrides_base(self, fighter):
        effect = make_effect(
            name="Grappled",
            modifiers=[Modifier(stat="speed", operation="set", value=0)],
        )
        EffectsEngine.apply_effect(fighter, effect)
        assert EffectsEngine.effective_stat(fighter, "speed") == 0

    def test_set_plus_add(self, fighter):
        """Set overrides base, then add applies on top of the set value."""
        e1 = make_effect(
            name="Web",
            modifiers=[Modifier(stat="speed", operation="set", value=0)],
        )
        e2 = make_effect(
            name="Speed Boost",
            modifiers=[Modifier(stat="speed", operation="add", value=10)],
        )
        EffectsEngine.apply_effect(fighter, e1)
        EffectsEngine.apply_effect(fighter, e2)
        # Set to 0, then add 10 = 10
        assert EffectsEngine.effective_stat(fighter, "speed") == 10

    def test_negative_add_modifier(self, fighter):
        effect = make_effect(
            name="Curse",
            modifiers=[Modifier(stat="armor_class", operation="add", value=-2)],
        )
        EffectsEngine.apply_effect(fighter, effect)
        assert EffectsEngine.effective_stat(fighter, "armor_class") == 16

    def test_ability_score_stat(self, fighter):
        """Ability scores should be retrievable."""
        assert EffectsEngine.effective_stat(fighter, "strength") == 16
        effect = make_effect(
            name="Bull's Strength",
            modifiers=[Modifier(stat="strength", operation="add", value=4)],
        )
        EffectsEngine.apply_effect(fighter, effect)
        assert EffectsEngine.effective_stat(fighter, "strength") == 20

    def test_ability_modifier_stat(self, fighter):
        """Ability modifiers (e.g., strength_mod) should be retrievable."""
        # STR 16 -> mod +3
        assert EffectsEngine.effective_stat(fighter, "strength_mod") == 3

    def test_unknown_stat_returns_zero(self, fighter):
        """Unknown stats (like 'attack_roll') return 0 base and then modifiers."""
        assert EffectsEngine.effective_stat(fighter, "attack_roll") == 0
        effect = make_effect(
            name="Bless bonus",
            modifiers=[Modifier(stat="attack_roll", operation="add", value=2)],
        )
        EffectsEngine.apply_effect(fighter, effect)
        assert EffectsEngine.effective_stat(fighter, "attack_roll") == 2

    def test_dice_modifiers_not_included_in_effective_stat(self, fighter):
        """Dice modifiers shouldn't affect the static effective_stat calculation."""
        effect = make_effect(
            name="Bless",
            modifiers=[Modifier(stat="attack_roll", operation="dice", value="1d4")],
        )
        EffectsEngine.apply_effect(fighter, effect)
        # Dice modifiers are not resolved in effective_stat
        assert EffectsEngine.effective_stat(fighter, "attack_roll") == 0

    def test_get_dice_modifiers(self, fighter):
        effect = make_effect(
            name="Bless",
            modifiers=[Modifier(stat="attack_roll", operation="dice", value="1d4")],
        )
        EffectsEngine.apply_effect(fighter, effect)
        dice = EffectsEngine.get_dice_modifiers(fighter, "attack_roll")
        assert dice == ["1d4"]

    def test_get_dice_modifiers_empty(self, fighter):
        assert EffectsEngine.get_dice_modifiers(fighter, "attack_roll") == []

    def test_mixed_modifiers_on_same_stat(self, fighter):
        """Multiple modifier types on the same stat from one effect."""
        effect = make_effect(
            name="Complex Buff",
            modifiers=[
                Modifier(stat="attack_roll", operation="add", value=2),
                Modifier(stat="attack_roll", operation="dice", value="1d4"),
            ],
        )
        EffectsEngine.apply_effect(fighter, effect)
        # Only add is reflected in effective_stat
        assert EffectsEngine.effective_stat(fighter, "attack_roll") == 2
        # Dice is separate
        assert EffectsEngine.get_dice_modifiers(fighter, "attack_roll") == ["1d4"]

    def test_proficiency_bonus_stat(self, fighter):
        """proficiency_bonus should be accessible as a stat."""
        # Level 5 fighter: proficiency bonus = 3
        assert EffectsEngine.effective_stat(fighter, "proficiency_bonus") == 3

    def test_hit_points_stats(self, fighter):
        assert EffectsEngine.effective_stat(fighter, "hit_points_max") == 44
        assert EffectsEngine.effective_stat(fighter, "hit_points_current") == 44


# ===========================================================================
# EffectsEngine: Advantage / Disadvantage
# ===========================================================================

class TestEffectsEngineAdvantageDisadvantage:
    """Tests for advantage/disadvantage resolution."""

    def test_no_effects_no_advantage(self, fighter):
        assert EffectsEngine.has_advantage(fighter, "attack_roll") is False
        assert EffectsEngine.has_disadvantage(fighter, "attack_roll") is False

    def test_advantage_from_effect(self, fighter):
        effect = make_effect(
            name="Invisible",
            grants_advantage=["attack_roll"],
        )
        EffectsEngine.apply_effect(fighter, effect)
        assert EffectsEngine.has_advantage(fighter, "attack_roll") is True
        assert EffectsEngine.has_disadvantage(fighter, "attack_roll") is False

    def test_disadvantage_from_effect(self, fighter):
        effect = make_effect(
            name="Poisoned",
            grants_disadvantage=["attack_roll", "ability_check"],
        )
        EffectsEngine.apply_effect(fighter, effect)
        assert EffectsEngine.has_disadvantage(fighter, "attack_roll") is True
        assert EffectsEngine.has_disadvantage(fighter, "ability_check") is True
        assert EffectsEngine.has_advantage(fighter, "attack_roll") is False

    def test_advantage_and_disadvantage_cancel_out(self, fighter):
        """5e rule: advantage + disadvantage on the same check cancel out."""
        adv = make_effect(name="Invisible", grants_advantage=["attack_roll"])
        disadv = make_effect(name="Poisoned", grants_disadvantage=["attack_roll"])
        EffectsEngine.apply_effect(fighter, adv)
        EffectsEngine.apply_effect(fighter, disadv)
        assert EffectsEngine.has_advantage(fighter, "attack_roll") is False
        assert EffectsEngine.has_disadvantage(fighter, "attack_roll") is False

    def test_multiple_advantage_sources_still_cancel_with_one_disadvantage(self, fighter):
        """Even multiple advantage sources cancel with one disadvantage source."""
        adv1 = make_effect(name="Invisible", grants_advantage=["attack_roll"])
        adv2 = make_effect(name="Flanking", grants_advantage=["attack_roll"])
        disadv = make_effect(name="Poisoned", grants_disadvantage=["attack_roll"])
        EffectsEngine.apply_effect(fighter, adv1)
        EffectsEngine.apply_effect(fighter, adv2)
        EffectsEngine.apply_effect(fighter, disadv)
        assert EffectsEngine.has_advantage(fighter, "attack_roll") is False
        assert EffectsEngine.has_disadvantage(fighter, "attack_roll") is False

    def test_advantage_on_different_check_types(self, fighter):
        """Advantage on one check doesn't affect other check types."""
        effect = make_effect(
            name="Invisible",
            grants_advantage=["attack_roll"],
        )
        EffectsEngine.apply_effect(fighter, effect)
        assert EffectsEngine.has_advantage(fighter, "attack_roll") is True
        assert EffectsEngine.has_advantage(fighter, "dexterity_save") is False

    def test_removing_effect_clears_advantage(self, fighter):
        effect = make_effect(name="Invisible", grants_advantage=["attack_roll"])
        applied = EffectsEngine.apply_effect(fighter, effect)
        assert EffectsEngine.has_advantage(fighter, "attack_roll") is True
        EffectsEngine.remove_effect(fighter, applied.id)
        assert EffectsEngine.has_advantage(fighter, "attack_roll") is False


# ===========================================================================
# EffectsEngine: Duration Ticking
# ===========================================================================

class TestEffectsEngineTick:
    """Tests for EffectsEngine.tick_effects."""

    def test_tick_round_duration(self, fighter):
        """Effects with duration_type='rounds' decrement on 'turn' events."""
        effect = make_effect(
            name="Shield",
            duration_type="rounds",
            duration_remaining=3,
        )
        EffectsEngine.apply_effect(fighter, effect)
        assert len(fighter.active_effects) == 1

        # Tick turn 1
        expired = EffectsEngine.tick_effects(fighter, event="turn")
        assert expired == []
        assert fighter.active_effects[0].duration_remaining == 2

        # Tick turn 2
        EffectsEngine.tick_effects(fighter, event="turn")
        assert fighter.active_effects[0].duration_remaining == 1

        # Tick turn 3 -> expires
        expired = EffectsEngine.tick_effects(fighter, event="turn")
        assert len(expired) == 1
        assert expired[0].name == "Shield"
        assert len(fighter.active_effects) == 0

    def test_tick_minutes_duration(self, fighter):
        """Effects with duration_type='minutes' decrement on 'round' events."""
        effect = make_effect(
            name="Bless",
            duration_type="minutes",
            duration_remaining=2,
        )
        EffectsEngine.apply_effect(fighter, effect)

        # Turn events should NOT decrement minutes-based effects
        expired = EffectsEngine.tick_effects(fighter, event="turn")
        assert expired == []
        assert fighter.active_effects[0].duration_remaining == 2

        # Round events should decrement
        expired = EffectsEngine.tick_effects(fighter, event="round")
        assert expired == []
        assert fighter.active_effects[0].duration_remaining == 1

        expired = EffectsEngine.tick_effects(fighter, event="round")
        assert len(expired) == 1

    def test_permanent_never_ticks(self, fighter):
        """Permanent effects never expire from ticking."""
        effect = make_effect(name="Darkvision", duration_type="permanent")
        EffectsEngine.apply_effect(fighter, effect)

        EffectsEngine.tick_effects(fighter, event="turn")
        EffectsEngine.tick_effects(fighter, event="round")
        assert len(fighter.active_effects) == 1

    def test_concentration_never_ticks(self, fighter):
        """Concentration effects don't expire from ticking (must be removed explicitly)."""
        effect = make_effect(name="Bless", duration_type="concentration")
        EffectsEngine.apply_effect(fighter, effect)

        EffectsEngine.tick_effects(fighter, event="turn")
        EffectsEngine.tick_effects(fighter, event="round")
        assert len(fighter.active_effects) == 1

    def test_tick_multiple_effects(self, fighter):
        """Ticking correctly handles a mix of effect durations."""
        e1 = make_effect(name="Shield", duration_type="rounds", duration_remaining=1)
        e2 = make_effect(name="Bless", duration_type="concentration")
        e3 = make_effect(name="Haste", duration_type="rounds", duration_remaining=3)
        EffectsEngine.apply_effect(fighter, e1)
        EffectsEngine.apply_effect(fighter, e2)
        EffectsEngine.apply_effect(fighter, e3)
        assert len(fighter.active_effects) == 3

        expired = EffectsEngine.tick_effects(fighter, event="turn")
        # Shield expires (was at 1), Haste goes to 2, Bless unchanged
        assert len(expired) == 1
        assert expired[0].name == "Shield"
        assert len(fighter.active_effects) == 2

    def test_tick_with_none_duration_remaining(self, fighter):
        """Effects with duration_remaining=None but type='rounds' should not crash."""
        effect = make_effect(
            name="Broken",
            duration_type="rounds",
            duration_remaining=None,
        )
        EffectsEngine.apply_effect(fighter, effect)
        # Should not crash, effect should remain (no decrement when None)
        expired = EffectsEngine.tick_effects(fighter, event="turn")
        assert expired == []
        assert len(fighter.active_effects) == 1


# ===========================================================================
# SRD Conditions
# ===========================================================================

class TestSRDConditions:
    """Tests for the SRD_CONDITIONS dictionary."""

    EXPECTED_CONDITIONS = [
        "blinded", "charmed", "deafened", "exhaustion", "frightened",
        "grappled", "incapacitated", "invisible", "paralyzed", "petrified",
        "poisoned", "prone", "restrained", "stunned",
    ]

    def test_all_14_conditions_defined(self):
        assert len(SRD_CONDITIONS) == 14
        for cond in self.EXPECTED_CONDITIONS:
            assert cond in SRD_CONDITIONS, f"Missing SRD condition: {cond}"

    def test_all_conditions_are_active_effects(self):
        for name, effect in SRD_CONDITIONS.items():
            assert isinstance(effect, ActiveEffect), f"{name} is not an ActiveEffect"

    def test_conditions_have_names(self):
        for key, effect in SRD_CONDITIONS.items():
            assert effect.name, f"Condition {key} has no name"

    def test_conditions_have_srd_source(self):
        for key, effect in SRD_CONDITIONS.items():
            assert "SRD" in effect.source, f"Condition {key} source should contain 'SRD'"

    def test_blinded_mechanics(self, fighter):
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["blinded"])
        assert EffectsEngine.has_disadvantage(fighter, "attack_roll") is True

    def test_frightened_mechanics(self, fighter):
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["frightened"])
        assert EffectsEngine.has_disadvantage(fighter, "attack_roll") is True
        assert EffectsEngine.has_disadvantage(fighter, "ability_check") is True

    def test_grappled_speed_zero(self, fighter):
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["grappled"])
        assert EffectsEngine.effective_stat(fighter, "speed") == 0

    def test_invisible_advantage(self, fighter):
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["invisible"])
        assert EffectsEngine.has_advantage(fighter, "attack_roll") is True

    def test_paralyzed_mechanics(self, fighter):
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["paralyzed"])
        assert EffectsEngine.effective_stat(fighter, "speed") == 0
        assert EffectsEngine.has_disadvantage(fighter, "strength_save") is True
        assert EffectsEngine.has_disadvantage(fighter, "dexterity_save") is True

    def test_petrified_mechanics(self, fighter):
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["petrified"])
        assert EffectsEngine.effective_stat(fighter, "speed") == 0
        immunities = EffectsEngine.get_immunities(fighter)
        assert "poison" in immunities

    def test_poisoned_mechanics(self, fighter):
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["poisoned"])
        assert EffectsEngine.has_disadvantage(fighter, "attack_roll") is True
        assert EffectsEngine.has_disadvantage(fighter, "ability_check") is True

    def test_prone_mechanics(self, fighter):
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["prone"])
        assert EffectsEngine.has_disadvantage(fighter, "attack_roll") is True

    def test_restrained_mechanics(self, fighter):
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["restrained"])
        assert EffectsEngine.effective_stat(fighter, "speed") == 0
        assert EffectsEngine.has_disadvantage(fighter, "attack_roll") is True
        assert EffectsEngine.has_disadvantage(fighter, "dexterity_save") is True

    def test_stunned_mechanics(self, fighter):
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["stunned"])
        assert EffectsEngine.effective_stat(fighter, "speed") == 0
        assert EffectsEngine.has_disadvantage(fighter, "strength_save") is True
        assert EffectsEngine.has_disadvantage(fighter, "dexterity_save") is True

    def test_exhaustion_is_stackable(self):
        assert SRD_CONDITIONS["exhaustion"].stackable is True

    def test_exhaustion_stacks(self, fighter):
        """Multiple exhaustion levels stack."""
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["exhaustion"])
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["exhaustion"])
        assert len(fighter.active_effects) == 2
        assert all(e.name == "Exhaustion" for e in fighter.active_effects)

    def test_non_stackable_condition_no_duplicate(self, fighter):
        """Non-stackable conditions should not duplicate."""
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["blinded"])
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["blinded"])
        assert len(fighter.active_effects) == 1

    def test_applying_condition_creates_copy(self, fighter, wizard):
        """Applying a condition to two characters should create independent copies."""
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["poisoned"])
        EffectsEngine.apply_effect(wizard, SRD_CONDITIONS["poisoned"])
        assert fighter.active_effects[0].id != wizard.active_effects[0].id
        # Original template should be unchanged
        assert SRD_CONDITIONS["poisoned"].id == "srd_poisoned"


# ===========================================================================
# Query Helpers
# ===========================================================================

class TestEffectsEngineQueryHelpers:
    """Tests for query helper methods."""

    def test_has_effect(self, fighter):
        assert EffectsEngine.has_effect(fighter, "Bless") is False
        EffectsEngine.apply_effect(fighter, make_effect(name="Bless"))
        assert EffectsEngine.has_effect(fighter, "Bless") is True

    def test_get_active_effects_by_name(self, fighter):
        EffectsEngine.apply_effect(fighter, make_effect(name="A"))
        EffectsEngine.apply_effect(fighter, make_effect(name="B"))
        results = EffectsEngine.get_active_effects_by_name(fighter, "A")
        assert len(results) == 1
        assert results[0].name == "A"

    def test_get_immunities(self, fighter):
        e1 = make_effect(name="Protection from Poison", immunities=["poison"])
        e2 = make_effect(name="Fire Shield", immunities=["fire", "cold"])
        EffectsEngine.apply_effect(fighter, e1)
        EffectsEngine.apply_effect(fighter, e2)
        immunities = EffectsEngine.get_immunities(fighter)
        assert immunities == {"poison", "fire", "cold"}

    def test_get_immunities_empty(self, fighter):
        assert EffectsEngine.get_immunities(fighter) == set()


# ===========================================================================
# Edge Cases and Complex Scenarios
# ===========================================================================

class TestEdgeCases:
    """Edge cases and complex interaction scenarios."""

    def test_multiple_set_modifiers_last_wins(self, fighter):
        """When multiple 'set' modifiers target the same stat, the last one in
        the iteration wins (both effects applied in order)."""
        e1 = make_effect(
            name="Slow",
            modifiers=[Modifier(stat="speed", operation="set", value=15)],
        )
        e2 = make_effect(
            name="Web",
            modifiers=[Modifier(stat="speed", operation="set", value=0)],
        )
        EffectsEngine.apply_effect(fighter, e1)
        EffectsEngine.apply_effect(fighter, e2)
        # Web (last) sets to 0
        assert EffectsEngine.effective_stat(fighter, "speed") == 0

    def test_effect_with_multiple_modifiers(self, fighter):
        """A single effect can modify multiple stats."""
        effect = make_effect(
            name="Haste",
            modifiers=[
                Modifier(stat="armor_class", operation="add", value=2),
                Modifier(stat="speed", operation="add", value=30),
            ],
        )
        EffectsEngine.apply_effect(fighter, effect)
        assert EffectsEngine.effective_stat(fighter, "armor_class") == 20
        assert EffectsEngine.effective_stat(fighter, "speed") == 60

    def test_effect_both_advantage_and_disadvantage(self, fighter):
        """A single effect can grant advantage on one check and disadvantage on another."""
        effect = make_effect(
            name="Reckless Attack",
            grants_advantage=["attack_roll"],
            grants_disadvantage=["dexterity_save"],
        )
        EffectsEngine.apply_effect(fighter, effect)
        assert EffectsEngine.has_advantage(fighter, "attack_roll") is True
        assert EffectsEngine.has_disadvantage(fighter, "dexterity_save") is True
        # No crossover
        assert EffectsEngine.has_disadvantage(fighter, "attack_roll") is False
        assert EffectsEngine.has_advantage(fighter, "dexterity_save") is False

    def test_empty_character_effects(self, fighter):
        """Operations on a character with no effects should work cleanly."""
        assert EffectsEngine.effective_stat(fighter, "armor_class") == 18
        assert EffectsEngine.has_advantage(fighter, "attack_roll") is False
        assert EffectsEngine.has_disadvantage(fighter, "attack_roll") is False
        expired = EffectsEngine.tick_effects(fighter, event="turn")
        assert expired == []
        assert EffectsEngine.get_dice_modifiers(fighter, "attack_roll") == []
        assert EffectsEngine.get_immunities(fighter) == set()

    def test_complex_combat_scenario(self, fighter):
        """Simulate a complex combat turn with multiple effects."""
        # Apply Bless (concentration, +1d4 to attacks and saves)
        bless = make_effect(
            name="Bless",
            source="Cleric spell",
            modifiers=[
                Modifier(stat="attack_roll", operation="dice", value="1d4"),
                Modifier(stat="saving_throw", operation="dice", value="1d4"),
            ],
            duration_type="concentration",
        )
        EffectsEngine.apply_effect(fighter, bless)

        # Fighter gets Shield of Faith (+2 AC, concentration)
        shield_of_faith = make_effect(
            name="Shield of Faith",
            source="Cleric spell",
            modifiers=[Modifier(stat="armor_class", operation="add", value=2)],
            duration_type="concentration",
        )
        EffectsEngine.apply_effect(fighter, shield_of_faith)

        # Fighter gets poisoned (2 round duration)
        poison = make_effect(
            name="Poisoned",
            source="Giant spider bite",
            grants_disadvantage=["attack_roll", "ability_check"],
            duration_type="rounds",
            duration_remaining=2,
        )
        EffectsEngine.apply_effect(fighter, poison)

        # Check stats
        assert EffectsEngine.effective_stat(fighter, "armor_class") == 20
        assert EffectsEngine.get_dice_modifiers(fighter, "attack_roll") == ["1d4"]

        # Poisoned gives disadvantage, but no advantage source -> disadvantage
        assert EffectsEngine.has_disadvantage(fighter, "attack_roll") is True

        # Tick turn 1
        expired = EffectsEngine.tick_effects(fighter, event="turn")
        assert expired == []
        # Tick turn 2 -> poison expires
        expired = EffectsEngine.tick_effects(fighter, event="turn")
        assert len(expired) == 1
        assert expired[0].name == "Poisoned"

        # After poison expires, no more disadvantage
        assert EffectsEngine.has_disadvantage(fighter, "attack_roll") is False
        # Concentration effects still active
        assert EffectsEngine.effective_stat(fighter, "armor_class") == 20
        assert len(fighter.active_effects) == 2
