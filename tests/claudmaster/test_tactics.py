"""
Tests for the AI Combat Tactics System (Issue #56).

Tests cover:
- Data model creation and validation
- TacticsEngine initialization and decision-making
- Archetype-specific tactics (tank, healer, striker, support)
- Personality trait influence on decisions
- Loyalty-based behavior changes
- Target evaluation and scoring
- Ability selection logic
- Edge cases (no enemies, no allies, low HP)
"""

import pytest
from pydantic import ValidationError

from dm20_protocol.claudmaster.tactics import (
    TacticalPriority,
    Combatant,
    TacticalDecision,
    BattlefieldState,
    TacticsEngine,
)
from dm20_protocol.claudmaster.companions import (
    CompanionProfile,
    CompanionArchetype,
    CombatStyle,
    PersonalityTraits,
)


# ============================================================================
# Data Model Tests
# ============================================================================

class TestCombatant:
    """Test Combatant model creation and properties."""

    def test_minimal_creation(self):
        combatant = Combatant(name="Goblin", hp_current=7, hp_max=7)
        assert combatant.name == "Goblin"
        assert combatant.hp_current == 7
        assert combatant.hp_max == 7
        assert combatant.armor_class == 10
        assert combatant.is_ally is False
        assert combatant.is_player is False
        assert combatant.position is None
        assert combatant.conditions == []
        assert combatant.damage_potential == 5.0
        assert combatant.threat_to_allies == 0.5
        assert combatant.value == 0.5

    def test_full_creation(self):
        combatant = Combatant(
            name="Elite Guard",
            hp_current=45,
            hp_max=50,
            armor_class=18,
            is_ally=True,
            position=(5, 10),
            conditions=["blessed"],
            damage_potential=12.0,
            threat_to_allies=0.8,
            value=0.9,
        )
        assert combatant.armor_class == 18
        assert combatant.is_ally is True
        assert combatant.position == (5, 10)
        assert "blessed" in combatant.conditions

    def test_hp_percentage_full(self):
        combatant = Combatant(name="Test", hp_current=50, hp_max=50)
        assert combatant.hp_percentage == 1.0

    def test_hp_percentage_half(self):
        combatant = Combatant(name="Test", hp_current=25, hp_max=50)
        assert combatant.hp_percentage == 0.5

    def test_hp_percentage_zero(self):
        combatant = Combatant(name="Test", hp_current=0, hp_max=50)
        assert combatant.hp_percentage == 0.0

    def test_hp_percentage_max_zero(self):
        combatant = Combatant(name="Test", hp_current=0, hp_max=0)
        assert combatant.hp_percentage == 0.0

    def test_threat_validation_below_zero(self):
        with pytest.raises(ValidationError):
            Combatant(name="Test", hp_current=10, hp_max=10, threat_to_allies=-0.1)

    def test_threat_validation_above_one(self):
        with pytest.raises(ValidationError):
            Combatant(name="Test", hp_current=10, hp_max=10, threat_to_allies=1.1)


class TestTacticalDecision:
    """Test TacticalDecision model creation."""

    def test_minimal_creation(self):
        decision = TacticalDecision(
            action_type="attack",
            priority=TacticalPriority.ELIMINATE_THREAT,
            confidence=0.8,
            reasoning="Test attack",
        )
        assert decision.action_type == "attack"
        assert decision.target is None
        assert decision.ability is None
        assert decision.priority == TacticalPriority.ELIMINATE_THREAT
        assert decision.confidence == 0.8
        assert decision.reasoning == "Test attack"
        assert decision.action_economy == "action"

    def test_full_creation(self):
        decision = TacticalDecision(
            action_type="ability",
            target="Goblin King",
            ability="smite",
            priority=TacticalPriority.PROTECT_ALLY,
            confidence=0.95,
            reasoning="Protecting the wizard",
            action_economy="bonus_action",
        )
        assert decision.target == "Goblin King"
        assert decision.ability == "smite"
        assert decision.action_economy == "bonus_action"

    def test_confidence_validation_below_zero(self):
        with pytest.raises(ValidationError):
            TacticalDecision(
                action_type="dodge",
                priority=TacticalPriority.SURVIVE,
                confidence=-0.1,
                reasoning="Invalid",
            )

    def test_confidence_validation_above_one(self):
        with pytest.raises(ValidationError):
            TacticalDecision(
                action_type="dodge",
                priority=TacticalPriority.SURVIVE,
                confidence=1.1,
                reasoning="Invalid",
            )


