"""
Tests for the Concentration Tracking system.

Covers:
- ConcentrationState model creation and serialization
- ConcentrationTracker: start/end concentration, CON save mechanics,
  auto-break on conditions/death, effect cleanup
- Single-concentration enforcement (new spell ends old)
- Backward compatibility (Character without concentration field)
- Edge cases: no damage, high damage, proficiency, effect modifiers
"""

import pytest
from unittest.mock import patch

from dm20_protocol.models import (
    ActiveEffect,
    ConcentrationState,
    Modifier,
    Character,
    CharacterClass,
    Race,
    AbilityScore,
)
from dm20_protocol.combat.effects import EffectsEngine, SRD_CONDITIONS
from dm20_protocol.combat.concentration import ConcentrationTracker, ConcentrationCheckResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def wizard() -> Character:
    """A level 5 wizard with reasonable stats and CON save proficiency."""
    return Character(
        name="Elara",
        player_name="TestPlayer",
        character_class=CharacterClass(name="Wizard", level=5, hit_dice="1d6"),
        race=Race(name="Elf"),
        abilities={
            "strength": AbilityScore(score=8),
            "dexterity": AbilityScore(score=14),
            "constitution": AbilityScore(score=14),  # +2 modifier
            "intelligence": AbilityScore(score=18),
            "wisdom": AbilityScore(score=12),
            "charisma": AbilityScore(score=10),
        },
        armor_class=12,
        speed=30,
        hit_points_max=32,
        hit_points_current=32,
        saving_throw_proficiencies=["constitution", "intelligence"],
        spellcasting_ability="intelligence",
    )


@pytest.fixture
def fighter() -> Character:
    """A level 5 fighter with no CON save proficiency."""
    return Character(
        name="Aldric",
        player_name="TestPlayer2",
        character_class=CharacterClass(name="Fighter", level=5, hit_dice="1d10"),
        race=Race(name="Human"),
        abilities={
            "strength": AbilityScore(score=16),
            "dexterity": AbilityScore(score=14),
            "constitution": AbilityScore(score=12),  # +1 modifier
            "intelligence": AbilityScore(score=10),
            "wisdom": AbilityScore(score=12),
            "charisma": AbilityScore(score=8),
        },
        armor_class=18,
        speed=30,
        hit_points_max=44,
        hit_points_current=44,
        saving_throw_proficiencies=["strength", "constitution"],
    )


def _make_concentration_effect(name: str = "Bless", source: str = "Bless spell") -> ActiveEffect:
    """Helper to create a concentration-type effect."""
    return ActiveEffect(
        name=name,
        source=source,
        duration_type="concentration",
        modifiers=[Modifier(stat="attack_roll", operation="dice", value="1d4")],
    )


# ---------------------------------------------------------------------------
# ConcentrationState Model Tests
# ---------------------------------------------------------------------------

class TestConcentrationStateModel:
    """Tests for the ConcentrationState Pydantic model."""

    def test_create_basic(self):
        state = ConcentrationState(spell_name="Bless")
        assert state.spell_name == "Bless"
        assert state.effect_ids == []
        assert state.started_round == 0

    def test_create_with_all_fields(self):
        state = ConcentrationState(
            spell_name="Hold Person",
            effect_ids=["eff1", "eff2"],
            started_round=3,
        )
        assert state.spell_name == "Hold Person"
        assert state.effect_ids == ["eff1", "eff2"]
        assert state.started_round == 3

    def test_serialization_roundtrip(self):
        state = ConcentrationState(
            spell_name="Fly",
            effect_ids=["abc123"],
            started_round=1,
        )
        data = state.model_dump()
        restored = ConcentrationState.model_validate(data)
        assert restored.spell_name == state.spell_name
        assert restored.effect_ids == state.effect_ids
        assert restored.started_round == state.started_round


# ---------------------------------------------------------------------------
# Character Model Integration Tests
# ---------------------------------------------------------------------------

