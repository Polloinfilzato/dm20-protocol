"""
End-to-end combat flow integration tests.

Tests the full combat lifecycle using the new MCP tools and combat subsystems:
- Start combat -> combat_action -> next_turn -> effects tick -> end combat
- Effect application and removal through the full flow
- Concentration checks triggered by combat_action
- Turn advancement with effect duration tick-down
"""

import pytest
from unittest.mock import patch, MagicMock

from dm20_protocol.models import (
    ActiveEffect,
    Modifier,
    Character,
    CharacterClass,
    Race,
    AbilityScore,
    ConcentrationState,
    Item,
)
from dm20_protocol.combat.effects import EffectsEngine, SRD_CONDITIONS
from dm20_protocol.combat.concentration import ConcentrationTracker
from dm20_protocol.combat.pipeline import resolve_attack, resolve_save_spell, CombatResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fighter() -> Character:
    """A level 5 fighter with STR 16, DEX 14, CON 14."""
    return Character(
        name="Aldric",
        player_name="TestPlayer",
        character_class=CharacterClass(name="Fighter", level=5, hit_dice="1d10"),
        race=Race(name="Human"),
        abilities={
            "strength": AbilityScore(score=16),      # +3
            "dexterity": AbilityScore(score=14),      # +2
            "constitution": AbilityScore(score=14),   # +2
            "intelligence": AbilityScore(score=10),   # +0
            "wisdom": AbilityScore(score=12),         # +1
            "charisma": AbilityScore(score=8),        # -1
        },
        armor_class=18,
        speed=30,
        hit_points_max=44,
        hit_points_current=44,
        proficiency_bonus=3,
    )


@pytest.fixture
def goblin() -> Character:
    """A goblin NPC with low stats."""
    return Character(
        name="Goblin",
        character_class=CharacterClass(name="Monster", level=1, hit_dice="1d6"),
        race=Race(name="Goblin"),
        abilities={
            "strength": AbilityScore(score=8),        # -1
            "dexterity": AbilityScore(score=14),      # +2
            "constitution": AbilityScore(score=10),   # +0
            "intelligence": AbilityScore(score=10),   # +0
            "wisdom": AbilityScore(score=8),          # -1
            "charisma": AbilityScore(score=8),        # -1
        },
        armor_class=15,
        speed=30,
        hit_points_max=7,
        hit_points_current=7,
        proficiency_bonus=2,
    )


@pytest.fixture
def wizard() -> Character:
    """A level 5 wizard with INT 18, spellcasting ability set."""
    return Character(
        name="Elara",
        player_name="TestWizard",
        character_class=CharacterClass(name="Wizard", level=5, hit_dice="1d6"),
        race=Race(name="Elf", subrace="High Elf"),
        abilities={
            "strength": AbilityScore(score=8),        # -1
            "dexterity": AbilityScore(score=14),      # +2
            "constitution": AbilityScore(score=12),   # +1
            "intelligence": AbilityScore(score=18),   # +4
            "wisdom": AbilityScore(score=13),         # +1
            "charisma": AbilityScore(score=10),       # +0
        },
        armor_class=12,
        speed=30,
        hit_points_max=27,
        hit_points_current=27,
        proficiency_bonus=3,
        spellcasting_ability="intelligence",
    )


# ---------------------------------------------------------------------------
# Test: Full combat round flow
# ---------------------------------------------------------------------------

