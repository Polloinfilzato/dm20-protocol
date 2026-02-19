"""
Abstract base class for TTS engines.

All engine wrappers (Kokoro, Qwen3-TTS, Edge-TTS, Piper) implement
this interface, allowing the TTSRouter to treat them uniformly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AudioFormat(Enum):
    """Supported audio output formats."""

    WAV = "wav"
    OPUS = "opus"
    MP3 = "mp3"


@dataclass
class VoiceConfig:
    """Configuration for TTS voice synthesis.

    Attributes:
        voice_id: Engine-specific voice identifier.
        language: Language code (e.g. "en", "it").
        speed: Playback speed multiplier (1.0 = normal).
        pitch: Pitch adjustment in semitones (0.0 = normal).
        output_format: Desired audio output format.
        extra: Engine-specific additional parameters.
    """

    voice_id: str = "default"
    language: str = "en"
    speed: float = 1.0
    pitch: float = 0.0
    output_format: AudioFormat = AudioFormat.WAV
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class TTSResult:
    """Result of a TTS synthesis operation.

    Attributes:
        audio_data: Raw audio bytes.
        format: Audio format of the data.
        sample_rate: Sample rate in Hz.
        duration_ms: Approximate duration of the audio in milliseconds.
        engine_name: Name of the engine that produced this result.
    """

    audio_data: bytes
    format: AudioFormat
    sample_rate: int
    duration_ms: float
    engine_name: str


class TTSEngine(ABC):
    """Abstract base class for Text-to-Speech engines.

    Subclasses must implement:
    - name: A human-readable engine name.
    - is_available(): Check whether the engine's dependencies are installed.
    - synthesize(): Convert text to audio bytes.

    Engines should handle missing optional dependencies gracefully,
    returning False from is_available() rather than raising ImportError.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable engine name."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this engine's dependencies are installed and functional.

        Returns:
            True if the engine can be used, False otherwise.
        """
        ...

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice_config: Optional[VoiceConfig] = None,
    ) -> TTSResult:
        """Synthesize text into audio.

        Args:
            text: The text to convert to speech.
            voice_config: Optional voice configuration. If None, use defaults.

        Returns:
            TTSResult containing the audio data and metadata.

        Raises:
            RuntimeError: If synthesis fails.
        """
        ...

    async def warmup(self) -> None:
        """Optional warmup to preload models or establish connections.

        Override in subclasses that benefit from preloading.
        Default implementation is a no-op.
        """

    async def shutdown(self) -> None:
        """Optional cleanup to release resources.

        Override in subclasses that hold resources (models, connections).
        Default implementation is a no-op.
        """

    def supported_languages(self) -> list[str]:
        """Return list of supported language codes.

        Override in subclasses. Default returns English and Italian.
        """
        return ["en", "it"]