class TestBattlefieldState:
    """Test BattlefieldState model creation."""

    def test_empty_battlefield(self):
        battlefield = BattlefieldState()
        assert battlefield.combatants == []
        assert battlefield.round_number == 1
        assert battlefield.companion_hp_current == 0
        assert battlefield.companion_hp_max == 1
        assert battlefield.companion_conditions == []

    def test_battlefield_with_combatants(self):
        combatants = [
            Combatant(name="Ally1", hp_current=30, hp_max=30, is_ally=True),
            Combatant(name="Enemy1", hp_current=20, hp_max=20),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            round_number=3,
            companion_hp_current=25,
            companion_hp_max=40,
            companion_conditions=["blessed"],
        )
        assert len(battlefield.combatants) == 2
        assert battlefield.round_number == 3
        assert battlefield.companion_hp_current == 25
        assert battlefield.companion_hp_max == 40
        assert "blessed" in battlefield.companion_conditions


# ============================================================================
# TacticsEngine Initialization Tests
# ============================================================================

class TestTacticsEngineInitialization:
    """Test TacticsEngine initialization and combatant partitioning."""

    def test_initialization_empty_battlefield(self):
        companion = CompanionProfile(
            npc_id="test",
            name="Test",
            archetype=CompanionArchetype.TANK,
            combat_style=CombatStyle.DEFENSIVE,
        )
        battlefield = BattlefieldState()
        engine = TacticsEngine(companion, battlefield)

        assert engine.companion == companion
        assert engine.battlefield == battlefield
        assert engine._allies == []
        assert engine._enemies == []

    def test_combatant_partitioning(self):
        companion = CompanionProfile(
            npc_id="test",
            name="Test",
            archetype=CompanionArchetype.TANK,
            combat_style=CombatStyle.DEFENSIVE,
        )
        combatants = [
            Combatant(name="Player", hp_current=30, hp_max=30, is_player=True),
            Combatant(name="Ally1", hp_current=25, hp_max=25, is_ally=True),
            Combatant(name="Enemy1", hp_current=20, hp_max=20),
            Combatant(name="Enemy2", hp_current=15, hp_max=15),
        ]
        battlefield = BattlefieldState(combatants=combatants)
        engine = TacticsEngine(companion, battlefield)

        assert len(engine._allies) == 2
        assert len(engine._enemies) == 2
        assert any(a.name == "Player" for a in engine._allies)
        assert any(a.name == "Ally1" for a in engine._allies)
        assert any(e.name == "Enemy1" for e in engine._enemies)
        assert any(e.name == "Enemy2" for e in engine._enemies)


# ============================================================================
# Tank Tactics Tests
# ============================================================================

