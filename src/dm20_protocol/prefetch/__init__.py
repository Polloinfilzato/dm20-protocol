"""
Prefetch Engine for dm20-protocol.

An intelligent prefetch system that anticipates likely DM responses by
monitoring game state context. In combat, pre-generates 2-3 narrative
variants (hit/miss/critical) using the campaign's main model, then uses
Haiku to select and refine the correct variant when the actual result
is known. This reduces response latency by 50%+.

Components:
- ContextObserver: Monitors game state and classifies context
- PrefetchCache: TTL-based cache for pre-generated variants
- PrefetchEngine: Pre-generation + refinement pipeline
- TokenUsage: Tracks token cost of prefetch operations

Usage:
    from dm20_protocol.prefetch import PrefetchEngine, PrefetchCache

    engine = PrefetchEngine(
        main_model=campaign_llm,
        refinement_model=haiku_llm,
        intensity="conservative",
    )

    # Feed game state updates
    engine.on_state_change(game_state)

    # Resolve with actual result (fast path via cache)
    narrative = await engine.resolve_with_actual(turn_id, actual_result)

    # Get token usage summary
    print(engine.get_token_summary())
"""

from .cache import PrefetchCache, PrefetchCacheStats, CacheEntry
from .observer import ContextObserver, GameContext, PlayerTurn
from .engine import PrefetchEngine, TokenUsage, LLMClient

__all__ = [
    # Engine
    "PrefetchEngine",
    "TokenUsage",
    "LLMClient",
    # Cache
    "PrefetchCache",
    "PrefetchCacheStats",
    "CacheEntry",
    # Observer
    "ContextObserver",
    "GameContext",
    "PlayerTurn",
]
