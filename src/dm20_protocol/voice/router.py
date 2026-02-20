"""
TTS Router for 3-tier engine selection.

The TTSRouter selects the best TTS engine based on the current context
(combat, narration, dialogue) and hardware capabilities. It implements
graceful degradation: if the preferred engine fails, it cascades to
the next available tier.

Tier hierarchy (Apple Silicon):
  1. Speed (Kokoro) - combat, action descriptions
  2. Quality (Qwen3-TTS) - narration, NPC dialogue
  3. Fallback (Edge-TTS) - cloud-based when local engines unavailable

Tier hierarchy (Intel Mac / Other):
  1. Speed (Piper) - combat, action descriptions
  2. Quality (Edge-TTS) - narration, NPC dialogue
  3. Fallback (Edge-TTS) - same as quality tier
"""

import logging
from enum import Enum
from typing import Optional

from .engines.base import TTSEngine, TTSResult, VoiceConfig
from .engines.edge_tts import EdgeTTSEngine
from .engines.kokoro import KokoroEngine
from .engines.piper import PiperEngine
from .engines.qwen3 import Qwen3TTSEngine
from .hardware import get_available_tiers

logger = logging.getLogger("dm20-protocol.voice.router")


class SynthesisContext(Enum):
    """Context types that influence engine selection.

    The context determines which tier (speed vs quality) is preferred:
    - COMBAT contexts prioritize low latency.
    - NARRATION/DIALOGUE contexts prioritize voice quality.
    """

    COMBAT = "combat"
    NARRATION = "narration"
    DIALOGUE = "dialogue"
    AMBIENT = "ambient"
    DEFAULT = "default"


# Map context to preferred tier
_CONTEXT_TIER_MAP: dict[SynthesisContext, str] = {
    SynthesisContext.COMBAT: "speed",
    SynthesisContext.NARRATION: "quality",
    SynthesisContext.DIALOGUE: "quality",
    SynthesisContext.AMBIENT: "quality",
    SynthesisContext.DEFAULT: "speed",
}

# Engine name to class mapping
_ENGINE_CLASSES: dict[str, type[TTSEngine]] = {
    "kokoro": KokoroEngine,
    "qwen3-tts": Qwen3TTSEngine,
    "edge-tts": EdgeTTSEngine,
    "piper": PiperEngine,
}