class TestTankTactics:
    """Test tactical decisions for tank archetype."""

    def test_tank_protects_ally(self):
        companion = CompanionProfile(
            npc_id="tank",
            name="Brunhilde",
            archetype=CompanionArchetype.TANK,
            combat_style=CombatStyle.DEFENSIVE,
            preferred_abilities=["shield", "taunt"],
        )
        combatants = [
            Combatant(name="Wizard", hp_current=10, hp_max=30, is_ally=True),
            Combatant(name="Orc", hp_current=40, hp_max=40, threat_to_allies=0.9),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=50,
            companion_hp_max=50,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        assert decision.priority == TacticalPriority.PROTECT_ALLY
        assert decision.target == "Orc"
        assert "Wizard" in decision.reasoning or "Orc" in decision.reasoning

    def test_tank_targets_high_threat_enemy(self):
        companion = CompanionProfile(
            npc_id="tank",
            name="Tank",
            archetype=CompanionArchetype.TANK,
            combat_style=CombatStyle.DEFENSIVE,
        )
        combatants = [
            Combatant(name="Enemy1", hp_current=20, hp_max=20, threat_to_allies=0.3),
            Combatant(name="Enemy2", hp_current=30, hp_max=30, threat_to_allies=0.9),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=40,
            companion_hp_max=40,
        )
        engine = TacticsEngine(companion, battlefield)
        targets = engine.evaluate_targets()

        # Enemy2 should score higher due to threat_to_allies
        assert targets[0][0] == "Enemy2"

    def test_tank_high_bravery_increases_confidence(self):
        companion = CompanionProfile(
            npc_id="tank",
            name="Brave Tank",
            archetype=CompanionArchetype.TANK,
            combat_style=CombatStyle.DEFENSIVE,
            personality=PersonalityTraits(bravery=90),
        )
        combatants = [
            Combatant(name="Ally", hp_current=10, hp_max=40, is_ally=True),
            Combatant(name="Dragon", hp_current=100, hp_max=100, threat_to_allies=1.0),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=50,
            companion_hp_max=50,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        # High bravery should boost confidence when protecting ally
        assert decision.confidence >= 0.8

    def test_tank_no_enemies_defensive_stance(self):
        companion = CompanionProfile(
            npc_id="tank",
            name="Tank",
            archetype=CompanionArchetype.TANK,
            combat_style=CombatStyle.DEFENSIVE,
        )
        battlefield = BattlefieldState(
            combatants=[],
            companion_hp_current=50,
            companion_hp_max=50,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        assert decision.action_type == "dodge"
        assert decision.priority == TacticalPriority.SURVIVE


# ============================================================================
# Healer Tactics Tests
# ============================================================================

class TestHealerTactics:
    """Test tactical decisions for healer archetype."""

    def test_healer_heals_wounded_ally(self):
        companion = CompanionProfile(
            npc_id="healer",
            name="Lyra",
            archetype=CompanionArchetype.HEALER,
            combat_style=CombatStyle.SUPPORTIVE,
            preferred_abilities=["heal", "cure"],
        )
        combatants = [
            Combatant(name="Fighter", hp_current=10, hp_max=50, is_ally=True),
            Combatant(name="Enemy", hp_current=30, hp_max=30),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=35,
            companion_hp_max=35,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        assert decision.priority == TacticalPriority.SUPPORT_PARTY
        assert decision.target == "Fighter"
        assert decision.action_type == "ability"
        assert "heal" in decision.reasoning.lower()

    def test_healer_attacks_when_all_healthy(self):
        companion = CompanionProfile(
            npc_id="healer",
            name="Lyra",
            archetype=CompanionArchetype.HEALER,
            combat_style=CombatStyle.SUPPORTIVE,
            preferred_abilities=["heal"],
        )
        combatants = [
            Combatant(name="Fighter", hp_current=50, hp_max=50, is_ally=True),
            Combatant(name="Enemy", hp_current=30, hp_max=30),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=35,
            companion_hp_max=35,
            round_number=5,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        # All allies healthy, should attack
        assert decision.action_type == "attack"
        assert decision.target == "Enemy"

    def test_healer_buffs_in_early_rounds(self):
        companion = CompanionProfile(
            npc_id="healer",
            name="Lyra",
            archetype=CompanionArchetype.HEALER,
            combat_style=CombatStyle.SUPPORTIVE,
            preferred_abilities=["bless", "heal"],
        )
        combatants = [
            Combatant(name="Fighter", hp_current=50, hp_max=50, is_ally=True, damage_potential=15.0),
            Combatant(name="Enemy", hp_current=30, hp_max=30),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=35,
            companion_hp_max=35,
            round_number=1,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        # Early round, should buff ally
        assert decision.action_type == "ability"
        assert decision.target == "Fighter"
        assert decision.ability == "bless"

    def test_healer_high_compassion_increases_confidence(self):
        companion = CompanionProfile(
            npc_id="healer",
            name="Compassionate Healer",
            archetype=CompanionArchetype.HEALER,
            combat_style=CombatStyle.SUPPORTIVE,
            personality=PersonalityTraits(compassion=95),
            preferred_abilities=["heal"],
        )
        combatants = [
            Combatant(name="Wounded", hp_current=5, hp_max=40, is_ally=True),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=30,
            companion_hp_max=30,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        assert decision.confidence >= 0.9


# ============================================================================
# Striker Tactics Tests
# ============================================================================

class TestStrikerTactics:
    """Test tactical decisions for striker archetype."""

    def test_striker_targets_low_hp_enemy(self):
        companion = CompanionProfile(
            npc_id="striker",
            name="Shadow",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
            preferred_abilities=["sneak_attack"],
        )
        combatants = [
            Combatant(name="Enemy1", hp_current=30, hp_max=30),
            Combatant(name="Enemy2", hp_current=5, hp_max=30),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=40,
            companion_hp_max=40,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        assert decision.priority == TacticalPriority.ELIMINATE_THREAT
        assert decision.target == "Enemy2"
        assert "Enemy2" in decision.reasoning

    def test_striker_targets_high_value_enemy(self):
        companion = CompanionProfile(
            npc_id="striker",
            name="Assassin",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
        )
        combatants = [
            Combatant(name="Grunt", hp_current=20, hp_max=20, value=0.2),
            Combatant(name="Mage", hp_current=25, hp_max=25, value=0.9),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=40,
            companion_hp_max=40,
        )
        engine = TacticsEngine(companion, battlefield)
        targets = engine.evaluate_targets()

        # Mage should score higher due to value
        assert targets[0][0] == "Mage"

    def test_striker_high_aggression_increases_confidence(self):
        companion = CompanionProfile(
            npc_id="striker",
            name="Aggressive Striker",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
            personality=PersonalityTraits(aggression=90),
        )
        combatants = [
            Combatant(name="Enemy", hp_current=30, hp_max=30),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=40,
            companion_hp_max=40,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        assert decision.confidence >= 0.85

    def test_striker_low_caution_boosts_confidence(self):
        companion = CompanionProfile(
            npc_id="striker",
            name="Reckless Striker",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
            personality=PersonalityTraits(caution=10),
        )
        combatants = [
            Combatant(name="Enemy", hp_current=30, hp_max=30),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=40,
            companion_hp_max=40,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        # Low caution should increase confidence
        assert decision.confidence >= 0.8


# ============================================================================
# Support Tactics Tests
# ============================================================================

class TestSupportTactics:
    """Test tactical decisions for support archetype."""

    def test_support_buffs_ally_early_combat(self):
        companion = CompanionProfile(
            npc_id="support",
            name="Bard",
            archetype=CompanionArchetype.SUPPORT,
            combat_style=CombatStyle.SUPPORTIVE,
            preferred_abilities=["inspire", "buff"],
        )
        combatants = [
            Combatant(name="Fighter", hp_current=50, hp_max=50, is_ally=True, damage_potential=15.0),
            Combatant(name="Enemy", hp_current=30, hp_max=30),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=30,
            companion_hp_max=30,
            round_number=1,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        assert decision.priority == TacticalPriority.SUPPORT_PARTY
        assert decision.target == "Fighter"
        assert decision.action_type == "ability"
        assert decision.ability in ["inspire", "buff"]

    def test_support_debuffs_dangerous_enemy(self):
        companion = CompanionProfile(
            npc_id="support",
            name="Enchanter",
            archetype=CompanionArchetype.SUPPORT,
            combat_style=CombatStyle.SUPPORTIVE,
            preferred_abilities=["debuff"],
        )
        combatants = [
            Combatant(name="Enemy1", hp_current=20, hp_max=20, value=0.3),
            Combatant(name="Boss", hp_current=100, hp_max=100, value=0.95),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=30,
            companion_hp_max=30,
            round_number=3,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        assert decision.target == "Boss"
        assert decision.ability == "debuff"
        assert decision.priority == TacticalPriority.CONTROL_BATTLEFIELD

    def test_support_helps_strongest_ally(self):
        companion = CompanionProfile(
            npc_id="support",
            name="Helper",
            archetype=CompanionArchetype.SUPPORT,
            combat_style=CombatStyle.SUPPORTIVE,
            preferred_abilities=[],
        )
        combatants = [
            Combatant(name="Weak", hp_current=30, hp_max=30, is_ally=True, damage_potential=5.0),
            Combatant(name="Strong", hp_current=50, hp_max=50, is_ally=True, damage_potential=20.0),
            Combatant(name="Enemy", hp_current=30, hp_max=30),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=30,
            companion_hp_max=30,
            round_number=3,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        assert decision.action_type == "help"
        assert decision.target == "Strong"


# ============================================================================
# Personality Influence Tests
# ============================================================================

class TestPersonalityInfluence:
    """Test how personality traits affect tactical decisions."""

    def test_high_aggression_increases_target_scores(self):
        companion_low = CompanionProfile(
            npc_id="low",
            name="Cautious",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
            personality=PersonalityTraits(aggression=10),
        )
        companion_high = CompanionProfile(
            npc_id="high",
            name="Aggressive",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
            personality=PersonalityTraits(aggression=90),
        )
        combatants = [
            Combatant(name="Enemy", hp_current=30, hp_max=30, damage_potential=10.0),
        ]
        battlefield = BattlefieldState(combatants=combatants)

        engine_low = TacticsEngine(companion_low, battlefield)
        engine_high = TacticsEngine(companion_high, battlefield)

        targets_low = engine_low.evaluate_targets()
        targets_high = engine_high.evaluate_targets()

        # High aggression should produce higher scores
        assert targets_high[0][1] > targets_low[0][1]

    def test_high_caution_reduces_target_scores(self):
        companion_low = CompanionProfile(
            npc_id="low",
            name="Reckless",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
            personality=PersonalityTraits(caution=10),
        )
        companion_high = CompanionProfile(
            npc_id="high",
            name="Cautious",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
            personality=PersonalityTraits(caution=90),
        )
        combatants = [
            Combatant(name="Enemy", hp_current=30, hp_max=30, threat_to_allies=0.8),
        ]
        battlefield = BattlefieldState(combatants=combatants)

        engine_low = TacticsEngine(companion_low, battlefield)
        engine_high = TacticsEngine(companion_high, battlefield)

        targets_low = engine_low.evaluate_targets()
        targets_high = engine_high.evaluate_targets()

        # High caution should reduce scores (especially for threats)
        assert targets_low[0][1] > targets_high[0][1]


# ============================================================================
# Preferred/Avoided Targets Tests
# ============================================================================

class TestPreferredAvoidedTargets:
    """Test preferred_targets and avoided_targets mechanics."""

    def test_preferred_target_multiplier(self):
        companion = CompanionProfile(
            npc_id="undead_hunter",
            name="Cleric",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
            preferred_targets=["Undead"],
        )
        combatants = [
            Combatant(name="Orc", hp_current=30, hp_max=30),
            Combatant(name="Undead", hp_current=30, hp_max=30),
        ]
        battlefield = BattlefieldState(combatants=combatants)
        engine = TacticsEngine(companion, battlefield)
        targets = engine.evaluate_targets()

        # Undead should score significantly higher due to 1.5x multiplier
        assert targets[0][0] == "Undead"
        assert targets[0][1] > targets[1][1]

    def test_avoided_target_multiplier(self):
        companion = CompanionProfile(
            npc_id="coward",
            name="Coward",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
            avoided_targets=["Dragon"],
        )
        combatants = [
            Combatant(name="Goblin", hp_current=10, hp_max=10),
            Combatant(name="Dragon", hp_current=100, hp_max=100),
        ]
        battlefield = BattlefieldState(combatants=combatants)
        engine = TacticsEngine(companion, battlefield)
        targets = engine.evaluate_targets()

        # Dragon should score much lower due to 0.3x multiplier
        assert targets[0][0] == "Goblin"


# ============================================================================
# Loyalty Influence Tests
# ============================================================================

class TestLoyaltyInfluence:
    """Test how loyalty affects tactical behavior."""

    def test_low_loyalty_low_hp_triggers_survival(self):
        companion = CompanionProfile(
            npc_id="disloyal",
            name="Mercenary",
            archetype=CompanionArchetype.TANK,
            combat_style=CombatStyle.DEFENSIVE,
            loyalty_score=20,
        )
        combatants = [
            Combatant(name="Enemy", hp_current=30, hp_max=30),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=8,
            companion_hp_max=40,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        # Low loyalty + low HP = disengage
        assert decision.action_type == "disengage"
        assert decision.priority == TacticalPriority.SURVIVE

    def test_high_loyalty_protects_wounded_ally(self):
        companion = CompanionProfile(
            npc_id="loyal",
            name="Knight",
            archetype=CompanionArchetype.TANK,
            combat_style=CombatStyle.DEFENSIVE,
            loyalty_score=95,
        )
        combatants = [
            Combatant(name="Wizard", hp_current=3, hp_max=30, is_ally=True),
            Combatant(name="Orc", hp_current=40, hp_max=40, threat_to_allies=0.9),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=50,
            companion_hp_max=50,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        # High loyalty should prioritize protecting wounded ally
        assert decision.priority == TacticalPriority.PROTECT_ALLY
        assert decision.target == "Orc"

    def test_medium_loyalty_normal_behavior(self):
        companion = CompanionProfile(
            npc_id="normal",
            name="Companion",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
            loyalty_score=50,
        )
        combatants = [
            Combatant(name="Enemy", hp_current=20, hp_max=20),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=10,
            companion_hp_max=40,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        # Medium loyalty should follow normal archetype behavior
        assert decision.priority == TacticalPriority.ELIMINATE_THREAT


# ============================================================================
# Target Evaluation Tests
# ============================================================================

class TestTargetEvaluation:
    """Test target evaluation and scoring logic."""

    def test_evaluate_targets_returns_sorted_list(self):
        companion = CompanionProfile(
            npc_id="test",
            name="Test",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
        )
        combatants = [
            Combatant(name="Low", hp_current=5, hp_max=30),
            Combatant(name="High", hp_current=30, hp_max=30),
        ]
        battlefield = BattlefieldState(combatants=combatants)
        engine = TacticsEngine(companion, battlefield)
        targets = engine.evaluate_targets()

        # Should return list of (name, score) tuples
        assert isinstance(targets, list)
        assert all(isinstance(t, tuple) and len(t) == 2 for t in targets)
        # Should be sorted descending
        assert targets[0][1] >= targets[1][1]

    def test_evaluate_targets_empty_enemies(self):
        companion = CompanionProfile(
            npc_id="test",
            name="Test",
            archetype=CompanionArchetype.TANK,
            combat_style=CombatStyle.DEFENSIVE,
        )
        battlefield = BattlefieldState(combatants=[])
        engine = TacticsEngine(companion, battlefield)
        targets = engine.evaluate_targets()

        assert targets == []


# ============================================================================
# Ability Selection Tests
# ============================================================================

class TestAbilitySelection:
    """Test ability selection logic."""

    def test_select_ability_for_ally_target(self):
        companion = CompanionProfile(
            npc_id="healer",
            name="Healer",
            archetype=CompanionArchetype.HEALER,
            combat_style=CombatStyle.SUPPORTIVE,
            preferred_abilities=["heal", "bless"],
        )
        combatants = [
            Combatant(name="Ally", hp_current=20, hp_max=40, is_ally=True),
        ]
        battlefield = BattlefieldState(combatants=combatants)
        engine = TacticsEngine(companion, battlefield)
        ability = engine.select_ability("Ally")

        assert ability == "heal"

    def test_select_ability_for_enemy_target(self):
        companion = CompanionProfile(
            npc_id="striker",
            name="Striker",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
            preferred_abilities=["sneak_attack", "strike"],
        )
        combatants = [
            Combatant(name="Enemy", hp_current=30, hp_max=30),
        ]
        battlefield = BattlefieldState(combatants=combatants)
        engine = TacticsEngine(companion, battlefield)
        ability = engine.select_ability("Enemy")

        assert ability == "sneak_attack"

    def test_select_ability_no_preferred(self):
        companion = CompanionProfile(
            npc_id="basic",
            name="Basic",
            archetype=CompanionArchetype.TANK,
            combat_style=CombatStyle.DEFENSIVE,
            preferred_abilities=[],
        )
        battlefield = BattlefieldState(combatants=[])
        engine = TacticsEngine(companion, battlefield)
        ability = engine.select_ability("Anyone")

        assert ability is None

    def test_select_ability_nonexistent_target(self):
        companion = CompanionProfile(
            npc_id="test",
            name="Test",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
            preferred_abilities=["strike"],
        )
        battlefield = BattlefieldState(combatants=[])
        engine = TacticsEngine(companion, battlefield)
        ability = engine.select_ability("Nonexistent")

        # Should still return offensive ability for nonexistent target
        assert ability == "strike"


# ============================================================================
# Edge Cases Tests
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_no_enemies_present(self):
        companion = CompanionProfile(
            npc_id="test",
            name="Test",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
        )
        combatants = [
            Combatant(name="Ally", hp_current=30, hp_max=30, is_ally=True),
        ]
        battlefield = BattlefieldState(combatants=combatants)
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        # Should default to defensive action
        assert decision.action_type == "dodge"

    def test_no_allies_present(self):
        companion = CompanionProfile(
            npc_id="healer",
            name="Solo Healer",
            archetype=CompanionArchetype.HEALER,
            combat_style=CombatStyle.SUPPORTIVE,
        )
        combatants = [
            Combatant(name="Enemy", hp_current=30, hp_max=30),
        ]
        battlefield = BattlefieldState(combatants=combatants)
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        # Healer with no allies should attack
        assert decision.action_type == "attack"
        assert decision.target == "Enemy"

    def test_companion_at_very_low_hp(self):
        companion = CompanionProfile(
            npc_id="wounded",
            name="Wounded",
            archetype=CompanionArchetype.TANK,
            combat_style=CombatStyle.DEFENSIVE,
            loyalty_score=25,
        )
        combatants = [
            Combatant(name="Enemy", hp_current=30, hp_max=30),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=2,
            companion_hp_max=50,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        # Very low HP + low loyalty = survival mode
        assert decision.action_type == "disengage"
        assert decision.priority == TacticalPriority.SURVIVE

    def test_all_combatants_full_hp(self):
        companion = CompanionProfile(
            npc_id="healer",
            name="Healer",
            archetype=CompanionArchetype.HEALER,
            combat_style=CombatStyle.SUPPORTIVE,
        )
        combatants = [
            Combatant(name="Ally", hp_current=50, hp_max=50, is_ally=True),
            Combatant(name="Enemy", hp_current=30, hp_max=30),
        ]
        battlefield = BattlefieldState(
            combatants=combatants,
            companion_hp_current=35,
            companion_hp_max=35,
            round_number=5,
        )
        engine = TacticsEngine(companion, battlefield)
        decision = engine.decide_action()

        # Healer should attack when no healing needed
        assert decision.action_type == "attack"

    def test_positioning_returns_none(self):
        # Positioning not yet implemented
        companion = CompanionProfile(
            npc_id="test",
            name="Test",
            archetype=CompanionArchetype.TANK,
            combat_style=CombatStyle.DEFENSIVE,
        )
        battlefield = BattlefieldState()
        engine = TacticsEngine(companion, battlefield)
        position = engine.calculate_positioning()

        assert position is None
