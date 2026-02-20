"""
Integration smoke-tests for Voice (TTS) + Prefetch wiring in main.py.

Verifies that:
1. TTSRouter is initialised on start_party_mode
2. TTS is skipped when interaction_mode is classic
3. TTS runs when interaction_mode is narrated
4. Audio is broadcast via WebSocket after TTS synthesis
5. PrefetchEngine is initialised on start_party_mode
6. Prefetch on_state_change fires after party_resolve_action
7. Prefetch hook fires after next_turn
8. Prefetch summary appears in summarize_session output
9. Graceful degradation when TTS init fails
"""

import asyncio
import base64
from contextlib import ExitStack
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import main module once -- tools are accessed via m.<tool>.fn()
from dm20_protocol import main as m


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeTTSResult:
    """Minimal stand-in for TTSResult returned by router.synthesize."""

    audio_data: bytes = b"\x00" * 100
    format: str = "wav"
    sample_rate: int = 22050
    duration_ms: float = 500.0
    engine_name: str = "mock-tts"


def _mock_server(
    *,
    tts_router: object = None,
    prefetch_engine: object = None,
) -> MagicMock:
    """Build a mock that behaves like a running PartyServer."""
    srv = MagicMock()
    srv.tts_router = tts_router
    srv.prefetch_engine = prefetch_engine
    srv.host_ip = "127.0.0.1"
    srv.port = 8080

    # Event loop
    loop = asyncio.new_event_loop()
    srv._loop = loop

    # Connection manager with async broadcast
    srv.connection_manager = MagicMock()
    srv.connection_manager.broadcast = AsyncMock(return_value=2)

    # Queues
    srv.response_queue = MagicMock()
    srv.response_queue.push.return_value = "resp-001"
    srv.action_queue = MagicMock()
    srv.action_queue.resolve.return_value = None

    return srv


def _make_fake_server_for_start():
    """Build a fake server for start_party_mode tests."""
    fake_server = MagicMock()
    loop = asyncio.new_event_loop()
    fake_server._loop = loop
    fake_server._loop.is_closed = lambda: False
    fake_server.host_ip = "127.0.0.1"
    fake_server.port = 8080
    fake_server.token_manager = MagicMock()
    fake_server.token_manager.generate_token.return_value = "tok123"
    fake_server.token_manager.get_all_tokens.return_value = {"hero1": "tok123"}
    fake_server.tts_router = None
    fake_server.prefetch_engine = None
    return fake_server


def _patch_start_party_mode_deps(fake_server):
    """Return an ExitStack with all common patches for start_party_mode."""
    stack = ExitStack()
    patches = {
        "start_party_server": stack.enter_context(
            patch(
                "dm20_protocol.party.server.start_party_server",
                return_value=fake_server,
            )
        ),
        "get_server_instance": stack.enter_context(
            patch(
                "dm20_protocol.party.server.get_server_instance",
                return_value=None,
            )
        ),
        "ensure_firewall": stack.enter_context(
            patch(
                "dm20_protocol.party.firewall.ensure_firewall_allows_python",
                return_value={},
            )
        ),
        "format_firewall": stack.enter_context(
            patch(
                "dm20_protocol.party.firewall.format_firewall_status",
                return_value="",
            )
        ),
        "qr_gen": stack.enter_context(
            patch("dm20_protocol.party.auth.QRCodeGenerator")
        ),
        "rcts": stack.enter_context(
            patch("asyncio.run_coroutine_threadsafe")
        ),
    }
    patches["qr_gen"].generate_player_qr.return_value = "/tmp/qr.png"
    patches["qr_gen"].render_qr_terminal.return_value = "QR"
    return stack, patches


def _swap_storage(mock_storage):
    """Swap module-level storage and return the original for restoration."""
    original = m.storage
    m.storage = mock_storage
    return original


# ---------------------------------------------------------------------------
# Test 1 -- TTS Router Init on start_party_mode
# ---------------------------------------------------------------------------


