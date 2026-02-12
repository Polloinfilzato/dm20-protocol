"""Tests for TermResolver.index_from_rulebook() integration with RulebookManager."""

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest

from dm20_protocol.terminology.models import TermEntry
from dm20_protocol.terminology.resolver import TermResolver


# ---------------------------------------------------------------------------
# Helpers — lightweight fakes for rulebook definitions
# ---------------------------------------------------------------------------

@dataclass
class FakeDefinition:
    """Minimal definition object with a .name attribute."""
    name: str


def _make_fake_source(
    source_id: str = "fake-srd",
    is_loaded: bool = True,
    spells: dict | None = None,
    monsters: dict | None = None,
    classes: dict | None = None,
    races: dict | None = None,
    items: dict | None = None,
    feats: dict | None = None,
    backgrounds: dict | None = None,
    subclasses: dict | None = None,
    subraces: dict | None = None,
) -> MagicMock:
    """Create a fake RulebookSourceBase with configurable storage dicts."""
    source = MagicMock()
    source.source_id = source_id
    type(source).is_loaded = PropertyMock(return_value=is_loaded)

    source._spells = spells or {}
    source._monsters = monsters or {}
    source._classes = classes or {}
    source._races = races or {}
    source._items = items or {}
    source._feats = feats or {}
    source._backgrounds = backgrounds or {}
    source._subclasses = subclasses or {}
    source._subraces = subraces or {}

    return source


def _make_fake_manager(sources: list) -> MagicMock:
    """Create a fake RulebookManager with given sources."""
    manager = MagicMock()
    manager._sources = {s.source_id: s for s in sources}
    return manager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_YAML = """\
terms:
  - canonical: fireball
    category: spell
    en: Fireball
    it_primary: Palla di Fuoco
    it_variants: [Palla di fuoco, PdF]
  - canonical: goblin
    category: monster
    en: Goblin
    it_primary: Goblin
    it_variants: []
"""


@pytest.fixture
def resolver_with_yaml(tmp_path: Path) -> TermResolver:
    """TermResolver pre-loaded with a small static YAML dictionary."""
    yaml_file = tmp_path / "terms.yaml"
    yaml_file.write_text(SAMPLE_YAML, encoding="utf-8")
    resolver = TermResolver()
    resolver.load_yaml(yaml_file)
    return resolver


@pytest.fixture
def empty_resolver() -> TermResolver:
    """TermResolver with no data loaded."""
    return TermResolver()


# ---------------------------------------------------------------------------
# Tests — index_from_rulebook
# ---------------------------------------------------------------------------

