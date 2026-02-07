"""
Unit tests for AtmosphereManager.

Tests tone detection, pacing selection, tension management, and LLM-based
atmosphere enhancement. All tests use mocked LLM clients.
"""

import asyncio
import pytest
from typing import Any

from gamemaster_mcp.claudmaster.atmosphere import (
    AtmosphereManager,
    Tone,
    Pacing,
    SceneType,
    SceneContext,
    TensionState,
    TONE_INDICATORS,
    PACING_BY_SCENE,
    TONE_MODIFIERS,
)


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------

class MockLLM:
    """LLM client that returns canned responses and records calls."""

    def __init__(self, response: str = "Enhanced atmospheric narrative.") -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens})
        return self.response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm() -> MockLLM:
    return MockLLM()


@pytest.fixture
def atmosphere_manager(mock_llm: MockLLM) -> AtmosphereManager:
    return AtmosphereManager(llm=mock_llm, max_tokens=512)


@pytest.fixture
def horror_scene() -> SceneContext:
    return SceneContext(
        scene_type=SceneType.EXPLORATION,
        description="A dark crypt filled with the stench of decay",
        keywords=["dark", "undead", "blood", "decay"],
        creature_types=["zombie", "skeleton"],
        environment="crypt",
    )


@pytest.fixture
def heroic_scene() -> SceneContext:
    return SceneContext(
        scene_type=SceneType.COMBAT,
        description="A legendary battle against a mighty dragon",
        keywords=["glory", "battle", "legendary", "epic"],
        creature_types=["dragon"],
        environment="battlefield",
    )


@pytest.fixture
def neutral_scene() -> SceneContext:
    return SceneContext(
        scene_type=SceneType.EXPLORATION,
        description="A simple room with basic furniture",
        keywords=[],
        creature_types=[],
        environment="room",
    )


@pytest.fixture
def mysterious_scene() -> SceneContext:
    return SceneContext(
        scene_type=SceneType.PUZZLE,
        description="Ancient ruins with strange arcane symbols",
        keywords=["ancient", "arcane", "mysterious", "riddle"],
        creature_types=["construct"],
        environment="ruins",
    )


@pytest.fixture
def peaceful_scene() -> SceneContext:
    return SceneContext(
        scene_type=SceneType.REST,
        description="A tranquil meadow with gentle breeze",
        keywords=["calm", "peaceful", "tranquil", "safe"],
        creature_types=["beast"],
        environment="meadow",
    )


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class TestTensionState:
    """Tests for TensionState model."""

    def test_default_values(self) -> None:
        tension = TensionState()
        assert tension.level == 0.5
        assert tension.build_rate == 0.1
        assert tension.release_rate == 0.15
        assert tension.peak_threshold == 0.9

    def test_custom_values(self) -> None:
        tension = TensionState(level=0.8, build_rate=0.2, release_rate=0.3, peak_threshold=0.95)
        assert tension.level == 0.8
        assert tension.build_rate == 0.2
        assert tension.release_rate == 0.3
        assert tension.peak_threshold == 0.95


class TestSceneContext:
    """Tests for SceneContext model."""

    def test_default_values(self) -> None:
        scene = SceneContext()
        assert scene.scene_type == SceneType.EXPLORATION
        assert scene.description == ""
        assert scene.keywords == []
        assert scene.creature_types == []
        assert scene.environment == ""
        assert scene.time_of_day == ""
        assert scene.metadata == {}

    def test_custom_values(self) -> None:
        scene = SceneContext(
            scene_type=SceneType.COMBAT,
            description="A battle scene",
            keywords=["fight", "danger"],
            creature_types=["goblin"],
            environment="cave",
            time_of_day="night",
            metadata={"player_level": 5},
        )
        assert scene.scene_type == SceneType.COMBAT
        assert scene.description == "A battle scene"
        assert scene.keywords == ["fight", "danger"]
        assert scene.creature_types == ["goblin"]
        assert scene.environment == "cave"
        assert scene.time_of_day == "night"
        assert scene.metadata == {"player_level": 5}