class TTSRouter:
    """3-tier TTS router with context-based engine selection and graceful cascade.

    The router initializes available engines based on hardware detection,
    then selects the appropriate engine for each synthesis request based
    on the context (combat -> speed, narration -> quality). If the selected
    engine fails, the router cascades through remaining tiers.

    Usage:
        router = TTSRouter()
        await router.initialize()
        result = await router.synthesize("The dragon attacks!", "combat")
        await router.shutdown()
    """

    def __init__(self, tier_override: Optional[dict[str, str]] = None) -> None:
        """Initialize the TTS router.

        Args:
            tier_override: Optional override for tier-to-engine mapping.
                           If None, auto-detect based on hardware.
        """
        self._tier_map: dict[str, str] = tier_override or get_available_tiers()
        self._engines: dict[str, TTSEngine] = {}
        self._initialized = False

    @property
    def tier_map(self) -> dict[str, str]:
        """Current tier-to-engine mapping."""
        return dict(self._tier_map)

    @property
    def engines(self) -> dict[str, TTSEngine]:
        """Currently loaded engines by name."""
        return dict(self._engines)

    async def initialize(self) -> None:
        """Initialize and validate available engines.

        Creates engine instances for each tier and checks availability.
        Engines whose dependencies are not installed are logged but
        do not prevent initialization.
        """
        if self._initialized:
            return

        # Collect unique engine names from tiers
        engine_names = set(self._tier_map.values())

        for engine_name in engine_names:
            cls = _ENGINE_CLASSES.get(engine_name)
            if cls is None:
                logger.warning("Unknown engine '%s' in tier map, skipping", engine_name)
                continue

            engine = cls()
            if engine.is_available():
                self._engines[engine_name] = engine
                logger.info("Engine '%s' is available", engine_name)
            else:
                logger.info(
                    "Engine '%s' is not available (dependencies not installed)",
                    engine_name,
                )

        self._initialized = True

        available = list(self._engines.keys())
        unavailable = [n for n in engine_names if n not in self._engines]
        logger.info(
            "TTSRouter initialized: available=%s, unavailable=%s",
            available,
            unavailable,
        )

    async def warmup(self, tiers: Optional[list[str]] = None) -> None:
        """Warmup engines for specific tiers (preload models).

        Args:
            tiers: List of tier names to warmup. If None, warmup all.
        """
        target_tiers = tiers or list(self._tier_map.keys())

        for tier in target_tiers:
            engine_name = self._tier_map.get(tier)
            if engine_name and engine_name in self._engines:
                try:
                    await self._engines[engine_name].warmup()
                    logger.info("Warmed up engine '%s' for tier '%s'", engine_name, tier)
                except Exception as exc:
                    logger.warning(
                        "Warmup failed for engine '%s': %s", engine_name, exc
                    )

    def _select_engine(self, context: str) -> Optional[TTSEngine]:
        """Select the best available engine for a given context.

        Args:
            context: Synthesis context string (maps to SynthesisContext).

        Returns:
            The best available TTSEngine, or None if no engines are available.
        """
        try:
            ctx = SynthesisContext(context)
        except ValueError:
            ctx = SynthesisContext.DEFAULT

        preferred_tier = _CONTEXT_TIER_MAP.get(ctx, "speed")
        engine_name = self._tier_map.get(preferred_tier)

        if engine_name and engine_name in self._engines:
            return self._engines[engine_name]

        # If preferred engine not available, fall through tiers
        return None

    def _get_cascade_order(self, context: str) -> list[TTSEngine]:
        """Get engines in cascade order for a given context.

        The cascade starts with the context-preferred engine, then
        falls through remaining tiers in priority order.

        Args:
            context: Synthesis context string.

        Returns:
            List of available engines in cascade order.
        """
        try:
            ctx = SynthesisContext(context)
        except ValueError:
            ctx = SynthesisContext.DEFAULT

        preferred_tier = _CONTEXT_TIER_MAP.get(ctx, "speed")

        # Build tier priority: preferred first, then others
        tier_order = ["speed", "quality", "fallback"]
        if preferred_tier in tier_order:
            tier_order.remove(preferred_tier)
            tier_order.insert(0, preferred_tier)

        # Collect unique engines in order
        seen: set[str] = set()
        cascade: list[TTSEngine] = []

        for tier in tier_order:
            engine_name = self._tier_map.get(tier)
            if engine_name and engine_name not in seen and engine_name in self._engines:
                seen.add(engine_name)
                cascade.append(self._engines[engine_name])

        return cascade

    async def synthesize(
        self,
        text: str,
        context: str = "default",
        voice_config: Optional[VoiceConfig] = None,
    ) -> TTSResult:
        """Synthesize text with automatic engine selection and cascade.

        Selects the best engine based on context, then falls through
        remaining tiers on failure.

        Args:
            text: Text to convert to speech.
            context: Synthesis context ("combat", "narration", "dialogue",
                     "ambient", or "default").
            voice_config: Optional voice configuration.

        Returns:
            TTSResult with audio data.

        Raises:
            RuntimeError: If all engines fail or no engines are available.
        """
        if not self._initialized:
            await self.initialize()

        cascade = self._get_cascade_order(context)

        if not cascade:
            raise RuntimeError(
                "No TTS engines available. Install voice dependencies: "
                "pip install dm20-protocol[voice]"
            )

        errors: list[str] = []

        for engine in cascade:
            try:
                logger.debug(
                    "Attempting synthesis with engine '%s' for context '%s'",
                    engine.name,
                    context,
                )
                result = await engine.synthesize(text, voice_config)
                logger.info(
                    "Synthesis succeeded with engine '%s' (context='%s')",
                    engine.name,
                    context,
                )
                return result
            except Exception as exc:
                error_msg = f"{engine.name}: {exc}"
                errors.append(error_msg)
                logger.warning(
                    "Engine '%s' failed, cascading to next: %s",
                    engine.name,
                    exc,
                )

        raise RuntimeError(
            f"All TTS engines failed. Errors: {'; '.join(errors)}"
        )

    def get_engine_for_context(self, context: str) -> Optional[str]:
        """Get the engine name that would be selected for a context.

        Useful for debugging and UI display.

        Args:
            context: Synthesis context string.

        Returns:
            Engine name, or None if no engine is available.
        """
        engine = self._select_engine(context)
        return engine.name if engine else None

    def get_status(self) -> dict[str, object]:
        """Get a status summary of the router and its engines.

        Returns:
            Dictionary with router status information.
        """
        return {
            "initialized": self._initialized,
            "tier_map": dict(self._tier_map),
            "available_engines": list(self._engines.keys()),
            "engine_details": {
                name: {
                    "available": engine.is_available(),
                    "languages": engine.supported_languages(),
                }
                for name, engine in self._engines.items()
            },
        }

    async def shutdown(self) -> None:
        """Shut down all engines and release resources."""
        for name, engine in self._engines.items():
            try:
                await engine.shutdown()
                logger.debug("Engine '%s' shut down", name)
            except Exception as exc:
                logger.warning("Error shutting down engine '%s': %s", name, exc)

        self._engines.clear()
        self._initialized = False
        logger.info("TTSRouter shut down")
