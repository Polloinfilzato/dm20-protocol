"""
Tests for the TTSRouter engine selection and cascade logic.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dm20_protocol.voice.engines.base import AudioFormat, TTSResult, VoiceConfig
from dm20_protocol.voice.router import SynthesisContext, TTSRouter


# ---------------------------------------------------------------------------
# Helper: create a mock engine
# ---------------------------------------------------------------------------


def _make_mock_engine(
    name: str,
    available: bool = True,
    fail_on_synthesize: bool = False,
) -> MagicMock:
    """Create a mock TTSEngine.

    Args:
        name: Engine name.
        available: Whether the engine reports as available.
        fail_on_synthesize: If True, synthesize() raises RuntimeError.
    """
    engine = MagicMock()
    engine.name = name
    engine.is_available.return_value = available

    if fail_on_synthesize:
        engine.synthesize = AsyncMock(
            side_effect=RuntimeError(f"{name} synthesis failed")
        )
    else:
        engine.synthesize = AsyncMock(
            return_value=TTSResult(
                audio_data=b"mock_audio_" + name.encode(),
                format=AudioFormat.WAV,
                sample_rate=24000,
                duration_ms=1000.0,
                engine_name=name,
            )
        )

    engine.warmup = AsyncMock()
    engine.shutdown = AsyncMock()
    engine.supported_languages.return_value = ["en", "it"]

    return engine


# ---------------------------------------------------------------------------
# SynthesisContext tests
# ---------------------------------------------------------------------------


class TestSynthesisContext:
    """Tests for the SynthesisContext enum."""

    def test_combat_context(self) -> None:
        ctx = SynthesisContext("combat")
        assert ctx == SynthesisContext.COMBAT

    def test_narration_context(self) -> None:
        ctx = SynthesisContext("narration")
        assert ctx == SynthesisContext.NARRATION

    def test_dialogue_context(self) -> None:
        ctx = SynthesisContext("dialogue")
        assert ctx == SynthesisContext.DIALOGUE

    def test_ambient_context(self) -> None:
        ctx = SynthesisContext("ambient")
        assert ctx == SynthesisContext.AMBIENT

    def test_default_context(self) -> None:
        ctx = SynthesisContext("default")
        assert ctx == SynthesisContext.DEFAULT

    def test_invalid_context(self) -> None:
        with pytest.raises(ValueError):
            SynthesisContext("invalid_context")


# ---------------------------------------------------------------------------
# TTSRouter initialization tests
# ---------------------------------------------------------------------------


class TestTTSRouterInit:
    """Tests for TTSRouter initialization."""

    def test_default_tier_detection(self) -> None:
        """Router should auto-detect tiers from hardware."""
        router = TTSRouter()
        tiers = router.tier_map
        assert "speed" in tiers
        assert "quality" in tiers
        assert "fallback" in tiers

    def test_custom_tier_override(self) -> None:
        override = {"speed": "kokoro", "quality": "edge-tts", "fallback": "edge-tts"}
        router = TTSRouter(tier_override=override)
        assert router.tier_map == override

    @pytest.mark.asyncio
    async def test_initialize_with_available_engines(self) -> None:
        """Initialize with engines whose deps are installed."""
        mock_kokoro = _make_mock_engine("kokoro")
        mock_edge = _make_mock_engine("edge-tts")

        with patch(
            "dm20_protocol.voice.router._ENGINE_CLASSES",
            {"kokoro": lambda: mock_kokoro, "edge-tts": lambda: mock_edge},
        ):
            router = TTSRouter(
                tier_override={"speed": "kokoro", "quality": "edge-tts", "fallback": "edge-tts"}
            )
            # Manually inject engines since we patched classes
            router._engines = {"kokoro": mock_kokoro, "edge-tts": mock_edge}
            router._initialized = True

            assert "kokoro" in router.engines
            assert "edge-tts" in router.engines

    @pytest.mark.asyncio
    async def test_initialize_handles_unavailable_engine(self) -> None:
        """Engines whose deps are missing should not block init."""
        mock_kokoro_cls = MagicMock(return_value=_make_mock_engine("kokoro", available=False))
        mock_edge_cls = MagicMock(return_value=_make_mock_engine("edge-tts", available=True))

        with patch(
            "dm20_protocol.voice.router._ENGINE_CLASSES",
            {"kokoro": mock_kokoro_cls, "edge-tts": mock_edge_cls},
        ):
            router = TTSRouter(
                tier_override={"speed": "kokoro", "quality": "edge-tts", "fallback": "edge-tts"}
            )
            await router.initialize()

            # Kokoro is not available, only edge-tts should be loaded
            assert "kokoro" not in router.engines
            assert "edge-tts" in router.engines


# ---------------------------------------------------------------------------
# Engine selection tests
# ---------------------------------------------------------------------------


class TestTTSRouterSelection:
    """Tests for context-based engine selection."""

    def _make_router_with_engines(
        self,
        speed_engine: MagicMock,
        quality_engine: MagicMock,
        fallback_engine: MagicMock | None = None,
    ) -> TTSRouter:
        """Create a router with pre-loaded mock engines."""
        router = TTSRouter(
            tier_override={
                "speed": speed_engine.name,
                "quality": quality_engine.name,
                "fallback": (fallback_engine or quality_engine).name,
            }
        )
        router._engines = {
            speed_engine.name: speed_engine,
            quality_engine.name: quality_engine,
        }
        if fallback_engine and fallback_engine.name not in router._engines:
            router._engines[fallback_engine.name] = fallback_engine
        router._initialized = True
        return router

    def test_combat_selects_speed_engine(self) -> None:
        speed = _make_mock_engine("kokoro")
        quality = _make_mock_engine("qwen3-tts")
        router = self._make_router_with_engines(speed, quality)

        engine_name = router.get_engine_for_context("combat")
        assert engine_name == "kokoro"

    def test_narration_selects_quality_engine(self) -> None:
        speed = _make_mock_engine("kokoro")
        quality = _make_mock_engine("qwen3-tts")
        router = self._make_router_with_engines(speed, quality)

        engine_name = router.get_engine_for_context("narration")
        assert engine_name == "qwen3-tts"

    def test_dialogue_selects_quality_engine(self) -> None:
        speed = _make_mock_engine("kokoro")
        quality = _make_mock_engine("qwen3-tts")
        router = self._make_router_with_engines(speed, quality)

        engine_name = router.get_engine_for_context("dialogue")
        assert engine_name == "qwen3-tts"

    def test_default_selects_speed_engine(self) -> None:
        speed = _make_mock_engine("kokoro")
        quality = _make_mock_engine("qwen3-tts")
        router = self._make_router_with_engines(speed, quality)

        engine_name = router.get_engine_for_context("default")
        assert engine_name == "kokoro"

    def test_unknown_context_uses_speed(self) -> None:
        speed = _make_mock_engine("kokoro")
        quality = _make_mock_engine("qwen3-tts")
        router = self._make_router_with_engines(speed, quality)

        engine_name = router.get_engine_for_context("totally_unknown")
        assert engine_name == "kokoro"


# ---------------------------------------------------------------------------
# Synthesis with cascade tests
# ---------------------------------------------------------------------------


class TestTTSRouterSynthesis:
    """Tests for synthesis with cascade on failure."""

    @pytest.mark.asyncio
    async def test_successful_synthesis(self) -> None:
        speed = _make_mock_engine("kokoro")
        quality = _make_mock_engine("qwen3-tts")

        router = TTSRouter(
            tier_override={"speed": "kokoro", "quality": "qwen3-tts", "fallback": "qwen3-tts"}
        )
        router._engines = {"kokoro": speed, "qwen3-tts": quality}
        router._initialized = True

        result = await router.synthesize("The dragon attacks!", "combat")

        assert result.engine_name == "kokoro"
        speed.synthesize.assert_called_once()

    @pytest.mark.asyncio
    async def test_cascade_on_speed_failure(self) -> None:
        """When speed engine fails, cascade to quality, then fallback."""
        speed = _make_mock_engine("kokoro", fail_on_synthesize=True)
        quality = _make_mock_engine("qwen3-tts")
        fallback = _make_mock_engine("edge-tts")

        router = TTSRouter(
            tier_override={"speed": "kokoro", "quality": "qwen3-tts", "fallback": "edge-tts"}
        )
        router._engines = {
            "kokoro": speed,
            "qwen3-tts": quality,
            "edge-tts": fallback,
        }
        router._initialized = True

        result = await router.synthesize("The dragon attacks!", "combat")

        # Should have cascaded to quality engine
        assert result.engine_name == "qwen3-tts"
        speed.synthesize.assert_called_once()
        quality.synthesize.assert_called_once()

    @pytest.mark.asyncio
    async def test_cascade_to_fallback(self) -> None:
        """When speed and quality fail, cascade to fallback."""
        speed = _make_mock_engine("kokoro", fail_on_synthesize=True)
        quality = _make_mock_engine("qwen3-tts", fail_on_synthesize=True)
        fallback = _make_mock_engine("edge-tts")

        router = TTSRouter(
            tier_override={"speed": "kokoro", "quality": "qwen3-tts", "fallback": "edge-tts"}
        )
        router._engines = {
            "kokoro": speed,
            "qwen3-tts": quality,
            "edge-tts": fallback,
        }
        router._initialized = True

        result = await router.synthesize("The dragon attacks!", "combat")

        assert result.engine_name == "edge-tts"
        speed.synthesize.assert_called_once()
        quality.synthesize.assert_called_once()
        fallback.synthesize.assert_called_once()

    @pytest.mark.asyncio
    async def test_all_engines_fail_raises(self) -> None:
        """When all engines fail, raise RuntimeError."""
        speed = _make_mock_engine("kokoro", fail_on_synthesize=True)
        quality = _make_mock_engine("qwen3-tts", fail_on_synthesize=True)
        fallback = _make_mock_engine("edge-tts", fail_on_synthesize=True)

        router = TTSRouter(
            tier_override={"speed": "kokoro", "quality": "qwen3-tts", "fallback": "edge-tts"}
        )
        router._engines = {
            "kokoro": speed,
            "qwen3-tts": quality,
            "edge-tts": fallback,
        }
        router._initialized = True

        with pytest.raises(RuntimeError, match="All TTS engines failed"):
            await router.synthesize("The dragon attacks!", "combat")

    @pytest.mark.asyncio
    async def test_no_engines_raises(self) -> None:
        """When no engines are available, raise RuntimeError."""
        router = TTSRouter(
            tier_override={"speed": "kokoro", "quality": "qwen3-tts", "fallback": "edge-tts"}
        )
        router._engines = {}
        router._initialized = True

        with pytest.raises(RuntimeError, match="No TTS engines available"):
            await router.synthesize("test")

    @pytest.mark.asyncio
    async def test_narration_prefers_quality(self) -> None:
        """Narration context should try quality engine first."""
        speed = _make_mock_engine("kokoro")
        quality = _make_mock_engine("qwen3-tts")

        router = TTSRouter(
            tier_override={"speed": "kokoro", "quality": "qwen3-tts", "fallback": "qwen3-tts"}
        )
        router._engines = {"kokoro": speed, "qwen3-tts": quality}
        router._initialized = True

        result = await router.synthesize(
            "The ancient forest whispers with secrets...",
            "narration",
        )

        assert result.engine_name == "qwen3-tts"
        quality.synthesize.assert_called_once()
        speed.synthesize.assert_not_called()

    @pytest.mark.asyncio
    async def test_narration_cascade_to_speed_on_quality_failure(self) -> None:
        """When quality engine fails for narration, cascade to speed."""
        speed = _make_mock_engine("kokoro")
        quality = _make_mock_engine("qwen3-tts", fail_on_synthesize=True)

        router = TTSRouter(
            tier_override={"speed": "kokoro", "quality": "qwen3-tts", "fallback": "qwen3-tts"}
        )
        router._engines = {"kokoro": speed, "qwen3-tts": quality}
        router._initialized = True

        result = await router.synthesize("A mysterious voice...", "narration")

        assert result.engine_name == "kokoro"

    @pytest.mark.asyncio
    async def test_voice_config_passed_through(self) -> None:
        """Voice config should be passed to the engine."""
        speed = _make_mock_engine("kokoro")

        router = TTSRouter(
            tier_override={"speed": "kokoro", "quality": "kokoro", "fallback": "kokoro"}
        )
        router._engines = {"kokoro": speed}
        router._initialized = True

        config = VoiceConfig(language="it", speed=1.5)
        await router.synthesize("Ciao!", "combat", voice_config=config)

        speed.synthesize.assert_called_once_with("Ciao!", config)

    @pytest.mark.asyncio
    async def test_auto_initialize_on_first_synthesize(self) -> None:
        """Router should auto-initialize if synthesize is called before initialize."""
        mock_engine_cls = MagicMock(return_value=_make_mock_engine("edge-tts"))

        with patch(
            "dm20_protocol.voice.router._ENGINE_CLASSES",
            {"edge-tts": mock_engine_cls},
        ):
            router = TTSRouter(
                tier_override={"speed": "edge-tts", "quality": "edge-tts", "fallback": "edge-tts"}
            )

            result = await router.synthesize("auto-init test", "default")
            assert result.engine_name == "edge-tts"


# ---------------------------------------------------------------------------
# Router status and lifecycle tests
# ---------------------------------------------------------------------------


class TestTTSRouterLifecycle:
    """Tests for router lifecycle management."""

    def test_get_status_before_init(self) -> None:
        router = TTSRouter()
        status = router.get_status()
        assert status["initialized"] is False
        assert status["available_engines"] == []

    @pytest.mark.asyncio
    async def test_get_status_after_init(self) -> None:
        speed = _make_mock_engine("kokoro")

        router = TTSRouter(
            tier_override={"speed": "kokoro", "quality": "kokoro", "fallback": "kokoro"}
        )
        router._engines = {"kokoro": speed}
        router._initialized = True

        status = router.get_status()
        assert status["initialized"] is True
        assert "kokoro" in status["available_engines"]

    @pytest.mark.asyncio
    async def test_shutdown_clears_engines(self) -> None:
        speed = _make_mock_engine("kokoro")
        quality = _make_mock_engine("edge-tts")

        router = TTSRouter(
            tier_override={"speed": "kokoro", "quality": "edge-tts", "fallback": "edge-tts"}
        )
        router._engines = {"kokoro": speed, "edge-tts": quality}
        router._initialized = True

        await router.shutdown()

        assert router.engines == {}
        assert router._initialized is False
        speed.shutdown.assert_called_once()
        quality.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_warmup_specific_tiers(self) -> None:
        speed = _make_mock_engine("kokoro")
        quality = _make_mock_engine("qwen3-tts")

        router = TTSRouter(
            tier_override={"speed": "kokoro", "quality": "qwen3-tts", "fallback": "qwen3-tts"}
        )
        router._engines = {"kokoro": speed, "qwen3-tts": quality}
        router._initialized = True

        await router.warmup(tiers=["speed"])

        speed.warmup.assert_called_once()
        quality.warmup.assert_not_called()

    @pytest.mark.asyncio
    async def test_warmup_all_tiers(self) -> None:
        speed = _make_mock_engine("kokoro")
        quality = _make_mock_engine("qwen3-tts")
        fallback = _make_mock_engine("edge-tts")

        router = TTSRouter(
            tier_override={"speed": "kokoro", "quality": "qwen3-tts", "fallback": "edge-tts"}
        )
        router._engines = {
            "kokoro": speed,
            "qwen3-tts": quality,
            "edge-tts": fallback,
        }
        router._initialized = True

        await router.warmup()

        speed.warmup.assert_called_once()
        quality.warmup.assert_called_once()
        fallback.warmup.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_handles_engine_errors(self) -> None:
        """Shutdown should not raise even if an engine's shutdown fails."""
        speed = _make_mock_engine("kokoro")
        speed.shutdown = AsyncMock(side_effect=Exception("shutdown error"))
        quality = _make_mock_engine("edge-tts")

        router = TTSRouter(
            tier_override={"speed": "kokoro", "quality": "edge-tts", "fallback": "edge-tts"}
        )
        router._engines = {"kokoro": speed, "edge-tts": quality}
        router._initialized = True

        # Should not raise
        await router.shutdown()

        assert router._initialized is False