# ---------------------------------------------------------------------------
# Tone Detection Tests
# ---------------------------------------------------------------------------

class TestToneDetection:
    """Tests for tone detection based on scene context."""

    def test_detect_horror_tone_from_keywords(self, atmosphere_manager: AtmosphereManager, horror_scene: SceneContext) -> None:
        tone = atmosphere_manager.detect_tone(horror_scene)
        assert tone == Tone.HORROR

    def test_detect_heroic_tone_from_keywords(self, atmosphere_manager: AtmosphereManager, heroic_scene: SceneContext) -> None:
        tone = atmosphere_manager.detect_tone(heroic_scene)
        assert tone == Tone.HEROIC

    def test_detect_mysterious_tone(self, atmosphere_manager: AtmosphereManager, mysterious_scene: SceneContext) -> None:
        tone = atmosphere_manager.detect_tone(mysterious_scene)
        assert tone == Tone.MYSTERIOUS

    def test_detect_peaceful_tone(self, atmosphere_manager: AtmosphereManager, peaceful_scene: SceneContext) -> None:
        tone = atmosphere_manager.detect_tone(peaceful_scene)
        assert tone == Tone.PEACEFUL

    def test_detect_neutral_for_generic_scene(self, atmosphere_manager: AtmosphereManager, neutral_scene: SceneContext) -> None:
        tone = atmosphere_manager.detect_tone(neutral_scene)
        assert tone == Tone.NEUTRAL

    def test_detect_tone_from_creature_types(self, atmosphere_manager: AtmosphereManager) -> None:
        scene = SceneContext(
            description="A creature approaches",
            creature_types=["undead", "fiend"],
        )
        tone = atmosphere_manager.detect_tone(scene)
        assert tone == Tone.HORROR

    def test_detect_tone_from_environment(self, atmosphere_manager: AtmosphereManager) -> None:
        scene = SceneContext(
            description="You stand here",
            environment="graveyard",
        )
        tone = atmosphere_manager.detect_tone(scene)
        assert tone == Tone.HORROR

    def test_detect_tone_from_description_text(self, atmosphere_manager: AtmosphereManager) -> None:
        scene = SceneContext(
            description="The dark shadows creep with undead corruption and blood",
            keywords=[],
            creature_types=[],
            environment="",
        )
        tone = atmosphere_manager.detect_tone(scene)
        assert tone == Tone.HORROR

    def test_multiple_tone_indicators_highest_score_wins(self, atmosphere_manager: AtmosphereManager) -> None:
        # Mix horror and heroic, but horror should score higher
        scene = SceneContext(
            description="A dark crypt with undead",
            keywords=["dark", "undead", "glory"],  # 2 horror, 1 heroic
            creature_types=["zombie"],  # horror
            environment="crypt",  # horror
        )
        tone = atmosphere_manager.detect_tone(scene)
        assert tone == Tone.HORROR

    def test_empty_scene_returns_neutral(self, atmosphere_manager: AtmosphereManager) -> None:
        scene = SceneContext()
        tone = atmosphere_manager.detect_tone(scene)
        assert tone == Tone.NEUTRAL


# ---------------------------------------------------------------------------
# Pacing Tests
# ---------------------------------------------------------------------------

