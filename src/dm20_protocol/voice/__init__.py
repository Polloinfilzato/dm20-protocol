"""
Voice subsystem for dm20-protocol.

Provides Text-to-Speech (TTS) with a 3-tier router:
- Tier 1 (Speed): Kokoro (Apple Silicon) or Piper (Intel/other)
- Tier 2 (Quality): Qwen3-TTS via mlx-audio (Apple Silicon) or Edge-TTS (Intel/other)
- Tier 3 (Fallback): Edge-TTS cloud-based synthesis

The router selects the best engine based on context (combat, narration, dialogue)
and cascades gracefully through tiers on failure.

Per-campaign VoiceRegistry maps speakers (DM, combat narrator, NPCs) to
specific engine/voice configurations with wildcard archetype defaults.

AudioStreamManager chunks synthesised audio and delivers it to player
browsers over WebSocket with sequence numbering.

Install voice dependencies: pip install dm20-protocol[voice]
"""

from .engines.base import AudioFormat, TTSEngine, TTSResult, VoiceConfig
from .hardware import get_available_tiers, get_hardware_info, is_apple_silicon
from .registry import VoiceRegistry
from .router import SynthesisContext, TTSRouter
from .streaming import AudioStreamManager

__all__ = [
    # Router
    "TTSRouter",
    "SynthesisContext",
    # Engine interface
    "TTSEngine",
    "VoiceConfig",
    "TTSResult",
    "AudioFormat",
    # Voice Registry
    "VoiceRegistry",
    # Audio Streaming
    "AudioStreamManager",
    # Hardware detection
    "is_apple_silicon",
    "get_available_tiers",
    "get_hardware_info",
]