# ---------------------------------------------------------------------------
# Intel Mac tier tests
# ---------------------------------------------------------------------------


class TestTTSRouterIntelMac:
    """Tests simulating Intel Mac configuration."""

    @pytest.mark.asyncio
    async def test_intel_mac_uses_piper_for_speed(self) -> None:
        """Intel Mac should use Piper for speed tier."""
        piper = _make_mock_engine("piper")
        edge = _make_mock_engine("edge-tts")

        router = TTSRouter(
            tier_override={"speed": "piper", "quality": "edge-tts", "fallback": "edge-tts"}
        )
        router._engines = {"piper": piper, "edge-tts": edge}
        router._initialized = True

        result = await router.synthesize("Attack!", "combat")
        assert result.engine_name == "piper"

    @pytest.mark.asyncio
    async def test_intel_mac_uses_edge_for_quality(self) -> None:
        """Intel Mac should use Edge-TTS for quality tier."""
        piper = _make_mock_engine("piper")
        edge = _make_mock_engine("edge-tts")

        router = TTSRouter(
            tier_override={"speed": "piper", "quality": "edge-tts", "fallback": "edge-tts"}
        )
        router._engines = {"piper": piper, "edge-tts": edge}
        router._initialized = True

        result = await router.synthesize("The story unfolds...", "narration")
        assert result.engine_name == "edge-tts"

    @pytest.mark.asyncio
    async def test_intel_mac_cascade_piper_to_edge(self) -> None:
        """When Piper fails on Intel Mac, cascade to Edge-TTS."""
        piper = _make_mock_engine("piper", fail_on_synthesize=True)
        edge = _make_mock_engine("edge-tts")

        router = TTSRouter(
            tier_override={"speed": "piper", "quality": "edge-tts", "fallback": "edge-tts"}
        )
        router._engines = {"piper": piper, "edge-tts": edge}
        router._initialized = True

        result = await router.synthesize("Attack!", "combat")
        assert result.engine_name == "edge-tts"