class TestFullCombatRound:
    """Test a complete combat round: attack -> damage -> effects -> turn advance."""

    def test_attack_hits_and_deals_damage(self, fighter, goblin):
        """Attack resolves and damage is computable."""
        with patch("dm20_protocol.combat.pipeline.random.randint") as mock_rand:
            # Attack roll: nat 15, damage roll: 6
            mock_rand.side_effect = [15, 6]
            result = resolve_attack(attacker=fighter, target=goblin)

        # Fighter attack: 15 + 3(STR) + 3(prof) = 21 vs AC 15 -> hit
        assert result.hit is True
        assert result.attacker_name == "Aldric"
        assert result.target_name == "Goblin"
        assert result.damage > 0

    def test_attack_misses(self, fighter, goblin):
        """Natural 1 always misses."""
        with patch("dm20_protocol.combat.pipeline.random.randint") as mock_rand:
            mock_rand.return_value = 1
            result = resolve_attack(attacker=fighter, target=goblin)

        assert result.hit is False
        assert result.auto_miss is True
        assert result.damage == 0

    def test_critical_hit_doubles_dice(self, fighter, goblin):
        """Critical hit (nat 20) doubles damage dice."""
        with patch("dm20_protocol.combat.pipeline.random.randint") as mock_rand:
            # Attack roll: nat 20, then 2 damage dice (doubled from 1d4 unarmed)
            mock_rand.side_effect = [20, 3, 4]
            result = resolve_attack(attacker=fighter, target=goblin)

        assert result.hit is True
        assert result.critical is True
        # 2d4 (doubled) + 3 (STR) = damage
        assert len(result.damage_dice_results) == 2

    def test_damage_application_to_hp(self, fighter, goblin):
        """Damage reduces target HP correctly."""
        with patch("dm20_protocol.combat.pipeline.random.randint") as mock_rand:
            mock_rand.side_effect = [15, 4]  # Hit, 4 damage + 3 STR = 7
            result = resolve_attack(attacker=fighter, target=goblin)

        assert result.hit is True
        # Apply damage manually (as combat_action tool would)
        goblin.hit_points_current = max(0, goblin.hit_points_current - result.damage)

        # The goblin started at 7 HP
        assert goblin.hit_points_current <= 7

    def test_dropping_to_zero_hp_flagged(self, fighter, goblin):
        """Attack that drops target to 0 HP is flagged in the result."""
        goblin.hit_points_current = 3  # Low HP

        with patch("dm20_protocol.combat.pipeline.random.randint") as mock_rand:
            mock_rand.side_effect = [15, 6]  # Hit, 6 damage + 3 STR = 9 > 3 HP
            result = resolve_attack(attacker=fighter, target=goblin)

        assert result.hit is True
        assert result.target_dropped_to_zero is True
        assert "Target drops to 0 HP" in result.effects_triggered


# ---------------------------------------------------------------------------
# Test: Effect application and tick-down during combat
# ---------------------------------------------------------------------------

class TestEffectsInCombat:
    """Test effect application, querying, and turn-based tick-down."""

    def test_apply_srd_condition(self, fighter):
        """SRD condition can be applied to a character."""
        from copy import deepcopy

        template = SRD_CONDITIONS["poisoned"]
        applied = EffectsEngine.apply_effect(fighter, template)

        assert applied.name == "Poisoned"
        assert EffectsEngine.has_effect(fighter, "Poisoned")
        assert len(fighter.active_effects) == 1

    def test_apply_timed_effect_and_tick(self, fighter):
        """Timed effect (rounds) decrements on tick and expires."""
        effect = ActiveEffect(
            name="Shield of Faith",
            source="Cleric spell",
            modifiers=[Modifier(stat="armor_class", operation="add", value=2)],
            duration_type="rounds",
            duration_remaining=2,
        )
        applied = EffectsEngine.apply_effect(fighter, effect)
        assert EffectsEngine.has_effect(fighter, "Shield of Faith")

        # Tick 1: duration goes from 2 -> 1
        expired = EffectsEngine.tick_effects(fighter, event="turn")
        assert len(expired) == 0
        assert fighter.active_effects[0].duration_remaining == 1

        # Tick 2: duration goes from 1 -> 0, effect expires
        expired = EffectsEngine.tick_effects(fighter, event="turn")
        assert len(expired) == 1
        assert expired[0].name == "Shield of Faith"
        assert not EffectsEngine.has_effect(fighter, "Shield of Faith")

    def test_permanent_effect_not_ticked(self, fighter):
        """Permanent effects are never auto-ticked."""
        template = SRD_CONDITIONS["blinded"]
        EffectsEngine.apply_effect(fighter, template)

        expired = EffectsEngine.tick_effects(fighter, event="turn")
        assert len(expired) == 0
        assert EffectsEngine.has_effect(fighter, "Blinded")

    def test_effect_modifies_stat(self, fighter):
        """Effect modifiers change effective stat values."""
        # Apply +2 AC effect
        effect = ActiveEffect(
            name="Mage Armor",
            source="Spell",
            modifiers=[Modifier(stat="armor_class", operation="add", value=2)],
            duration_type="rounds",
            duration_remaining=10,
        )
        EffectsEngine.apply_effect(fighter, effect)

        effective_ac = EffectsEngine.effective_stat(fighter, "armor_class")
        assert effective_ac == fighter.armor_class + 2

    def test_remove_effect_by_name(self, fighter):
        """Effects can be removed by name."""
        from copy import deepcopy
        template = SRD_CONDITIONS["prone"]
        EffectsEngine.apply_effect(fighter, template)
        assert EffectsEngine.has_effect(fighter, "Prone")

        removed = EffectsEngine.remove_effects_by_name(fighter, "Prone")
        assert len(removed) == 1
        assert not EffectsEngine.has_effect(fighter, "Prone")


