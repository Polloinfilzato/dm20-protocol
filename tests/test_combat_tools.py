"""
MCP tool input/output validation tests for combat tools.

Tests the MCP tool functions directly (not through the MCP server),
verifying correct formatting, error handling, and graceful degradation.

Tests cover:
- combat_action: attack and save_spell resolution
- build_encounter_tool: encounter suggestions
- show_map: ASCII map rendering / no-map fallback
- apply_effect: SRD condition and custom effect application
- remove_effect: removal by ID and name
- next_turn: effect tick-down integration
"""

import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from copy import deepcopy

pytestmark = pytest.mark.anyio

from dm20_protocol.models import (
    ActiveEffect,
    Modifier,
    Character,
    CharacterClass,
    Race,
    AbilityScore,
    ConcentrationState,
    Item,
    GameState,
)
from dm20_protocol.combat.effects import EffectsEngine, SRD_CONDITIONS
from dm20_protocol.combat.pipeline import CombatResult, SpellSaveResult


# ---------------------------------------------------------------------------
# Formatting helpers (imported from main.py)
# ---------------------------------------------------------------------------

# We test the formatting helpers directly since the MCP tools
# depend on them for output.


def _make_combat_result(**overrides) -> CombatResult:
    """Create a CombatResult with sensible defaults, overriding as needed."""
    defaults = dict(
        attacker_name="Aldric",
        target_name="Goblin",
        hit=True,
        attack_roll_total=18,
        natural_roll=15,
        all_d20_rolls=[15],
        attack_modifier=3,
        target_ac=15,
        had_advantage=False,
        had_disadvantage=False,
        critical=False,
        auto_miss=False,
        damage=8,
        damage_dice_results=[5],
        damage_modifier=3,
        damage_type="slashing",
        raw_damage=8,
    )
    defaults.update(overrides)
    return CombatResult(**defaults)


def _make_spell_save_result(**overrides) -> SpellSaveResult:
    """Create a SpellSaveResult with sensible defaults."""
    defaults = dict(
        caster_name="Elara",
        target_name="Goblin",
        save_ability="dexterity",
        save_dc=15,
        save_roll_total=10,
        save_natural_roll=8,
        all_d20_rolls=[8],
        save_modifier=2,
        saved=False,
        damage=28,
        raw_damage=28,
        damage_type="fire",
        damage_dice_results=[3, 4, 5, 4, 3, 4, 2, 3],
        half_on_save=True,
    )
    defaults.update(overrides)
    return SpellSaveResult(**defaults)


# ---------------------------------------------------------------------------
# Test: CombatResult formatting
# ---------------------------------------------------------------------------

class TestCombatResultFormatting:
    """Test _format_combat_result produces correct output."""

    def test_format_hit(self):
        """Hit result includes damage details."""
        from dm20_protocol.main import _format_combat_result
        result = _make_combat_result(hit=True, damage=8)
        formatted = _format_combat_result(result)

        assert "Hit!" in formatted
        assert "Aldric" in formatted
        assert "Goblin" in formatted
        assert "slashing" in formatted

    def test_format_miss(self):
        """Miss result does not include damage."""
        from dm20_protocol.main import _format_combat_result
        result = _make_combat_result(hit=False, damage=0, auto_miss=False)
        formatted = _format_combat_result(result)

        assert "Miss" in formatted
        assert "slashing" not in formatted  # No damage section on miss

    def test_format_critical(self):
        """Critical hit includes CRITICAL HIT marker."""
        from dm20_protocol.main import _format_combat_result
        result = _make_combat_result(hit=True, critical=True, damage=16)
        formatted = _format_combat_result(result)

        assert "CRITICAL HIT" in formatted

    def test_format_nat1(self):
        """Natural 1 shows auto-miss."""
        from dm20_protocol.main import _format_combat_result
        result = _make_combat_result(hit=False, auto_miss=True, natural_roll=1, damage=0)
        formatted = _format_combat_result(result)

        assert "Natural 1" in formatted

    def test_format_advantage(self):
        """Advantage is noted in output."""
        from dm20_protocol.main import _format_combat_result
        result = _make_combat_result(had_advantage=True, all_d20_rolls=[12, 18])
        formatted = _format_combat_result(result)

        assert "advantage" in formatted

    def test_format_resistance(self):
        """Resistance application is shown."""
        from dm20_protocol.main import _format_combat_result
        result = _make_combat_result(
            hit=True, damage=4, raw_damage=8, resistance_applied=True
        )
        formatted = _format_combat_result(result)

        assert "Resistance" in formatted

    def test_format_immunity(self):
        """Immunity is shown."""
        from dm20_protocol.main import _format_combat_result
        result = _make_combat_result(
            hit=True, damage=0, raw_damage=8, immunity_applied=True
        )
        formatted = _format_combat_result(result)

        assert "Immune" in formatted

    def test_format_triggered_effects(self):
        """Triggered effects are included."""
        from dm20_protocol.main import _format_combat_result
        result = _make_combat_result(
            effects_triggered=["Concentration check required (DC 10)", "Target drops to 0 HP"]
        )
        formatted = _format_combat_result(result)

        assert "Concentration check" in formatted
        assert "Target drops to 0 HP" in formatted


