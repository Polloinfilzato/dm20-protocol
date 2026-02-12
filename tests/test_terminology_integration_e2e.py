"""
End-to-end integration tests for the terminology system in Claudmaster.

Tests the full integration of TermResolver and StyleTracker into the
player_action pipeline, including:
- Term detection in player input
- Language preference tracking per category
- Style context injection into narrator prompts
- Session state persistence
"""

import pytest
from pathlib import Path

from dm20_protocol.terminology import TermResolver, StyleTracker
from dm20_protocol.terminology.models import TermEntry
from dm20_protocol.claudmaster.agents.narrator import format_style_hint


class TestFormatStyleHint:
    """Test the format_style_hint utility function."""

    def test_format_style_hint_empty(self):
        """Empty preferences should return empty string."""
        assert format_style_hint({}) == ""

    def test_format_style_hint_single_category(self):
        """Single category should format correctly."""
        result = format_style_hint({"spell": "en"})
        assert "Player language preferences" in result
        assert "Spells: English" in result
        assert "Fireball" in result

    def test_format_style_hint_multiple_categories(self):
        """Multiple categories should all be included."""
        result = format_style_hint({
            "spell": "en",
            "skill": "it",
            "combat": "it"
        })
        assert "Spells: English" in result
        assert "Skills: Italian" in result
        assert "Combat terms: Italian" in result

    def test_format_style_hint_italian_preferences(self):
        """Italian preferences should show Italian examples."""
        result = format_style_hint({"spell": "it"})
        assert "Spells: Italian" in result
        assert "Palla di Fuoco" in result

    def test_format_style_hint_sorted_categories(self):
        """Categories should be sorted alphabetically."""
        result = format_style_hint({
            "spell": "en",
            "combat": "it",
            "ability": "en",
        })
        lines = result.split("\n")
        # Extract category names from lines
        categories = [line.split(":")[0].strip("- ") for line in lines[1:]]
        assert categories == sorted(categories)


class TestStyleTrackerSerialization:
    """Test serialization of StyleTracker state for session persistence."""

    def test_observations_dict_is_json_serializable(self):
        """StyleTracker._observations should be JSON-serializable."""
        import json

        tracker = StyleTracker()
        term = TermEntry(
            canonical="fireball",
            category="spell",
            en="Fireball",
            it_primary="Palla di Fuoco",
            it_variants=["palla di fuoco"]
        )

        tracker.observe(term, "Fireball")
        tracker.observe(term, "palla di fuoco")

        # Should be serializable
        serialized = json.dumps(dict(tracker._observations))
        deserialized = json.loads(serialized)

        assert deserialized == {
            "spell": {"en": 1, "it": 1}
        }

    def test_restore_from_serialized_state(self):
        """StyleTracker should restore correctly from saved state."""
        # Create tracker with observations
        tracker1 = StyleTracker()
        term_spell = TermEntry(
            canonical="fireball",
            category="spell",
            en="Fireball",
            it_primary="Palla di Fuoco",
            it_variants=["palla di fuoco"]
        )
        term_skill = TermEntry(
            canonical="stealth",
            category="skill",
            en="Stealth",
            it_primary="Furtività",
            it_variants=["furtivita"]
        )

        tracker1.observe(term_spell, "Fireball")
        tracker1.observe(term_spell, "Fireball")
        tracker1.observe(term_skill, "furtivita")

        # Save state
        saved_state = dict(tracker1._observations)

        # Create new tracker and restore
        tracker2 = StyleTracker()
        tracker2._observations = saved_state

        # Verify restored state
        assert tracker2.preferred_language("spell") == "en"
        assert tracker2.preferred_language("skill") == "it"
        assert tracker2.preferences_summary() == {
            "spell": "en",
            "skill": "it"
        }


class TestTermResolverGracefulDegradation:
    """Test graceful degradation when terminology system fails."""

    def test_missing_yaml_file_doesnt_crash_resolver(self):
        """TermResolver should handle missing YAML files gracefully."""
        resolver = TermResolver()

        # Try to load non-existent file
        with pytest.raises(FileNotFoundError):
            resolver.load_yaml(Path("/nonexistent/path/core_terms.yaml"))

        # Resolver should still be usable (empty lookup)
        result = resolver.resolve("fireball")
        assert result is None

    def test_resolve_in_text_with_empty_resolver(self):
        """resolve_in_text should work with empty resolver."""
        resolver = TermResolver()

        matches = resolver.resolve_in_text("I cast Fireball")
        assert matches == []


