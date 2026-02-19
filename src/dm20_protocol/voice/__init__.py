"""
Voice subsystem for dm20-protocol.

Provides Text-to-Speech (TTS) with a 3-tier router:
- Tier 1 (Speed): Kokoro (Apple Silicon) or Piper (Intel/other)
- Tier 2 (Quality): Qwen3-TTS via mlx-audio (Apple Silicon) or Edge-TTS (Intel/other)
- Tier 3 (Fallback): Edge-TTS cloud-based synthesis

The router selects the best engine based on context (combat, narration, dialogue)
and cascades gracefully through tiers on failure.

Install voice dependencies: pip install dm20-protocol[voice]
"""

from .engines.base import AudioFormat, TTSEngine, TTSResult, VoiceConfig
from .hardware import get_available_tiers, get_hardware_info, is_apple_silicon
from .router import SynthesisContext, TTSRouter

__all__ = [
    # Router
    "TTSRouter",
    "SynthesisContext",
    # Engine interface
    "TTSEngine",
    "VoiceConfig",
    "TTSResult",
    "AudioFormat",
    # Hardware detection
    "is_apple_silicon",
    "get_available_tiers",
    "get_hardware_info",
]
