"""
Qwen3-TTS engine wrapper via mlx-audio.

Qwen3-TTS is a high-quality TTS model that runs locally on Apple Silicon
through the mlx-audio framework. It serves as the Tier 2 (Quality) engine,
providing rich, expressive voices for DM narration and NPC dialogue.

Requires the `mlx-audio` package: pip install mlx-audio
"""

import io
import logging
import struct
import time
from typing import Optional

from .base import AudioFormat, TTSEngine, TTSResult, VoiceConfig

logger = logging.getLogger("dm20-protocol.voice.qwen3")

# Default model identifier for Qwen3-TTS via mlx-audio
_DEFAULT_MODEL = "mlx-community/Qwen3-TTS-0.6B-bf16"

# Default reference voice for cloning/style
_DEFAULT_VOICE = "default"

# Default sample rate for Qwen3-TTS output
_DEFAULT_SAMPLE_RATE = 24000


def _check_mlx_audio_available() -> bool:
    """Check if the mlx-audio package is importable."""
    try:
        import mlx_audio  # noqa: F401

        return True
    except ImportError:
        return False


def _audio_to_wav(samples: list[float], sample_rate: int) -> bytes:
    """Convert raw float audio samples to WAV bytes.

    Args:
        samples: Audio samples as floats in [-1.0, 1.0].
        sample_rate: Sample rate in Hz.

    Returns:
        WAV file bytes.
    """
    buf = io.BytesIO()
    num_samples = len(samples)
    data_size = num_samples * 2

    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))
    buf.write(struct.pack("<H", 1))
    buf.write(struct.pack("<H", 1))
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", sample_rate * 2))
    buf.write(struct.pack("<H", 2))
    buf.write(struct.pack("<H", 16))
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    for sample in samples:
        clamped = max(-1.0, min(1.0, sample))
        buf.write(struct.pack("<h", int(clamped * 32767)))

    return buf.getvalue()


class Qwen3TTSEngine(TTSEngine):
    """Qwen3-TTS engine via mlx-audio for high-quality speech synthesis.

    This engine uses Apple's MLX framework through mlx-audio to run
    Qwen3-TTS locally on Apple Silicon. It provides high-quality,
    expressive voices suitable for DM narration and NPC dialogue.
    """

    def __init__(self, model_id: str = _DEFAULT_MODEL) -> None:
        self._model_id = model_id
        self._tts: object | None = None
        self._available: bool | None = None

    @property
    def name(self) -> str:
        return "qwen3-tts"

    def is_available(self) -> bool:
        if self._available is None:
            self._available = _check_mlx_audio_available()
            if not self._available:
                logger.debug("mlx-audio package not installed")
        return self._available

    async def warmup(self) -> None:
        """Preload the Qwen3-TTS model for faster first synthesis."""
        if not self.is_available():
            return

        if self._tts is None:
            try:
                from mlx_audio.tts import TTS

                self._tts = TTS(self._model_id)
                logger.info("Qwen3-TTS model loaded: %s", self._model_id)
            except Exception as exc:
                logger.warning("Failed to load Qwen3-TTS model: %s", exc)
                self._available = False

    async def synthesize(
        self,
        text: str,
        voice_config: Optional[VoiceConfig] = None,
    ) -> TTSResult:
        """Synthesize text using Qwen3-TTS via mlx-audio.

        Args:
            text: Text to synthesize.
            voice_config: Optional voice configuration.

        Returns:
            TTSResult with WAV audio data.

        Raises:
            RuntimeError: If mlx-audio is not available or synthesis fails.
        """
        if not self.is_available():
            raise RuntimeError(
                "Qwen3-TTS engine is not available (mlx-audio not installed)"
            )

        config = voice_config or VoiceConfig()

        try:
            if self._tts is None:
                from mlx_audio.tts import TTS

                self._tts = TTS(self._model_id)

            start_time = time.monotonic()

            # mlx-audio TTS.generate() returns audio data
            # The exact API depends on the mlx-audio version
            result = self._tts.generate(
                text=text,
                language=config.language,
                speed=config.speed,
            )

            # Handle different return types from mlx-audio
            if hasattr(result, "tolist"):
                samples = result.tolist()
            elif hasattr(result, "numpy"):
                samples = result.numpy().tolist()
            elif isinstance(result, (list, tuple)):
                samples = list(result)
            else:
                # May return a dict or object with audio field
                audio = getattr(result, "audio", result)
                if hasattr(audio, "tolist"):
                    samples = audio.tolist()
                else:
                    samples = list(audio)

            # Flatten if nested
            if samples and isinstance(samples[0], list):
                samples = [s for sublist in samples for s in sublist]

            elapsed_ms = (time.monotonic() - start_time) * 1000
            sample_rate = _DEFAULT_SAMPLE_RATE
            duration_ms = (len(samples) / sample_rate) * 1000

            wav_data = _audio_to_wav(samples, sample_rate)

            logger.info(
                "Qwen3-TTS synthesis: %.0fms latency, %.0fms audio duration",
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
            raise RuntimeError("mlx-audio package not found during synthesis")
        except Exception as exc:
            raise RuntimeError(f"Qwen3-TTS synthesis failed: {exc}") from exc

    async def shutdown(self) -> None:
        """Release the Qwen3-TTS model."""
        self._tts = None
        logger.debug("Qwen3-TTS model released")

    def supported_languages(self) -> list[str]:
        return ["en", "it", "zh", "ja", "ko"]
