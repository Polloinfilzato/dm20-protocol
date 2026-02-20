"""
Tests for PrefetchEngine (Issue #172).

Tests cover:
- Variant pre-generation
- Refinement pipeline (select + refine with Haiku)
- Cache miss fallback to full generation
- Token usage tracking
- Integration with observer and cache
- Edge cases (errors, empty variants)
"""

from __future__ import annotations

from typing import Any

import pytest

from dm20_protocol.prefetch.cache import PrefetchCache
from dm20_protocol.prefetch.observer import ContextObserver, GameContext, PlayerTurn
from dm20_protocol.prefetch.engine import (
    PrefetchEngine,
    TokenUsage,
    ESTIMATED_FULL_GENERATION_TOKENS,
)

# Configure pytest to use anyio with asyncio backend for async tests
pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Mock LLM Client for testing
# ---------------------------------------------------------------------------


class MockLLMClient:
    """Mock LLM client for testing the prefetch engine."""

    def __init__(
        self,
        responses: list[str] | None = None,
        default_response: str = "Mock narrative response.",
    ) -> None:
        self.responses = responses or []
        self.default_response = default_response
        self.call_count = 0
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """Generate a mock response."""
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens})
        self.call_count += 1

        if not self.responses:
            return self.default_response

        response_index = (self.call_count - 1) % len(self.responses)
        return self.responses[response_index]


class FailingLLMClient:
    """Mock LLM client that always raises errors."""

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        raise RuntimeError("LLM API Error")


# ---------------------------------------------------------------------------
# Helper to create a standard PlayerTurn for tests
# ---------------------------------------------------------------------------


def make_player_turn(
    character_name: str = "Aragorn",
    character_class: str = "ranger",
    target_name: str = "Goblin",
    turn_id: str = "round_1_aragorn",
) -> PlayerTurn:
    """Create a test PlayerTurn."""
    return PlayerTurn(
        turn_id=turn_id,
        character_name=character_name,
        character_class=character_class,
        target_name=target_name,
        target_ac=15,
        weapon="longsword",
        action_type="attack",
    )


# ============================================================================
# Variant Pre-generation Tests
# ============================================================================


class TestPreGeneration:
    """Test variant pre-generation."""

    async def test_generates_three_variants(self):
        """Test that pre-generation creates 3 variants (hit/miss/crit)."""
        main_model = MockLLMClient(responses=[
            "The sword bites deep into the goblin's side.",
            "The blade whistles past, missing by inches.",
            "A devastating overhead strike cleaves through armor!",
        ])
        refinement_model = MockLLMClient()

        engine = PrefetchEngine(
            main_model=main_model,
            refinement_model=refinement_model,
            intensity="conservative",
        )

        turn = make_player_turn()
        game_state = {"combat_active": True}

        result = await engine.pre_generate_combat_variants(game_state, turn)

        assert result is True
        assert main_model.call_count == 3  # One per scenario

    async def test_variants_cached_after_generation(self):
        """Test that generated variants are stored in cache."""
        main_model = MockLLMClient(responses=["hit", "miss", "crit"])
        refinement_model = MockLLMClient()
        cache = PrefetchCache()

        engine = PrefetchEngine(
            main_model=main_model,
            refinement_model=refinement_model,
            cache=cache,
        )

        turn = make_player_turn()
        await engine.pre_generate_combat_variants({"combat_active": True}, turn)

        cached = cache.get(turn.turn_id)
        assert cached is not None
        assert len(cached) == 3

    async def test_skipped_when_intensity_off(self):
        """Test that pre-generation is skipped when intensity is off."""
        main_model = MockLLMClient()
        refinement_model = MockLLMClient()

        engine = PrefetchEngine(
            main_model=main_model,
            refinement_model=refinement_model,
            intensity="off",
        )

        turn = make_player_turn()
        result = await engine.pre_generate_combat_variants({}, turn)

        assert result is False
        assert main_model.call_count == 0

    async def test_partial_failure_still_caches(self):
        """Test that partial variant generation failures still cache what succeeded."""
        call_count = 0

        class PartialFailClient:
            async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise RuntimeError("API Error on second call")
                return f"Variant {call_count}"

        main_model = PartialFailClient()
        refinement_model = MockLLMClient()
        cache = PrefetchCache()

        engine = PrefetchEngine(
            main_model=main_model,
            refinement_model=refinement_model,
            cache=cache,
        )

        turn = make_player_turn()
        result = await engine.pre_generate_combat_variants(
            {"combat_active": True}, turn
        )

        assert result is True
        cached = cache.get(turn.turn_id)
        assert cached is not None
        assert len(cached) == 2  # Two out of three succeeded

    async def test_all_failures_returns_false(self):
        """Test that complete failure returns False and doesn't cache."""
        main_model = FailingLLMClient()
        refinement_model = MockLLMClient()
        cache = PrefetchCache()

        engine = PrefetchEngine(
            main_model=main_model,
            refinement_model=refinement_model,
            cache=cache,
        )

        turn = make_player_turn()
        result = await engine.pre_generate_combat_variants(
            {"combat_active": True}, turn
        )

        assert result is False
        assert cache.size == 0


