"""
WebSocket audio streaming for Party Mode.

Takes synthesised audio from the TTSRouter, splits it into sequenced
chunks, and delivers them to player browsers via the Party Mode
ConnectionManager.  If synthesis or streaming fails the caller can
still send text — graceful degradation is a first-class concern.

Typical flow::

    manager = AudioStreamManager(tts_router, voice_registry, connection_mgr)
    await manager.stream_to_player("player1", "The dragon roars!", speaker="combat")
    await manager.stream_to_all("Welcome, adventurers.", speaker="dm")
"""

import asyncio
import base64
import logging
import math
from typing import TYPE_CHECKING, Optional

from .engines.base import AudioFormat, VoiceConfig
from .registry import VoiceRegistry
from .router import TTSRouter

if TYPE_CHECKING:
    from dm20_protocol.party.server import ConnectionManager

logger = logging.getLogger("dm20-protocol.voice.streaming")

# Default chunk size in bytes (~4 KB — keeps WebSocket frames small)
DEFAULT_CHUNK_SIZE = 4096


class AudioStreamManager:
    """Manages TTS synthesis and chunked WebSocket delivery.

    The manager ties together three layers:

    * **VoiceRegistry** — resolves *who* is speaking to a ``VoiceConfig``.
    * **TTSRouter** — converts text → audio bytes.
    * **ConnectionManager** — sends JSON messages over WebSocket.

    Args:
        tts_router: Initialised TTSRouter instance.
        voice_registry: Campaign VoiceRegistry.
        connection_manager: Party Mode ConnectionManager.
        chunk_size: Bytes per audio chunk (default 4096).
    """

    def __init__(
        self,
        tts_router: TTSRouter,
        voice_registry: VoiceRegistry,
        connection_manager: "ConnectionManager",
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        self._router = tts_router
        self._registry = voice_registry
        self._conn = connection_manager
        self._chunk_size = chunk_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def stream_to_player(
        self,
        player_id: str,
        text: str,
        *,
        speaker: str = "dm",
        context: str = "default",
        voice_config: Optional[VoiceConfig] = None,
    ) -> bool:
        """Synthesise and stream audio to a single player.

        Args:
            player_id: Target player identifier.
            text: Text to synthesise.
            speaker: Speaker identifier for registry lookup.
            context: Synthesis context for engine selection.
            voice_config: Explicit config (overrides registry lookup).

        Returns:
            ``True`` if audio was delivered, ``False`` on failure.
        """
        config = voice_config or self._resolve_voice(speaker)
        return await self._synthesize_and_send(
            text, config, context, player_id=player_id
        )

    async def stream_to_all(
        self,
        text: str,
        *,
        speaker: str = "dm",
        context: str = "default",
        voice_config: Optional[VoiceConfig] = None,
    ) -> bool:
        """Synthesise and broadcast audio to all connected players.

        Args:
            text: Text to synthesise.
            speaker: Speaker identifier for registry lookup.
            context: Synthesis context for engine selection.
            voice_config: Explicit config (overrides registry lookup).

        Returns:
            ``True`` if audio was delivered, ``False`` on failure.
        """
        config = voice_config or self._resolve_voice(speaker)
        return await self._synthesize_and_send(text, config, context)

    async def stream_npc_to_player(
        self,
        player_id: str,
        text: str,
        npc_name: str,
        *,
        race: Optional[str] = None,
        gender: Optional[str] = None,
        context: str = "dialogue",
    ) -> bool:
        """Synthesise NPC dialogue and stream to a player.

        Uses the full archetype cascade from the VoiceRegistry.

        Args:
            player_id: Target player.
            text: Dialogue text.
            npc_name: NPC identifier for voice lookup.
            race: Optional NPC race for archetype fallback.
            gender: Optional NPC gender for archetype fallback.
            context: Synthesis context (default ``"dialogue"``).

        Returns:
            ``True`` if audio was delivered.
        """
        config = self._registry.get_npc_voice(npc_name, race=race, gender=gender)
        return await self._synthesize_and_send(
            text, config, context, player_id=player_id
        )

    async def stream_npc_to_all(
        self,
        text: str,
        npc_name: str,
        *,
        race: Optional[str] = None,
        gender: Optional[str] = None,
        context: str = "dialogue",
    ) -> bool:
        """Synthesise NPC dialogue and broadcast to all players.

        Args:
            text: Dialogue text.
            npc_name: NPC identifier for voice lookup.
            race: Optional NPC race.
            gender: Optional NPC gender.
            context: Synthesis context.

        Returns:
            ``True`` if audio was delivered.
        """
        config = self._registry.get_npc_voice(npc_name, race=race, gender=gender)
        return await self._synthesize_and_send(text, config, context)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_voice(self, speaker: str) -> VoiceConfig:
        """Resolve speaker identifier through the VoiceRegistry."""
        return self._registry.get_voice_config(speaker)

    async def _synthesize_and_send(
        self,
        text: str,
        voice_config: VoiceConfig,
        context: str,
        *,
        player_id: Optional[str] = None,
    ) -> bool:
        """Synthesise audio and stream chunks.

        If player_id is None, broadcasts to all connected players.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        try:
            result = await self._router.synthesize(text, context, voice_config)
        except RuntimeError as exc:
            logger.warning("TTS synthesis failed (text will still be sent): %s", exc)
            return False

        audio_data = result.audio_data
        fmt = result.format.value  # "wav", "opus", "mp3"
        total_chunks = math.ceil(len(audio_data) / self._chunk_size)

        for seq in range(total_chunks):
            start = seq * self._chunk_size
            end = start + self._chunk_size
            chunk = audio_data[start:end]

            message = {
                "type": "audio",
                "format": fmt,
                "data": base64.b64encode(chunk).decode("ascii"),
                "sequence": seq,
                "total_chunks": total_chunks,
                "sample_rate": result.sample_rate,
                "duration_ms": result.duration_ms,
            }

            try:
                if player_id:
                    await self._conn.send_to_player(player_id, message)
                else:
                    await self._conn.broadcast(message)
            except Exception as exc:
                logger.warning(
                    "Failed to send audio chunk %d/%d: %s", seq, total_chunks, exc
                )
                return False

        logger.info(
            "Streamed %d audio chunks (%d bytes, format=%s) to %s",
            total_chunks,
            len(audio_data),
            fmt,
            player_id or "all players",
        )
        return True