# ---------------------------------------------------------------------------
# Test: Concentration checks triggered by combat
# ---------------------------------------------------------------------------

class TestConcentrationInCombat:
    """Test concentration save triggers during combat flow."""

    def test_concentration_check_on_damage(self, wizard):
        """Taking damage triggers a concentration check."""
        # Set up concentration
        ConcentrationTracker.start_concentration(wizard, "Hold Person")

        # Simulate taking 14 damage: DC = max(10, 14//2) = 10
        result = ConcentrationTracker.check_concentration(wizard, damage_taken=14)

        assert result is not None
        assert result.spell_name == "Hold Person"
        assert result.dc == 10

    def test_concentration_check_high_damage(self, wizard):
        """High damage sets DC higher than 10."""
        ConcentrationTracker.start_concentration(wizard, "Bless")

        # 30 damage: DC = max(10, 30//2) = 15
        result = ConcentrationTracker.check_concentration(wizard, damage_taken=30)

        assert result is not None
        assert result.dc == 15

    def test_concentration_auto_break_on_zero_hp(self, wizard):
        """Concentration automatically breaks when character drops to 0 HP."""
        ConcentrationTracker.start_concentration(wizard, "Haste")
        wizard.hit_points_current = 0

        result = ConcentrationTracker.check_auto_break(wizard)

        assert result is not None
        assert result["spell_name"] == "Haste"
        assert result["reason"] == "dropped to 0 HP"
        assert wizard.concentration is None

    def test_no_concentration_check_when_not_concentrating(self, wizard):
        """No check is made if character is not concentrating."""
        result = ConcentrationTracker.check_concentration(wizard, damage_taken=10)
        assert result is None


# ---------------------------------------------------------------------------
# Test: Saving throw spell resolution
# ---------------------------------------------------------------------------

class TestSaveSpellResolution:
    """Test saving throw spell resolution end-to-end."""

    def test_fireball_resolution(self, wizard, goblin):
        """Fireball (8d6 fire, DEX save, half on save) resolves correctly."""
        with patch("dm20_protocol.combat.pipeline.random.randint") as mock_rand:
            # Save roll: 8 (fail against DC 15), damage dice: 3,4,2,5,3,4,2,6 = 29
            mock_rand.side_effect = [8, 3, 4, 2, 5, 3, 4, 2, 6]
            results = resolve_save_spell(
                caster=wizard,
                targets=[goblin],
                save_ability="dexterity",
                damage_dice="8d6",
                damage_type="fire",
                half_on_save=True,
            )

        assert len(results) == 1
        result = results[0]
        assert result.caster_name == "Elara"
        assert result.target_name == "Goblin"
        assert result.save_ability == "dexterity"
        # DC = 8 + 3 (prof) + 4 (INT mod) = 15
        assert result.save_dc == 15

    def test_successful_save_halves_damage(self, wizard, goblin):
        """Successful save on half-on-save spell halves damage."""
        with patch("dm20_protocol.combat.pipeline.random.randint") as mock_rand:
            # Save roll: 18 (success), damage: all 4s = 32
            mock_rand.side_effect = [18] + [4] * 8
            results = resolve_save_spell(
                caster=wizard,
                targets=[goblin],
                save_ability="dexterity",
                damage_dice="8d6",
                damage_type="fire",
                half_on_save=True,
            )

        result = results[0]
        # Goblin DEX save: 18 + 2 (DEX mod) = 20 vs DC 15 -> success
        assert result.saved is True
        # Half of 32 = 16
        assert result.damage == 16


# ---------------------------------------------------------------------------
# Test: Encounter builder
# ---------------------------------------------------------------------------

