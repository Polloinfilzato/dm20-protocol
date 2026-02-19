"""
TTS engine wrappers for dm20-protocol voice subsystem.

Each engine implements the TTSEngine interface and handles
graceful import failures for optional dependencies.
"""

from .base import TTSEngine, VoiceConfig, TTSResult

__all__ = [
    "TTSEngine",
    "VoiceConfig",
    "TTSResult",
]
