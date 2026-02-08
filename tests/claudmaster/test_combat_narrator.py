"""
Tests for the Combat Narration System.

Tests cover:
- Damage severity classification
- Description tracking and anti-repetition
- LLM-based narrative generation for all combat events
- Critical hit and fumble special cases
- Player vs NPC death drama differences
"""

import pytest
from unittest.mock import AsyncMock

# Configure pytest to use anyio with asyncio backend only
pytestmark = pytest.mark.anyio


# Configure anyio to use only asyncio backend
@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


from dm20_protocol.claudmaster.combat_narrator import (
    CombatNarrator,
    DamageSeverity,
    SpellInfo,
    SpellEffect,
    DramaticMoment,
    DescriptionTracker,
)
from dm20_protocol.claudmaster.agents.archivist import InitiativeEntry


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_llm():
    """Create a mock LLM client."""
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="Generated narrative text.")
    return llm


@pytest.fixture
def narrator(mock_llm):
    """Create a CombatNarrator with mocked LLM."""
    return CombatNarrator(llm=mock_llm, max_tokens=512)


# ============================================================================
# Damage Severity Tests
# ============================================================================

def test_scratch_damage():
    """Test damage < 10% is classified as scratch."""
    severity = CombatNarrator.get_damage_severity(damage=5, max_hp=100)
    assert severity == DamageSeverity.SCRATCH


def test_light_damage():
    """Test damage 10-25% is classified as light."""
    severity = CombatNarrator.get_damage_severity(damage=15, max_hp=100)
    assert severity == DamageSeverity.LIGHT


def test_moderate_damage():
    """Test damage 25-50% is classified as moderate."""
    severity = CombatNarrator.get_damage_severity(damage=30, max_hp=100)
    assert severity == DamageSeverity.MODERATE


def test_heavy_damage():
    """Test damage 50-75% is classified as heavy."""
    severity = CombatNarrator.get_damage_severity(damage=60, max_hp=100)
    assert severity == DamageSeverity.HEAVY


def test_devastating_damage():
    """Test damage > 75% is classified as devastating."""
    severity = CombatNarrator.get_damage_severity(damage=80, max_hp=100)
    assert severity == DamageSeverity.DEVASTATING


def test_edge_case_10_percent():
    """Test 10% damage is classified as light (boundary)."""
    severity = CombatNarrator.get_damage_severity(damage=10, max_hp=100)
    assert severity == DamageSeverity.LIGHT


def test_edge_case_25_percent():
    """Test 25% damage is classified as moderate (boundary)."""
    severity = CombatNarrator.get_damage_severity(damage=25, max_hp=100)
    assert severity == DamageSeverity.MODERATE


def test_edge_case_50_percent():
    """Test 50% damage is classified as heavy (boundary)."""
    severity = CombatNarrator.get_damage_severity(damage=50, max_hp=100)
    assert severity == DamageSeverity.HEAVY


def test_edge_case_75_percent():
    """Test 75% damage is classified as devastating (boundary)."""
    severity = CombatNarrator.get_damage_severity(damage=75, max_hp=100)
    assert severity == DamageSeverity.DEVASTATING


def test_zero_max_hp():
    """Test zero max HP returns moderate (safe default)."""
    severity = CombatNarrator.get_damage_severity(damage=10, max_hp=0)
    assert severity == DamageSeverity.MODERATE


def test_damage_exceeds_max_hp():
    """Test overkill damage is classified as devastating."""
    severity = CombatNarrator.get_damage_severity(damage=150, max_hp=100)
    assert severity == DamageSeverity.DEVASTATING


# ============================================================================
# DescriptionTracker Tests
# ============================================================================

def test_record_description():
    """Test recording a description."""
    tracker = DescriptionTracker(history_size=5)
    tracker.record("The sword strikes true.", template_key="attack_hit")
    assert not tracker.is_too_similar("A completely different description.")


def test_similarity_detection():
    """Test detection of similar descriptions."""
    tracker = DescriptionTracker(history_size=5)
    tracker.record("The mighty warrior swings his sword with great force.")

    # Very similar description should be flagged
    similar = "The mighty warrior swings his sword with great strength."
    assert tracker.is_too_similar(similar, threshold=0.5)