# ============================================================================
# Refinement Pipeline Tests
# ============================================================================


class TestRefinementPipeline:
    """Test the Haiku refinement pipeline."""

    async def test_cache_hit_uses_refinement(self):
        """Test that cache hit triggers refinement model."""
        main_model = MockLLMClient()
        refinement_model = MockLLMClient(
            responses=["Refined: Aragorn's blade strikes true!"]
        )
        cache = PrefetchCache()

        # Pre-populate cache
        cache.store("round_1_aragorn", [
            "Hit variant",
            "Miss variant",
            "Critical variant",
        ])

        engine = PrefetchEngine(
            main_model=main_model,
            refinement_model=refinement_model,
            cache=cache,
        )

        actual_result = {
            "outcome": "hit",
            "roll": 18,
            "damage": 12,
            "target_hp": 25,
        }

        narrative = await engine.resolve_with_actual(
            "round_1_aragorn", actual_result
        )

        assert narrative == "Refined: Aragorn's blade strikes true!"
        assert refinement_model.call_count == 1
        assert main_model.call_count == 0  # Main model not needed

    async def test_variant_selection_by_outcome(self):
        """Test that the correct variant is selected based on outcome."""
        refinement_model = MockLLMClient(default_response="Refined text")
        cache = PrefetchCache()

        cache.store("turn_1", ["Hit text", "Miss text", "Crit text"])

        engine = PrefetchEngine(
            main_model=MockLLMClient(),
            refinement_model=refinement_model,
            cache=cache,
        )

        # Test hit selects index 0
        await engine.resolve_with_actual("turn_1", {"outcome": "hit"})
        assert "Hit text" in refinement_model.calls[0]["prompt"]

        # Re-populate cache (was consumed)
        cache.store("turn_1", ["Hit text", "Miss text", "Crit text"])

        # Test miss selects index 1
        await engine.resolve_with_actual("turn_1", {"outcome": "miss"})
        assert "Miss text" in refinement_model.calls[1]["prompt"]

        # Re-populate cache
        cache.store("turn_1", ["Hit text", "Miss text", "Crit text"])

        # Test critical selects index 2
        await engine.resolve_with_actual("turn_1", {"outcome": "critical"})
        assert "Crit text" in refinement_model.calls[2]["prompt"]

    async def test_variant_selection_fallback(self):
        """Test fallback when requested index exceeds available variants."""
        refinement_model = MockLLMClient(default_response="Refined")
        cache = PrefetchCache()

        # Only one variant available
        cache.store("turn_1", ["Only variant"])

        engine = PrefetchEngine(
            main_model=MockLLMClient(),
            refinement_model=refinement_model,
            cache=cache,
        )

        # Request "critical" (index 2) but only 1 variant exists
        await engine.resolve_with_actual("turn_1", {"outcome": "critical"})
        assert "Only variant" in refinement_model.calls[0]["prompt"]

    async def test_refinement_failure_falls_back_to_raw_variant(self):
        """Test that refinement failure falls back to raw variant text."""
        cache = PrefetchCache()
        cache.store("turn_1", ["Raw hit variant with {ROLL} damage"])

        engine = PrefetchEngine(
            main_model=MockLLMClient(),
            refinement_model=FailingLLMClient(),
            cache=cache,
        )

        actual_result = {
            "outcome": "hit",
            "roll": 18,
            "damage": 12,
            "target_hp": 25,
        }

        narrative = await engine.resolve_with_actual("turn_1", actual_result)

        # Should use basic replacement on raw variant
        assert "18" in narrative  # {ROLL} replaced

    async def test_cache_miss_uses_full_generation(self):
        """Test that cache miss falls back to full main model generation."""
        main_model = MockLLMClient(
            responses=["Full generation narrative"]
        )
        refinement_model = MockLLMClient()

        engine = PrefetchEngine(
            main_model=main_model,
            refinement_model=refinement_model,
            cache=PrefetchCache(),
        )

        actual_result = {
            "outcome": "hit",
            "character_name": "Aragorn",
            "target_name": "Goblin",
        }

        narrative = await engine.resolve_with_actual("missing_turn", actual_result)

        assert main_model.call_count == 1
        assert refinement_model.call_count == 0

    async def test_full_generation_failure_returns_fallback(self):
        """Test graceful fallback when full generation also fails."""
        engine = PrefetchEngine(
            main_model=FailingLLMClient(),
            refinement_model=MockLLMClient(),
            cache=PrefetchCache(),
        )

        narrative = await engine.resolve_with_actual(
            "missing_turn", {"outcome": "miss"}
        )

        assert "miss" in narrative.lower()