class TestStyleTrackerIntegration:
    """Integration tests for StyleTracker with TermResolver."""

    def test_italian_spell_input_tracked_as_it(self):
        """Italian spell input should be tracked as IT preference."""
        resolver = TermResolver()
        tracker = StyleTracker()

        # Add a test term (must populate both _lookup and _sorted_variants)
        term = TermEntry(
            canonical="fireball",
            category="spell",
            en="Fireball",
            it_primary="Palla di Fuoco",
            it_variants=["palla di fuoco", "Palla Di Fuoco"]
        )

        # Populate lookup dict
        normalized_it = resolver._normalize("palla di fuoco")
        resolver._lookup[normalized_it] = term

        # Populate sorted variants for text scanning
        resolver._sorted_variants.append((normalized_it, "palla di fuoco"))
        resolver._sorted_variants.sort(key=lambda x: len(x[0]), reverse=True)

        # Simulate player input in Italian
        matches = resolver.resolve_in_text("Lancio palla di fuoco sul goblin")

        for original_text, term_entry in matches:
            tracker.observe(term_entry, original_text)

        # Should prefer Italian for spells
        assert tracker.preferred_language("spell") == "it"
        assert tracker.preferences_summary() == {"spell": "it"}

    def test_english_skill_input_tracked_as_en(self):
        """English skill input should be tracked as EN preference."""
        resolver = TermResolver()
        tracker = StyleTracker()

        # Add a test term
        term = TermEntry(
            canonical="stealth",
            category="skill",
            en="Stealth",
            it_primary="Furtività",
            it_variants=["furtivita"]
        )

        # Populate lookup dict
        normalized_en = resolver._normalize("Stealth")
        resolver._lookup[normalized_en] = term

        # Populate sorted variants
        resolver._sorted_variants.append((normalized_en, "Stealth"))
        resolver._sorted_variants.sort(key=lambda x: len(x[0]), reverse=True)

        # Simulate player input in English
        matches = resolver.resolve_in_text("I use Stealth to sneak past")

        for original_text, term_entry in matches:
            tracker.observe(term_entry, original_text)

        # Should prefer English for skills
        assert tracker.preferred_language("skill") == "en"
        assert tracker.preferences_summary() == {"skill": "en"}

    def test_mixed_input_correct_per_category_preferences(self):
        """Mixed IT/EN input should track per-category preferences correctly."""
        resolver = TermResolver()
        tracker = StyleTracker()

        # Add test terms
        spell_term = TermEntry(
            canonical="fireball",
            category="spell",
            en="Fireball",
            it_primary="Palla di Fuoco",
            it_variants=["palla di fuoco"]
        )
        skill_term = TermEntry(
            canonical="stealth",
            category="skill",
            en="Stealth",
            it_primary="Furtività",
            it_variants=["furtivita"]
        )

        # Populate resolver for both terms
        spell_norm = resolver._normalize("Fireball")
        skill_norm = resolver._normalize("furtivita")

        resolver._lookup[spell_norm] = spell_term
        resolver._lookup[skill_norm] = skill_term

        resolver._sorted_variants.append((spell_norm, "Fireball"))
        resolver._sorted_variants.append((skill_norm, "furtivita"))
        resolver._sorted_variants.sort(key=lambda x: len(x[0]), reverse=True)

        # Simulate mixed input: English spell, Italian skill
        input1 = "I cast Fireball"
        matches1 = resolver.resolve_in_text(input1)
        for orig, term in matches1:
            tracker.observe(term, orig)

        input2 = "Then I use furtivita"
        matches2 = resolver.resolve_in_text(input2)
        for orig, term in matches2:
            tracker.observe(term, orig)

        # Should have correct per-category preferences
        prefs = tracker.preferences_summary()
        assert prefs["spell"] == "en"
        assert prefs["skill"] == "it"

    def test_accent_insensitive_observation(self):
        """Tracker should handle accent variations correctly."""
        tracker = StyleTracker()

        term = TermEntry(
            canonical="stealth",
            category="skill",
            en="Stealth",
            it_primary="Furtività",
            it_variants=["furtivita"]  # normalized variant
        )

        # Observe with accents
        tracker.observe(term, "Furtività")
        assert tracker.preferred_language("skill") == "it"

        # Observe without accents (should still count as IT)
        tracker.observe(term, "furtivita")
        assert tracker.preferred_language("skill") == "it"

        # Both should count toward IT preference
        assert tracker._observations["skill"]["it"] == 2


