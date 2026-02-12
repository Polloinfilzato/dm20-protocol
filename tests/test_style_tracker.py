"""
Unit tests for StyleTracker - per-category language preference tracking.
"""

import pytest

from dm20_protocol.terminology import StyleTracker, TermEntry


@pytest.fixture
def tracker() -> StyleTracker:
    """Create a fresh StyleTracker instance."""
    return StyleTracker()


@pytest.fixture
def sample_terms() -> dict[str, TermEntry]:
    """Create sample TermEntry objects for testing."""
    return {
        "fireball": TermEntry(
            canonical="fireball",
            category="spell",
            en="Fireball",
            it_primary="Palla di Fuoco",
            it_variants=["palla di fuoco"],
        ),
        "stealth": TermEntry(
            canonical="stealth",
            category="skill",
            en="Stealth",
            it_primary="Furtività",
            it_variants=["furtivita", "Furtivita"],
        ),
        "grappled": TermEntry(
            canonical="grappled",
            category="condition",
            en="Grappled",
            it_primary="In Lotta",
            it_variants=["in lotta"],
        ),
        "attack": TermEntry(
            canonical="attack",
            category="combat",
            en="Attack",
            it_primary="Attacco",
            it_variants=["attacco"],
        ),
    }


def test_single_observation_english(tracker: StyleTracker, sample_terms: dict[str, TermEntry]) -> None:
    """Test single EN observation correctly increments counter."""
    tracker.observe(sample_terms["fireball"], "Fireball")
    assert tracker.preferred_language("spell") == "en"


def test_single_observation_italian(tracker: StyleTracker, sample_terms: dict[str, TermEntry]) -> None:
    """Test single IT observation correctly increments counter."""
    tracker.observe(sample_terms["fireball"], "palla di fuoco")
    assert tracker.preferred_language("spell") == "it"


def test_multiple_observations_majority_en(tracker: StyleTracker, sample_terms: dict[str, TermEntry]) -> None:
    """Test that preference follows majority (EN wins)."""
    # 5 EN, 3 IT → should prefer EN
    for _ in range(5):
        tracker.observe(sample_terms["fireball"], "Fireball")
    for _ in range(3):
        tracker.observe(sample_terms["fireball"], "palla di fuoco")

    assert tracker.preferred_language("spell") == "en"


def test_multiple_observations_majority_it(tracker: StyleTracker, sample_terms: dict[str, TermEntry]) -> None:
    """Test that preference follows majority (IT wins)."""
    # 3 EN, 7 IT → should prefer IT
    for _ in range(3):
        tracker.observe(sample_terms["stealth"], "Stealth")
    for _ in range(7):
        tracker.observe(sample_terms["stealth"], "Furtività")

    assert tracker.preferred_language("skill") == "it"


def test_preference_flip(tracker: StyleTracker, sample_terms: dict[str, TermEntry]) -> None:
    """Test preference can flip when new observations change majority."""
    # Start with 5 EN observations
    for _ in range(5):
        tracker.observe(sample_terms["grappled"], "Grappled")

    assert tracker.preferred_language("condition") == "en"

    # Add 6 IT observations → should flip to IT
    for _ in range(6):
        tracker.observe(sample_terms["grappled"], "in lotta")

    assert tracker.preferred_language("condition") == "it"


def test_tie_breaking_defaults_to_en(tracker: StyleTracker, sample_terms: dict[str, TermEntry]) -> None:
    """Test that ties default to EN."""
    # 5 EN, 5 IT → tie
    for _ in range(5):
        tracker.observe(sample_terms["attack"], "Attack")
    for _ in range(5):
        tracker.observe(sample_terms["attack"], "attacco")

    assert tracker.preferred_language("combat") == "en"


def test_no_observations_defaults_to_en(tracker: StyleTracker) -> None:
    """Test that categories with no observations default to EN."""
    assert tracker.preferred_language("spell") == "en"
    assert tracker.preferred_language("skill") == "en"
    assert tracker.preferred_language("unknown_category") == "en"


