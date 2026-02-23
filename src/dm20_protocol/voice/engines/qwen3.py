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
                from mlx_audio.tts.utils import load_model

                start = time.monotonic()
                self._tts = load_model(self._model_id)
                elapsed = (time.monotonic() - start) * 1000
                logger.info(
                    "Qwen3-TTS model loaded: %s (%.0fms)", self._model_id, elapsed
                )
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
                from mlx_audio.tts.utils import load_model

                self._tts = load_model(self._model_id)

            start_time = time.monotonic()
            logger.info(
                "Qwen3-TTS synthesizing %d chars, lang=%s, speed=%.1f",
                len(text),
                config.language or "it",
                config.speed or 1.0,
            )

            # mlx-audio 0.2.10+ model.generate() returns a generator of result objects
            results = list(self._tts.generate(
                text,
                lang_code=config.language or "it",
                speed=config.speed or 1.0,
                verbose=False,
            ))

            # Concatenate audio from result chunks
            all_samples: list[float] = []
            sample_rate = _DEFAULT_SAMPLE_RATE
            for r in results:
                audio = getattr(r, "audio", r)
                if hasattr(audio, "tolist"):
                    all_samples.extend(audio.tolist())
                elif hasattr(audio, "numpy"):
                    all_samples.extend(audio.numpy().tolist())
                elif isinstance(audio, (list, tuple)):
                    all_samples.extend(list(audio))
                if hasattr(r, "sample_rate") and r.sample_rate:
                    sample_rate = r.sample_rate

            # Flatten if nested
            if all_samples and isinstance(all_samples[0], list):
                all_samples = [s for sublist in all_samples for s in sublist]

            elapsed_ms = (time.monotonic() - start_time) * 1000
            duration_ms = (len(all_samples) / sample_rate) * 1000

            wav_data = _audio_to_wav(all_samples, sample_rate)

            logger.info(
                "Qwen3-TTS synthesis complete: %.0fms latency, %.0fms audio, %d samples",
                elapsed_ms,
                duration_ms,
                len(all_samples),
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