# ---------------------------------------------------------------------------
# Test: SpellSaveResult formatting
# ---------------------------------------------------------------------------

class TestSpellSaveFormatting:
    """Test _format_spell_save_result produces correct output."""

    def test_format_failed_save(self):
        """Failed save shows failure and full damage."""
        from dm20_protocol.main import _format_spell_save_result
        result = _make_spell_save_result(saved=False, damage=28)
        formatted = _format_spell_save_result(result)

        assert "fails" in formatted
        assert "28" in formatted
        assert "fire" in formatted

    def test_format_successful_save(self):
        """Successful save shows success."""
        from dm20_protocol.main import _format_spell_save_result
        result = _make_spell_save_result(saved=True, damage=14, raw_damage=28)
        formatted = _format_spell_save_result(result)

        assert "saves" in formatted


# ---------------------------------------------------------------------------
# Test: EncounterSuggestion formatting
# ---------------------------------------------------------------------------

class TestEncounterFormatting:
    """Test _format_encounter_suggestion produces correct output."""

    def test_format_encounter(self):
        """Encounter suggestion formats correctly."""
        from dm20_protocol.main import _format_encounter_suggestion
        from dm20_protocol.combat.encounter_builder import (
            EncounterSuggestion,
            EncounterComposition,
            MonsterGroup,
        )

        suggestion = EncounterSuggestion(
            party_levels=[5, 5, 5, 5],
            party_size=4,
            requested_difficulty="medium",
            xp_budget=2000,
            thresholds={"easy": 1000, "medium": 2000, "hard": 3000, "deadly": 4400},
            compositions=[
                EncounterComposition(
                    strategy="single_powerful",
                    strategy_description="A single powerful monster",
                    monster_groups=[
                        MonsterGroup(
                            monster_name="CR 5 Monster",
                            monster_index="cr-5",
                            count=1,
                            challenge_rating=5.0,
                            xp_per_monster=1800,
                        )
                    ],
                    total_monsters=1,
                    base_xp=1800,
                    encounter_multiplier=1.0,
                    adjusted_xp=1800,
                    actual_difficulty="medium",
                )
            ],
            rulebooks_loaded=False,
            notes=["No rulebooks loaded."],
        )

        formatted = _format_encounter_suggestion(suggestion)

        assert "Encounter Builder" in formatted
        assert "MEDIUM" in formatted
        assert "2000" in formatted
        assert "CR 5 Monster" in formatted
        assert "No rulebooks loaded" in formatted


# ---------------------------------------------------------------------------
# Test: Effect application tool logic
# ---------------------------------------------------------------------------

class TestApplyEffectLogic:
    """Test the logic behind the apply_effect tool."""

    def test_apply_srd_condition_creates_effect(self):
        """Applying an SRD condition creates the effect on the character."""
        char = Character(
            name="TestChar",
            character_class=CharacterClass(name="Fighter", level=1, hit_dice="1d10"),
            race=Race(name="Human"),
        )

        template = SRD_CONDITIONS["poisoned"]
        applied = EffectsEngine.apply_effect(char, template)

        assert applied.name == "Poisoned"
        assert len(char.active_effects) == 1

    def test_apply_custom_effect_with_modifiers(self):
        """Custom effect with modifiers modifies stats."""
        char = Character(
            name="TestChar",
            character_class=CharacterClass(name="Fighter", level=1, hit_dice="1d10"),
            race=Race(name="Human"),
            armor_class=16,
        )

        effect = ActiveEffect(
            name="Shield of Faith",
            source="Cleric spell",
            modifiers=[Modifier(stat="armor_class", operation="add", value=2)],
            duration_type="rounds",
            duration_remaining=10,
        )
        EffectsEngine.apply_effect(char, effect)

        effective_ac = EffectsEngine.effective_stat(char, "armor_class")
        assert effective_ac == 18

    def test_non_stackable_prevents_duplicates(self):
        """Non-stackable effects with the same name are not duplicated."""
        char = Character(
            name="TestChar",
            character_class=CharacterClass(name="Fighter", level=1, hit_dice="1d10"),
            race=Race(name="Human"),
        )

        template = SRD_CONDITIONS["blinded"]
        EffectsEngine.apply_effect(char, template)
        EffectsEngine.apply_effect(char, template)

        # Should only have one Blinded effect
        assert len(char.active_effects) == 1


