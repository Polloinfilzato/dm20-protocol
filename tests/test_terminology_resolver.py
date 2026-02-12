"""
Unit tests for terminology resolution system.
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from dm20_protocol.terminology import TermEntry, TermResolver


# Test fixture YAML data
TEST_TERMS = {
    "terms": [
        {
            "canonical": "fireball",
            "category": "spell",
            "en": "Fireball",
            "it_primary": "Palla di Fuoco",
            "it_variants": ["palla di fuoco", "Sfera Infuocata"],
        },
        {
            "canonical": "stealth",
            "category": "skill",
            "en": "Stealth",
            "it_primary": "Furtività",
            "it_variants": ["furtività", "furtivita"],
        },
        {
            "canonical": "poisoned",
            "category": "condition",
            "en": "Poisoned",
            "it_primary": "Avvelenato",
            "it_variants": ["avvelenato"],
        },
        {
            "canonical": "strength",
            "category": "ability",
            "en": "Strength",
            "it_primary": "Forza",
            "it_variants": ["forza"],
        },
        {
            "canonical": "initiative",
            "category": "combat",
            "en": "Initiative",
            "it_primary": "Iniziativa",
            "it_variants": ["iniziativa"],
        },
        {
            "canonical": "longsword",
            "category": "item",
            "en": "Longsword",
            "it_primary": "Spada Lunga",
            "it_variants": ["spada lunga"],
        },
        {
            "canonical": "wizard",
            "category": "class",
            "en": "Wizard",
            "it_primary": "Mago",
            "it_variants": ["mago"],
        },
        {
            "canonical": "elf",
            "category": "race",
            "en": "Elf",
            "it_primary": "Elfo",
            "it_variants": ["elfo"],
        },
        {
            "canonical": "dungeon",
            "category": "general",
            "en": "Dungeon",
            "it_primary": "Dungeon",
            "it_variants": ["dungeon"],
        },
    ]
}


@pytest.fixture
def test_yaml_file() -> Path:
    """Create a temporary YAML file with test terms."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        yaml.dump(TEST_TERMS, f, allow_unicode=True)
        path = Path(f.name)

    yield path

    # Cleanup
    path.unlink()


@pytest.fixture
def resolver(test_yaml_file: Path) -> TermResolver:
    """Create a TermResolver loaded with test data."""
    r = TermResolver()
    r.load_yaml(test_yaml_file)
    return r


class TestTermEntry:
    """Test TermEntry model."""

    def test_create_term_entry(self) -> None:
        """Test creating a basic TermEntry."""
        entry = TermEntry(
            canonical="fireball",
            category="spell",
            en="Fireball",
            it_primary="Palla di Fuoco",
            it_variants=["palla di fuoco"],
        )
        assert entry.canonical == "fireball"
        assert entry.category == "spell"
        assert entry.en == "Fireball"
        assert entry.it_primary == "Palla di Fuoco"
        assert entry.it_variants == ["palla di fuoco"]

    def test_term_entry_defaults(self) -> None:
        """Test TermEntry with default it_variants."""
        entry = TermEntry(
            canonical="stealth",
            category="skill",
            en="Stealth",
            it_primary="Furtività",
        )
        assert entry.it_variants == []