class TestCharacterConcentrationField:
    """Tests for the concentration field on Character."""

    def test_default_is_none(self, wizard: Character):
        assert wizard.concentration is None

    def test_set_concentration_state(self, wizard: Character):
        wizard.concentration = ConcentrationState(spell_name="Bless")
        assert wizard.concentration is not None
        assert wizard.concentration.spell_name == "Bless"

    def test_clear_concentration(self, wizard: Character):
        wizard.concentration = ConcentrationState(spell_name="Bless")
        wizard.concentration = None
        assert wizard.concentration is None

    def test_backward_compatibility_no_field(self):
        """Characters created without concentration field load as None."""
        data = {
            "name": "OldChar",
            "character_class": {"name": "Fighter", "level": 1},
            "race": {"name": "Human"},
        }
        char = Character.model_validate(data)
        assert char.concentration is None

    def test_serialization_with_concentration(self, wizard: Character):
        wizard.concentration = ConcentrationState(
            spell_name="Haste",
            effect_ids=["e1", "e2"],
            started_round=5,
        )
        data = wizard.model_dump()
        restored = Character.model_validate(data)
        assert restored.concentration is not None
        assert restored.concentration.spell_name == "Haste"
        assert restored.concentration.effect_ids == ["e1", "e2"]

    def test_serialization_without_concentration(self, wizard: Character):
        data = wizard.model_dump()
        assert data["concentration"] is None
        restored = Character.model_validate(data)
        assert restored.concentration is None


# ---------------------------------------------------------------------------
# Start Concentration Tests
# ---------------------------------------------------------------------------

class TestStartConcentration:
    """Tests for ConcentrationTracker.start_concentration()."""

    def test_start_basic(self, wizard: Character):
        result = ConcentrationTracker.start_concentration(wizard, "Bless")
        assert result["spell_name"] == "Bless"
        assert result["previous_spell"] is None
        assert result["previous_effects_removed"] == []
        assert wizard.concentration is not None
        assert wizard.concentration.spell_name == "Bless"

    def test_start_with_effect_ids(self, wizard: Character):
        result = ConcentrationTracker.start_concentration(
            wizard, "Hold Person", effect_ids=["eff1", "eff2"], current_round=3
        )
        assert wizard.concentration.effect_ids == ["eff1", "eff2"]
        assert wizard.concentration.started_round == 3

    def test_start_replaces_old_concentration(self, wizard: Character):
        # Start first concentration with an effect
        effect = _make_concentration_effect("Bless")
        applied = EffectsEngine.apply_effect(wizard, effect)
        ConcentrationTracker.start_concentration(
            wizard, "Bless", effect_ids=[applied.id]
        )
        assert wizard.concentration.spell_name == "Bless"
        assert len(wizard.active_effects) == 1

        # Start second concentration -> old one should break
        result = ConcentrationTracker.start_concentration(wizard, "Hold Person")
        assert result["previous_spell"] == "Bless"
        assert applied.id in result["previous_effects_removed"]
        assert wizard.concentration.spell_name == "Hold Person"
        # Old effect should be removed
        assert len(wizard.active_effects) == 0

    def test_start_new_without_effect_ids(self, wizard: Character):
        ConcentrationTracker.start_concentration(wizard, "Bless")
        assert wizard.concentration.effect_ids == []

    def test_start_preserves_non_concentration_effects(self, wizard: Character):
        """Starting concentration should not remove unrelated effects."""
        unrelated = ActiveEffect(name="Shield of Faith", source="Ally", duration_type="rounds", duration_remaining=10)
        EffectsEngine.apply_effect(wizard, unrelated)
        assert len(wizard.active_effects) == 1

        ConcentrationTracker.start_concentration(wizard, "Bless")
        # Unrelated effect should still be there
        assert len(wizard.active_effects) == 1
        assert wizard.active_effects[0].name == "Shield of Faith"


# ---------------------------------------------------------------------------
# End Concentration Tests
# ---------------------------------------------------------------------------

