"""
Tests for ContextObserver (Issue #172).

Tests cover:
- Context classification (combat, exploration, dialogue, idle)
- Intensity settings (off, conservative, aggressive)
- Combat turn detection and callback invocation
- Context change notifications
- Player turn extraction from game state
- Edge cases (empty state, invalid intensity)
"""

from __future__ import annotations

import pytest

from dm20_protocol.prefetch.observer import (
    ContextObserver,
    GameContext,
    PlayerTurn,
)


# ============================================================================
# Context Classification Tests
# ============================================================================


class TestContextClassification:
    """Test game state context classification."""

    def test_combat_detected_from_combat_active(self):
        """Test combat detected when combat_active is True."""
        observer = ContextObserver(intensity="conservative")

        game_state = {"combat_active": True, "current_round": 3}
        context = observer.on_state_change(game_state)

        assert context == GameContext.COMBAT

    def test_combat_detected_from_in_combat(self):
        """Test combat detected from in_combat key."""
        observer = ContextObserver(intensity="conservative")

        game_state = {"in_combat": True}
        context = observer.on_state_change(game_state)

        assert context == GameContext.COMBAT

    def test_combat_detected_from_initiative_order(self):
        """Test combat detected from initiative_order."""
        observer = ContextObserver(intensity="conservative")

        game_state = {"initiative_order": ["Goblin", "Fighter", "Wizard"]}
        context = observer.on_state_change(game_state)

        assert context == GameContext.COMBAT

    def test_combat_not_detected_when_false(self):
        """Test combat not detected when indicator is False."""
        observer = ContextObserver(intensity="conservative")

        game_state = {"combat_active": False}
        context = observer.on_state_change(game_state)

        assert context == GameContext.IDLE

    def test_exploration_detected(self):
        """Test exploration context detected."""
        observer = ContextObserver(intensity="aggressive")

        game_state = {"exploring": True, "current_location": "Dark Forest"}
        context = observer.on_state_change(game_state)

        assert context == GameContext.EXPLORATION

    def test_dialogue_detected(self):
        """Test dialogue context detected."""
        observer = ContextObserver(intensity="aggressive")

        game_state = {"dialogue_active": True, "speaking_npc": "Elrond"}
        context = observer.on_state_change(game_state)

        assert context == GameContext.DIALOGUE

    def test_idle_with_empty_state(self):
        """Test idle context with empty game state."""
        observer = ContextObserver(intensity="conservative")

        context = observer.on_state_change({})
        assert context == GameContext.IDLE

    def test_combat_takes_priority_over_exploration(self):
        """Test that combat context has higher priority."""
        observer = ContextObserver(intensity="aggressive")

        game_state = {
            "combat_active": True,
            "exploring": True,  # Both present
        }
        context = observer.on_state_change(game_state)

        assert context == GameContext.COMBAT

    def test_exploration_takes_priority_over_dialogue(self):
        """Test that exploration has higher priority than dialogue."""
        observer = ContextObserver(intensity="aggressive")

        game_state = {
            "exploring": True,
            "dialogue_active": True,
        }
        context = observer.on_state_change(game_state)

        assert context == GameContext.EXPLORATION


# ============================================================================
# Intensity Settings Tests
# ============================================================================


class TestIntensitySettings:
    """Test prefetch intensity configuration."""

    def test_default_intensity(self):
        """Test default intensity is conservative."""
        observer = ContextObserver()
        assert observer.intensity == "conservative"

    def test_off_intensity(self):
        """Test off intensity disables all context detection."""
        observer = ContextObserver(intensity="off")

        game_state = {"combat_active": True}
        context = observer.on_state_change(game_state)

        assert context == GameContext.IDLE

    def test_conservative_prefetches_combat_only(self):
        """Test conservative intensity only prefetches in combat."""
        observer = ContextObserver(intensity="conservative")

        assert observer.should_prefetch(GameContext.COMBAT) is True
        assert observer.should_prefetch(GameContext.EXPLORATION) is False
        assert observer.should_prefetch(GameContext.DIALOGUE) is False
        assert observer.should_prefetch(GameContext.IDLE) is False

    def test_aggressive_prefetches_combat_and_exploration(self):
        """Test aggressive intensity prefetches combat and exploration."""
        observer = ContextObserver(intensity="aggressive")

        assert observer.should_prefetch(GameContext.COMBAT) is True
        assert observer.should_prefetch(GameContext.EXPLORATION) is True
        assert observer.should_prefetch(GameContext.DIALOGUE) is False
        assert observer.should_prefetch(GameContext.IDLE) is False

    def test_off_never_prefetches(self):
        """Test off intensity never prefetches."""
        observer = ContextObserver(intensity="off")

        assert observer.should_prefetch(GameContext.COMBAT) is False
        assert observer.should_prefetch(GameContext.EXPLORATION) is False

    def test_intensity_setter(self):
        """Test changing intensity at runtime."""
        observer = ContextObserver(intensity="conservative")

        observer.intensity = "aggressive"
        assert observer.intensity == "aggressive"

    def test_invalid_intensity_raises(self):
        """Test that invalid intensity raises ValueError."""
        with pytest.raises(ValueError, match="Invalid prefetch intensity"):
            ContextObserver(intensity="invalid")

    def test_invalid_intensity_setter_raises(self):
        """Test that setting invalid intensity raises ValueError."""
        observer = ContextObserver()

        with pytest.raises(ValueError, match="Invalid prefetch intensity"):
            observer.intensity = "turbo"

    def test_should_prefetch_uses_current_context(self):
        """Test should_prefetch uses current context when none given."""
        observer = ContextObserver(intensity="conservative")

        observer.on_state_change({"combat_active": True})
        assert observer.should_prefetch() is True

        observer.on_state_change({})
        assert observer.should_prefetch() is False