class TestTermResolver:
    """Test TermResolver functionality."""

    def test_empty_resolver(self) -> None:
        """Test empty resolver returns None for all queries."""
        resolver = TermResolver()
        assert resolver.resolve("fireball") is None
        assert resolver.resolve("anything") is None
        assert resolver.resolve_in_text("some text") == []

    def test_load_yaml(self, test_yaml_file: Path) -> None:
        """Test loading YAML dictionary."""
        resolver = TermResolver()
        resolver.load_yaml(test_yaml_file)

        # Should be able to resolve loaded terms
        entry = resolver.resolve("fireball")
        assert entry is not None
        assert entry.canonical == "fireball"

    def test_load_yaml_missing_file(self) -> None:
        """Test loading non-existent YAML file raises error."""
        resolver = TermResolver()
        with pytest.raises(FileNotFoundError):
            resolver.load_yaml(Path("/nonexistent/file.yaml"))

    def test_load_yaml_invalid_format(self) -> None:
        """Test loading YAML without 'terms' key raises error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump({"invalid": "data"}, f)
            path = Path(f.name)

        try:
            resolver = TermResolver()
            with pytest.raises(ValueError, match="must contain a 'terms' key"):
                resolver.load_yaml(path)
        finally:
            path.unlink()

    def test_normalize(self, resolver: TermResolver) -> None:
        """Test text normalization."""
        # Accent removal
        assert resolver._normalize("Furtività") == "furtivita"
        assert resolver._normalize("furtività") == "furtivita"

        # Case normalization
        assert resolver._normalize("FIREBALL") == "fireball"
        assert resolver._normalize("Fireball") == "fireball"

        # Whitespace stripping
        assert resolver._normalize("  Fireball  ") == "fireball"
        assert resolver._normalize("Palla di Fuoco") == "palla di fuoco"

        # Combined
        assert resolver._normalize("  FURTIVITÀ  ") == "furtivita"

    def test_resolve_exact_match_english(self, resolver: TermResolver) -> None:
        """Test resolving exact English match."""
        entry = resolver.resolve("Fireball")
        assert entry is not None
        assert entry.canonical == "fireball"
        assert entry.category == "spell"
        assert entry.en == "Fireball"

    def test_resolve_exact_match_italian(self, resolver: TermResolver) -> None:
        """Test resolving exact Italian match."""
        entry = resolver.resolve("Palla di Fuoco")
        assert entry is not None
        assert entry.canonical == "fireball"
        assert entry.en == "Fireball"

    def test_resolve_canonical(self, resolver: TermResolver) -> None:
        """Test resolving canonical key."""
        entry = resolver.resolve("fireball")
        assert entry is not None
        assert entry.canonical == "fireball"

    def test_resolve_case_insensitive(self, resolver: TermResolver) -> None:
        """Test case-insensitive resolution."""
        # All should resolve to same entry
        entries = [
            resolver.resolve("FIREBALL"),
            resolver.resolve("fireball"),
            resolver.resolve("Fireball"),
            resolver.resolve("FiReBaLl"),
        ]

        for entry in entries:
            assert entry is not None
            assert entry.canonical == "fireball"

    def test_resolve_accent_insensitive(self, resolver: TermResolver) -> None:
        """Test accent-insensitive resolution."""
        # With and without accents should resolve to same entry
        entry_with_accent = resolver.resolve("Furtività")
        entry_without_accent = resolver.resolve("Furtivita")

        assert entry_with_accent is not None
        assert entry_without_accent is not None
        assert entry_with_accent.canonical == "stealth"
        assert entry_without_accent.canonical == "stealth"
        assert entry_with_accent == entry_without_accent

    def test_resolve_italian_variant(self, resolver: TermResolver) -> None:
        """Test resolving Italian variant."""
        entry = resolver.resolve("Sfera Infuocata")
        assert entry is not None
        assert entry.canonical == "fireball"

    def test_resolve_unknown_term(self, resolver: TermResolver) -> None:
        """Test unknown term returns None."""
        entry = resolver.resolve("unknown_term")
        assert entry is None

        entry = resolver.resolve("nonexistent")
        assert entry is None

    def test_resolve_empty_string(self, resolver: TermResolver) -> None:
        """Test empty string returns None."""
        entry = resolver.resolve("")
        assert entry is None

    def test_resolve_in_text_empty(self, resolver: TermResolver) -> None:
        """Test resolve_in_text with empty input."""
        assert resolver.resolve_in_text("") == []

    def test_resolve_in_text_no_matches(self, resolver: TermResolver) -> None:
        """Test resolve_in_text with no known terms."""
        result = resolver.resolve_in_text("This has no known terms")
        assert result == []

    def test_resolve_in_text_single_term(self, resolver: TermResolver) -> None:
        """Test resolve_in_text with single term."""
        result = resolver.resolve_in_text("I cast Fireball")

        assert len(result) == 1
        matched_text, entry = result[0]
        assert matched_text == "Fireball"
        assert entry.canonical == "fireball"

    def test_resolve_in_text_multiple_terms(self, resolver: TermResolver) -> None:
        """Test resolve_in_text with multiple terms."""
        result = resolver.resolve_in_text("Lancio Fireball con Furtività")

        assert len(result) == 2

        # First match: Fireball
        matched_text, entry = result[0]
        assert matched_text == "Fireball"
        assert entry.canonical == "fireball"

        # Second match: Furtività
        matched_text, entry = result[1]
        assert matched_text == "Furtività"
        assert entry.canonical == "stealth"

    def test_resolve_in_text_multiword_term(self, resolver: TermResolver) -> None:
        """Test resolve_in_text with multi-word term."""
        result = resolver.resolve_in_text("Uso la Spada Lunga")

        assert len(result) == 1
        matched_text, entry = result[0]
        assert matched_text == "Spada Lunga"
        assert entry.canonical == "longsword"

    def test_resolve_in_text_case_preserved(self, resolver: TermResolver) -> None:
        """Test resolve_in_text preserves original case."""
        result = resolver.resolve_in_text("I cast FIREBALL")

        assert len(result) == 1
        matched_text, entry = result[0]
        assert matched_text == "FIREBALL"  # Original case preserved
        assert entry.canonical == "fireball"

    def test_resolve_in_text_accent_preserved(self, resolver: TermResolver) -> None:
        """Test resolve_in_text preserves original accents."""
        result = resolver.resolve_in_text("Check di Furtività")

        assert len(result) == 1
        matched_text, entry = result[0]
        assert matched_text == "Furtività"  # Accent preserved
        assert entry.canonical == "stealth"

    def test_resolve_in_text_mixed_languages(self, resolver: TermResolver) -> None:
        """Test resolve_in_text with Italian and English mixed."""
        result = resolver.resolve_in_text("Il Wizard lancia Palla di Fuoco")

        assert len(result) == 2

        # Check both terms found
        terms = {entry.canonical for _, entry in result}
        assert terms == {"wizard", "fireball"}

    def test_resolve_in_text_all_categories(self, resolver: TermResolver) -> None:
        """Test resolve_in_text finds terms from different categories."""
        text = "The Elf Wizard uses Stealth and casts Fireball in the Dungeon"
        result = resolver.resolve_in_text(text)

        # Should find 5 terms
        assert len(result) == 5

        categories = {entry.category for _, entry in result}
        assert "race" in categories  # Elf
        assert "class" in categories  # Wizard
        assert "skill" in categories  # Stealth
        assert "spell" in categories  # Fireball
        assert "general" in categories  # Dungeon

    def test_multiple_load_yaml(self, test_yaml_file: Path) -> None:
        """Test loading YAML multiple times clears previous data."""
        resolver = TermResolver()

        # Load first time
        resolver.load_yaml(test_yaml_file)
        assert resolver.resolve("fireball") is not None

        # Create new YAML with different terms
        new_data = {
            "terms": [
                {
                    "canonical": "cure_wounds",
                    "category": "spell",
                    "en": "Cure Wounds",
                    "it_primary": "Cura Ferite",
                    "it_variants": [],
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            yaml.dump(new_data, f, allow_unicode=True)
            new_path = Path(f.name)

        try:
            # Load second time
            resolver.load_yaml(new_path)

            # Old term should be gone
            assert resolver.resolve("fireball") is None

            # New term should be present
            assert resolver.resolve("cure_wounds") is not None
        finally:
            new_path.unlink()

    def test_resolve_in_text_word_boundaries(self, resolver: TermResolver) -> None:
        """Test resolve_in_text respects word boundaries."""
        # "elf" should not match "yourself" or "selfish"
        result = resolver.resolve_in_text("The Elf yourself selfish")

        # Should only match "Elf"
        assert len(result) == 1
        matched_text, entry = result[0]
        assert matched_text == "Elf"
        assert entry.canonical == "elf"