class TestPacing:
    """Tests for pacing selection based on scene type."""

    def test_combat_scene_fast_pacing(self, atmosphere_manager: AtmosphereManager) -> None:
        pacing = atmosphere_manager.get_pacing(SceneType.COMBAT)
        assert pacing == Pacing.FAST

    def test_exploration_scene_deliberate_pacing(self, atmosphere_manager: AtmosphereManager) -> None:
        pacing = atmosphere_manager.get_pacing(SceneType.EXPLORATION)
        assert pacing == Pacing.DELIBERATE

    def test_social_scene_normal_pacing(self, atmosphere_manager: AtmosphereManager) -> None:
        pacing = atmosphere_manager.get_pacing(SceneType.SOCIAL)
        assert pacing == Pacing.NORMAL

    def test_puzzle_scene_slow_pacing(self, atmosphere_manager: AtmosphereManager) -> None:
        pacing = atmosphere_manager.get_pacing(SceneType.PUZZLE)
        assert pacing == Pacing.SLOW

    def test_rest_scene_slow_pacing(self, atmosphere_manager: AtmosphereManager) -> None:
        pacing = atmosphere_manager.get_pacing(SceneType.REST)
        assert pacing == Pacing.SLOW

    def test_transition_scene_normal_pacing(self, atmosphere_manager: AtmosphereManager) -> None:
        pacing = atmosphere_manager.get_pacing(SceneType.TRANSITION)
        assert pacing == Pacing.NORMAL


# ---------------------------------------------------------------------------
# Tension Management Tests
# ---------------------------------------------------------------------------

class TestTensionManagement:
    """Tests for tension level management."""

    def test_initial_tension_level(self, atmosphere_manager: AtmosphereManager) -> None:
        assert atmosphere_manager.tension.level == 0.5

    def test_increase_tension(self, atmosphere_manager: AtmosphereManager) -> None:
        new_level = atmosphere_manager.update_tension(0.2)
        assert new_level == 0.7
        assert atmosphere_manager.tension.level == 0.7

    def test_decrease_tension(self, atmosphere_manager: AtmosphereManager) -> None:
        new_level = atmosphere_manager.update_tension(-0.3)
        assert new_level == 0.2
        assert atmosphere_manager.tension.level == 0.2

    def test_tension_clamped_at_maximum(self, atmosphere_manager: AtmosphereManager) -> None:
        new_level = atmosphere_manager.update_tension(0.8)
        assert new_level == 1.0
        assert atmosphere_manager.tension.level == 1.0

    def test_tension_clamped_at_minimum(self, atmosphere_manager: AtmosphereManager) -> None:
        new_level = atmosphere_manager.update_tension(-1.0)
        assert new_level == 0.0
        assert atmosphere_manager.tension.level == 0.0

    def test_multiple_tension_updates(self, atmosphere_manager: AtmosphereManager) -> None:
        atmosphere_manager.update_tension(0.2)  # 0.7
        atmosphere_manager.update_tension(0.1)  # 0.8
        final = atmosphere_manager.update_tension(-0.3)  # 0.5
        assert abs(final - 0.5) < 0.0001  # Use tolerance for floating point


# ---------------------------------------------------------------------------
# Tone Modifiers Tests
# ---------------------------------------------------------------------------

class TestToneModifiers:
    """Tests for retrieving tone modifiers."""

    def test_get_horror_modifiers(self, atmosphere_manager: AtmosphereManager) -> None:
        modifiers = atmosphere_manager.get_tone_modifiers(Tone.HORROR)
        assert "verbs" in modifiers
        assert "adjectives" in modifiers
        assert "sentence_style" in modifiers
        assert "sensory_focus" in modifiers
        assert "creeps" in modifiers["verbs"]
        assert "cold" in modifiers["adjectives"]

    def test_get_heroic_modifiers(self, atmosphere_manager: AtmosphereManager) -> None:
        modifiers = atmosphere_manager.get_tone_modifiers(Tone.HEROIC)
        assert "verbs" in modifiers
        assert "charges" in modifiers["verbs"]
        assert "gleaming" in modifiers["adjectives"]

    def test_get_modifiers_for_undefined_tone(self, atmosphere_manager: AtmosphereManager) -> None:
        modifiers = atmosphere_manager.get_tone_modifiers(Tone.NEUTRAL)
        assert modifiers == {}

    def test_all_defined_modifiers_have_required_keys(self) -> None:
        required_keys = {"verbs", "adjectives", "sentence_style", "sensory_focus"}
        for tone, modifiers in TONE_MODIFIERS.items():
            assert required_keys.issubset(modifiers.keys()), f"Tone {tone} missing required keys"