# ============================================================================
# Context Change Callback Tests
# ============================================================================


class TestContextChangeCallbacks:
    """Test context change notification system."""

    def test_context_change_callback_invoked(self):
        """Test that context change callbacks are invoked."""
        observer = ContextObserver(intensity="conservative")

        changes = []
        observer.on_context_change(lambda old, new: changes.append((old, new)))

        observer.on_state_change({"combat_active": True})

        assert len(changes) == 1
        assert changes[0] == (GameContext.IDLE, GameContext.COMBAT)

    def test_no_callback_on_same_context(self):
        """Test that callback is not invoked when context doesn't change."""
        observer = ContextObserver(intensity="conservative")

        changes = []
        observer.on_context_change(lambda old, new: changes.append((old, new)))

        observer.on_state_change({"combat_active": True})
        observer.on_state_change({"combat_active": True})  # Same context

        assert len(changes) == 1  # Only first change

    def test_multiple_callbacks_invoked(self):
        """Test multiple registered callbacks are all invoked."""
        observer = ContextObserver(intensity="conservative")

        results_a = []
        results_b = []

        observer.on_context_change(lambda old, new: results_a.append(new))
        observer.on_context_change(lambda old, new: results_b.append(new))

        observer.on_state_change({"combat_active": True})

        assert results_a == [GameContext.COMBAT]
        assert results_b == [GameContext.COMBAT]

    def test_callback_error_does_not_crash(self):
        """Test that a callback error doesn't crash the observer."""
        observer = ContextObserver(intensity="conservative")

        def bad_callback(old, new):
            raise RuntimeError("Callback failed")

        observer.on_context_change(bad_callback)

        # Should not raise
        context = observer.on_state_change({"combat_active": True})
        assert context == GameContext.COMBAT


# ============================================================================
# Combat Turn Detection Tests
# ============================================================================


class TestCombatTurnDetection:
    """Test combat turn detection and callback invocation."""

    def test_combat_turn_callback_invoked(self):
        """Test combat turn callback is invoked on turn change."""
        observer = ContextObserver(intensity="conservative")

        turns = []
        observer.on_combat_turn(
            lambda state, turn: turns.append(turn.character_name)
        )

        game_state = {
            "combat_active": True,
            "current_round": 1,
            "current_turn": {
                "character_name": "Aragorn",
                "class": "ranger",
                "weapon": "longsword",
            },
        }
        observer.on_state_change(game_state)

        assert len(turns) == 1
        assert turns[0] == "Aragorn"

    def test_no_callback_on_same_turn(self):
        """Test callback not invoked when turn hasn't changed."""
        observer = ContextObserver(intensity="conservative")

        turns = []
        observer.on_combat_turn(lambda state, turn: turns.append(turn))

        game_state = {
            "combat_active": True,
            "current_turn": {"character_name": "Aragorn"},
        }

        observer.on_state_change(game_state)
        observer.on_state_change(game_state)  # Same turn

        assert len(turns) == 1

    def test_callback_on_new_turn(self):
        """Test callback invoked when turn changes."""
        observer = ContextObserver(intensity="conservative")

        turns = []
        observer.on_combat_turn(lambda state, turn: turns.append(turn.character_name))

        # First turn
        observer.on_state_change({
            "combat_active": True,
            "current_turn": {"character_name": "Aragorn"},
        })

        # Second turn
        observer.on_state_change({
            "combat_active": True,
            "current_turn": {"character_name": "Legolas"},
        })

        assert turns == ["Aragorn", "Legolas"]

    def test_no_callback_without_turn_data(self):
        """Test no callback when combat state lacks turn data."""
        observer = ContextObserver(intensity="conservative")

        turns = []
        observer.on_combat_turn(lambda state, turn: turns.append(turn))

        observer.on_state_change({"combat_active": True})

        assert len(turns) == 0

    def test_combat_turn_callback_error_handled(self):
        """Test that callback errors don't crash the observer."""
        observer = ContextObserver(intensity="conservative")

        def bad_callback(state, turn):
            raise RuntimeError("Callback failed")

        observer.on_combat_turn(bad_callback)

        # Should not raise
        observer.on_state_change({
            "combat_active": True,
            "current_turn": {"character_name": "Gimli"},
        })


