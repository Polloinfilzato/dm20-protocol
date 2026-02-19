"""
Hardware detection for TTS engine selection.

Detects Apple Silicon vs Intel to determine which local TTS engines
are available and optimal for the current machine.
"""

import logging
import platform

logger = logging.getLogger("dm20-protocol.voice.hardware")


def is_apple_silicon() -> bool:
    """Detect if running on Apple Silicon (M1/M2/M3/M4).

    Returns:
        True if the machine is an Apple Silicon Mac (arm64 + Darwin).
    """
    return platform.machine() == "arm64" and platform.system() == "Darwin"


def is_intel_mac() -> bool:
    """Detect if running on an Intel Mac.

    Returns:
        True if the machine is an Intel Mac (x86_64 + Darwin).
    """
    return platform.machine() == "x86_64" and platform.system() == "Darwin"


def is_mac() -> bool:
    """Detect if running on any Mac.

    Returns:
        True if the system is macOS (Darwin).
    """
    return platform.system() == "Darwin"


def get_available_tiers() -> dict[str, str]:
    """Determine available TTS tiers based on hardware.

    Apple Silicon Macs get Kokoro (speed), Qwen3-TTS (quality),
    and Edge-TTS (fallback). Intel Macs get Piper (speed) and
    Edge-TTS for both quality and fallback. Non-Mac systems
    get Piper (speed) and Edge-TTS for quality/fallback.

    Returns:
        Dictionary mapping tier names to engine identifiers:
        - "speed": Engine for low-latency synthesis (combat).
        - "quality": Engine for high-quality synthesis (narration).
        - "fallback": Cloud-based fallback engine.
    """
    if is_apple_silicon():
        tiers = {
            "speed": "kokoro",
            "quality": "qwen3-tts",
            "fallback": "edge-tts",
        }
        logger.info("Apple Silicon detected: tiers=%s", tiers)
        return tiers
    else:
        tiers = {
            "speed": "piper",
            "quality": "edge-tts",
            "fallback": "edge-tts",
        }
        if is_intel_mac():
            logger.info("Intel Mac detected: tiers=%s", tiers)
        else:
            logger.info("Non-Mac platform detected: tiers=%s", tiers)
        return tiers


def get_hardware_info() -> dict[str, str]:
    """Get a summary of hardware information relevant to TTS.

    Returns:
        Dictionary with hardware details:
        - "platform": Operating system name.
        - "machine": CPU architecture.
        - "processor": Processor description.
        - "chip_family": "apple_silicon", "intel_mac", or "other".
    """
    if is_apple_silicon():
        chip_family = "apple_silicon"
    elif is_intel_mac():
        chip_family = "intel_mac"
    else:
        chip_family = "other"

    return {
        "platform": platform.system(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "chip_family": chip_family,
    }
