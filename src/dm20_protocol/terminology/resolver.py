"""
Term resolver with O(1) lookup and accent normalization.
"""

import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from .models import TermEntry


class TermResolver:
    """Resolves bilingual D&D terms with O(1) lookup.

    Provides fast dictionary-based resolution of Italian and English term variants
    to canonical game entities. Handles accent normalization, case-insensitivity,
    and multi-word term matching.

    The resolver builds an internal lookup dictionary mapping all normalized variants
    (canonical, en, it_primary, all it_variants) to their TermEntry objects.

    Example:
        >>> resolver = TermResolver()
        >>> resolver.load_yaml(Path("core_terms.yaml"))
        >>> entry = resolver.resolve("palla di fuoco")
        >>> entry.canonical
        'fireball'
        >>> matches = resolver.resolve_in_text("Lancio Fireball con Furtività")
        >>> [(text, entry.canonical) for text, entry in matches]
        [('Fireball', 'fireball'), ('Furtività', 'stealth')]
    """

    def __init__(self) -> None:
        """Initialize an empty resolver."""
        self._lookup: dict[str, TermEntry] = {}
        self._sorted_variants: list[tuple[str, str]] = []  # (normalized, original) sorted by length

    def _normalize(self, text: str) -> str:
        """Normalize text for accent-insensitive, case-insensitive matching.

        Uses Unicode NFD normalization to decompose accented characters,
        then strips combining marks. Also lowercases and strips whitespace.

        Args:
            text: Input text to normalize

        Returns:
            Normalized text (lowercase, no accents, stripped)

        Example:
            >>> resolver._normalize("Furtività")
            'furtivita'
            >>> resolver._normalize("  PALLA DI FUOCO  ")
            'palla di fuoco'
        """
        # Normalize to NFD form (decompose accents)
        nfkd = unicodedata.normalize("NFD", text.lower().strip())
        # Strip combining marks (accents)
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    def load_yaml(self, path: Path) -> None:
        """Load term dictionary from YAML file.

        Parses the YAML file and builds the internal lookup dictionary.
        All variants (canonical, en, it_primary, it_variants) are mapped
        to their TermEntry for O(1) resolution.

        Expected YAML format:
            terms:
              - canonical: fireball
                category: spell
                en: Fireball
                it_primary: Palla di Fuoco
                it_variants: [Palla di fuoco, palla di fuoco]

        Args:
            path: Path to YAML file

        Raises:
            FileNotFoundError: If the YAML file doesn't exist
            yaml.YAMLError: If the YAML is malformed
            ValueError: If required fields are missing
        """
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "terms" not in data:
            raise ValueError("YAML file must contain a 'terms' key")

        # Clear existing data
        self._lookup.clear()
        self._sorted_variants.clear()

        for term_data in data["terms"]:
            entry = TermEntry(**term_data)

            # Collect all variants for this entry
            variants = [
                entry.canonical,
                entry.en,
                entry.it_primary,
                *entry.it_variants,
            ]

            # Map normalized variants to entry
            for variant in variants:
                normalized = self._normalize(variant)
                if normalized:  # Skip empty strings
                    self._lookup[normalized] = entry
                    # Store both normalized and original for text scanning
                    self._sorted_variants.append((normalized, variant))

        # Sort variants by length (longest first) for greedy matching
        # This ensures "palla di fuoco" matches before "palla"
        self._sorted_variants.sort(key=lambda x: len(x[0]), reverse=True)

    def resolve(self, text: str) -> TermEntry | None:
        """Resolve a single term to its TermEntry.

        Performs O(1) dictionary lookup after normalization.
        Returns None for unknown terms (no errors, graceful passthrough).

        Args:
            text: Term to resolve (any variant)

        Returns:
            TermEntry if found, None otherwise

        Example:
            >>> entry = resolver.resolve("furtivita")  # accent-insensitive
            >>> entry.canonical
            'stealth'
            >>> resolver.resolve("unknown_term")
            None
        """
        normalized = self._normalize(text)
        return self._lookup.get(normalized)

    def resolve_in_text(self, text: str) -> list[tuple[str, TermEntry]]:
        """Find all known terms in a text string.

        Scans the input text for all known term variants and returns
        the original matched text spans with their resolved TermEntry objects.
        Handles multi-word terms (e.g., "Palla di Fuoco").

        Uses greedy matching with longest-first strategy to handle overlapping terms.

        Args:
            text: Input text to scan

        Returns:
            List of (matched_text, TermEntry) tuples in order of appearance

        Example:
            >>> matches = resolver.resolve_in_text("Lancio Fireball con Furtività")
            >>> [(m, e.canonical) for m, e in matches]
            [('Fireball', 'fireball'), ('Furtività', 'stealth')]
        """
        if not text:
            return []

        results: list[tuple[str, TermEntry]] = []
        normalized_text = self._normalize(text)

        # Track matched positions to avoid overlaps
        matched_positions: set[int] = set()

        # Try to match each variant (sorted longest-first)
        for normalized_variant, original_variant in self._sorted_variants:
            # Build regex pattern for word boundaries
            # Escape special regex chars
            pattern = re.escape(normalized_variant)
            # Use word boundaries for single words, space boundaries for multi-word
            if " " in pattern:
                pattern = r"\b" + pattern + r"\b"
            else:
                pattern = r"\b" + pattern + r"\b"

            # Find all matches in normalized text
            for match in re.finditer(pattern, normalized_text):
                start, end = match.span()

                # Check if this position overlaps with existing match
                if any(pos in matched_positions for pos in range(start, end)):
                    continue

                # Mark positions as matched
                matched_positions.update(range(start, end))

                # Extract original text (preserve case/accents)
                matched_text = text[start:end]

                # Resolve the term
                entry = self._lookup.get(normalized_variant)
                if entry:
                    results.append((matched_text, entry))

        # Sort by position in text
        results.sort(key=lambda x: text.find(x[0]))

        return results