# ============================================================================
# Token Usage Tracking Tests
# ============================================================================


class TestTokenTracking:
    """Test token usage tracking."""

    async def test_prefetch_tokens_tracked(self):
        """Test that pre-generation token usage is tracked."""
        main_model = MockLLMClient(responses=[
            "Short variant one",
            "Short variant two",
            "Short variant three",
        ])

        engine = PrefetchEngine(
            main_model=main_model,
            refinement_model=MockLLMClient(),
        )

        turn = make_player_turn()
        await engine.pre_generate_combat_variants({"combat_active": True}, turn)

        usage = engine.get_token_usage()
        assert usage.prefetch_input_tokens > 0
        assert usage.prefetch_output_tokens > 0

    async def test_refinement_tokens_tracked(self):
        """Test that refinement token usage is tracked."""
        cache = PrefetchCache()
        cache.store("turn_1", ["variant"])

        engine = PrefetchEngine(
            main_model=MockLLMClient(),
            refinement_model=MockLLMClient(responses=["Refined text"]),
            cache=cache,
        )

        await engine.resolve_with_actual("turn_1", {"outcome": "hit"})

        usage = engine.get_token_usage()
        assert usage.refinement_input_tokens > 0
        assert usage.refinement_output_tokens > 0

    async def test_cache_hit_tracks_saved_tokens(self):
        """Test that cache hits track estimated saved tokens."""
        cache = PrefetchCache()
        cache.store("turn_1", ["variant"])

        engine = PrefetchEngine(
            main_model=MockLLMClient(),
            refinement_model=MockLLMClient(responses=["Refined"]),
            cache=cache,
        )

        await engine.resolve_with_actual("turn_1", {"outcome": "hit"})

        usage = engine.get_token_usage()
        assert usage.cache_hits == 1
        assert usage.estimated_tokens_saved == ESTIMATED_FULL_GENERATION_TOKENS

    async def test_cache_miss_tracked(self):
        """Test that cache misses are tracked."""
        engine = PrefetchEngine(
            main_model=MockLLMClient(),
            refinement_model=MockLLMClient(),
        )

        await engine.resolve_with_actual("missing", {"outcome": "hit"})

        usage = engine.get_token_usage()
        assert usage.cache_misses == 1

    def test_token_summary_format(self):
        """Test token usage summary format."""
        usage = TokenUsage(
            prefetch_input_tokens=500,
            prefetch_output_tokens=300,
            refinement_input_tokens=100,
            refinement_output_tokens=50,
            cache_hits=3,
            cache_misses=1,
            estimated_tokens_saved=2400,
        )

        summary = usage.to_summary()
        assert "950 tokens used" in summary
        assert "2400 tokens saved" in summary
        assert "75% cache hits" in summary
        assert "3/4" in summary

    def test_token_summary_no_lookups(self):
        """Test token summary with no lookups."""
        usage = TokenUsage()
        summary = usage.to_summary()
        assert "0% cache hits" in summary
        assert "0/0" in summary

    def test_total_tokens(self):
        """Test total token calculations."""
        usage = TokenUsage(
            prefetch_input_tokens=100,
            prefetch_output_tokens=50,
            refinement_input_tokens=30,
            refinement_output_tokens=20,
        )

        assert usage.total_prefetch_tokens == 150
        assert usage.total_refinement_tokens == 50
        assert usage.total_tokens_used == 200

    def test_net_tokens_saved(self):
        """Test net tokens saved calculation."""
        usage = TokenUsage(
            prefetch_input_tokens=100,
            prefetch_output_tokens=50,
            refinement_input_tokens=30,
            refinement_output_tokens=20,
            estimated_tokens_saved=800,
        )

        assert usage.net_tokens_saved == 600  # 800 - 200

    def test_reset_token_tracking(self):
        """Test resetting token usage counters."""
        engine = PrefetchEngine(
            main_model=MockLLMClient(),
            refinement_model=MockLLMClient(),
        )

        engine.token_usage.prefetch_input_tokens = 500
        engine.token_usage.cache_hits = 5

        engine.reset_token_tracking()

        usage = engine.get_token_usage()
        assert usage.prefetch_input_tokens == 0
        assert usage.cache_hits == 0

    def test_token_usage_reset_method(self):
        """Test the TokenUsage reset method."""
        usage = TokenUsage(
            prefetch_input_tokens=100,
            prefetch_output_tokens=50,
            cache_hits=3,
        )

        usage.reset()

        assert usage.prefetch_input_tokens == 0
        assert usage.prefetch_output_tokens == 0
        assert usage.cache_hits == 0