class TestIndexFromRulebook:
    """Tests for auto-indexing content from RulebookManager sources."""

    def test_indexes_spells_from_source(self, empty_resolver: TermResolver):
        """Spells from a source should become resolvable."""
        source = _make_fake_source(spells={
            "magic-missile": FakeDefinition("Magic Missile"),
            "shield": FakeDefinition("Shield"),
        })
        manager = _make_fake_manager([source])

        count = empty_resolver.index_from_rulebook(manager)

        assert count == 2
        entry = empty_resolver.resolve("Magic Missile")
        assert entry is not None
        assert entry.canonical == "magic-missile"
        assert entry.category == "spell"
        assert entry.en == "Magic Missile"

    def test_indexes_monsters_from_source(self, empty_resolver: TermResolver):
        """Monsters from a source should become resolvable."""
        source = _make_fake_source(monsters={
            "adult-red-dragon": FakeDefinition("Adult Red Dragon"),
        })
        manager = _make_fake_manager([source])

        count = empty_resolver.index_from_rulebook(manager)

        assert count == 1
        entry = empty_resolver.resolve("Adult Red Dragon")
        assert entry is not None
        assert entry.category == "monster"

    def test_indexes_classes_and_races(self, empty_resolver: TermResolver):
        """Classes and races should be indexed with correct categories."""
        source = _make_fake_source(
            classes={"wizard": FakeDefinition("Wizard")},
            races={"elf": FakeDefinition("Elf")},
        )
        manager = _make_fake_manager([source])

        count = empty_resolver.index_from_rulebook(manager)

        assert count == 2
        wizard = empty_resolver.resolve("Wizard")
        assert wizard is not None
        assert wizard.category == "class"

        elf = empty_resolver.resolve("Elf")
        assert elf is not None
        assert elf.category == "race"

    def test_indexes_items_and_feats(self, empty_resolver: TermResolver):
        """Items and feats should be indexed with correct categories."""
        source = _make_fake_source(
            items={"longsword": FakeDefinition("Longsword")},
            feats={"alert": FakeDefinition("Alert")},
        )
        manager = _make_fake_manager([source])

        count = empty_resolver.index_from_rulebook(manager)

        assert count == 2

        sword = empty_resolver.resolve("Longsword")
        assert sword is not None
        assert sword.category == "item"

        alert = empty_resolver.resolve("Alert")
        assert alert is not None
        assert alert.category == "general"  # feats map to 'general'

    def test_static_yaml_takes_priority(self, resolver_with_yaml: TermResolver):
        """Terms already in YAML dict should NOT be overwritten by auto-indexing."""
        # 'fireball' and 'goblin' are in YAML with Italian translations
        source = _make_fake_source(
            spells={"fireball": FakeDefinition("Fireball")},
            monsters={"goblin": FakeDefinition("Goblin")},
        )
        manager = _make_fake_manager([source])

        count = resolver_with_yaml.index_from_rulebook(manager)

        # Both should be skipped — already in YAML
        assert count == 0

        # Verify the YAML version is preserved (has Italian translation)
        entry = resolver_with_yaml.resolve("Fireball")
        assert entry is not None
        assert entry.it_primary == "Palla di Fuoco"  # From YAML, not "Fireball"

    def test_new_terms_indexed_alongside_yaml(self, resolver_with_yaml: TermResolver):
        """New terms from sources should be added without affecting YAML terms."""
        source = _make_fake_source(
            spells={
                "fireball": FakeDefinition("Fireball"),     # Already in YAML
                "ice-storm": FakeDefinition("Ice Storm"),    # New
            },
            monsters={
                "goblin": FakeDefinition("Goblin"),          # Already in YAML
                "beholder": FakeDefinition("Beholder"),      # New
            },
        )
        manager = _make_fake_manager([source])

        count = resolver_with_yaml.index_from_rulebook(manager)

        assert count == 2  # Only ice-storm and beholder are new

        # YAML terms preserved
        fireball = resolver_with_yaml.resolve("Fireball")
        assert fireball.it_primary == "Palla di Fuoco"

        # New terms indexed
        ice_storm = resolver_with_yaml.resolve("Ice Storm")
        assert ice_storm is not None
        assert ice_storm.en == "Ice Storm"
        assert ice_storm.it_primary == "Ice Storm"  # No translation for auto-indexed

    def test_empty_manager_returns_zero(self, empty_resolver: TermResolver):
        """Manager with no sources returns 0."""
        manager = _make_fake_manager([])

        count = empty_resolver.index_from_rulebook(manager)

        assert count == 0

    def test_unloaded_source_skipped(self, empty_resolver: TermResolver):
        """Sources that aren't loaded should be skipped."""
        source = _make_fake_source(
            is_loaded=False,
            spells={"fireball": FakeDefinition("Fireball")},
        )
        manager = _make_fake_manager([source])

        count = empty_resolver.index_from_rulebook(manager)

        assert count == 0

    def test_multiple_sources_indexed(self, empty_resolver: TermResolver):
        """Terms from multiple sources should all be indexed."""
        source1 = _make_fake_source(
            source_id="srd-2014",
            spells={"fireball": FakeDefinition("Fireball")},
        )
        source2 = _make_fake_source(
            source_id="custom-homebrew",
            spells={"eldritch-blast": FakeDefinition("Eldritch Blast")},
        )
        manager = _make_fake_manager([source1, source2])

        count = empty_resolver.index_from_rulebook(manager)

        assert count == 2
        assert empty_resolver.resolve("Fireball") is not None
        assert empty_resolver.resolve("Eldritch Blast") is not None

    def test_index_key_also_resolvable(self, empty_resolver: TermResolver):
        """Both display name and index key should be resolvable."""
        source = _make_fake_source(spells={
            "cure-wounds": FakeDefinition("Cure Wounds"),
        })
        manager = _make_fake_manager([source])

        empty_resolver.index_from_rulebook(manager)

        # Resolve by display name
        assert empty_resolver.resolve("Cure Wounds") is not None
        # Resolve by index key
        assert empty_resolver.resolve("cure-wounds") is not None

    def test_auto_indexed_entry_structure(self, empty_resolver: TermResolver):
        """Auto-indexed entries should have correct structure."""
        source = _make_fake_source(spells={
            "magic-missile": FakeDefinition("Magic Missile"),
        })
        manager = _make_fake_manager([source])

        empty_resolver.index_from_rulebook(manager)

        entry = empty_resolver.resolve("Magic Missile")
        assert entry.canonical == "magic-missile"
        assert entry.category == "spell"
        assert entry.en == "Magic Missile"
        assert entry.it_primary == "Magic Missile"  # Same as en (no translation)
        assert entry.it_variants == []

    def test_category_mapping(self, empty_resolver: TermResolver):
        """Verify all category mappings are correct."""
        source = _make_fake_source(
            spells={"s1": FakeDefinition("Spell1")},
            monsters={"m1": FakeDefinition("Monster1")},
            classes={"c1": FakeDefinition("Class1")},
            races={"r1": FakeDefinition("Race1")},
            items={"i1": FakeDefinition("Item1")},
            feats={"f1": FakeDefinition("Feat1")},
            backgrounds={"b1": FakeDefinition("Background1")},
            subclasses={"sc1": FakeDefinition("Subclass1")},
            subraces={"sr1": FakeDefinition("Subrace1")},
        )
        manager = _make_fake_manager([source])

        empty_resolver.index_from_rulebook(manager)

        assert empty_resolver.resolve("Spell1").category == "spell"
        assert empty_resolver.resolve("Monster1").category == "monster"
        assert empty_resolver.resolve("Class1").category == "class"
        assert empty_resolver.resolve("Race1").category == "race"
        assert empty_resolver.resolve("Item1").category == "item"
        assert empty_resolver.resolve("Feat1").category == "general"
        assert empty_resolver.resolve("Background1").category == "general"
        assert empty_resolver.resolve("Subclass1").category == "general"
        assert empty_resolver.resolve("Subrace1").category == "race"

    def test_resolve_in_text_works_with_auto_indexed(self, empty_resolver: TermResolver):
        """Auto-indexed terms should be findable via resolve_in_text."""
        source = _make_fake_source(spells={
            "magic-missile": FakeDefinition("Magic Missile"),
        })
        manager = _make_fake_manager([source])

        empty_resolver.index_from_rulebook(manager)

        matches = empty_resolver.resolve_in_text("I cast Magic Missile at the goblin")
        assert len(matches) == 1
        assert matches[0][0] == "Magic Missile"
        assert matches[0][1].canonical == "magic-missile"

    def test_definition_without_name_skipped(self, empty_resolver: TermResolver):
        """Definitions missing a name attribute should be skipped."""
        no_name = MagicMock(spec=[])  # No .name attribute
        del no_name.name  # Ensure getattr returns None

        source = _make_fake_source(spells={
            "broken": no_name,
            "valid": FakeDefinition("Valid Spell"),
        })
        manager = _make_fake_manager([source])

        count = empty_resolver.index_from_rulebook(manager)

        assert count == 1
        assert empty_resolver.resolve("Valid Spell") is not None
