"""
Piper TTS engine wrapper.

Piper is a fast, local TTS engine that runs on CPU without requiring
GPU acceleration. It serves as the Tier 1 (Speed) engine on Intel Macs
and non-Apple-Silicon platforms.

Requires the `piper-tts` package: pip install piper-tts
"""

import io
import logging
import struct
import time
from typing import Optional

from .base import AudioFormat, TTSEngine, TTSResult, VoiceConfig

logger = logging.getLogger("dm20-protocol.voice.piper")

# Default model paths/names per language
_DEFAULT_MODELS: dict[str, str] = {
    "en": "en_US-lessac-medium",
    "it": "it_IT-riccardo-x_low",
}

# Default sample rate for Piper output
_DEFAULT_SAMPLE_RATE = 22050


def _check_piper_available() -> bool:
    """Check if the piper-tts package is importable."""
    try:
        import piper  # noqa: F401

        return True
    except ImportError:
        return False


def _audio_to_wav(samples: bytes, sample_rate: int) -> bytes:
    """Wrap raw PCM 16-bit samples in a WAV container.

    Args:
        samples: Raw 16-bit PCM audio bytes.
        sample_rate: Sample rate in Hz.

    Returns:
        WAV file bytes.
    """
    buf = io.BytesIO()
    data_size = len(samples)

    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))
    buf.write(struct.pack("<H", 1))  # PCM
    buf.write(struct.pack("<H", 1))  # mono
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", sample_rate * 2))
    buf.write(struct.pack("<H", 2))  # block align
    buf.write(struct.pack("<H", 16))  # bits per sample
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(samples)

    return buf.getvalue()


class PiperEngine(TTSEngine):
    """Piper TTS engine for fast CPU-based speech synthesis.

    Piper is a lightweight TTS system that runs efficiently on CPU,
    making it the preferred speed-tier engine for Intel Macs and
    non-Apple-Silicon platforms.
    """

    def __init__(self) -> None:
        self._voice: object | None = None
        self._available: bool | None = None
        self._current_model: str | None = None

    @property
    def name(self) -> str:
        return "piper"

    def is_available(self) -> bool:
        if self._available is None:
            self._available = _check_piper_available()
            if not self._available:
                logger.debug("piper-tts package not installed")
        return self._available

    def _get_or_load_voice(self, model_name: str) -> object:
        """Load or reuse the Piper voice model.

        Args:
            model_name: Piper model identifier.

        Returns:
            Loaded PiperVoice instance.
        """
        if self._voice is not None and self._current_model == model_name:
            return self._voice

        from piper import PiperVoice

        self._voice = PiperVoice.load(model_name)
        self._current_model = model_name
        logger.info("Piper voice loaded: %s", model_name)
        return self._voice

    async def warmup(self) -> None:
        """Preload the default Piper voice."""
        if not self.is_available():
            return

        try:
            default_model = _DEFAULT_MODELS.get("en", "en_US-lessac-medium")
            self._get_or_load_voice(default_model)
        except Exception as exc:
            logger.warning("Failed to preload Piper voice: %s", exc)
            self._available = False

    async def synthesize(
        self,
        text: str,
        voice_config: Optional[VoiceConfig] = None,
    ) -> TTSResult:
        """Synthesize text using Piper TTS.

        Args:
            text: Text to synthesize.
            voice_config: Optional voice configuration.

        Returns:
            TTSResult with WAV audio data.

        Raises:
            RuntimeError: If piper-tts is not available or synthesis fails.
        """
        if not self.is_available():
            raise RuntimeError(
                "Piper engine is not available (piper-tts not installed)"
            )

        config = voice_config or VoiceConfig()
        lang = config.language

        # Determine model
        model_name = config.voice_id
        if model_name == "default":
            model_name = _DEFAULT_MODELS.get(lang, "en_US-lessac-medium")

        try:
            voice = self._get_or_load_voice(model_name)

            start_time = time.monotonic()

            # Piper synthesize_stream_raw yields raw PCM 16-bit audio chunks
            audio_chunks: list[bytes] = []
            for audio_bytes in voice.synthesize_stream_raw(text):
                audio_chunks.append(audio_bytes)

            raw_audio = b"".join(audio_chunks)
            elapsed_ms = (time.monotonic() - start_time) * 1000

            sample_rate = _DEFAULT_SAMPLE_RATE
            # Duration from 16-bit mono PCM
            num_samples = len(raw_audio) // 2
            duration_ms = (num_samples / sample_rate) * 1000

            wav_data = _audio_to_wav(raw_audio, sample_rate)

            logger.info(
                "Piper synthesis: %.0fms latency, %.0fms audio duration",
                elapsed_ms,
                duration_ms,
            )

            return TTSResult(
                audio_data=wav_data,
                format=AudioFormat.WAV,
                sample_rate=sample_rate,
                duration_ms=duration_ms,
                engine_name=self.name,
            )

        except ImportError:
            self._available = False
            raise RuntimeError("piper-tts package not found during synthesis")
        except Exception as exc:
            raise RuntimeError(f"Piper synthesis failed: {exc}") from exc

    async def shutdown(self) -> None:
        """Release the Piper voice model."""
        self._voice = None
        self._current_model = None
        logger.debug("Piper voice released")

    def supported_languages(self) -> list[str]:
        return ["en", "it", "de", "fr", "es", "pt", "nl", "pl", "uk", "ru"]