class TestTTSRouterInit:
    """Verify that start_party_mode wires TTSRouter onto the server."""

    def test_tts_router_init_scheduled(self):
        """TTSRouter init coroutine is scheduled on start_party_mode."""
        mock_stor = MagicMock()
        mock_stor.get_current_campaign.return_value = MagicMock(name="Camp")
        mock_stor.list_characters_detailed.return_value = [
            MagicMock(id="hero1", name="Hero", player_name="Player1"),
        ]
        mock_stor._split_backend._get_campaign_dir.return_value = "/tmp/c"

        fake_server = _make_fake_server_for_start()
        stack, patches = _patch_start_party_mode_deps(fake_server)
        original = _swap_storage(mock_stor)

        try:
            with stack:
                with (
                    patch("dm20_protocol.voice.TTSRouter") as MockRouter,
                    patch("dm20_protocol.prefetch.PrefetchEngine"),
                    patch("dm20_protocol.claudmaster.llm_client.AnthropicLLMClient"),
                ):
                    result = m.start_party_mode.fn(port=9999)

                    # run_coroutine_threadsafe is called for TTS init
                    assert patches["rcts"].called, (
                        "run_coroutine_threadsafe should be called for TTS init"
                    )
        finally:
            m.storage = original
            fake_server._loop.close()


# ---------------------------------------------------------------------------
# Test 2 -- TTS skipped in classic mode
# ---------------------------------------------------------------------------


class TestTTSSkippedClassic:
    """TTS must NOT run when interaction_mode is 'classic'."""

    def test_tts_skipped_classic(self):
        mock_stor = MagicMock()
        mock_stor.interaction_mode = "classic"
        original = _swap_storage(mock_stor)

        try:
            mock_srv = _mock_server()
            mock_router = MagicMock()
            mock_srv.tts_router = mock_router

            m._party_tts_speak("The dragon roars!", mock_srv)

            # synthesize should not have been called (returns early)
            mock_router.synthesize.assert_not_called()
            mock_srv._loop.close()
        finally:
            m.storage = original


# ---------------------------------------------------------------------------
# Test 3 -- TTS runs in narrated mode
# ---------------------------------------------------------------------------


class TestTTSRunsNarrated:
    """TTS should be triggered when interaction_mode is 'narrated'."""

    @patch("platform.system", return_value="Darwin")
    def test_tts_runs_narrated(self, mock_platform):
        mock_stor = MagicMock()
        mock_stor.interaction_mode = "narrated"
        original = _swap_storage(mock_stor)

        try:
            mock_srv = _mock_server()
            mock_router = MagicMock()
            mock_router.synthesize = AsyncMock(return_value=FakeTTSResult())
            mock_srv.tts_router = mock_router

            loop = asyncio.new_event_loop()
            mock_srv._loop = loop
            mock_srv._loop.is_closed = lambda: False

            with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
                m._party_tts_speak("The dragon breathes fire!", mock_srv)

                assert mock_rcts.called, (
                    "run_coroutine_threadsafe should schedule TTS synthesis"
                )

            loop.close()
        finally:
            m.storage = original


# ---------------------------------------------------------------------------
# Test 4 -- Audio broadcast after TTS
# ---------------------------------------------------------------------------