# ============================================================================
# Invalidation Tests
# ============================================================================


class TestEngineInvalidation:
    """Test engine-level cache invalidation."""

    def test_invalidate_turn(self):
        """Test invalidating a specific turn."""
        cache = PrefetchCache()
        cache.store("round_1_aragorn", ["v1", "v2", "v3"])

        engine = PrefetchEngine(
            main_model=MockLLMClient(),
            refinement_model=MockLLMClient(),
            cache=cache,
        )

        result = engine.invalidate_turn("round_1_aragorn")

        assert result is True
        assert cache.get("round_1_aragorn") is None

    def test_invalidate_combat(self):
        """Test invalidating all combat variants."""
        cache = PrefetchCache()
        cache.store("round_1_aragorn", ["v1"])
        cache.store("round_1_legolas", ["v2"])
        cache.store("round_2_gimli", ["v3"])

        engine = PrefetchEngine(
            main_model=MockLLMClient(),
            refinement_model=MockLLMClient(),
            cache=cache,
        )

        count = engine.invalidate_combat()

        assert count == 3
        assert cache.size == 0


# ============================================================================
# Engine Configuration Tests
# ============================================================================


class TestEngineConfiguration:
    """Test engine configuration and intensity settings."""

    def test_default_intensity(self):
        """Test default intensity is conservative."""
        engine = PrefetchEngine(
            main_model=MockLLMClient(),
            refinement_model=MockLLMClient(),
        )

        assert engine.intensity == "conservative"

    def test_intensity_setter(self):
        """Test changing intensity at runtime."""
        engine = PrefetchEngine(
            main_model=MockLLMClient(),
            refinement_model=MockLLMClient(),
            intensity="conservative",
        )

        engine.intensity = "aggressive"
        assert engine.intensity == "aggressive"

    def test_on_state_change_delegates_to_observer(self):
        """Test that on_state_change delegates to the observer."""
        engine = PrefetchEngine(
            main_model=MockLLMClient(),
            refinement_model=MockLLMClient(),
            intensity="conservative",
        )

        context = engine.on_state_change({"combat_active": True})
        assert context == GameContext.COMBAT


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for the full prefetch pipeline."""

    async def test_full_pipeline_hit(self):
        """Test the complete pipeline: pre-generate -> resolve with hit."""
        main_model = MockLLMClient(responses=[
            "The sword strikes the goblin's {ROLL} armor!",
            "The blade swings wide, missing entirely.",
            "A devastating critical blow!",
        ])
        refinement_model = MockLLMClient(
            responses=["Aragorn's longsword bites deep, dealing 12 damage!"]
        )

        engine = PrefetchEngine(
            main_model=main_model,
            refinement_model=refinement_model,
            intensity="conservative",
        )

        # Step 1: Pre-generate
        turn = make_player_turn()
        game_state = {"combat_active": True}
        success = await engine.pre_generate_combat_variants(game_state, turn)
        assert success is True

        # Step 2: Resolve with actual result
        actual = {
            "outcome": "hit",
            "roll": 18,
            "damage": 12,
            "target_hp": 25,
        }
        narrative = await engine.resolve_with_actual(turn.turn_id, actual)

        assert "Aragorn" in narrative
        assert refinement_model.call_count == 1

        # Step 3: Check token tracking
        usage = engine.get_token_usage()
        assert usage.cache_hits == 1
        assert usage.cache_misses == 0
        assert usage.estimated_tokens_saved > 0

    async def test_full_pipeline_cache_miss(self):
        """Test pipeline when cache misses (no pre-generation)."""
        main_model = MockLLMClient(
            responses=["Aragorn swings and connects!"]
        )
        refinement_model = MockLLMClient()

        engine = PrefetchEngine(
            main_model=main_model,
            refinement_model=refinement_model,
            intensity="conservative",
        )

        # Resolve without pre-generating
        actual = {
            "outcome": "hit",
            "character_name": "Aragorn",
            "target_name": "Goblin",
        }
        narrative = await engine.resolve_with_actual("unknown_turn", actual)

        assert main_model.call_count == 1
        assert refinement_model.call_count == 0

        usage = engine.get_token_usage()
        assert usage.cache_hits == 0
        assert usage.cache_misses == 1

    async def test_multiple_turns_sequential(self):
        """Test handling multiple sequential turns."""
        main_model = MockLLMClient(default_response="Variant text")
        refinement_model = MockLLMClient(default_response="Refined text")

        engine = PrefetchEngine(
            main_model=main_model,
            refinement_model=refinement_model,
            intensity="conservative",
        )

        # Pre-generate for two turns
        turn1 = make_player_turn(
            character_name="Aragorn",
            turn_id="round_1_aragorn",
        )
        turn2 = make_player_turn(
            character_name="Legolas",
            turn_id="round_1_legolas",
        )

        await engine.pre_generate_combat_variants({"combat_active": True}, turn1)
        await engine.pre_generate_combat_variants({"combat_active": True}, turn2)

        # Resolve both
        await engine.resolve_with_actual(
            "round_1_aragorn", {"outcome": "hit"}
        )
        await engine.resolve_with_actual(
            "round_1_legolas", {"outcome": "miss"}
        )

        usage = engine.get_token_usage()
        assert usage.cache_hits == 2

    async def test_get_token_summary(self):
        """Test getting a human-readable token summary."""
        engine = PrefetchEngine(
            main_model=MockLLMClient(),
            refinement_model=MockLLMClient(),
        )

        summary = engine.get_token_summary()
        assert "Prefetch:" in summary
        assert "tokens used" in summary
        assert "tokens saved" in summary
        assert "cache hits" in summary