class TestNarratorStyleInjection:
    """Test style preferences injection into narrator context."""

    def test_narrator_receives_style_preferences_in_context(self):
        """Narrator should receive style preferences from session metadata."""
        from dm20_protocol.claudmaster.agents.narrator import NarratorAgent, NarrativeStyle

        # Create a mock LLM client
        class MockLLM:
            last_prompt = None

            async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
                self.last_prompt = prompt
                return "The room is dark and mysterious."

        mock_llm = MockLLM()
        narrator = NarratorAgent(llm=mock_llm, style=NarrativeStyle.DESCRIPTIVE)

        # Simulate context with style preferences
        context = {
            "player_action": "I look around",
            "location": {"name": "Dark Cavern"},
            "style_preferences": {
                "spell": "en",
                "skill": "it"
            }
        }

        # Run narrator through ReAct cycle
        import asyncio
        async def run_test():
            reasoning = await narrator.reason(context)
            narrative = await narrator.act(reasoning)
            return narrative

        result = asyncio.run(run_test())

        # Check that style hint was injected into prompt
        assert mock_llm.last_prompt is not None
        assert "Player language preferences" in mock_llm.last_prompt
        assert "Spells: English" in mock_llm.last_prompt
        assert "Skills: Italian" in mock_llm.last_prompt

    def test_narrator_prompt_without_style_preferences(self):
        """Narrator should work normally when no style preferences are set."""
        from dm20_protocol.claudmaster.agents.narrator import NarratorAgent, NarrativeStyle

        class MockLLM:
            last_prompt = None

            async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
                self.last_prompt = prompt
                return "You enter the tavern."

        mock_llm = MockLLM()
        narrator = NarratorAgent(llm=mock_llm, style=NarrativeStyle.TERSE)

        # Context without style preferences
        context = {
            "player_action": "I enter the tavern",
            "location": {"name": "The Prancing Pony"}
        }

        import asyncio
        async def run_test():
            reasoning = await narrator.reason(context)
            narrative = await narrator.act(reasoning)
            return narrative

        result = asyncio.run(run_test())

        # Prompt should not contain style hint
        assert mock_llm.last_prompt is not None
        assert "Player language preferences" not in mock_llm.last_prompt


class TestYAMLLoadingIntegration:
    """Test that core_terms.yaml can be loaded correctly."""

    def test_core_terms_yaml_exists_and_loads(self):
        """Verify core_terms.yaml exists and can be loaded."""
        # Path from session_tools.py perspective
        core_terms_path = Path(__file__).parent.parent / "src" / "dm20_protocol" / "terminology" / "data" / "core_terms.yaml"

        assert core_terms_path.exists(), f"core_terms.yaml not found at {core_terms_path}"

        resolver = TermResolver()
        resolver.load_yaml(core_terms_path)

        # Should have loaded terms
        assert len(resolver._lookup) > 0

        # Spot check: "fireball" should be in the dictionary
        result = resolver.resolve("fireball")
        assert result is not None
        assert result.canonical == "fireball"
        assert result.category == "spell"

    def test_core_terms_contains_expected_categories(self):
        """Verify core_terms.yaml contains expected term categories."""
        core_terms_path = Path(__file__).parent.parent / "src" / "dm20_protocol" / "terminology" / "data" / "core_terms.yaml"

        resolver = TermResolver()
        resolver.load_yaml(core_terms_path)

        # Collect all categories
        categories = set()
        for term in resolver._lookup.values():
            categories.add(term.category)

        # Should have core categories
        expected_categories = {"spell", "skill", "ability", "condition", "combat"}
        assert expected_categories.issubset(categories), f"Missing categories: {expected_categories - categories}"