def test_preferences_summary_format(tracker: StyleTracker, sample_terms: dict[str, TermEntry]) -> None:
    """Test preferences_summary returns correct dict format."""
    # Add observations for multiple categories
    tracker.observe(sample_terms["fireball"], "Fireball")  # spell → EN
    tracker.observe(sample_terms["stealth"], "furtivita")  # skill → IT
    tracker.observe(sample_terms["stealth"], "Furtività")  # skill → IT
    tracker.observe(sample_terms["grappled"], "in lotta")  # condition → IT

    summary = tracker.preferences_summary()

    assert isinstance(summary, dict)
    assert summary == {
        "spell": "en",
        "skill": "it",
        "condition": "it",
    }


def test_preferences_summary_empty_tracker(tracker: StyleTracker) -> None:
    """Test preferences_summary returns empty dict when no observations."""
    assert tracker.preferences_summary() == {}


def test_reset_clears_observations(tracker: StyleTracker, sample_terms: dict[str, TermEntry]) -> None:
    """Test reset() clears all observations."""
    # Add observations
    tracker.observe(sample_terms["fireball"], "palla di fuoco")
    tracker.observe(sample_terms["stealth"], "Furtività")

    assert tracker.preferences_summary() == {"spell": "it", "skill": "it"}

    # Reset
    tracker.reset()

    # Should be empty
    assert tracker.preferences_summary() == {}
    assert tracker.preferred_language("spell") == "en"


def test_multiple_categories_tracked_independently(
    tracker: StyleTracker, sample_terms: dict[str, TermEntry]
) -> None:
    """Test that different categories maintain independent preferences."""
    # Spell → EN preference (5 EN, 2 IT)
    for _ in range(5):
        tracker.observe(sample_terms["fireball"], "Fireball")
    for _ in range(2):
        tracker.observe(sample_terms["fireball"], "palla di fuoco")

    # Skill → IT preference (2 EN, 8 IT)
    for _ in range(2):
        tracker.observe(sample_terms["stealth"], "Stealth")
    for _ in range(8):
        tracker.observe(sample_terms["stealth"], "furtivita")

    assert tracker.preferred_language("spell") == "en"
    assert tracker.preferred_language("skill") == "it"


def test_accent_insensitive_variant_detection(tracker: StyleTracker, sample_terms: dict[str, TermEntry]) -> None:
    """Test that accent normalization correctly detects IT variants."""
    # "furtivita" (no accent) should be detected as IT
    tracker.observe(sample_terms["stealth"], "furtivita")
    assert tracker.preferred_language("skill") == "it"

    # "Furtività" (with accent) should also be detected as IT
    tracker.observe(sample_terms["stealth"], "Furtività")
    assert tracker.preferred_language("skill") == "it"


def test_canonical_form_detected_as_en(tracker: StyleTracker, sample_terms: dict[str, TermEntry]) -> None:
    """Test that canonical form is detected as English."""
    # Using canonical form "fireball" (lowercase) should be detected as EN
    tracker.observe(sample_terms["fireball"], "fireball")
    assert tracker.preferred_language("spell") == "en"


def test_mixed_case_variants(tracker: StyleTracker, sample_terms: dict[str, TermEntry]) -> None:
    """Test that mixed case variants are correctly normalized and detected."""
    # "FIREBALL", "Fireball", "fireball" should all be EN
    tracker.observe(sample_terms["fireball"], "FIREBALL")
    tracker.observe(sample_terms["fireball"], "Fireball")
    tracker.observe(sample_terms["fireball"], "fireball")

    assert tracker.preferred_language("spell") == "en"


def test_it_primary_vs_variants(tracker: StyleTracker, sample_terms: dict[str, TermEntry]) -> None:
    """Test that both it_primary and it_variants are detected as IT."""
    # Use it_primary
    tracker.observe(sample_terms["fireball"], "Palla di Fuoco")
    # Use it_variant
    tracker.observe(sample_terms["fireball"], "palla di fuoco")

    # Both should count as IT
    assert tracker.preferred_language("spell") == "it"


def test_unknown_variant_defaults_to_en(tracker: StyleTracker, sample_terms: dict[str, TermEntry]) -> None:
    """Test that unknown variants default to EN (safety fallback)."""
    # Use a variant that doesn't match any known form
    # (This shouldn't happen in practice if called via TermResolver)
    tracker.observe(sample_terms["fireball"], "unknown_variant_xyz")

    # Should default to EN as fallback
    assert tracker.preferred_language("spell") == "en"
