"""
Tests for WebSocket real-time push (Task 152).

Tests broadcast_response filtering, reconnect replay, heartbeat
stale detection, and join/leave events.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dm20_protocol.party.bridge import format_response
from dm20_protocol.party.queue import ResponseQueue
from dm20_protocol.party.server import ConnectionManager
from dm20_protocol.permissions import PlayerRole

# Use anyio for async tests (compatible with pytest-anyio)
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    """Configure anyio to use asyncio backend."""
    return "asyncio"


class TestBroadcastResponse:
    """Tests for ConnectionManager.broadcast_response."""

    def _mock_resolver(self, role_map: dict[str, PlayerRole]) -> MagicMock:
        """Create a mock PermissionResolver with role mapping."""
        resolver = MagicMock()
        resolver.get_player_role.side_effect = lambda pid: role_map.get(pid, PlayerRole.PLAYER)
        return resolver

    async def test_broadcast_sends_to_all_players(self) -> None:
        """Test that broadcast_response sends to all connected players."""
        cm = ConnectionManager()

        ws1 = AsyncMock()
        ws2 = AsyncMock()

        # Manually add connections (bypass accept())
        cm._connections = {
            "thorin": {ws1},
            "legolas": {ws2},
        }

        resolver = self._mock_resolver({
            "thorin": PlayerRole.PLAYER,
            "legolas": PlayerRole.PLAYER,
        })

        response = {
            "id": "res_0001",
            "timestamp": "2026-02-17T20:00:00Z",
            "narrative": "The door opens.",
        }

        total = await cm.broadcast_response(response, resolver)
        assert total == 2
        assert ws1.send_json.called
        assert ws2.send_json.called

    async def test_broadcast_filters_private_per_player(self) -> None:
        """Test that private messages go only to the intended player."""
        cm = ConnectionManager()

        ws_thorin = AsyncMock()
        ws_legolas = AsyncMock()

        cm._connections = {
            "thorin": {ws_thorin},
            "legolas": {ws_legolas},
        }

        resolver = self._mock_resolver({
            "thorin": PlayerRole.PLAYER,
            "legolas": PlayerRole.PLAYER,
        })

        response = {
            "id": "res_0001",
            "timestamp": "2026-02-17T20:00:00Z",
            "narrative": "You see a chest.",
            "private": {"thorin": "You notice a trap"},
        }

        await cm.broadcast_response(response, resolver)

        # Check what thorin received
        thorin_msg = ws_thorin.send_json.call_args[0][0]
        assert "private" in thorin_msg or thorin_msg.get("content") == "You notice a trap"

        # Legolas should NOT have received private info
        legolas_msg = ws_legolas.send_json.call_args[0][0]
        assert legolas_msg.get("private") is None or "private" not in legolas_msg

    async def test_broadcast_strips_dm_only(self) -> None:
        """Test that dm_only content is stripped for non-DM players."""
        cm = ConnectionManager()

        ws_player = AsyncMock()
        ws_dm = AsyncMock()

        cm._connections = {
            "thorin": {ws_player},
            "dm_user": {ws_dm},
        }

        resolver = self._mock_resolver({
            "thorin": PlayerRole.PLAYER,
            "dm_user": PlayerRole.DM,
        })

        response = {
            "id": "res_0001",
            "timestamp": "2026-02-17T20:00:00Z",
            "narrative": "The NPC greets you.",
            "dm_only": "NPC is a spy",
        }

        await cm.broadcast_response(response, resolver)

        player_msg = ws_player.send_json.call_args[0][0]
        assert "dm_only" not in player_msg

    async def test_observer_gets_only_narrative(self) -> None:
        """Test that OBSERVER connections get only public narrative."""
        cm = ConnectionManager()

        ws_obs = AsyncMock()
        cm._connections = {"observer_1": {ws_obs}}

        resolver = self._mock_resolver({"observer_1": PlayerRole.OBSERVER})

        response = {
            "id": "res_0001",
            "timestamp": "2026-02-17T20:00:00Z",
            "narrative": "Combat!",
            "private": {"thorin": "secret"},
            "dm_only": "hidden",
        }

        await cm.broadcast_response(response, resolver)

        obs_msg = ws_obs.send_json.call_args[0][0]
        assert "private" not in obs_msg
        assert "dm_only" not in obs_msg

    async def test_multiple_tabs_all_receive(self) -> None:
        """Test that multiple tabs from same player all receive updates."""
        cm = ConnectionManager()

        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()

        cm._connections = {"thorin": {ws1, ws2, ws3}}

        resolver = self._mock_resolver({"thorin": PlayerRole.PLAYER})

        response = {
            "id": "res_0001",
            "timestamp": "2026-02-17T20:00:00Z",
            "narrative": "Hello",
        }

        total = await cm.broadcast_response(response, resolver)
        assert total == 3
        assert ws1.send_json.called
        assert ws2.send_json.called
        assert ws3.send_json.called


class TestReconnect:
    """Tests for reconnection with message replay."""

    async def test_handle_reconnect_replays_missed(self, tmp_path: Path) -> None:
        """Test that reconnecting player receives missed messages."""
        rq = ResponseQueue(tmp_path)
        rq.push({"narrative": "Message 1", "action_id": "act_0001"})
        ts_after_first = rq.get_all()[-1]["timestamp"]
        rq.push({"narrative": "Message 2", "action_id": "act_0002"})

        cm = ConnectionManager()
        ws = AsyncMock()
        cm._connections = {"thorin": {ws}}

        resolver = MagicMock()
        resolver.get_player_role.return_value = PlayerRole.PLAYER

        count = await cm.handle_reconnect(
            "thorin", ts_after_first, rq, resolver
        )

        assert count == 1
        # Should have received only the second message
        sent_msg = ws.send_json.call_args[0][0]
        assert "Message 2" in sent_msg.get("narrative", "")

    async def test_handle_reconnect_no_messages(self, tmp_path: Path) -> None:
        """Test reconnect with no missed messages."""
        rq = ResponseQueue(tmp_path)

        cm = ConnectionManager()
        ws = AsyncMock()
        cm._connections = {"thorin": {ws}}

        resolver = MagicMock()
        resolver.get_player_role.return_value = PlayerRole.PLAYER

        count = await cm.handle_reconnect("thorin", None, rq, resolver)
        # With since=None, gets all messages (0 in this case)
        assert count == 0


class TestHeartbeat:
    """Tests for heartbeat and stale connection detection."""

    def test_mark_pong_updates_timestamp(self) -> None:
        """Test that mark_pong updates the last pong time."""
        cm = ConnectionManager()
        cm.mark_pong("thorin")

        assert "thorin" in cm._last_pong
        assert time.time() - cm._last_pong["thorin"] < 1.0

    def test_stale_detection(self) -> None:
        """Test that stale connections are detected correctly."""
        cm = ConnectionManager()
        cm._connections = {"thorin": set(), "legolas": set()}

        # thorin ponged recently
        cm._last_pong["thorin"] = time.time()

        # legolas ponged 120 seconds ago
        cm._last_pong["legolas"] = time.time() - 120

        stale = cm.get_stale_players(timeout_seconds=60.0)
        assert "legolas" in stale
        assert "thorin" not in stale

    def test_no_pong_not_stale_initially(self) -> None:
        """Test that players without pong record are not immediately stale."""
        cm = ConnectionManager()
        cm._connections = {"thorin": set()}
        # No pong recorded yet — default is current time
        stale = cm.get_stale_players(timeout_seconds=60.0)
        assert "thorin" not in stale


class TestPermissionBoundary:
    """Cross-player privacy boundary tests."""

    async def test_100_messages_no_leakage(self) -> None:
        """Verify Player A never receives Player B's private content."""
        cm = ConnectionManager()

        ws_a = AsyncMock()
        ws_b = AsyncMock()
        cm._connections = {"player_a": {ws_a}, "player_b": {ws_b}}

        resolver = MagicMock()
        resolver.get_player_role.return_value = PlayerRole.PLAYER

        for i in range(100):
            response = {
                "id": f"res_{i:04d}",
                "timestamp": f"2026-02-17T20:{i:02d}:00Z",
                "narrative": f"Public message {i}",
                "private": {
                    "player_a": f"Secret for A #{i}",
                    "player_b": f"Secret for B #{i}",
                },
            }
            await cm.broadcast_response(response, resolver)

        # Check all messages sent to player_a
        for call in ws_a.send_json.call_args_list:
            msg = call[0][0]
            content = str(msg)
            assert "Secret for B" not in content, \
                f"Player A received Player B's secret: {msg}"

        # Check all messages sent to player_b
        for call in ws_b.send_json.call_args_list:
            msg = call[0][0]
            content = str(msg)
            assert "Secret for A" not in content, \
                f"Player B received Player A's secret: {msg}"
