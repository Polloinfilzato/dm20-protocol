"""
Per-category language preference tracking for bilingual terminology.
"""

import unicodedata
from collections import defaultdict

from .models import TermEntry


class StyleTracker:
    """Tracks per-category language preferences based on player term usage.

    Observes which language variant (Italian or English) a player uses for each
    D&D term category and tracks per-category preferences. The tracker produces
    a summary dictionary suitable for injection into the Claudmaster narrator
    agent's prompt, enabling the AI DM to mirror the player's language style.

    Example:
        >>> tracker = StyleTracker()
        >>> term = TermEntry(canonical="fireball", category="spell", en="Fireball",
        ...                  it_primary="Palla di Fuoco", it_variants=["palla di fuoco"])
        >>> tracker.observe(term, "Fireball")
        >>> tracker.observe(term, "palla di fuoco")
        >>> tracker.observe(term, "palla di fuoco")
        >>> tracker.preferred_language("spell")
        'it'
        >>> tracker.preferences_summary()
        {'spell': 'it'}
    """

    def __init__(self) -> None:
        """Initialize an empty tracker."""
        # category → {"en": count, "it": count}
        self._observations: dict[str, dict[str, int]] = defaultdict(lambda: {"en": 0, "it": 0})

    def _normalize(self, text: str) -> str:
        """Normalize text for accent-insensitive, case-insensitive matching.

        Uses Unicode NFD normalization to decompose accented characters,
        then strips combining marks. Also lowercases and strips whitespace.

        Args:
            text: Input text to normalize

        Returns:
            Normalized text (lowercase, no accents, stripped)

        Example:
            >>> tracker._normalize("Furtività")
            'furtivita'
            >>> tracker._normalize("  PALLA DI FUOCO  ")
            'palla di fuoco'
        """
        # Normalize to NFD form (decompose accents)
        nfkd = unicodedata.normalize("NFD", text.lower().strip())
        # Strip combining marks (accents)
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    def observe(self, term: TermEntry, used_variant: str) -> None:
        """Record that the player used `used_variant` to refer to `term`.

        Determines whether the variant is English or Italian by comparing
        against term.en, term.it_primary, and term.it_variants.
        Uses accent-insensitive normalization for matching.

        Args:
            term: The resolved TermEntry object
            used_variant: The exact text the player used (preserves case/accents)

        Example:
            >>> tracker.observe(term, "Fireball")  # Detected as EN
            >>> tracker.observe(term, "furtivita")  # Detected as IT (accent-insensitive)
        """
        normalized_used = self._normalize(used_variant)

        # Check if it's the English variant
        if normalized_used == self._normalize(term.en):
            detected_lang = "en"
        # Check if it's the canonical form (fallback for EN)
        elif normalized_used == self._normalize(term.canonical):
            detected_lang = "en"
        # Check if it's the primary Italian variant
        elif normalized_used == self._normalize(term.it_primary):
            detected_lang = "it"
        # Check if it's any of the Italian variants
        elif any(normalized_used == self._normalize(var) for var in term.it_variants):
            detected_lang = "it"
        else:
            # Fallback: default to English if no match found
            # (This shouldn't happen if called correctly via TermResolver)
            detected_lang = "en"

        # Increment the counter for the detected language
        self._observations[term.category][detected_lang] += 1

    def preferred_language(self, category: str) -> str:
        """Return 'en' or 'it' based on observation counts for a category.

        Returns the language with more observations for the given category.
        Defaults to 'en' when no observations exist or on a tie.

        Args:
            category: Term category (e.g., "spell", "skill", "combat")

        Returns:
            "en" or "it"

        Example:
            >>> tracker.preferred_language("spell")  # 5 EN, 10 IT observations
            'it'
            >>> tracker.preferred_language("unknown_category")  # No data
            'en'
        """
        if category not in self._observations:
            return "en"

        counts = self._observations[category]
        en_count = counts["en"]
        it_count = counts["it"]

        # Tie-breaking: default to EN
        if it_count > en_count:
            return "it"
        return "en"

    def preferences_summary(self) -> dict[str, str]:
        """Return preferred language for all observed categories.

        Returns:
            Dictionary mapping category to preferred language ("en" or "it")

        Example:
            >>> tracker.preferences_summary()
            {'spell': 'en', 'skill': 'it', 'combat': 'it'}
        """
        return {category: self.preferred_language(category) for category in self._observations}

    def reset(self) -> None:
        """Clear all observations.

        Resets the tracker to an empty state, removing all observation data.

        Example:
            >>> tracker.reset()
            >>> tracker.preferences_summary()
            {}
        """
        self._observations.clear()
