"""Tests for AudioStreamManager — chunking, sequencing, degradation."""

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dm20_protocol.voice.engines.base import AudioFormat, TTSResult, VoiceConfig
from dm20_protocol.voice.streaming import AudioStreamManager, DEFAULT_CHUNK_SIZE


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_router():
    router = AsyncMock()
    router.synthesize = AsyncMock(return_value=TTSResult(
        audio_data=b"\x00" * 10000,
        format=AudioFormat.WAV,
        sample_rate=24000,
        duration_ms=500.0,
        engine_name="mock-engine",
    ))
    return router


@pytest.fixture
def mock_registry():
    registry = MagicMock()
    registry.get_voice_config.return_value = VoiceConfig(voice_id="test")
    registry.get_npc_voice.return_value = VoiceConfig(voice_id="npc_test")
    registry.default_language = "en"
    return registry


@pytest.fixture
def mock_connection():
    conn = AsyncMock()
    conn.send_to_player = AsyncMock(return_value=1)
    conn.broadcast = AsyncMock(return_value=3)
    return conn


@pytest.fixture
def manager(mock_router, mock_registry, mock_connection):
    return AudioStreamManager(
        tts_router=mock_router,
        voice_registry=mock_registry,
        connection_manager=mock_connection,
        chunk_size=DEFAULT_CHUNK_SIZE,
    )


# ── Basic streaming ─────────────────────────────────────────────────

class TestStreamToPlayer:
    @pytest.mark.asyncio
    async def test_sends_all_chunks(self, manager, mock_connection):
        result = await manager.stream_to_player("player1", "Hello!")
        assert result is True
        # 10000 bytes / 4096 = 3 chunks (ceil)
        assert mock_connection.send_to_player.call_count == 3

    @pytest.mark.asyncio
    async def test_chunk_format(self, manager, mock_connection):
        await manager.stream_to_player("player1", "Hello!")
        call_args = mock_connection.send_to_player.call_args_list[0]
        msg = call_args[0][1]  # second positional arg = message dict
        assert msg["type"] == "audio"
        assert msg["format"] == "wav"
        assert msg["sequence"] == 0
        assert msg["total_chunks"] == 3
        assert msg["sample_rate"] == 24000
        assert msg["duration_ms"] == 500.0
        # Data should be valid base64
        decoded = base64.b64decode(msg["data"])
        assert len(decoded) == DEFAULT_CHUNK_SIZE

    @pytest.mark.asyncio
    async def test_sequence_numbers(self, manager, mock_connection):
        await manager.stream_to_player("player1", "Hello!")
        seqs = [
            call[0][1]["sequence"]
            for call in mock_connection.send_to_player.call_args_list
        ]
        assert seqs == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_last_chunk_smaller(self, manager, mock_connection):
        """Last chunk may be smaller than chunk_size."""
        await manager.stream_to_player("player1", "Hello!")
        last_msg = mock_connection.send_to_player.call_args_list[-1][0][1]
        decoded = base64.b64decode(last_msg["data"])
        # 10000 - 2*4096 = 1808
        assert len(decoded) == 10000 - 2 * DEFAULT_CHUNK_SIZE


class TestStreamToAll:
    @pytest.mark.asyncio
    async def test_broadcasts(self, manager, mock_connection):
        result = await manager.stream_to_all("Welcome!", speaker="dm")
        assert result is True
        assert mock_connection.broadcast.call_count == 3

    @pytest.mark.asyncio
    async def test_uses_registry(self, manager, mock_registry):
        await manager.stream_to_all("Hello!", speaker="combat")
        mock_registry.get_voice_config.assert_called_once_with("combat")


class TestNPCStreaming:
    @pytest.mark.asyncio
    async def test_npc_to_player(self, manager, mock_registry, mock_connection):
        result = await manager.stream_npc_to_player(
            "player1", "Welcome to my inn!", "giuseppe", race="human", gender="male"
        )
        assert result is True
        mock_registry.get_npc_voice.assert_called_once_with(
            "giuseppe", race="human", gender="male"
        )

    @pytest.mark.asyncio
    async def test_npc_to_all(self, manager, mock_registry, mock_connection):
        result = await manager.stream_npc_to_all(
            "You shall not pass!", "gandalf", race="human", gender="male"
        )
        assert result is True
        mock_registry.get_npc_voice.assert_called_once_with(
            "gandalf", race="human", gender="male"
        )


# ── Graceful degradation ────────────────────────────────────────────

class TestGracefulDegradation:
    @pytest.mark.asyncio
    async def test_synthesis_failure_returns_false(self, manager, mock_router):
        mock_router.synthesize.side_effect = RuntimeError("No engines available")
        result = await manager.stream_to_player("player1", "Hello!")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_failure_returns_false(self, manager, mock_connection):
        mock_connection.send_to_player.side_effect = Exception("Connection lost")
        result = await manager.stream_to_player("player1", "Hello!")
        assert result is False


# ── Custom chunk size ────────────────────────────────────────────────

class TestChunkSize:
    @pytest.mark.asyncio
    async def test_small_chunk_size(self, mock_router, mock_registry, mock_connection):
        mgr = AudioStreamManager(
            mock_router, mock_registry, mock_connection, chunk_size=1000,
        )
        await mgr.stream_to_player("player1", "Hello!")
        # 10000 / 1000 = 10 chunks
        assert mock_connection.send_to_player.call_count == 10

    @pytest.mark.asyncio
    async def test_large_chunk_size(self, mock_router, mock_registry, mock_connection):
        mgr = AudioStreamManager(
            mock_router, mock_registry, mock_connection, chunk_size=20000,
        )
        await mgr.stream_to_player("player1", "Hello!")
        # 10000 / 20000 = 1 chunk
        assert mock_connection.send_to_player.call_count == 1


# ── Explicit voice_config override ───────────────────────────────────

class TestVoiceConfigOverride:
    @pytest.mark.asyncio
    async def test_explicit_config_skips_registry(
        self, manager, mock_router, mock_registry
    ):
        custom = VoiceConfig(voice_id="custom_voice", language="it")
        await manager.stream_to_player(
            "player1", "Ciao!", voice_config=custom
        )
        mock_registry.get_voice_config.assert_not_called()
        # Router should have been called with the custom config
        mock_router.synthesize.assert_called_once()
        call_args = mock_router.synthesize.call_args
        assert call_args[0][0] == "Ciao!"
        assert call_args[1].get("voice_config") or call_args[0][2] == custom