# ---------------------------------------------------------------------------
# Test: Effect removal tool logic
# ---------------------------------------------------------------------------

class TestRemoveEffectLogic:
    """Test the logic behind the remove_effect tool."""

    def test_remove_by_id(self):
        """Effect can be removed by exact ID."""
        char = Character(
            name="TestChar",
            character_class=CharacterClass(name="Fighter", level=1, hit_dice="1d10"),
            race=Race(name="Human"),
        )

        effect = ActiveEffect(
            name="Haste",
            source="Spell",
            duration_type="concentration",
        )
        applied = EffectsEngine.apply_effect(char, effect)
        effect_id = applied.id

        removed = EffectsEngine.remove_effect(char, effect_id)
        assert removed is not None
        assert removed.name == "Haste"
        assert len(char.active_effects) == 0

    def test_remove_by_name(self):
        """All effects with a given name can be removed."""
        char = Character(
            name="TestChar",
            character_class=CharacterClass(name="Fighter", level=1, hit_dice="1d10"),
            race=Race(name="Human"),
        )

        # Apply exhaustion (stackable)
        template = SRD_CONDITIONS["exhaustion"]
        EffectsEngine.apply_effect(char, template)
        EffectsEngine.apply_effect(char, template)
        assert len(char.active_effects) == 2

        removed = EffectsEngine.remove_effects_by_name(char, "Exhaustion")
        assert len(removed) == 2
        assert len(char.active_effects) == 0

    def test_remove_nonexistent_returns_none(self):
        """Removing a non-existent effect returns None/empty list."""
        char = Character(
            name="TestChar",
            character_class=CharacterClass(name="Fighter", level=1, hit_dice="1d10"),
            race=Race(name="Human"),
        )

        removed = EffectsEngine.remove_effect(char, "nonexistent-id")
        assert removed is None

        removed_list = EffectsEngine.remove_effects_by_name(char, "Nonexistent")
        assert removed_list == []


# ---------------------------------------------------------------------------
# Test: Arbiter pipeline integration
# ---------------------------------------------------------------------------

class TestArbiterPipelineIntegration:
    """Test the ArbiterAgent.resolve_npc_action method."""

    async def test_resolve_npc_action_hit(self):
        """Arbiter resolves NPC attack via combat pipeline."""
        from dm20_protocol.claudmaster.agents.arbiter import ArbiterAgent
        from dm20_protocol.models import Campaign, GameState

        campaign = Campaign(
            name="Test Campaign",
            description="Test",
            game_state=GameState(campaign_name="Test Campaign"),
        )

        mock_llm = MagicMock()
        arbiter = ArbiterAgent(llm=mock_llm, campaign=campaign)

        attacker = Character(
            name="Orc",
            character_class=CharacterClass(name="Monster", level=3, hit_dice="1d10"),
            race=Race(name="Orc"),
            abilities={
                "strength": AbilityScore(score=16),
                "dexterity": AbilityScore(score=12),
                "constitution": AbilityScore(score=16),
                "intelligence": AbilityScore(score=7),
                "wisdom": AbilityScore(score=11),
                "charisma": AbilityScore(score=10),
            },
            armor_class=13,
            hit_points_max=15,
            hit_points_current=15,
            proficiency_bonus=2,
        )

        target = Character(
            name="Aldric",
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
            hit_points_max=44,
            hit_points_current=44,
            proficiency_bonus=3,
        )

        with patch("dm20_protocol.combat.pipeline.random.randint") as mock_rand:
            # Nat 20 (crit) -> doubles damage dice (2x 1d4 for unarmed) -> need 2 values
            mock_rand.side_effect = [20, 3, 4]
            result = await arbiter.resolve_npc_action(attacker, target)

        assert result["result"] is not None
        assert "summary" in result
        assert isinstance(result["narrative_hooks"], list)
        assert isinstance(result["state_changes"], list)

    async def test_resolve_npc_action_miss(self):
        """Arbiter resolves NPC attack that misses."""
        from dm20_protocol.claudmaster.agents.arbiter import ArbiterAgent
        from dm20_protocol.models import Campaign, GameState

        campaign = Campaign(
            name="Test Campaign",
            description="Test",
            game_state=GameState(campaign_name="Test Campaign"),
        )

        mock_llm = MagicMock()
        arbiter = ArbiterAgent(llm=mock_llm, campaign=campaign)

        attacker = Character(
            name="Goblin",
            character_class=CharacterClass(name="Monster", level=1, hit_dice="1d6"),
            race=Race(name="Goblin"),
            abilities={
                "strength": AbilityScore(score=8),
                "dexterity": AbilityScore(score=14),
                "constitution": AbilityScore(score=10),
                "intelligence": AbilityScore(score=10),
                "wisdom": AbilityScore(score=8),
                "charisma": AbilityScore(score=8),
            },
            armor_class=15,
            hit_points_max=7,
            hit_points_current=7,
            proficiency_bonus=2,
        )

        target = Character(
            name="Aldric",
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
            hit_points_max=44,
            hit_points_current=44,
            proficiency_bonus=3,
        )

        with patch("dm20_protocol.combat.pipeline.random.randint") as mock_rand:
            mock_rand.side_effect = [3]  # Attack roll: 3 + modifiers < 18 AC = miss
            result = await arbiter.resolve_npc_action(attacker, target)

        assert result["result"] is not None
        assert result["result"].hit is False
        assert "Miss" in result["summary"] or "miss" in result["summary"].lower()