# ---------------------------------------------------------------------------
# LLM Integration Tests
# ---------------------------------------------------------------------------

class TestApplyAtmosphere:
    """Tests for applying atmospheric tone via LLM."""

    def test_apply_atmosphere_calls_llm(self, atmosphere_manager: AtmosphereManager, mock_llm: MockLLM) -> None:
        narrative = "You enter a room."
        result = asyncio.run(atmosphere_manager.apply_atmosphere(narrative, Tone.HORROR, intensity=0.7))

        assert len(mock_llm.calls) == 1
        assert mock_llm.calls[0]["max_tokens"] == 512
        assert "horror" in mock_llm.calls[0]["prompt"].lower()
        assert narrative in mock_llm.calls[0]["prompt"]
        assert result == "Enhanced atmospheric narrative."

    def test_apply_atmosphere_with_different_intensities(
        self, atmosphere_manager: AtmosphereManager, mock_llm: MockLLM
    ) -> None:
        narrative = "A dark corridor."

        # Low intensity
        asyncio.run(atmosphere_manager.apply_atmosphere(narrative, Tone.HORROR, intensity=0.2))
        assert "0.2" in mock_llm.calls[0]["prompt"]

        # High intensity
        mock_llm.calls.clear()
        asyncio.run(atmosphere_manager.apply_atmosphere(narrative, Tone.HORROR, intensity=0.9))
        assert "0.9" in mock_llm.calls[0]["prompt"]

    def test_apply_atmosphere_clamps_intensity(
        self, atmosphere_manager: AtmosphereManager, mock_llm: MockLLM
    ) -> None:
        narrative = "A scene."

        # Test upper bound
        asyncio.run(atmosphere_manager.apply_atmosphere(narrative, Tone.HORROR, intensity=1.5))
        assert "1.0" in mock_llm.calls[0]["prompt"]

        # Test lower bound
        mock_llm.calls.clear()
        asyncio.run(atmosphere_manager.apply_atmosphere(narrative, Tone.HORROR, intensity=-0.5))
        assert "0.0" in mock_llm.calls[0]["prompt"]

    def test_apply_atmosphere_with_undefined_tone_uses_fallback(
        self, atmosphere_manager: AtmosphereManager, mock_llm: MockLLM
    ) -> None:
        narrative = "A scene."
        result = asyncio.run(atmosphere_manager.apply_atmosphere(narrative, Tone.NEUTRAL, intensity=0.5))

        # Should still call LLM with fallback modifiers
        assert len(mock_llm.calls) == 1
        assert "neutral" in mock_llm.calls[0]["prompt"].lower()
        assert result == "Enhanced atmospheric narrative."

    def test_apply_atmosphere_includes_tone_modifiers(
        self, atmosphere_manager: AtmosphereManager, mock_llm: MockLLM
    ) -> None:
        narrative = "A dark place."
        asyncio.run(atmosphere_manager.apply_atmosphere(narrative, Tone.HORROR, intensity=0.6))

        prompt = mock_llm.calls[0]["prompt"]
        # Check that horror-specific modifiers are in the prompt
        assert any(verb in prompt for verb in ["creeps", "lurks", "slithers"])
        assert any(adj in prompt for adj in ["cold", "damp", "rotting"])


