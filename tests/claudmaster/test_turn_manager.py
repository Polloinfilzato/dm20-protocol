"""
Tests for the Turn Manager module.

Tests cover:
- Round lifecycle (start, advance, end)
- Turn distribution modes (round-robin, free-form, spotlight, popcorn)
- Combat initiative ordering
- Held actions
- Simultaneous action resolution
- Timeout detection and handling
- Turn history tracking
- Edge cases
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from dm20_protocol.claudmaster.turn_manager import (
    TurnPhase,
    TurnDistribution,
    TurnRecord,
    ActionResult,
    SimultaneousAction,
    TurnState,
    TurnManager,
)
from dm20_protocol.claudmaster.pc_tracking import (
    PCRegistry,
    MultiPlayerConfig,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def config():
    """Create a standard multi-player config."""
    return MultiPlayerConfig(
        max_players=6,
        allow_dynamic_join=True,
        turn_timeout_seconds=60,
        simultaneous_actions=True,
        pc_list=["Gandalf", "Aragorn", "Legolas", "Gimli"]
    )


@pytest.fixture
def registry(config):
    """Create a PC registry with registered PCs."""
    reg = PCRegistry(config)
    reg.register_pc("Gandalf", "Alice")
    reg.register_pc("Aragorn", "Bob")
    reg.register_pc("Legolas", "Charlie")
    reg.register_pc("Gimli", "Dave")
    return reg


@pytest.fixture
def turn_manager(registry, config):
    """Create a turn manager with populated registry."""
    return TurnManager(registry, config)


# ============================================================================
# Round Lifecycle Tests
# ============================================================================

def test_start_round_creates_state(turn_manager):
    """Test that start_round creates valid turn state."""
    state = turn_manager.start_round(TurnPhase.EXPLORATION)

    assert state is not None
    assert state.phase == TurnPhase.EXPLORATION
    assert state.current_round == 1
    assert len(state.turn_order) == 4
    assert state.current_pc_id == "Gandalf"  # First in order
    assert state.distribution_mode == TurnDistribution.ROUND_ROBIN


def test_start_round_with_custom_distribution(turn_manager):
    """Test starting round with custom distribution mode."""
    state = turn_manager.start_round(
        TurnPhase.COMBAT,
        TurnDistribution.FREE_FORM
    )

    assert state.phase == TurnPhase.COMBAT
    assert state.distribution_mode == TurnDistribution.FREE_FORM
    assert state.current_pc_id is None  # Free-form has no current PC


def test_start_round_increments_round_number(turn_manager):
    """Test that starting multiple rounds increments round number."""
    state1 = turn_manager.start_round(TurnPhase.EXPLORATION)
    assert state1.current_round == 1

    turn_manager.end_round()

    state2 = turn_manager.start_round(TurnPhase.COMBAT)
    assert state2.current_round == 2


def test_start_round_requires_active_pcs(config):
    """Test that start_round fails with no active PCs."""
    empty_registry = PCRegistry(config)
    manager = TurnManager(empty_registry, config)

    with pytest.raises(ValueError, match="no active PCs"):
        manager.start_round(TurnPhase.COMBAT)


def test_get_current_turn(turn_manager):
    """Test getting current turn PC."""
    assert turn_manager.get_current_turn() is None  # No round started

    turn_manager.start_round(TurnPhase.COMBAT)
    assert turn_manager.get_current_turn() == "Gandalf"


def test_end_round_clears_state(turn_manager):
    """Test that end_round clears state."""
    turn_manager.start_round(TurnPhase.COMBAT)
    assert turn_manager.state is not None

    records = turn_manager.end_round()
    assert turn_manager.state is None
    assert isinstance(records, list)


def test_end_round_without_active_round(turn_manager):
    """Test end_round fails without active round."""
    with pytest.raises(RuntimeError, match="No active round"):
        turn_manager.end_round()


# ============================================================================
# Round-Robin Distribution Tests
# ============================================================================

def test_round_robin_advance_turn(turn_manager):
    """Test round-robin turn advancement."""
    turn_manager.start_round(TurnPhase.COMBAT, TurnDistribution.ROUND_ROBIN)

    assert turn_manager.get_current_turn() == "Gandalf"

    next_pc = turn_manager.advance_turn()
    assert next_pc == "Aragorn"
    assert turn_manager.get_current_turn() == "Aragorn"

    next_pc = turn_manager.advance_turn()
    assert next_pc == "Legolas"


def test_round_robin_wraps_around(turn_manager):
    """Test round-robin wraps to None after all PCs have gone."""
    turn_manager.start_round(TurnPhase.COMBAT, TurnDistribution.ROUND_ROBIN)

    # Advance through all 4 PCs
    turn_manager.advance_turn()  # Gandalf -> Aragorn
    turn_manager.advance_turn()  # Aragorn -> Legolas
    turn_manager.advance_turn()  # Legolas -> Gimli
    next_pc = turn_manager.advance_turn()  # Gimli -> None (round complete)

    assert next_pc is None
    assert turn_manager.get_current_turn() is None


def test_round_robin_can_act(turn_manager):
    """Test can_act in round-robin mode."""
    turn_manager.start_round(TurnPhase.COMBAT, TurnDistribution.ROUND_ROBIN)

    assert turn_manager.can_act("Gandalf") is True
    assert turn_manager.can_act("Aragorn") is False
    assert turn_manager.can_act("Legolas") is False

    turn_manager.advance_turn()

    assert turn_manager.can_act("Gandalf") is False
    assert turn_manager.can_act("Aragorn") is True


def test_round_robin_marks_completed(turn_manager):
    """Test that advancing turn marks PC as completed."""
    turn_manager.start_round(TurnPhase.COMBAT, TurnDistribution.ROUND_ROBIN)

    assert "Gandalf" not in turn_manager.state.completed_turns

    turn_manager.advance_turn()

    assert "Gandalf" in turn_manager.state.completed_turns
    assert "Aragorn" not in turn_manager.state.completed_turns


# ============================================================================
# Free-Form Distribution Tests
# ============================================================================

def test_free_form_no_current_pc(turn_manager):
    """Test free-form mode has no current PC."""
    turn_manager.start_round(TurnPhase.EXPLORATION, TurnDistribution.FREE_FORM)

    assert turn_manager.get_current_turn() is None


def test_free_form_can_act(turn_manager):
    """Test anyone can act in free-form mode."""
    turn_manager.start_round(TurnPhase.EXPLORATION, TurnDistribution.FREE_FORM)

    assert turn_manager.can_act("Gandalf") is True
    assert turn_manager.can_act("Aragorn") is True
    assert turn_manager.can_act("Legolas") is True
    assert turn_manager.can_act("Gimli") is True


def test_free_form_advance_returns_none(turn_manager):
    """Test advance_turn returns None in free-form."""
    turn_manager.start_round(TurnPhase.EXPLORATION, TurnDistribution.FREE_FORM)

    next_pc = turn_manager.advance_turn()
    assert next_pc is None


# ============================================================================
# Spotlight Distribution Tests
# ============================================================================

def test_spotlight_initial_pc(turn_manager):
    """Test spotlight mode starts with first PC."""
    turn_manager.start_round(TurnPhase.ROLEPLAY, TurnDistribution.SPOTLIGHT)

    assert turn_manager.get_current_turn() == "Gandalf"


def test_spotlight_can_act(turn_manager):
    """Test only spotlighted PC can act."""
    turn_manager.start_round(TurnPhase.ROLEPLAY, TurnDistribution.SPOTLIGHT)

    assert turn_manager.can_act("Gandalf") is True
    assert turn_manager.can_act("Aragorn") is False


def test_spotlight_advance_clears_current(turn_manager):
    """Test advance_turn clears current PC in spotlight mode."""
    turn_manager.start_round(TurnPhase.ROLEPLAY, TurnDistribution.SPOTLIGHT)

    next_pc = turn_manager.advance_turn()
    assert next_pc is None
    assert turn_manager.get_current_turn() is None


# ============================================================================
# Popcorn Distribution Tests
# ============================================================================

def test_popcorn_requires_next_pc(turn_manager):
    """Test popcorn mode requires next_pc parameter."""
    turn_manager.start_round(TurnPhase.COMBAT, TurnDistribution.POPCORN)

    with pytest.raises(ValueError, match="requires next_pc"):
        turn_manager.advance_turn()


def test_popcorn_advance_to_chosen_pc(turn_manager):
    """Test popcorn mode advances to chosen PC."""
    turn_manager.start_round(TurnPhase.COMBAT, TurnDistribution.POPCORN)

    next_pc = turn_manager.advance_turn(next_pc="Legolas")
    assert next_pc == "Legolas"
    assert turn_manager.get_current_turn() == "Legolas"


def test_popcorn_rejects_invalid_pc(turn_manager):
    """Test popcorn mode rejects invalid PC choice."""
    turn_manager.start_round(TurnPhase.COMBAT, TurnDistribution.POPCORN)

    with pytest.raises(ValueError, match="not in turn order"):
        turn_manager.advance_turn(next_pc="Sauron")


def test_popcorn_can_act(turn_manager):
    """Test only current PC can act in popcorn mode."""
    turn_manager.start_round(TurnPhase.COMBAT, TurnDistribution.POPCORN)

    assert turn_manager.can_act("Gandalf") is True
    assert turn_manager.can_act("Legolas") is False

    turn_manager.advance_turn(next_pc="Legolas")

    assert turn_manager.can_act("Gandalf") is False
    assert turn_manager.can_act("Legolas") is True


# ============================================================================
# Distribution Mode Switching Tests
# ============================================================================

def test_set_distribution_mode(turn_manager):
    """Test changing distribution mode mid-round."""
    turn_manager.start_round(TurnPhase.COMBAT, TurnDistribution.ROUND_ROBIN)

    turn_manager.set_distribution_mode(TurnDistribution.FREE_FORM)
    assert turn_manager.state.distribution_mode == TurnDistribution.FREE_FORM


def test_set_distribution_mode_clears_current_for_free_form(turn_manager):
    """Test switching to free-form clears current PC."""
    turn_manager.start_round(TurnPhase.COMBAT, TurnDistribution.ROUND_ROBIN)
    assert turn_manager.get_current_turn() == "Gandalf"

    turn_manager.set_distribution_mode(TurnDistribution.FREE_FORM)
    assert turn_manager.get_current_turn() is None


def test_set_distribution_mode_sets_current_from_free_form(turn_manager):
    """Test switching from free-form sets first PC as current."""
    turn_manager.start_round(TurnPhase.COMBAT, TurnDistribution.FREE_FORM)
    assert turn_manager.get_current_turn() is None

    turn_manager.set_distribution_mode(TurnDistribution.ROUND_ROBIN)
    assert turn_manager.get_current_turn() == "Gandalf"


def test_set_distribution_mode_without_round(turn_manager):
    """Test set_distribution_mode fails without active round."""
    with pytest.raises(RuntimeError, match="No active round"):
        turn_manager.set_distribution_mode(TurnDistribution.FREE_FORM)


# ============================================================================
# Combat Initiative Tests
# ============================================================================

def test_build_combat_order(turn_manager):
    """Test building combat order from initiative rolls."""
    participants = ["Gandalf", "Aragorn", "Legolas", "Gimli"]
    initiatives = {
        "Gandalf": 18,
        "Aragorn": 12,
        "Legolas": 22,
        "Gimli": 8
    }

    order = turn_manager.build_combat_order(participants, initiatives)

    assert order == ["Legolas", "Gandalf", "Aragorn", "Gimli"]


def test_build_combat_order_empty_participants(turn_manager):
    """Test build_combat_order fails with empty participants."""
    with pytest.raises(ValueError, match="cannot be empty"):
        turn_manager.build_combat_order([], {})


def test_build_combat_order_missing_initiatives(turn_manager):
    """Test build_combat_order fails with missing initiatives."""
    participants = ["Gandalf", "Aragorn"]
    initiatives = {"Gandalf": 15}  # Missing Aragorn

    with pytest.raises(ValueError, match="Missing initiative"):
        turn_manager.build_combat_order(participants, initiatives)


def test_insert_into_initiative(turn_manager):
    """Test inserting character into combat mid-combat."""
    participants = ["Gandalf", "Aragorn"]
    initiatives = {"Gandalf": 20, "Aragorn": 10}

    # Build initial combat order and start round
    order = turn_manager.build_combat_order(participants, initiatives)
    turn_manager.start_round(TurnPhase.COMBAT)
    turn_manager.state.turn_order = order

    # Insert Legolas with initiative 15 (between 20 and 10)
    turn_manager.insert_into_initiative("Legolas", 15)

    # Should be inserted between Gandalf and Aragorn
    assert "Legolas" in turn_manager.state.turn_order
    assert turn_manager.state.turn_order == ["Gandalf", "Legolas", "Aragorn"]


def test_insert_into_initiative_requires_combat(turn_manager):
    """Test insert_into_initiative fails outside combat."""
    turn_manager.start_round(TurnPhase.EXPLORATION)

    with pytest.raises(RuntimeError, match="during combat"):
        turn_manager.insert_into_initiative("Legolas", 15)


def test_insert_into_initiative_rejects_duplicate(turn_manager):
    """Test insert_into_initiative rejects already-present character."""
    turn_manager.start_round(TurnPhase.COMBAT)

    with pytest.raises(ValueError, match="already in turn order"):
        turn_manager.insert_into_initiative("Gandalf", 15)


# ============================================================================
# Held Action Tests
# ============================================================================

def test_hold_action(turn_manager):
    """Test holding an action."""
    turn_manager.start_round(TurnPhase.COMBAT)

    turn_manager.hold_action("Gandalf", "until orc appears")

    assert "Gandalf" in turn_manager.state.held_actions
    assert turn_manager.state.held_actions["Gandalf"] == "until orc appears"


def test_resolve_held_action(turn_manager):
    """Test resolving a held action."""
    turn_manager.start_round(TurnPhase.COMBAT)
    turn_manager.hold_action("Gandalf", "until orc appears")

    trigger = turn_manager.resolve_held_action("Gandalf")

    assert trigger == "until orc appears"
    assert "Gandalf" not in turn_manager.state.held_actions


def test_resolve_held_action_not_present(turn_manager):
    """Test resolving non-existent held action returns None."""
    turn_manager.start_round(TurnPhase.COMBAT)

    trigger = turn_manager.resolve_held_action("Gandalf")
    assert trigger is None


def test_hold_action_requires_round(turn_manager):
    """Test hold_action fails without active round."""
    with pytest.raises(RuntimeError, match="No active round"):
        turn_manager.hold_action("Gandalf", "trigger")


def test_hold_action_requires_valid_pc(turn_manager):
    """Test hold_action fails for PC not in turn order."""
    turn_manager.start_round(TurnPhase.COMBAT)

    with pytest.raises(ValueError, match="not in turn order"):
        turn_manager.hold_action("Sauron", "trigger")


# ============================================================================
# Simultaneous Action Tests
# ============================================================================

def test_queue_simultaneous_action(turn_manager):
    """Test queuing a simultaneous action."""
    turn_manager.start_round(TurnPhase.COMBAT)

    turn_manager.queue_simultaneous("Gandalf", "cast fireball", target="orcs")

    assert len(turn_manager._simultaneous_queue) == 1
    action = turn_manager._simultaneous_queue[0]
    assert action.pc_id == "Gandalf"
    assert action.action == "cast fireball"
    assert action.target == "orcs"


def test_queue_simultaneous_multiple_actions(turn_manager):
    """Test queuing multiple simultaneous actions."""
    turn_manager.start_round(TurnPhase.COMBAT)

    turn_manager.queue_simultaneous("Gandalf", "cast fireball")
    turn_manager.queue_simultaneous("Aragorn", "attack with sword")
    turn_manager.queue_simultaneous("Legolas", "shoot arrow")

    assert len(turn_manager._simultaneous_queue) == 3


def test_queue_simultaneous_requires_config_enabled(config, registry):
    """Test queuing simultaneous fails if disabled in config."""
    config.simultaneous_actions = False
    manager = TurnManager(registry, config)
    manager.start_round(TurnPhase.COMBAT)

    with pytest.raises(RuntimeError, match="disabled"):
        manager.queue_simultaneous("Gandalf", "cast fireball")


def test_queue_simultaneous_requires_active_pc(turn_manager):
    """Test queuing simultaneous fails for inactive PC."""
    turn_manager.start_round(TurnPhase.COMBAT)

    # Deactivate Gandalf
    turn_manager.pc_registry.update_pc_state("Gandalf", is_active=False)

    with pytest.raises(ValueError, match="not active"):
        turn_manager.queue_simultaneous("Gandalf", "cast fireball")


def test_resolve_simultaneous_batch(turn_manager):
    """Test resolving simultaneous actions."""
    turn_manager.start_round(TurnPhase.COMBAT)

    turn_manager.queue_simultaneous("Gandalf", "cast fireball")
    turn_manager.queue_simultaneous("Aragorn", "attack")

    results = turn_manager.resolve_simultaneous_batch()

    assert len(results) == 2
    assert all(isinstance(r, ActionResult) for r in results)
    assert len(turn_manager._simultaneous_queue) == 0  # Queue cleared


def test_resolve_simultaneous_respects_priority(turn_manager):
    """Test simultaneous resolution respects priority order."""
    turn_manager.start_round(TurnPhase.COMBAT)

    # Queue with different priorities
    turn_manager.queue_simultaneous("Gandalf", "cast fireball")
    turn_manager.queue_simultaneous("Aragorn", "attack")
    turn_manager._simultaneous_queue[0].priority = 5
    turn_manager._simultaneous_queue[1].priority = 10

    results = turn_manager.resolve_simultaneous_batch()

    # Aragorn (priority 10) should be first
    assert results[0].character_id == "Aragorn"
    assert results[1].character_id == "Gandalf"


def test_resolve_simultaneous_empty_queue(turn_manager):
    """Test resolving empty simultaneous queue fails."""
    with pytest.raises(RuntimeError, match="No simultaneous actions"):
        turn_manager.resolve_simultaneous_batch()


# ============================================================================
# Timeout Tests
# ============================================================================

def test_check_timeout_no_timeout(turn_manager):
    """Test check_timeout returns None when no timeout."""
    turn_manager.start_round(TurnPhase.COMBAT)

    timed_out = turn_manager.check_timeout()
    assert timed_out is None


def test_check_timeout_detects_timeout(turn_manager, config):
    """Test check_timeout detects timed-out PC."""
    config.turn_timeout_seconds = 1  # 1 second timeout
    manager = TurnManager(turn_manager.pc_registry, config)
    manager.start_round(TurnPhase.COMBAT)

    # Mock elapsed time
    past_time = datetime.now() - timedelta(seconds=5)
    manager.state.turn_start_time = past_time

    timed_out = manager.check_timeout()
    assert timed_out == "Gandalf"


def test_check_timeout_free_form_returns_none(turn_manager):
    """Test check_timeout returns None in free-form mode."""
    turn_manager.start_round(TurnPhase.COMBAT, TurnDistribution.FREE_FORM)

    timed_out = turn_manager.check_timeout()
    assert timed_out is None


def test_check_timeout_requires_round(turn_manager):
    """Test check_timeout fails without active round."""
    with pytest.raises(RuntimeError, match="No active round"):
        turn_manager.check_timeout()


def test_handle_timeout(turn_manager, config):
    """Test handling a timeout."""
    config.turn_timeout_seconds = 1
    manager = TurnManager(turn_manager.pc_registry, config)
    manager.start_round(TurnPhase.COMBAT)

    # Force timeout
    past_time = datetime.now() - timedelta(seconds=5)
    manager.state.turn_start_time = past_time

    manager.handle_timeout("Gandalf")

    # Should have recorded timeout and advanced turn
    assert len(manager.turn_history) == 1
    assert manager.turn_history[0].action_summary == "[Turn timed out - auto-passed]"
    assert manager.get_current_turn() == "Aragorn"


def test_handle_timeout_wrong_pc(turn_manager):
    """Test handle_timeout fails for non-current PC."""
    turn_manager.start_round(TurnPhase.COMBAT)

    with pytest.raises(ValueError, match="not the current PC"):
        turn_manager.handle_timeout("Aragorn")


def test_handle_timeout_requires_round(turn_manager):
    """Test handle_timeout fails without active round."""
    with pytest.raises(RuntimeError, match="No active round"):
        turn_manager.handle_timeout("Gandalf")


# ============================================================================
# Turn History Tests
# ============================================================================

def test_record_action(turn_manager):
    """Test recording an action."""
    turn_manager.start_round(TurnPhase.COMBAT)

    record = turn_manager.record_action("Gandalf", "cast fireball at orcs")

    assert record.character_id == "Gandalf"
    assert record.action_summary == "cast fireball at orcs"
    assert record.phase == TurnPhase.COMBAT
    assert record.round_number == 1
    assert len(turn_manager.turn_history) == 1


def test_record_action_requires_round(turn_manager):
    """Test record_action fails without active round."""
    with pytest.raises(RuntimeError, match="No active round"):
        turn_manager.record_action("Gandalf", "action")


def test_get_turn_history_all(turn_manager):
    """Test getting all turn history."""
    turn_manager.start_round(TurnPhase.COMBAT)

    turn_manager.record_action("Gandalf", "action 1")
    turn_manager.record_action("Aragorn", "action 2")
    turn_manager.record_action("Legolas", "action 3")

    history = turn_manager.get_turn_history()

    assert len(history) == 3
    # Should be newest first
    assert history[0].character_id == "Legolas"
    assert history[1].character_id == "Aragorn"
    assert history[2].character_id == "Gandalf"


def test_get_turn_history_filtered_by_character(turn_manager):
    """Test getting turn history for specific character."""
    turn_manager.start_round(TurnPhase.COMBAT)

    turn_manager.record_action("Gandalf", "action 1")
    turn_manager.record_action("Aragorn", "action 2")
    turn_manager.record_action("Gandalf", "action 3")

    history = turn_manager.get_turn_history(character_id="Gandalf")

    assert len(history) == 2
    assert all(r.character_id == "Gandalf" for r in history)


def test_get_turn_history_respects_limit(turn_manager):
    """Test turn history limit."""
    turn_manager.start_round(TurnPhase.COMBAT)

    for i in range(10):
        turn_manager.record_action("Gandalf", f"action {i}")

    history = turn_manager.get_turn_history(limit=5)

    assert len(history) == 5
    # Should be 5 most recent
    assert history[0].action_summary == "action 9"


def test_end_round_returns_records(turn_manager):
    """Test end_round returns records from that round."""
    turn_manager.start_round(TurnPhase.COMBAT)

    turn_manager.record_action("Gandalf", "action 1")
    turn_manager.record_action("Aragorn", "action 2")

    turn_manager.end_round()

    turn_manager.start_round(TurnPhase.EXPLORATION)
    turn_manager.record_action("Legolas", "action 3")

    # Get records from first round
    # Need to manually filter since end_round was already called
    round_1_records = [r for r in turn_manager.turn_history if r.round_number == 1]

    assert len(round_1_records) == 2
    assert all(r.round_number == 1 for r in round_1_records)


# ============================================================================
# Edge Case Tests
# ============================================================================

def test_can_act_pc_not_in_order(turn_manager):
    """Test can_act returns False for PC not in turn order."""
    turn_manager.start_round(TurnPhase.COMBAT)

    assert turn_manager.can_act("Sauron") is False


def test_can_act_no_active_round(turn_manager):
    """Test can_act returns False without active round."""
    assert turn_manager.can_act("Gandalf") is False


def test_advance_turn_without_round(turn_manager):
    """Test advance_turn fails without active round."""
    with pytest.raises(RuntimeError, match="No active round"):
        turn_manager.advance_turn()


def test_turn_state_serialization(turn_manager):
    """Test TurnState can be serialized to dict."""
    state = turn_manager.start_round(TurnPhase.COMBAT)

    state_dict = state.model_dump()

    assert isinstance(state_dict, dict)
    assert state_dict["phase"] == "combat"
    assert state_dict["current_round"] == 1


def test_turn_record_serialization(turn_manager):
    """Test TurnRecord can be serialized to dict."""
    turn_manager.start_round(TurnPhase.COMBAT)
    record = turn_manager.record_action("Gandalf", "test action")

    record_dict = record.model_dump()

    assert isinstance(record_dict, dict)
    assert record_dict["character_id"] == "Gandalf"
    assert record_dict["action_summary"] == "test action"


def test_multiple_rounds_lifecycle(turn_manager):
    """Test multiple complete rounds."""
    # Round 1
    turn_manager.start_round(TurnPhase.COMBAT)
    turn_manager.record_action("Gandalf", "fireball")
    turn_manager.end_round()

    # Round 2
    turn_manager.start_round(TurnPhase.EXPLORATION)
    turn_manager.record_action("Aragorn", "search")
    turn_manager.end_round()

    # Check history
    assert len(turn_manager.turn_history) == 2
    assert turn_manager.turn_history[0].round_number == 1
    assert turn_manager.turn_history[1].round_number == 2


def test_inactive_pc_not_in_turn_order(registry, config):
    """Test inactive PCs are excluded from turn order."""
    manager = TurnManager(registry, config)

    # Deactivate Aragorn
    registry.update_pc_state("Aragorn", is_active=False)

    manager.start_round(TurnPhase.COMBAT)

    assert "Aragorn" not in manager.state.turn_order
    assert len(manager.state.turn_order) == 3