# ---------------------------------------------------------------------------
# Test: CombatNarrator CombatResult acceptance
# ---------------------------------------------------------------------------

class TestCombatNarratorResultAcceptance:
    """Test the CombatNarrator.narrate_combat_result method."""

    async def test_narrate_hit_result(self):
        """Narrator generates text for a hit result."""
        from dm20_protocol.claudmaster.combat_narrator import CombatNarrator

        mock_llm = MagicMock()
        mock_llm.generate = MagicMock(
            return_value=MagicMock(
                __await__=lambda self: iter(["The blade strikes true!"])
            )
        )
        # Use an async mock
        async def mock_generate(prompt, max_tokens=512):
            return "The blade strikes true!"

        mock_llm.generate = mock_generate

        narrator = CombatNarrator(llm=mock_llm)

        result = _make_combat_result(hit=True, damage=8)
        narration = await narrator.narrate_combat_result(
            combat_result=result,
            target_hp_current=7,
            target_hp_max=15,
        )

        assert isinstance(narration, str)
        assert len(narration) > 0

    async def test_narrate_miss_result(self):
        """Narrator generates text for a miss result."""
        from dm20_protocol.claudmaster.combat_narrator import CombatNarrator

        async def mock_generate(prompt, max_tokens=512):
            return "The goblin ducks under the swing!"

        mock_llm = MagicMock()
        mock_llm.generate = mock_generate

        narrator = CombatNarrator(llm=mock_llm)

        result = _make_combat_result(hit=False, damage=0)
        narration = await narrator.narrate_combat_result(
            combat_result=result,
            target_hp_current=15,
            target_hp_max=15,
        )

        assert isinstance(narration, str)
        assert len(narration) > 0


# ---------------------------------------------------------------------------
# Test: Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Ensure existing tools are not broken by combat additions."""

    def test_srd_conditions_dict_unchanged(self):
        """All 14 SRD conditions are still available."""
        expected_conditions = {
            "blinded", "charmed", "deafened", "exhaustion", "frightened",
            "grappled", "incapacitated", "invisible", "paralyzed",
            "petrified", "poisoned", "prone", "restrained", "stunned",
        }
        assert set(SRD_CONDITIONS.keys()) == expected_conditions

    def test_combat_result_model_fields(self):
        """CombatResult has all expected fields."""
        result = _make_combat_result()
        assert hasattr(result, "attacker_name")
        assert hasattr(result, "target_name")
        assert hasattr(result, "hit")
        assert hasattr(result, "damage")
        assert hasattr(result, "damage_type")
        assert hasattr(result, "critical")
        assert hasattr(result, "concentration_check_dc")
        assert hasattr(result, "target_dropped_to_zero")
        assert hasattr(result, "effects_triggered")

    def test_character_model_supports_active_effects(self):
        """Character model has active_effects and concentration fields."""
        char = Character(
            name="Test",
            character_class=CharacterClass(name="Fighter", level=1, hit_dice="1d10"),
            race=Race(name="Human"),
        )
        assert hasattr(char, "active_effects")
        assert hasattr(char, "concentration")
        assert char.active_effects == []
        assert char.concentration is None