class TestBuildTension:
    """Tests for building tension via LLM."""

    def test_build_tension_calls_llm(self, atmosphere_manager: AtmosphereManager, mock_llm: MockLLM) -> None:
        description = "A quiet hallway."
        result = asyncio.run(atmosphere_manager.build_tension(description, target_level=0.8))

        assert len(mock_llm.calls) == 1
        assert mock_llm.calls[0]["max_tokens"] == 512
        assert description in mock_llm.calls[0]["prompt"]
        assert "0.8" in mock_llm.calls[0]["prompt"]
        assert result == "Enhanced atmospheric narrative."

    def test_build_tension_with_different_levels(
        self, atmosphere_manager: AtmosphereManager, mock_llm: MockLLM
    ) -> None:
        description = "A room."

        # Low tension
        asyncio.run(atmosphere_manager.build_tension(description, target_level=0.2))
        assert "0.2" in mock_llm.calls[0]["prompt"]

        # High tension
        mock_llm.calls.clear()
        asyncio.run(atmosphere_manager.build_tension(description, target_level=0.95))
        assert "0.9" in mock_llm.calls[0]["prompt"] or "1.0" in mock_llm.calls[0]["prompt"]

    def test_build_tension_clamps_target_level(
        self, atmosphere_manager: AtmosphereManager, mock_llm: MockLLM
    ) -> None:
        description = "A scene."

        # Test upper bound
        asyncio.run(atmosphere_manager.build_tension(description, target_level=1.5))
        assert "1.0" in mock_llm.calls[0]["prompt"]

        # Test lower bound
        mock_llm.calls.clear()
        asyncio.run(atmosphere_manager.build_tension(description, target_level=-0.3))
        assert "0.0" in mock_llm.calls[0]["prompt"]


class TestTransitionTone:
    """Tests for tone transitions via LLM."""

    def test_transition_tone_calls_llm(self, atmosphere_manager: AtmosphereManager, mock_llm: MockLLM) -> None:
        result = asyncio.run(atmosphere_manager.transition_tone(
            from_tone=Tone.PEACEFUL,
            to_tone=Tone.HORROR,
            trigger="a scream echoes from the darkness"
        ))

        assert len(mock_llm.calls) == 1
        assert mock_llm.calls[0]["max_tokens"] == 512
        prompt = mock_llm.calls[0]["prompt"]
        assert "peaceful" in prompt.lower()
        assert "horror" in prompt.lower()
        assert "scream echoes" in prompt.lower()
        assert result == "Enhanced atmospheric narrative."

    def test_transition_tone_different_combinations(
        self, atmosphere_manager: AtmosphereManager, mock_llm: MockLLM
    ) -> None:
        # Heroic to Tragic
        asyncio.run(atmosphere_manager.transition_tone(
            from_tone=Tone.HEROIC,
            to_tone=Tone.TRAGIC,
            trigger="the champion falls"
        ))
        prompt = mock_llm.calls[0]["prompt"]
        assert "heroic" in prompt.lower()
        assert "tragic" in prompt.lower()
        assert "champion falls" in prompt.lower()


# ---------------------------------------------------------------------------
# Set Scene Tests
# ---------------------------------------------------------------------------