def test_dissimilar_descriptions_pass():
    """Test that dissimilar descriptions are not flagged."""
    tracker = DescriptionTracker(history_size=5)
    tracker.record("The sword strikes the shield with a resounding clang.")

    # Completely different description
    different = "The wizard casts a fireball at the dragon."
    assert not tracker.is_too_similar(different, threshold=0.5)


def test_history_size_limit():
    """Test that history is limited to specified size."""
    tracker = DescriptionTracker(history_size=3)

    for i in range(5):
        tracker.record(f"Description {i}", template_key=f"template_{i}")

    # Only last 3 should be in history
    assert len(tracker._history) == 3


def test_template_usage_tracking():
    """Test that template usage is tracked correctly."""
    tracker = DescriptionTracker(history_size=10)

    tracker.record("Attack 1", template_key="attack_hit")
    tracker.record("Attack 2", template_key="attack_hit")
    tracker.record("Attack 3", template_key="attack_miss")

    assert tracker._template_usage["attack_hit"] == 2
    assert tracker._template_usage["attack_miss"] == 1


def test_get_least_used_template():
    """Test selection of least-used template."""
    tracker = DescriptionTracker(history_size=10)

    tracker.record("Hit 1", template_key="attack_hit")
    tracker.record("Hit 2", template_key="attack_hit")
    tracker.record("Miss 1", template_key="attack_miss")

    templates = ["attack_hit", "attack_miss", "attack_critical"]
    least_used = tracker.get_least_used_template(templates)

    # attack_critical has 0 uses, should be selected
    assert least_used == "attack_critical"


def test_get_least_used_template_empty_list():
    """Test least-used template with empty list."""
    tracker = DescriptionTracker(history_size=10)
    assert tracker.get_least_used_template([]) == ""


def test_empty_history_not_similar():
    """Test that empty history doesn't flag similarity."""
    tracker = DescriptionTracker(history_size=10)
    assert not tracker.is_too_similar("Any description")


def test_jaccard_similarity_calculation():
    """Test Jaccard similarity calculation."""
    tracker = DescriptionTracker(history_size=10)
    tracker.record("the quick brown fox")

    # Exact match: similarity = 1.0
    assert tracker.is_too_similar("the quick brown fox", threshold=0.9)

    # Partial overlap: "the brown" = 2 common, 5 total words
    # Similarity = 2/5 = 0.4
    assert not tracker.is_too_similar("the brown dog", threshold=0.5)


# ============================================================================
# CombatNarrator Tests (Async)
# ============================================================================

async def test_narrate_round_start(narrator, mock_llm):
    """Test round start narration."""
    initiative_order = [
        InitiativeEntry(name="Fighter", initiative=18, is_current=True, is_player=True),
        InitiativeEntry(name="Goblin", initiative=12, is_current=False, is_player=False),
    ]

    result = await narrator.narrate_round_start(
        round_number=2,
        initiative_order=initiative_order,
    )

    assert result == "Generated narrative text."
    mock_llm.generate.assert_called_once()

    # Verify prompt contains round number and initiative
    prompt = mock_llm.generate.call_args[0][0]
    assert "round 2" in prompt.lower()
    assert "Fighter" in prompt
    assert "Goblin" in prompt


async def test_narrate_attack_hit(narrator, mock_llm):
    """Test narration of a successful attack."""
    result = await narrator.narrate_attack(
        attacker="Paladin",
        defender="Orc",
        weapon="longsword",
        roll=18,
        hit=True,
        critical=False,
        fumble=False,
    )

    assert result == "Generated narrative text."
    mock_llm.generate.assert_called_once()

    prompt = mock_llm.generate.call_args[0][0]
    assert "Paladin" in prompt
    assert "Orc" in prompt
    assert "longsword" in prompt
    assert "Hit" in prompt