class TestEndConcentration:
    """Tests for ConcentrationTracker.end_concentration()."""

    def test_end_when_concentrating(self, wizard: Character):
        effect = _make_concentration_effect("Bless")
        applied = EffectsEngine.apply_effect(wizard, effect)
        ConcentrationTracker.start_concentration(wizard, "Bless", effect_ids=[applied.id])

        result = ConcentrationTracker.end_concentration(wizard)
        assert result["spell_name"] == "Bless"
        assert applied.id in result["effects_removed"]
        assert wizard.concentration is None
        assert len(wizard.active_effects) == 0

    def test_end_when_not_concentrating(self, wizard: Character):
        result = ConcentrationTracker.end_concentration(wizard)
        assert result["spell_name"] is None
        assert result["effects_removed"] == []


# ---------------------------------------------------------------------------
# Concentration Check (CON Save) Tests
# ---------------------------------------------------------------------------

class TestCheckConcentration:
    """Tests for ConcentrationTracker.check_concentration()."""

    def test_not_concentrating_returns_none(self, wizard: Character):
        result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)
        assert result is None

    def test_dc_calculation_low_damage(self, wizard: Character):
        """DC should be 10 for damage <= 20."""
        ConcentrationTracker.start_concentration(wizard, "Bless")
        # For damage=10, DC = max(10, 10 // 2) = max(10, 5) = 10
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=20):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)
        assert result.dc == 10

    def test_dc_calculation_high_damage(self, wizard: Character):
        """DC should be damage // 2 for damage > 20."""
        ConcentrationTracker.start_concentration(wizard, "Bless")
        # For damage=30, DC = max(10, 30 // 2) = max(10, 15) = 15
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=20):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=30)
        assert result.dc == 15

    def test_dc_minimum_is_10(self, wizard: Character):
        """DC should never go below 10, even for very low damage."""
        ConcentrationTracker.start_concentration(wizard, "Bless")
        # For damage=1, DC = max(10, 1 // 2) = max(10, 0) = 10
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=20):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=1)
        assert result.dc == 10

    def test_successful_save_maintains_concentration(self, wizard: Character):
        """High roll should maintain concentration."""
        effect = _make_concentration_effect("Bless")
        applied = EffectsEngine.apply_effect(wizard, effect)
        ConcentrationTracker.start_concentration(wizard, "Bless", effect_ids=[applied.id])

        # Wizard: CON mod +2, proficiency +3 = +5 total
        # Roll 20 + 5 = 25 vs DC 10 -> success
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=20):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)

        assert result.success is True
        assert result.broke is False
        assert result.effects_removed == []
        assert wizard.concentration is not None
        assert wizard.concentration.spell_name == "Bless"
        assert len(wizard.active_effects) == 1

    def test_failed_save_breaks_concentration(self, wizard: Character):
        """Low roll should break concentration and remove effects."""
        effect = _make_concentration_effect("Bless")
        applied = EffectsEngine.apply_effect(wizard, effect)
        ConcentrationTracker.start_concentration(wizard, "Bless", effect_ids=[applied.id])

        # Wizard: CON mod +2, proficiency +3 = +5 total
        # Roll 1 + 5 = 6 vs DC 10 -> fail
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=1):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)

        assert result.success is False
        assert result.broke is True
        assert applied.id in result.effects_removed
        assert wizard.concentration is None
        assert len(wizard.active_effects) == 0

    def test_save_with_proficiency(self, wizard: Character):
        """Wizard has CON save proficiency, should use it."""
        ConcentrationTracker.start_concentration(wizard, "Bless")

        # Wizard has CON proficiency: CON mod +2, prof +3 = +5
        # Roll 5 + 5 = 10, DC = 10 -> success (equal meets DC)
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=5):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)

        assert result.total == 10  # 5 + 5
        assert result.success is True

    def test_save_without_proficiency(self, wizard: Character):
        """Test save calculation without CON save proficiency."""
        # Remove CON save proficiency
        wizard.saving_throw_proficiencies = ["intelligence"]
        ConcentrationTracker.start_concentration(wizard, "Bless")

        # Now just CON mod +2, no proficiency
        # Roll 5 + 2 = 7 vs DC 10 -> fail
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=5):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)

        assert result.total == 7  # 5 + 2
        assert result.success is False

    def test_save_with_effect_modifier(self, wizard: Character):
        """Active effect modifiers should affect CON save bonus."""
        # Apply an effect that adds +2 to constitution_save
        bonus_effect = ActiveEffect(
            name="Aura of Protection",
            source="Paladin aura",
            modifiers=[Modifier(stat="constitution_save", operation="add", value=2)],
        )
        EffectsEngine.apply_effect(wizard, bonus_effect)

        ConcentrationTracker.start_concentration(wizard, "Bless")

        # Wizard: CON mod +2, prof +3, effect +2 = +7
        # Roll 3 + 7 = 10, DC 10 -> success
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=3):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)

        assert result.total == 10  # 3 + 7
        assert result.success is True

    def test_result_contains_spell_name(self, wizard: Character):
        ConcentrationTracker.start_concentration(wizard, "Hold Person")
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=20):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=5)
        assert result.spell_name == "Hold Person"

    def test_result_detail_string(self, wizard: Character):
        ConcentrationTracker.start_concentration(wizard, "Bless")
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=20):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)
        assert "Elara" in result.detail
        assert "Bless" in result.detail
        assert "maintains" in result.detail

    def test_failed_result_detail_string(self, wizard: Character):
        ConcentrationTracker.start_concentration(wizard, "Bless")
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=1):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)
        assert "loses" in result.detail

    def test_multiple_effects_cleaned_on_break(self, wizard: Character):
        """Multiple effects tied to concentration should all be removed on break."""
        effect1 = ActiveEffect(name="Bless A", source="Bless spell", duration_type="concentration")
        effect2 = ActiveEffect(name="Bless B", source="Bless spell", duration_type="concentration")
        applied1 = EffectsEngine.apply_effect(wizard, effect1)
        applied2 = EffectsEngine.apply_effect(wizard, effect2)

        ConcentrationTracker.start_concentration(
            wizard, "Bless", effect_ids=[applied1.id, applied2.id]
        )
        assert len(wizard.active_effects) == 2

        with patch("dm20_protocol.combat.concentration._random.randint", return_value=1):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)

        assert result.broke is True
        assert len(result.effects_removed) == 2
        assert len(wizard.active_effects) == 0


