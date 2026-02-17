"""
Tests for combat turn coordination in Party Mode.

Covers:
- get_combat_state() for turn-based and simultaneous modes
- is_players_turn() convenience wrapper
- _build_initiative_list() character data integration
- Turn gating in PartyServer._check_turn_gate()
- Combat lifecycle: start → turn advance → end
"""

from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from dm20_protocol.claudmaster.turn_manager import (
    SimultaneousAction,
    TurnDistribution,
    TurnManager,
    TurnPhase,
    TurnState,
)
from dm20_protocol.party.bridge import (
    _build_initiative_list,
    get_combat_state,
    is_players_turn,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_turn_manager(
    phase: TurnPhase = TurnPhase.COMBAT,
    distribution: TurnDistribution = TurnDistribution.ROUND_ROBIN,
    current_pc: str = "thorin",
    turn_order: list[str] | None = None,
    current_round: int = 1,
    initiatives: dict[str, int] | None = None,
    simultaneous_queue: list[SimultaneousAction] | None = None,
) -> MagicMock:
    """Build a mock TurnManager with the given combat state."""
    if turn_order is None:
        turn_order = ["thorin", "elara", "goblin_1"]

    state = TurnState(
        phase=phase,
        current_round=current_round,
        current_pc_id=current_pc,
        turn_order=turn_order,
        distribution_mode=distribution,
    )

    tm = MagicMock(spec=TurnManager)
    tm.state = state
    tm.get_current_turn.return_value = current_pc
    tm._combat_initiatives = initiatives or {
        "thorin": 18, "elara": 12, "goblin_1": 15
    }
    tm._simultaneous_queue = simultaneous_queue or []

    # can_act delegates to real logic for turn-based
    def _can_act(pc_id: str) -> bool:
        if state.distribution_mode == TurnDistribution.FREE_FORM:
            return True
        return pc_id == state.current_pc_id

    tm.can_act.side_effect = _can_act
    return tm


def _make_storage(*characters: dict) -> MagicMock:
    """Build a mock DnDStorage that returns character data by ID."""
    storage = MagicMock()

    char_map = {}
    for c in characters:
        mock_char = MagicMock()
        mock_char.name = c.get("name", c["id"])
        mock_char.hit_points_current = c.get("hp", 45)
        mock_char.hit_points_max = c.get("max_hp", 52)
        mock_char.armor_class = c.get("ac", 18)
        mock_char.conditions = c.get("conditions", [])
        char_map[c["id"]] = mock_char

    def _get_char(char_id: str):
        return char_map.get(char_id)

    storage.get_character.side_effect = _get_char
    return storage


# ---------------------------------------------------------------------------
# get_combat_state — Turn-based mode
# ---------------------------------------------------------------------------

class TestGetCombatStateTurnBased:
    """Tests for get_combat_state in turn-based mode."""

    def test_returns_active_state(self) -> None:
        tm = _make_turn_manager()
        storage = _make_storage(
            {"id": "thorin", "name": "Thorin", "hp": 45, "max_hp": 52, "ac": 18},
            {"id": "elara", "name": "Elara", "hp": 32, "max_hp": 32, "ac": 15},
        )

        result = get_combat_state("thorin", tm, storage)
        assert result is not None
        data = result["data"]
        assert data["active"] is True
        assert data["mode"] == "turn_based"
        assert data["current_turn"] == "thorin"
        assert data["round"] == 1

    def test_your_turn_true_for_active_player(self) -> None:
        tm = _make_turn_manager(current_pc="thorin")
        storage = _make_storage()

        result = get_combat_state("thorin", tm, storage)
        assert result["data"]["your_turn"] is True

    def test_your_turn_false_for_other_player(self) -> None:
        tm = _make_turn_manager(current_pc="thorin")
        storage = _make_storage()

        result = get_combat_state("elara", tm, storage)
        assert result["data"]["your_turn"] is False

    def test_initiative_list_ordered(self) -> None:
        tm = _make_turn_manager(turn_order=["thorin", "goblin_1", "elara"])
        storage = _make_storage(
            {"id": "thorin", "name": "Thorin"},
            {"id": "goblin_1", "name": "Goblin Archer"},
            {"id": "elara", "name": "Elara"},
        )

        result = get_combat_state("thorin", tm, storage)
        ids = [e["id"] for e in result["data"]["initiative"]]
        assert ids == ["thorin", "goblin_1", "elara"]

    def test_initiative_entries_have_stats(self) -> None:
        tm = _make_turn_manager()
        storage = _make_storage(
            {"id": "thorin", "name": "Thorin", "hp": 45, "max_hp": 52, "ac": 18, "conditions": ["poisoned"]},
        )

        result = get_combat_state("thorin", tm, storage)
        entry = result["data"]["initiative"][0]
        assert entry["name"] == "Thorin"
        assert entry["hp"] == 45
        assert entry["max_hp"] == 52
        assert entry["ac"] == 18
        assert entry["conditions"] == ["poisoned"]
        assert entry["initiative"] == 18

    def test_round_number_preserved(self) -> None:
        tm = _make_turn_manager(current_round=5)
        storage = _make_storage()

        result = get_combat_state("thorin", tm, storage)
        assert result["data"]["round"] == 5


# ---------------------------------------------------------------------------
# get_combat_state — No active combat
# ---------------------------------------------------------------------------

class TestGetCombatStateInactive:
    """Tests for get_combat_state when no combat is active."""

    def test_no_state_returns_inactive(self) -> None:
        tm = MagicMock(spec=TurnManager)
        tm.state = None
        storage = _make_storage()

        result = get_combat_state("thorin", tm, storage)
        assert result["data"]["active"] is False

    def test_exploration_phase_returns_inactive(self) -> None:
        tm = _make_turn_manager(phase=TurnPhase.EXPLORATION)
        storage = _make_storage()

        result = get_combat_state("thorin", tm, storage)
        assert result["data"]["active"] is False

    def test_roleplay_phase_returns_inactive(self) -> None:
        tm = _make_turn_manager(phase=TurnPhase.ROLEPLAY)
        storage = _make_storage()

        result = get_combat_state("thorin", tm, storage)
        assert result["data"]["active"] is False


# ---------------------------------------------------------------------------
# get_combat_state — Simultaneous mode
# ---------------------------------------------------------------------------

class TestGetCombatStateSimultaneous:
    """Tests for simultaneous combat mode."""

    def test_simultaneous_mode_detected(self) -> None:
        queue = [SimultaneousAction(pc_id="elara", action="DEX save")]
        tm = _make_turn_manager(
            distribution=TurnDistribution.FREE_FORM,
            current_pc=None,
            simultaneous_queue=queue,
        )
        storage = _make_storage()

        result = get_combat_state("thorin", tm, storage)
        assert result["data"]["mode"] == "simultaneous"
        assert result["data"]["active"] is True

    def test_submitted_and_waiting_lists(self) -> None:
        queue = [SimultaneousAction(pc_id="elara", action="DEX save")]
        tm = _make_turn_manager(
            distribution=TurnDistribution.FREE_FORM,
            current_pc=None,
            turn_order=["thorin", "elara", "goblin_1"],
            simultaneous_queue=queue,
        )
        storage = _make_storage()

        result = get_combat_state("thorin", tm, storage)
        data = result["data"]
        assert "elara" in data["submitted"]
        assert "thorin" in data["waiting_for"]
        assert "goblin_1" in data["waiting_for"]

    def test_simultaneous_has_timeout(self) -> None:
        queue = [SimultaneousAction(pc_id="elara", action="DEX save")]
        tm = _make_turn_manager(
            distribution=TurnDistribution.FREE_FORM,
            current_pc=None,
            simultaneous_queue=queue,
        )
        storage = _make_storage()

        result = get_combat_state("thorin", tm, storage)
        assert result["data"]["timeout_seconds"] == 300


# ---------------------------------------------------------------------------
# is_players_turn
# ---------------------------------------------------------------------------

class TestIsPlayersTurn:
    """Tests for is_players_turn wrapper."""

    def test_active_player_can_act(self) -> None:
        tm = _make_turn_manager(current_pc="thorin")
        assert is_players_turn("thorin", tm) is True

    def test_other_player_cannot_act(self) -> None:
        tm = _make_turn_manager(current_pc="thorin")
        assert is_players_turn("elara", tm) is False

    def test_free_form_everyone_can_act(self) -> None:
        tm = _make_turn_manager(
            distribution=TurnDistribution.FREE_FORM,
            current_pc=None,
        )
        assert is_players_turn("thorin", tm) is True
        assert is_players_turn("elara", tm) is True


# ---------------------------------------------------------------------------
# _build_initiative_list
# ---------------------------------------------------------------------------

class TestBuildInitiativeList:
    """Tests for _build_initiative_list helper."""

    def test_includes_character_data(self) -> None:
        storage = _make_storage(
            {"id": "thorin", "name": "Thorin", "hp": 45, "max_hp": 52, "ac": 18, "conditions": []},
        )
        initiatives = {"thorin": 18}

        result = _build_initiative_list(["thorin"], initiatives, storage)
        assert len(result) == 1
        assert result[0]["name"] == "Thorin"
        assert result[0]["initiative"] == 18

    def test_missing_character_uses_defaults(self) -> None:
        storage = _make_storage()  # No characters
        initiatives = {"goblin_1": 15}

        result = _build_initiative_list(["goblin_1"], initiatives, storage)
        assert result[0]["name"] == "goblin_1"
        assert result[0]["hp"] == 0
        assert result[0]["ac"] == 10

    def test_preserves_turn_order(self) -> None:
        storage = _make_storage()
        initiatives = {"a": 5, "b": 20, "c": 10}

        result = _build_initiative_list(["b", "c", "a"], initiatives, storage)
        ids = [e["id"] for e in result]
        assert ids == ["b", "c", "a"]


# ---------------------------------------------------------------------------
# Turn gating — _check_turn_gate
# ---------------------------------------------------------------------------

class TestCheckTurnGate:
    """Tests for PartyServer._check_turn_gate."""

    def _make_server_with_turn_manager(self, tm: MagicMock) -> MagicMock:
        """Create a minimal mock PartyServer with _check_turn_gate."""
        from dm20_protocol.party.server import PartyServer

        server = MagicMock(spec=PartyServer)
        server.turn_manager = tm
        # Bind the real method
        server._check_turn_gate = PartyServer._check_turn_gate.__get__(server)
        return server

    def test_no_turn_manager_allows_action(self) -> None:
        server = self._make_server_with_turn_manager(None)
        assert server._check_turn_gate("thorin") is None

    def test_no_active_round_allows_action(self) -> None:
        tm = MagicMock(spec=TurnManager)
        tm.state = None
        server = self._make_server_with_turn_manager(tm)
        assert server._check_turn_gate("thorin") is None

    def test_exploration_phase_allows_action(self) -> None:
        tm = _make_turn_manager(phase=TurnPhase.EXPLORATION)
        server = self._make_server_with_turn_manager(tm)
        assert server._check_turn_gate("thorin") is None

    def test_combat_active_player_allowed(self) -> None:
        tm = _make_turn_manager(current_pc="thorin")
        server = self._make_server_with_turn_manager(tm)
        assert server._check_turn_gate("thorin") is None

    def test_combat_other_player_blocked(self) -> None:
        tm = _make_turn_manager(current_pc="thorin")
        server = self._make_server_with_turn_manager(tm)
        result = server._check_turn_gate("elara")
        assert result is not None
        assert "thorin" in result.lower()

    def test_free_form_allows_everyone(self) -> None:
        tm = _make_turn_manager(
            distribution=TurnDistribution.FREE_FORM,
            current_pc=None,
        )
        server = self._make_server_with_turn_manager(tm)
        assert server._check_turn_gate("thorin") is None
        assert server._check_turn_gate("elara") is None


# ---------------------------------------------------------------------------
# Combat lifecycle integration
# ---------------------------------------------------------------------------

class TestCombatLifecycle:
    """Integration tests for combat start → turns → end cycle."""

    def test_combat_start_shows_active(self) -> None:
        tm = _make_turn_manager(current_pc="thorin", current_round=1)
        storage = _make_storage(
            {"id": "thorin", "name": "Thorin"},
            {"id": "elara", "name": "Elara"},
        )

        state = get_combat_state("thorin", tm, storage)
        assert state["data"]["active"] is True
        assert state["data"]["your_turn"] is True

    def test_turn_advance_changes_active_player(self) -> None:
        # Simulate: first it's thorin's turn, then elara's
        tm1 = _make_turn_manager(current_pc="thorin")
        tm2 = _make_turn_manager(current_pc="elara")
        storage = _make_storage()

        state1 = get_combat_state("elara", tm1, storage)
        assert state1["data"]["your_turn"] is False

        state2 = get_combat_state("elara", tm2, storage)
        assert state2["data"]["your_turn"] is True

    def test_combat_end_shows_inactive(self) -> None:
        tm = MagicMock(spec=TurnManager)
        tm.state = None
        storage = _make_storage()

        state = get_combat_state("thorin", tm, storage)
        assert state["data"]["active"] is False

    def test_full_round_cycle(self) -> None:
        """Simulate a complete round: thorin → elara → end."""
        storage = _make_storage(
            {"id": "thorin", "name": "Thorin"},
            {"id": "elara", "name": "Elara"},
        )

        # Round start: Thorin's turn
        tm = _make_turn_manager(
            current_pc="thorin",
            turn_order=["thorin", "elara"],
            current_round=1,
        )

        s1 = get_combat_state("thorin", tm, storage)
        assert s1["data"]["your_turn"] is True
        s1b = get_combat_state("elara", tm, storage)
        assert s1b["data"]["your_turn"] is False

        # Turn advance: Elara's turn
        tm.state.current_pc_id = "elara"
        tm.get_current_turn.return_value = "elara"
        tm.can_act.side_effect = lambda pc: pc == "elara"

        s2 = get_combat_state("elara", tm, storage)
        assert s2["data"]["your_turn"] is True
        s2b = get_combat_state("thorin", tm, storage)
        assert s2b["data"]["your_turn"] is False

        # Combat end
        tm.state = None

        s3 = get_combat_state("thorin", tm, storage)
        assert s3["data"]["active"] is False