async def test_narrate_attack_miss(narrator, mock_llm):
    """Test narration of a missed attack."""
    result = await narrator.narrate_attack(
        attacker="Rogue",
        defender="Dragon",
        weapon="dagger",
        roll=5,
        hit=False,
        critical=False,
        fumble=False,
    )

    assert result == "Generated narrative text."

    prompt = mock_llm.generate.call_args[0][0]
    assert "Miss" in prompt


async def test_narrate_attack_critical(narrator, mock_llm):
    """Test narration of a critical hit."""
    result = await narrator.narrate_attack(
        attacker="Barbarian",
        defender="Troll",
        weapon="greataxe",
        roll=20,
        hit=True,
        critical=True,
        fumble=False,
    )

    assert result == "Generated narrative text."

    prompt = mock_llm.generate.call_args[0][0]
    assert "CRITICAL HIT" in prompt


async def test_narrate_attack_fumble(narrator, mock_llm):
    """Test narration of a critical fumble."""
    result = await narrator.narrate_attack(
        attacker="Wizard",
        defender="Skeleton",
        weapon="staff",
        roll=1,
        hit=False,
        critical=False,
        fumble=True,
    )

    assert result == "Generated narrative text."

    prompt = mock_llm.generate.call_args[0][0]
    assert "CRITICAL FUMBLE" in prompt


async def test_narrate_damage(narrator, mock_llm):
    """Test damage narration."""
    result = await narrator.narrate_damage(
        target="Knight",
        damage=25,
        damage_type="slashing",
        current_hp=45,
        max_hp=70,
    )

    assert result == "Generated narrative text."

    prompt = mock_llm.generate.call_args[0][0]
    assert "Knight" in prompt
    assert "25" in prompt
    assert "slashing" in prompt
    assert "moderate" in prompt.lower()  # 25/70 ≈ 35% = moderate


async def test_narrate_damage_devastating(narrator, mock_llm):
    """Test devastating damage narration."""
    result = await narrator.narrate_damage(
        target="Ranger",
        damage=80,
        damage_type="fire",
        current_hp=5,
        max_hp=85,
    )

    assert result == "Generated narrative text."

    prompt = mock_llm.generate.call_args[0][0]
    assert "devastating" in prompt.lower()


async def test_narrate_spell(narrator, mock_llm):
    """Test spell narration."""
    spell = SpellInfo(
        name="Fireball",
        school="evocation",
        level=3,
        damage_type="fire",
    )

    effects = [
        SpellEffect(target="Goblin 1", effect_type="damage", value=28),
        SpellEffect(target="Goblin 2", effect_type="damage", value=28),
    ]

    result = await narrator.narrate_spell(
        caster="Sorcerer",
        spell=spell,
        targets=["Goblin 1", "Goblin 2"],
        effects=effects,
    )

    assert result == "Generated narrative text."

    prompt = mock_llm.generate.call_args[0][0]
    assert "Sorcerer" in prompt
    assert "Fireball" in prompt
    assert "evocation" in prompt
    assert "Goblin 1" in prompt


async def test_narrate_spell_healing(narrator, mock_llm):
    """Test healing spell narration."""
    spell = SpellInfo(
        name="Cure Wounds",
        school="evocation",
        level=1,
    )

    effects = [
        SpellEffect(target="Cleric", effect_type="heal", value=12),
    ]

    result = await narrator.narrate_spell(
        caster="Cleric",
        spell=spell,
        targets=["Cleric"],
        effects=effects,
    )

    assert result == "Generated narrative text."

    prompt = mock_llm.generate.call_args[0][0]
    assert "heal" in prompt.lower()


async def test_narrate_death_player(narrator, mock_llm):
    """Test player character death narration (more dramatic)."""
    result = await narrator.narrate_death(
        character="Brave Hero",
        killing_blow="dragon's fiery breath",
        is_player=True,
    )

    assert result == "Generated narrative text."

    prompt = mock_llm.generate.call_args[0][0]
    assert "Brave Hero" in prompt
    assert "dragon's fiery breath" in prompt
    assert "Player Character" in prompt
    assert "heroic" in prompt.lower()


