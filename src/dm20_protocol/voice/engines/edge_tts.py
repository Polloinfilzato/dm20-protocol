"""
Edge-TTS engine wrapper.

Edge-TTS uses Microsoft's Azure edge speech service (free, no API key)
to provide cloud-based text-to-speech. It serves as the fallback tier
(Tier 3) on Apple Silicon and as both quality and fallback tiers on
Intel Macs.

Requires the `edge-tts` package: pip install edge-tts
"""

import logging
import time
from typing import Optional

from .base import AudioFormat, TTSEngine, TTSResult, VoiceConfig

logger = logging.getLogger("dm20-protocol.voice.edge_tts")

# Voice mapping: language -> default voice name
_DEFAULT_VOICES: dict[str, str] = {
    "en": "en-US-GuyNeural",
    "en-us": "en-US-GuyNeural",
    "en-gb": "en-GB-RyanNeural",
    "it": "it-IT-DiegoNeural",
}

# Female voice alternatives
_FEMALE_VOICES: dict[str, str] = {
    "en": "en-US-JennyNeural",
    "en-us": "en-US-JennyNeural",
    "en-gb": "en-GB-SoniaNeural",
    "it": "it-IT-ElsaNeural",
}


def _check_edge_tts_available() -> bool:
    """Check if the edge-tts package is importable."""
    try:
        import edge_tts  # noqa: F401

        return True
    except ImportError:
        return False


class EdgeTTSEngine(TTSEngine):
    """Edge-TTS engine for cloud-based speech synthesis.

    Uses Microsoft's free edge speech service (no API key required).
    Provides reliable fallback with good quality across many languages.
    Requires an internet connection.
    """

    def __init__(self) -> None:
        self._available: bool | None = None

    @property
    def name(self) -> str:
        return "edge-tts"

    def is_available(self) -> bool:
        if self._available is None:
            self._available = _check_edge_tts_available()
            if not self._available:
                logger.debug("edge-tts package not installed")
        return self._available

    async def synthesize(
        self,
        text: str,
        voice_config: Optional[VoiceConfig] = None,
    ) -> TTSResult:
        """Synthesize text using Edge-TTS.

        Args:
            text: Text to synthesize.
            voice_config: Optional voice configuration.

        Returns:
            TTSResult with MP3 audio data (Edge-TTS native format).

        Raises:
            RuntimeError: If edge-tts is not available or synthesis fails.
        """
        if not self.is_available():
            raise RuntimeError(
                "Edge-TTS engine is not available (edge-tts not installed)"
            )

        config = voice_config or VoiceConfig()
        lang = config.language

        # Determine voice
        voice_id = config.voice_id
        if voice_id == "default":
            voice_id = _DEFAULT_VOICES.get(lang, "en-US-GuyNeural")
        elif voice_id == "female":
            voice_id = _FEMALE_VOICES.get(lang, "en-US-JennyNeural")

        # Build rate and pitch parameters
        rate_str = f"+{int((config.speed - 1) * 100)}%" if config.speed >= 1.0 else \
            f"{int((config.speed - 1) * 100)}%"
        pitch_str = f"+{int(config.pitch)}Hz" if config.pitch >= 0 else \
            f"{int(config.pitch)}Hz"

        try:
            import edge_tts

            start_time = time.monotonic()

            communicate = edge_tts.Communicate(
                text,
                voice=voice_id,
                rate=rate_str,
                pitch=pitch_str,
            )

            # Collect all audio chunks
            audio_chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])

            audio_data = b"".join(audio_chunks)
            elapsed_ms = (time.monotonic() - start_time) * 1000

            # Edge-TTS returns MP3 by default
            # Estimate duration from MP3 data size (rough: ~16kbps)
            estimated_duration_ms = (len(audio_data) / 2000) * 1000

            logger.info(
                "Edge-TTS synthesis: %.0fms latency, ~%.0fms estimated duration",
                elapsed_ms,
                estimated_duration_ms,
            )

            return TTSResult(
                audio_data=audio_data,
                format=AudioFormat.MP3,
                sample_rate=24000,  # Edge-TTS typical sample rate
                duration_ms=estimated_duration_ms,
                engine_name=self.name,
            )

        except ImportError:
            self._available = False
            raise RuntimeError("edge-tts package not found during synthesis")
        except Exception as exc:
            raise RuntimeError(f"Edge-TTS synthesis failed: {exc}") from exc

    def supported_languages(self) -> list[str]:
        return [
            "en", "it", "de", "fr", "es", "pt", "ja", "ko", "zh",
            "ar", "hi", "ru", "pl", "nl", "sv", "da", "no", "fi",
        ]
