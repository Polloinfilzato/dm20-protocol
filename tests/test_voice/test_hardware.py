"""
Tests for voice hardware detection module.
"""

from unittest.mock import patch

import pytest

from dm20_protocol.voice.hardware import (
    get_available_tiers,
    get_hardware_info,
    is_apple_silicon,
    is_intel_mac,
    is_mac,
)


class TestIsAppleSilicon:
    """Tests for is_apple_silicon()."""

    def test_apple_silicon_detected(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.machine.return_value = "arm64"
            mock_platform.system.return_value = "Darwin"
            assert is_apple_silicon() is True

    def test_intel_mac_not_apple_silicon(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.machine.return_value = "x86_64"
            mock_platform.system.return_value = "Darwin"
            assert is_apple_silicon() is False

    def test_linux_arm_not_apple_silicon(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.machine.return_value = "arm64"
            mock_platform.system.return_value = "Linux"
            assert is_apple_silicon() is False

    def test_linux_x86_not_apple_silicon(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.machine.return_value = "x86_64"
            mock_platform.system.return_value = "Linux"
            assert is_apple_silicon() is False

    def test_windows_not_apple_silicon(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.machine.return_value = "AMD64"
            mock_platform.system.return_value = "Windows"
            assert is_apple_silicon() is False


class TestIsIntelMac:
    """Tests for is_intel_mac()."""

    def test_intel_mac_detected(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.machine.return_value = "x86_64"
            mock_platform.system.return_value = "Darwin"
            assert is_intel_mac() is True

    def test_apple_silicon_not_intel(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.machine.return_value = "arm64"
            mock_platform.system.return_value = "Darwin"
            assert is_intel_mac() is False

    def test_linux_x86_not_intel_mac(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.machine.return_value = "x86_64"
            mock_platform.system.return_value = "Linux"
            assert is_intel_mac() is False


class TestIsMac:
    """Tests for is_mac()."""

    def test_mac_detected(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.system.return_value = "Darwin"
            assert is_mac() is True

    def test_linux_not_mac(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.system.return_value = "Linux"
            assert is_mac() is False


class TestGetAvailableTiers:
    """Tests for get_available_tiers()."""

    def test_apple_silicon_tiers(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.machine.return_value = "arm64"
            mock_platform.system.return_value = "Darwin"

            tiers = get_available_tiers()

            assert tiers["speed"] == "kokoro"
            assert tiers["quality"] == "qwen3-tts"
            assert tiers["fallback"] == "edge-tts"

    def test_intel_mac_tiers(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.machine.return_value = "x86_64"
            mock_platform.system.return_value = "Darwin"

            tiers = get_available_tiers()

            assert tiers["speed"] == "piper"
            assert tiers["quality"] == "edge-tts"
            assert tiers["fallback"] == "edge-tts"

    def test_linux_tiers(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.machine.return_value = "x86_64"
            mock_platform.system.return_value = "Linux"

            tiers = get_available_tiers()

            assert tiers["speed"] == "piper"
            assert tiers["quality"] == "edge-tts"
            assert tiers["fallback"] == "edge-tts"

    def test_tiers_have_all_keys(self) -> None:
        tiers = get_available_tiers()
        assert "speed" in tiers
        assert "quality" in tiers
        assert "fallback" in tiers


class TestGetHardwareInfo:
    """Tests for get_hardware_info()."""

    def test_apple_silicon_info(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.machine.return_value = "arm64"
            mock_platform.system.return_value = "Darwin"
            mock_platform.processor.return_value = "arm"

            info = get_hardware_info()

            assert info["platform"] == "Darwin"
            assert info["machine"] == "arm64"
            assert info["chip_family"] == "apple_silicon"

    def test_intel_mac_info(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.machine.return_value = "x86_64"
            mock_platform.system.return_value = "Darwin"
            mock_platform.processor.return_value = "i386"

            info = get_hardware_info()

            assert info["platform"] == "Darwin"
            assert info["machine"] == "x86_64"
            assert info["chip_family"] == "intel_mac"

    def test_linux_info(self) -> None:
        with patch("dm20_protocol.voice.hardware.platform") as mock_platform:
            mock_platform.machine.return_value = "x86_64"
            mock_platform.system.return_value = "Linux"
            mock_platform.processor.return_value = "x86_64"

            info = get_hardware_info()

            assert info["chip_family"] == "other"

    def test_info_has_all_keys(self) -> None:
        info = get_hardware_info()
        assert "platform" in info
        assert "machine" in info
        assert "processor" in info
        assert "chip_family" in info