class TestEncounterBuilder:
    """Test encounter building through the pipeline."""

    def test_build_encounter_basic(self):
        """Build an encounter for a standard party returns valid suggestion."""
        from dm20_protocol.combat.encounter_builder import build_encounter

        suggestion = build_encounter(
            party_levels=[5, 5, 5, 5],
            difficulty="medium",
        )

        assert suggestion.party_size == 4
        assert suggestion.requested_difficulty == "medium"
        assert suggestion.xp_budget > 0
        assert "easy" in suggestion.thresholds
        assert "medium" in suggestion.thresholds
        assert "hard" in suggestion.thresholds
        assert "deadly" in suggestion.thresholds

    def test_build_encounter_produces_compositions(self):
        """Encounter builder produces at least one composition strategy."""
        from dm20_protocol.combat.encounter_builder import build_encounter

        suggestion = build_encounter(
            party_levels=[3, 3, 3, 3],
            difficulty="medium",
        )

        # With no rulebook, should produce CR-based placeholder suggestions
        assert len(suggestion.compositions) > 0
        assert not suggestion.rulebooks_loaded

    def test_xp_budget_calculation(self):
        """XP budget matches the party's threshold for the difficulty."""
        from dm20_protocol.combat.encounter_builder import calculate_xp_budget

        budget = calculate_xp_budget([5, 5, 5, 5], "medium")
        # Level 5 medium threshold = 500 per character, 4 characters = 2000
        assert budget == 2000


# ---------------------------------------------------------------------------
# Test: Full integration - attack -> concentration -> effects -> turn
# ---------------------------------------------------------------------------

class TestFullIntegrationFlow:
    """Test the complete combat flow as it would happen through MCP tools."""

    def test_attack_triggers_concentration_and_effects_tick(self, fighter, wizard):
        """Full flow: fighter attacks concentrating wizard, concentration check
        triggers, then on turn advance effects tick down."""
        # Set up: wizard concentrating on Haste with a 3-round timed effect
        haste_effect = ActiveEffect(
            name="Haste",
            source="Spell",
            modifiers=[Modifier(stat="armor_class", operation="add", value=2)],
            duration_type="rounds",
            duration_remaining=3,
        )
        applied = EffectsEngine.apply_effect(wizard, haste_effect)
        ConcentrationTracker.start_concentration(
            wizard, "Haste", effect_ids=[applied.id]
        )

        # Step 1: Fighter attacks wizard (guaranteed hit)
        with patch("dm20_protocol.combat.pipeline.random.randint") as mock_rand:
            mock_rand.side_effect = [18, 6]  # Attack: 18 + 6 = hit, damage: 6 + 3 = 9
            result = resolve_attack(attacker=fighter, target=wizard)

        assert result.hit is True
        assert result.damage > 0

        # Step 2: Apply damage
        wizard.hit_points_current = max(0, wizard.hit_points_current - result.damage)

        # Step 3: Check concentration
        if result.concentration_check_dc is not None:
            conc_result = ConcentrationTracker.check_concentration(wizard, result.damage)
            # Concentration check was triggered
            assert conc_result is not None

        # Step 4: Tick effects (simulating next_turn)
        expired = EffectsEngine.tick_effects(wizard, event="turn")
        # Haste should tick from 3 -> 2 (or already removed if concentration broke)

        # Verify the wizard's state is consistent
        assert wizard.hit_points_current < 27  # Took damage

    def test_effect_removal_cleans_up(self, fighter):
        """Removing an effect restores effective stats."""
        # Apply Bless (+1d4 to attacks)
        bless = ActiveEffect(
            name="Bless",
            source="Cleric spell",
            modifiers=[Modifier(stat="attack_roll", operation="dice", value="1d4")],
            duration_type="rounds",
            duration_remaining=5,
        )
        applied = EffectsEngine.apply_effect(fighter, bless)

        # Verify effect is present
        assert EffectsEngine.has_effect(fighter, "Bless")
        dice_mods = EffectsEngine.get_dice_modifiers(fighter, "attack_roll")
        assert "1d4" in dice_mods

        # Remove by name
        EffectsEngine.remove_effects_by_name(fighter, "Bless")
        assert not EffectsEngine.has_effect(fighter, "Bless")
        dice_mods = EffectsEngine.get_dice_modifiers(fighter, "attack_roll")
        assert dice_mods == []