# ============================================================================
# Player Turn Extraction Tests
# ============================================================================


class TestPlayerTurnExtraction:
    """Test extraction of player turn data from game state."""

    def test_extract_full_turn_data(self):
        """Test extracting complete turn data."""
        observer = ContextObserver()

        game_state = {
            "current_round": 3,
            "current_turn": {
                "character_name": "Gandalf",
                "class": "wizard",
                "weapon": "staff",
                "action_type": "spell",
                "target": {
                    "name": "Balrog",
                    "ac": 18,
                },
            },
        }

        turn = observer.extract_player_turn(game_state)

        assert turn is not None
        assert turn.character_name == "Gandalf"
        assert turn.character_class == "wizard"
        assert turn.weapon == "staff"
        assert turn.action_type == "spell"
        assert turn.target_name == "Balrog"
        assert turn.target_ac == 18
        assert turn.turn_id == "round_3_gandalf"

    def test_extract_minimal_turn_data(self):
        """Test extracting turn with minimal data."""
        observer = ContextObserver()

        game_state = {
            "current_turn": {
                "character_name": "Fighter",
            },
        }

        turn = observer.extract_player_turn(game_state)

        assert turn is not None
        assert turn.character_name == "Fighter"
        assert turn.character_class == "fighter"  # Default
        assert turn.target_name == "enemy"  # Default

    def test_extract_returns_none_without_turn(self):
        """Test extraction returns None when no turn data."""
        observer = ContextObserver()

        turn = observer.extract_player_turn({})
        assert turn is None

    def test_extract_returns_none_empty_turn(self):
        """Test extraction returns None for empty turn dict."""
        observer = ContextObserver()

        turn = observer.extract_player_turn({"current_turn": {}})
        assert turn is None

    def test_extract_with_name_key(self):
        """Test extraction with 'name' key instead of 'character_name'."""
        observer = ContextObserver()

        game_state = {
            "current_turn": {"name": "Rogue"},
        }

        turn = observer.extract_player_turn(game_state)

        assert turn is not None
        assert turn.character_name == "Rogue"

    def test_extract_with_string_target(self):
        """Test extraction with a string target instead of dict."""
        observer = ContextObserver()

        game_state = {
            "current_turn": {
                "character_name": "Archer",
                "target": "Dragon",
            },
        }

        turn = observer.extract_player_turn(game_state)

        assert turn is not None
        assert turn.target_name == "Dragon"

    def test_turn_id_format(self):
        """Test that turn_id is formatted correctly."""
        observer = ContextObserver()

        game_state = {
            "current_round": 5,
            "current_turn": {"character_name": "Sir Lancelot"},
        }

        turn = observer.extract_player_turn(game_state)
        assert turn.turn_id == "round_5_sir_lancelot"

    def test_extract_with_alternative_turn_key(self):
        """Test extraction with active_turn key."""
        observer = ContextObserver()

        game_state = {
            "active_turn": {"character_name": "Paladin"},
        }

        turn = observer.extract_player_turn(game_state)
        assert turn is not None
        assert turn.character_name == "Paladin"


# ============================================================================
# Current Context Property Tests
# ============================================================================


class TestCurrentContext:
    """Test the current_context property."""

    def test_initial_context_is_idle(self):
        """Test that initial context is IDLE."""
        observer = ContextObserver()
        assert observer.current_context == GameContext.IDLE

    def test_context_updates_on_state_change(self):
        """Test that context property reflects latest state."""
        observer = ContextObserver(intensity="conservative")

        observer.on_state_change({"combat_active": True})
        assert observer.current_context == GameContext.COMBAT

        observer.on_state_change({})
        assert observer.current_context == GameContext.IDLE