# ---------------------------------------------------------------------------
# Auto-break Tests
# ---------------------------------------------------------------------------

class TestAutoBreak:
    """Tests for ConcentrationTracker.check_auto_break()."""

    def test_auto_break_on_zero_hp(self, wizard: Character):
        """Concentration should break when HP drops to 0."""
        effect = _make_concentration_effect("Bless")
        applied = EffectsEngine.apply_effect(wizard, effect)
        ConcentrationTracker.start_concentration(wizard, "Bless", effect_ids=[applied.id])

        wizard.hit_points_current = 0
        result = ConcentrationTracker.check_auto_break(wizard)

        assert result is not None
        assert result["spell_name"] == "Bless"
        assert "0 HP" in result["reason"]
        assert applied.id in result["effects_removed"]
        assert wizard.concentration is None
        assert len(wizard.active_effects) == 0

    def test_auto_break_on_incapacitated_condition(self, wizard: Character):
        """Concentration should break when incapacitated condition is added."""
        ConcentrationTracker.start_concentration(wizard, "Bless")

        wizard.conditions.append("incapacitated")
        result = ConcentrationTracker.check_auto_break(wizard)

        assert result is not None
        assert "incapacitated" in result["reason"]
        assert wizard.concentration is None

    def test_auto_break_on_stunned_condition(self, wizard: Character):
        """Stunned implies incapacitated, should break concentration."""
        ConcentrationTracker.start_concentration(wizard, "Bless")

        wizard.conditions.append("stunned")
        result = ConcentrationTracker.check_auto_break(wizard)

        assert result is not None
        assert "stunned" in result["reason"]

    def test_auto_break_on_paralyzed_condition(self, wizard: Character):
        """Paralyzed implies incapacitated, should break concentration."""
        ConcentrationTracker.start_concentration(wizard, "Bless")

        wizard.conditions.append("paralyzed")
        result = ConcentrationTracker.check_auto_break(wizard)

        assert result is not None
        assert "paralyzed" in result["reason"]

    def test_auto_break_on_petrified_condition(self, wizard: Character):
        """Petrified implies incapacitated, should break concentration."""
        ConcentrationTracker.start_concentration(wizard, "Bless")

        wizard.conditions.append("petrified")
        result = ConcentrationTracker.check_auto_break(wizard)

        assert result is not None
        assert "petrified" in result["reason"]

    def test_auto_break_on_incapacitated_active_effect(self, wizard: Character):
        """Concentration should break when Incapacitated effect is present."""
        ConcentrationTracker.start_concentration(wizard, "Bless")

        EffectsEngine.apply_effect(wizard, SRD_CONDITIONS["incapacitated"])
        result = ConcentrationTracker.check_auto_break(wizard)

        assert result is not None
        assert "Incapacitated" in result["reason"]

    def test_auto_break_on_stunned_active_effect(self, wizard: Character):
        """Stunned effect should trigger auto-break."""
        ConcentrationTracker.start_concentration(wizard, "Bless")

        EffectsEngine.apply_effect(wizard, SRD_CONDITIONS["stunned"])
        result = ConcentrationTracker.check_auto_break(wizard)

        assert result is not None
        assert "Stunned" in result["reason"]

    def test_no_auto_break_when_healthy(self, wizard: Character):
        """No auto-break when character is healthy and unconditioned."""
        ConcentrationTracker.start_concentration(wizard, "Bless")
        result = ConcentrationTracker.check_auto_break(wizard)
        assert result is None
        assert wizard.concentration is not None

    def test_no_auto_break_when_not_concentrating(self, wizard: Character):
        """No auto-break when not concentrating."""
        wizard.hit_points_current = 0
        result = ConcentrationTracker.check_auto_break(wizard)
        assert result is None

    def test_auto_break_detail_string(self, wizard: Character):
        ConcentrationTracker.start_concentration(wizard, "Fly")
        wizard.hit_points_current = 0
        result = ConcentrationTracker.check_auto_break(wizard)
        assert "Elara" in result["detail"]
        assert "Fly" in result["detail"]
        assert "0 HP" in result["detail"]