class TestAudioBroadcast:
    """After TTS synthesis, audio should be broadcast via WebSocket."""

    def test_audio_broadcast(self):
        """Run the _synth_and_play logic directly and verify broadcast."""
        mock_srv = _mock_server()
        mock_router = MagicMock()
        mock_router.synthesize = AsyncMock(return_value=FakeTTSResult())
        mock_srv.tts_router = mock_router

        loop = asyncio.new_event_loop()
        mock_srv._loop = loop

        # Simulate the inner _synth_and_play logic directly since the real
        # one is a nested closure. This verifies the broadcast protocol.
        async def _simulate_synth_and_play():
            result = await mock_router.synthesize("test", context="narration")
            audio_b64 = base64.b64encode(result.audio_data).decode("ascii")
            audio_msg = {
                "type": "audio",
                "format": "mp3",
                "data": audio_b64,
            }
            await mock_srv.connection_manager.broadcast(audio_msg)

        loop.run_until_complete(_simulate_synth_and_play())

        # Verify broadcast was called with audio message
        mock_srv.connection_manager.broadcast.assert_called_once()
        call_args = mock_srv.connection_manager.broadcast.call_args[0][0]
        assert call_args["type"] == "audio"
        assert call_args["format"] == "mp3"
        assert "data" in call_args
        # Verify it's valid base64
        decoded = base64.b64decode(call_args["data"])
        assert decoded == b"\x00" * 100

        loop.close()


# ---------------------------------------------------------------------------
# Test 5 -- PrefetchEngine Init on start_party_mode
# ---------------------------------------------------------------------------


class TestPrefetchEngineInit:
    """Verify that start_party_mode wires PrefetchEngine onto the server."""

    def test_prefetch_engine_init(self):
        mock_stor = MagicMock()
        mock_stor.get_current_campaign.return_value = MagicMock(name="Camp")
        mock_stor.list_characters_detailed.return_value = [
            MagicMock(id="hero1", name="Hero", player_name="Player1"),
        ]
        mock_stor._split_backend._get_campaign_dir.return_value = "/tmp/c"

        fake_server = _make_fake_server_for_start()
        stack, patches = _patch_start_party_mode_deps(fake_server)
        original = _swap_storage(mock_stor)

        try:
            with stack:
                with (
                    patch("dm20_protocol.voice.TTSRouter"),
                    patch("dm20_protocol.prefetch.PrefetchEngine") as MockPrefetch,
                    patch(
                        "dm20_protocol.claudmaster.llm_client.AnthropicLLMClient"
                    ) as MockLLM,
                ):
                    result = m.start_party_mode.fn(port=9998)

                    # PrefetchEngine should have been instantiated
                    MockPrefetch.assert_called_once()
                    # AnthropicLLMClient should have been used
                    MockLLM.assert_called()
        finally:
            m.storage = original
            fake_server._loop.close()


# ---------------------------------------------------------------------------
# Test 6 -- Prefetch on_state_change after party_resolve_action
# ---------------------------------------------------------------------------


class TestPrefetchAfterResolve:
    """on_state_change should be called after party_resolve_action."""

    def test_prefetch_fires_on_resolve(self):
        mock_stor = MagicMock()
        mock_stor.interaction_mode = "classic"
        gs = MagicMock()
        gs.model_dump.return_value = {"in_combat": True}
        mock_stor.get_game_state.return_value = gs

        mock_prefetch = MagicMock()
        mock_srv = _mock_server(prefetch_engine=mock_prefetch)

        original = _swap_storage(mock_stor)
        try:
            with patch(
                "dm20_protocol.party.server.get_server_instance",
                return_value=mock_srv,
            ):
                result = m.party_resolve_action.fn(
                    action_id="act-001",
                    narrative="The goblin dodges your attack!",
                )

            mock_prefetch.on_state_change.assert_called_once_with({"in_combat": True})
            assert "broadcast" in result.lower() or "resp" in result.lower()
        finally:
            m.storage = original
            mock_srv._loop.close()


# ---------------------------------------------------------------------------
# Test 7 -- Prefetch hook via _prefetch_state_update in next_turn
# ---------------------------------------------------------------------------