class TestSetScene:
    """Tests for the set_scene convenience method."""

    def test_set_scene_updates_tone_and_pacing(
        self, atmosphere_manager: AtmosphereManager, horror_scene: SceneContext
    ) -> None:
        tone, pacing = atmosphere_manager.set_scene(horror_scene)

        assert tone == Tone.HORROR
        assert pacing == Pacing.DELIBERATE
        assert atmosphere_manager.current_tone == Tone.HORROR
        assert atmosphere_manager.pacing == Pacing.DELIBERATE

    def test_set_scene_with_different_scene_types(
        self, atmosphere_manager: AtmosphereManager
    ) -> None:
        # Combat scene
        combat_scene = SceneContext(
            scene_type=SceneType.COMBAT,
            keywords=["battle", "glory"],
            environment="arena",
        )
        tone, pacing = atmosphere_manager.set_scene(combat_scene)
        assert pacing == Pacing.FAST

        # Puzzle scene
        puzzle_scene = SceneContext(
            scene_type=SceneType.PUZZLE,
            keywords=["mysterious", "riddle"],
            environment="ruins",
        )
        tone, pacing = atmosphere_manager.set_scene(puzzle_scene)
        assert pacing == Pacing.SLOW

    def test_set_scene_neutral_tone_normal_pacing(
        self, atmosphere_manager: AtmosphereManager, neutral_scene: SceneContext
    ) -> None:
        tone, pacing = atmosphere_manager.set_scene(neutral_scene)

        assert tone == Tone.NEUTRAL
        assert pacing == Pacing.DELIBERATE  # EXPLORATION default
        assert atmosphere_manager.current_tone == Tone.NEUTRAL


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestAtmosphereIntegration:
    """Integration tests for complete atmosphere workflows."""

    def test_full_atmosphere_workflow(
        self, atmosphere_manager: AtmosphereManager, mock_llm: MockLLM, horror_scene: SceneContext
    ) -> None:
        # Set scene
        tone, pacing = atmosphere_manager.set_scene(horror_scene)
        assert tone == Tone.HORROR
        assert pacing == Pacing.DELIBERATE

        # Build tension
        description = "A dark corridor stretches before you."
        tense_description = asyncio.run(atmosphere_manager.build_tension(description, target_level=0.7))
        assert tense_description == "Enhanced atmospheric narrative."
        assert len(mock_llm.calls) == 1

        # Apply atmosphere
        mock_llm.calls.clear()
        narrative = "You cautiously move forward."
        atmospheric_narrative = asyncio.run(atmosphere_manager.apply_atmosphere(narrative, tone, intensity=0.8))
        assert atmospheric_narrative == "Enhanced atmospheric narrative."
        assert len(mock_llm.calls) == 1

        # Update tension
        new_tension = atmosphere_manager.update_tension(0.2)
        assert new_tension == 0.7

    def test_tone_transition_workflow(
        self, atmosphere_manager: AtmosphereManager, mock_llm: MockLLM
    ) -> None:
        # Start in peaceful scene
        peaceful = SceneContext(
            scene_type=SceneType.REST,
            keywords=["calm", "peaceful"],
            environment="meadow",
        )
        tone, _ = atmosphere_manager.set_scene(peaceful)
        assert tone == Tone.PEACEFUL

        # Transition to horror
        transition = asyncio.run(atmosphere_manager.transition_tone(
            from_tone=Tone.PEACEFUL,
            to_tone=Tone.HORROR,
            trigger="a blood-curdling scream pierces the silence"
        ))
        assert transition == "Enhanced atmospheric narrative."

        # Update to horror scene
        horror = SceneContext(
            scene_type=SceneType.EXPLORATION,
            keywords=["dark", "undead"],
            environment="crypt",
        )
        tone, pacing = atmosphere_manager.set_scene(horror)
        assert tone == Tone.HORROR
        assert atmosphere_manager.current_tone == Tone.HORROR


# ---------------------------------------------------------------------------
# Constants Validation Tests
# ---------------------------------------------------------------------------

class TestConstantsValidation:
    """Tests to validate the configuration dictionaries."""

    def test_tone_indicators_structure(self) -> None:
        required_keys = {"keywords", "creature_types", "environment"}
        for tone, indicators in TONE_INDICATORS.items():
            assert required_keys.issubset(indicators.keys()), f"Tone {tone} missing required keys"
            assert isinstance(indicators["keywords"], list)
            assert isinstance(indicators["creature_types"], list)
            assert isinstance(indicators["environment"], list)

    def test_pacing_by_scene_covers_all_scene_types(self) -> None:
        for scene_type in SceneType:
            assert scene_type in PACING_BY_SCENE, f"No pacing defined for {scene_type}"

    def test_tone_modifiers_structure(self) -> None:
        required_keys = {"verbs", "adjectives", "sentence_style", "sensory_focus"}
        for tone, modifiers in TONE_MODIFIERS.items():
            assert required_keys.issubset(modifiers.keys()), f"Modifiers for {tone} missing required keys"
            assert isinstance(modifiers["verbs"], list)
            assert isinstance(modifiers["adjectives"], list)
            assert isinstance(modifiers["sentence_style"], str)
            assert isinstance(modifiers["sensory_focus"], list)