# ---------------------------------------------------------------------------
# Query Helper Tests
# ---------------------------------------------------------------------------

class TestQueryHelpers:
    """Tests for is_concentrating() and get_concentration_info()."""

    def test_is_concentrating_false(self, wizard: Character):
        assert ConcentrationTracker.is_concentrating(wizard) is False

    def test_is_concentrating_true(self, wizard: Character):
        ConcentrationTracker.start_concentration(wizard, "Bless")
        assert ConcentrationTracker.is_concentrating(wizard) is True

    def test_get_info_none(self, wizard: Character):
        assert ConcentrationTracker.get_concentration_info(wizard) is None

    def test_get_info_active(self, wizard: Character):
        ConcentrationTracker.start_concentration(
            wizard, "Haste", effect_ids=["e1"], current_round=2
        )
        info = ConcentrationTracker.get_concentration_info(wizard)
        assert info is not None
        assert info["spell_name"] == "Haste"
        assert info["effect_ids"] == ["e1"]
        assert info["started_round"] == 2


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases and integration scenarios."""

    def test_concentration_with_no_effects_to_clean(self, wizard: Character):
        """Starting concentration without effect_ids should work cleanly."""
        ConcentrationTracker.start_concentration(wizard, "Detect Magic")
        assert wizard.concentration.effect_ids == []

        with patch("dm20_protocol.combat.concentration._random.randint", return_value=1):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)
        assert result.broke is True
        assert result.effects_removed == []

    def test_effect_ids_with_already_removed_effects(self, wizard: Character):
        """If an effect ID references an already-removed effect, break should still succeed."""
        ConcentrationTracker.start_concentration(
            wizard, "Bless", effect_ids=["nonexistent_id"]
        )
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=1):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)
        assert result.broke is True
        assert result.effects_removed == []  # nonexistent ID not in removed list

    def test_switch_concentration_cleans_up_properly(self, wizard: Character):
        """Switching spells should remove old effects and set new state."""
        # First spell with effect
        eff1 = _make_concentration_effect("Bless")
        applied1 = EffectsEngine.apply_effect(wizard, eff1)
        ConcentrationTracker.start_concentration(wizard, "Bless", effect_ids=[applied1.id])

        # Second spell with different effect
        eff2 = ActiveEffect(
            name="Hold Person Effect",
            source="Hold Person spell",
            duration_type="concentration",
            modifiers=[],
        )
        applied2 = EffectsEngine.apply_effect(wizard, eff2)
        result = ConcentrationTracker.start_concentration(
            wizard, "Hold Person", effect_ids=[applied2.id]
        )

        assert result["previous_spell"] == "Bless"
        assert applied1.id in result["previous_effects_removed"]
        assert wizard.concentration.spell_name == "Hold Person"
        assert wizard.concentration.effect_ids == [applied2.id]
        # Old effect removed, new effect preserved
        assert len(wizard.active_effects) == 1
        assert wizard.active_effects[0].name == "Hold Person Effect"

    def test_non_concentration_effects_preserved_on_break(self, wizard: Character):
        """Breaking concentration should not remove unrelated effects."""
        # Add non-concentration effect
        shield = ActiveEffect(
            name="Shield",
            source="Shield spell",
            duration_type="rounds",
            duration_remaining=1,
        )
        shield_applied = EffectsEngine.apply_effect(wizard, shield)

        # Add concentration effect
        bless = _make_concentration_effect("Bless")
        bless_applied = EffectsEngine.apply_effect(wizard, bless)
        ConcentrationTracker.start_concentration(wizard, "Bless", effect_ids=[bless_applied.id])

        assert len(wizard.active_effects) == 2

        # Break concentration via failed save
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=1):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)

        assert result.broke is True
        # Only concentration effect removed, Shield preserved
        assert len(wizard.active_effects) == 1
        assert wizard.active_effects[0].name == "Shield"

    def test_fighter_con_save_with_proficiency(self, fighter: Character):
        """Fighter with CON save proficiency should use it."""
        ConcentrationTracker.start_concentration(fighter, "Bless")

        # Fighter: CON mod +1, prof +3 = +4
        # Roll 6 + 4 = 10 vs DC 10 -> success
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=6):
            result = ConcentrationTracker.check_concentration(fighter, damage_taken=10)

        assert result.total == 10  # 6 + 4
        assert result.success is True

    def test_zero_damage_dc_is_10(self, wizard: Character):
        """Even zero damage should use DC 10."""
        ConcentrationTracker.start_concentration(wizard, "Bless")
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=20):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=0)
        assert result.dc == 10

    def test_massive_damage_high_dc(self, wizard: Character):
        """Very high damage should produce a proportionally high DC."""
        ConcentrationTracker.start_concentration(wizard, "Bless")
        # damage=100, DC = max(10, 100 // 2) = 50
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=20):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=100)
        assert result.dc == 50

    def test_exact_dc_roll_succeeds(self, wizard: Character):
        """Meeting the DC exactly should count as a success."""
        ConcentrationTracker.start_concentration(wizard, "Bless")
        # Wizard: CON mod +2, prof +3 = +5. Roll + 5 = DC (10) => roll = 5
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=5):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)
        assert result.total == 10
        assert result.dc == 10
        assert result.success is True

    def test_one_below_dc_fails(self, wizard: Character):
        """Being one below DC should fail."""
        ConcentrationTracker.start_concentration(wizard, "Bless")
        # Wizard: +5 bonus. Roll 4 + 5 = 9 vs DC 10 -> fail
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=4):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)
        assert result.total == 9
        assert result.success is False

    def test_concentration_check_result_dataclass(self, wizard: Character):
        """ConcentrationCheckResult should have all expected fields."""
        ConcentrationTracker.start_concentration(wizard, "Bless")
        with patch("dm20_protocol.combat.concentration._random.randint", return_value=10):
            result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)

        assert isinstance(result, ConcentrationCheckResult)
        assert isinstance(result.success, bool)
        assert isinstance(result.roll, int)
        assert isinstance(result.total, int)
        assert isinstance(result.dc, int)
        assert isinstance(result.spell_name, str)
        assert isinstance(result.broke, bool)
        assert isinstance(result.effects_removed, list)
        assert isinstance(result.detail, str)