async def test_narrate_death_npc(narrator, mock_llm):
    """Test NPC death narration (less dramatic)."""
    result = await narrator.narrate_death(
        character="Goblin Chief",
        killing_blow="arrow to the heart",
        is_player=False,
    )

    assert result == "Generated narrative text."

    prompt = mock_llm.generate.call_args[0][0]
    assert "Goblin Chief" in prompt
    assert "Enemy/NPC" in prompt


async def test_narrate_unconscious(narrator, mock_llm):
    """Test unconscious narration."""
    result = await narrator.narrate_unconscious(
        character="Monk",
        cause="massive bludgeoning damage",
    )

    assert result == "Generated narrative text."

    prompt = mock_llm.generate.call_args[0][0]
    assert "Monk" in prompt
    assert "massive bludgeoning damage" in prompt


async def test_tracker_records_descriptions(narrator, mock_llm):
    """Test that descriptions are recorded in the tracker."""
    initial_size = len(narrator._tracker._history)

    await narrator.narrate_attack(
        attacker="Test",
        defender="Test",
        weapon="test",
        roll=10,
        hit=True,
    )

    assert len(narrator._tracker._history) == initial_size + 1


async def test_different_prompts_for_critical_vs_normal(narrator, mock_llm):
    """Test that critical hits use different prompts than normal hits."""
    # Normal hit
    await narrator.narrate_attack(
        attacker="A", defender="B", weapon="sword", roll=15, hit=True, critical=False
    )
    normal_prompt = mock_llm.generate.call_args[0][0]

    mock_llm.reset_mock()

    # Critical hit
    await narrator.narrate_attack(
        attacker="A", defender="B", weapon="sword", roll=20, hit=True, critical=True
    )
    crit_prompt = mock_llm.generate.call_args[0][0]

    # Prompts should differ
    assert "CRITICAL HIT" in crit_prompt
    assert "CRITICAL HIT" not in normal_prompt


async def test_max_tokens_passed_to_llm(narrator, mock_llm):
    """Test that max_tokens is passed correctly to LLM."""
    await narrator.narrate_round_start(round_number=1, initiative_order=[])

    # Verify max_tokens argument
    call_kwargs = mock_llm.generate.call_args[1]
    assert call_kwargs["max_tokens"] == 512


# ============================================================================
# Integration Tests
# ============================================================================

async def test_full_combat_sequence():
    """Test a complete combat sequence."""
    # Mock LLM that returns different responses
    mock_llm = AsyncMock()
    responses = [
        "Round 1 begins! The combatants ready their weapons.",
        "The fighter's sword slashes across the goblin's chest!",
        "The goblin staggers, blood flowing from the wound.",
        "The wizard's hands glow with arcane energy as she unleashes a fireball!",
        "The goblins shriek as flames engulf them.",
    ]
    mock_llm.generate = AsyncMock(side_effect=responses)

    narrator = CombatNarrator(llm=mock_llm, max_tokens=512)

    # Round start
    init_order = [
        InitiativeEntry(name="Fighter", initiative=18, is_current=True, is_player=True),
        InitiativeEntry(name="Wizard", initiative=15, is_current=False, is_player=True),
        InitiativeEntry(name="Goblin", initiative=10, is_current=False, is_player=False),
    ]
    round_text = await narrator.narrate_round_start(1, init_order)
    assert "Round 1" in round_text

    # Attack
    attack_text = await narrator.narrate_attack(
        attacker="Fighter", defender="Goblin", weapon="longsword",
        roll=18, hit=True
    )
    assert "sword" in attack_text

    # Damage
    damage_text = await narrator.narrate_damage(
        target="Goblin", damage=15, damage_type="slashing",
        current_hp=5, max_hp=20
    )
    assert "wound" in damage_text

    # Spell
    spell = SpellInfo(name="Fireball", school="evocation", level=3)
    effects = [SpellEffect(target="Goblin", effect_type="damage", value=28)]
    spell_text = await narrator.narrate_spell(
        caster="Wizard", spell=spell, targets=["Goblin"], effects=effects
    )
    assert "arcane" in spell_text or "fireball" in spell_text.lower()

    # Verify all responses were used
    assert mock_llm.generate.call_count == 4