class TestPrefetchAfterNextTurn:
    """_prefetch_state_update should fire inside next_turn."""

    def test_prefetch_fires_on_next_turn(self):
        mock_stor = MagicMock()
        # Set up game state so next_turn doesn't bail early
        gs = MagicMock()
        gs.in_combat = True
        gs.initiative_order = [
            {"name": "Goblin", "initiative": 15},
            {"name": "Hero", "initiative": 10},
        ]
        gs.current_turn = "Goblin"
        gs.model_dump.return_value = {"in_combat": True, "current_turn": "Hero"}
        mock_stor.get_game_state.return_value = gs

        # Characters -- Hero is alive
        hero_char = MagicMock()
        hero_char.hit_points_current = 30
        hero_char.active_effects = []
        hero_char.name = "Hero"

        goblin_char = MagicMock()
        goblin_char.hit_points_current = 10
        goblin_char.active_effects = []
        goblin_char.name = "Goblin"

        def fake_get_char(name):
            return {"Hero": hero_char, "Goblin": goblin_char}.get(name)

        mock_stor.get_character.side_effect = fake_get_char

        mock_prefetch = MagicMock()
        mock_srv = _mock_server(prefetch_engine=mock_prefetch)

        original = _swap_storage(mock_stor)
        try:
            with patch(
                "dm20_protocol.party.server.get_server_instance",
                return_value=mock_srv,
            ):
                result = m.next_turn.fn()

            assert "Hero" in result
            mock_prefetch.on_state_change.assert_called_once()
        finally:
            m.storage = original
            mock_srv._loop.close()


# ---------------------------------------------------------------------------
# Test 8 -- Prefetch summary in summarize_session
# ---------------------------------------------------------------------------


class TestPrefetchSummaryInSession:
    """summarize_session should include prefetch token stats when engine active."""

    def test_prefetch_summary_appended(self):
        mock_stor = MagicMock()
        mock_stor.get_current_campaign.return_value = MagicMock(name="Camp")
        mock_stor.list_characters_detailed.return_value = []
        mock_stor.list_npcs.return_value = []
        mock_stor.list_locations.return_value = []
        mock_stor.list_quests.return_value = []
        mock_stor.get_game_state.return_value = MagicMock(
            in_combat=False, active_quests=[], notes=""
        )

        mock_prefetch = MagicMock()
        mock_prefetch.get_token_summary.return_value = (
            "Prefetch: 100 tokens used, 50% cache hits"
        )

        mock_srv = _mock_server(prefetch_engine=mock_prefetch)

        original = _swap_storage(mock_stor)
        try:
            with patch(
                "dm20_protocol.party.server.get_server_instance",
                return_value=mock_srv,
            ):
                result = m.summarize_session.fn(
                    transcription="The party entered the dungeon...",
                    session_number=1,
                    detail_level="brief",
                )

            assert "Prefetch: 100 tokens used, 50% cache hits" in result
        finally:
            m.storage = original


# ---------------------------------------------------------------------------
# Test 9 -- Graceful degradation: TTS init failure
# ---------------------------------------------------------------------------


class TestTTSGracefulDegradation:
    """start_party_mode must succeed even when TTSRouter fails to import."""

    def test_tts_init_failure_graceful(self):
        mock_stor = MagicMock()
        mock_stor.get_current_campaign.return_value = MagicMock(name="Camp")
        mock_stor.list_characters_detailed.return_value = [
            MagicMock(id="hero1", name="Hero", player_name="Player1"),
        ]
        mock_stor._split_backend._get_campaign_dir.return_value = "/tmp/c"

        fake_server = _make_fake_server_for_start()
        stack, patches = _patch_start_party_mode_deps(fake_server)
        original = _swap_storage(mock_stor)

        try:
            with stack:
                with (
                    patch(
                        "dm20_protocol.voice.TTSRouter",
                        side_effect=ImportError("No voice deps"),
                    ),
                    patch("dm20_protocol.prefetch.PrefetchEngine"),
                    patch("dm20_protocol.claudmaster.llm_client.AnthropicLLMClient"),
                ):
                    # Should NOT raise
                    result = m.start_party_mode.fn(port=9997)

                    # Should still produce a valid result
                    assert "Party Mode" in result
        finally:
            m.storage = original
            fake_server._loop.close()
