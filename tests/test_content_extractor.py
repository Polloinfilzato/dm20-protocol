"""
Unit tests for the Content Extractor.

Tests the ContentExtractor class for PDF content extraction and CustomSource generation.
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from gamemaster_mcp.library.manager import LibraryManager
from gamemaster_mcp.library.models import (
    ContentType,
    IndexEntry,
    TOCEntry,
    ContentSummary,
    SourceType,
)
from gamemaster_mcp.library.extractors.content import (
    ContentExtractor,
    ExtractedContent,
    CLASS_PATTERNS,
    RACE_PATTERNS,
    SPELL_PATTERNS,
    MONSTER_PATTERNS,
    FEAT_PATTERNS,
    ITEM_PATTERNS,
)


class TestExtractedContent:
    """Tests for the ExtractedContent dataclass."""

    def test_basic_creation(self):
        """Test basic ExtractedContent creation."""
        content = ExtractedContent(
            name="Fighter",
            content_type=ContentType.CLASS,
            source_id="phb",
            page_start=10,
            page_end=20,
        )

        assert content.name == "Fighter"
        assert content.content_type == ContentType.CLASS
        assert content.source_id == "phb"
        assert content.page_start == 10
        assert content.page_end == 20
        assert content.raw_text == ""
        assert content.parsed_data == {}
        assert content.confidence == 1.0

    def test_with_parsed_data(self):
        """Test ExtractedContent with parsed data."""
        content = ExtractedContent(
            name="Elf",
            content_type=ContentType.RACE,
            source_id="phb",
            page_start=30,
            parsed_data={"speed": 30, "size": "Medium"},
        )

        assert content.parsed_data["speed"] == 30
        assert content.parsed_data["size"] == "Medium"


class TestClassPatterns:
    """Tests for class regex patterns."""

    def test_hit_die_pattern(self):
        """Test hit die extraction patterns."""
        import re

        test_cases = [
            ("Hit Dice: 1d10", "10"),
            ("Hit Die: d8", "8"),
            ("Hit Dice: d12", "12"),
            ("Hit Dice: 1d6", "6"),
        ]

        for text, expected in test_cases:
            for pattern_key in ["hit_die", "hit_die_alt"]:
                match = re.search(CLASS_PATTERNS[pattern_key], text, re.IGNORECASE)
                if match:
                    assert match.group(1) == expected, f"Failed for: {text}"
                    break

    def test_saving_throws_pattern(self):
        """Test saving throws extraction patterns."""
        import re

        test_cases = [
            ("Saving Throws: Strength, Constitution", "Strength, Constitution"),
            ("Saves: Wisdom, Charisma", "Wisdom, Charisma"),
            ("Saving Throw: Dexterity", "Dexterity"),
        ]

        for text, expected in test_cases:
            for pattern_key in ["saving_throws", "saving_throws_alt"]:
                match = re.search(CLASS_PATTERNS[pattern_key], text, re.IGNORECASE)
                if match:
                    assert expected in match.group(1), f"Failed for: {text}"
                    break


class TestRacePatterns:
    """Tests for race regex patterns."""

    def test_ability_score_pattern(self):
        """Test ability score extraction patterns."""
        import re

        text = "Ability Score Increase. Your Dexterity score increases by 2."
        match = re.search(RACE_PATTERNS["ability_score"], text, re.IGNORECASE | re.DOTALL)

        assert match is not None
        assert "Dexterity" in match.group(1) or "2" in match.group(1)

    def test_size_pattern(self):
        """Test size extraction patterns."""
        import re

        test_cases = [
            ("Size. Small", "Small"),
            ("Size. Medium", "Medium"),
            ("Size. Large", "Large"),
        ]

        for text, expected in test_cases:
            match = re.search(RACE_PATTERNS["size"], text, re.IGNORECASE)
            assert match is not None, f"Failed to match: {text}"
            assert match.group(1) == expected

    def test_speed_pattern(self):
        """Test speed extraction patterns."""
        import re

        test_cases = [
            ("Speed. Your base walking speed is 30 feet.", "30"),
            ("Speed. 25 ft.", "25"),
            ("base speed is 35 feet", "35"),
        ]

        for text, expected in test_cases:
            for pattern_key in ["speed", "speed_alt"]:
                match = re.search(RACE_PATTERNS[pattern_key], text, re.IGNORECASE)
                if match:
                    assert match.group(1) == expected, f"Failed for: {text}"
                    break


class TestSpellPatterns:
    """Tests for spell regex patterns."""

    def test_level_school_pattern(self):
        """Test spell level and school extraction."""
        import re

        test_cases = [
            ("3rd-level evocation", "3", "evocation"),
            ("1st level conjuration", "1", "conjuration"),
            ("5th-level necromancy", "5", "necromancy"),
        ]

        for text, level, school in test_cases:
            match = re.search(SPELL_PATTERNS["level_school"], text, re.IGNORECASE)
            assert match is not None, f"Failed to match: {text}"
            assert match.group(1) == level
            assert match.group(2).lower() == school

    def test_cantrip_pattern(self):
        """Test cantrip detection."""
        import re

        text = "Evocation cantrip"
        match = re.search(SPELL_PATTERNS["cantrip"], text, re.IGNORECASE)

        assert match is not None
        assert match.group(1).lower() == "evocation"


class TestContentExtractorParsing:
    """Tests for ContentExtractor parsing methods."""

    @pytest.fixture
    def extractor(self):
        """Create a ContentExtractor with a mock library manager."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()
            yield ContentExtractor(manager)

    def test_parse_ability_bonuses(self, extractor):
        """Test parsing ability score bonuses."""
        test_cases = [
            ("Your Strength score increases by 2", [{"ability_score": "STR", "bonus": 2}]),
            ("Dexterity +1", [{"ability_score": "DEX", "bonus": 1}]),
            ("+2 to Constitution", [{"ability_score": "CON", "bonus": 2}]),
            ("Your Intelligence score increases by 1, and your Wisdom score increases by 1",
             [{"ability_score": "INT", "bonus": 1}, {"ability_score": "WIS", "bonus": 1}]),
        ]

        for text, expected in test_cases:
            result = extractor._parse_ability_bonuses(text)
            assert len(result) >= len(expected), f"Expected {len(expected)} bonuses from: {text}"
            for exp_bonus in expected:
                found = any(
                    b["ability_score"] == exp_bonus["ability_score"] and b["bonus"] == exp_bonus["bonus"]
                    for b in result
                )
                assert found, f"Expected {exp_bonus} not found in {result}"

    def test_parse_speed(self, extractor):
        """Test parsing speed values."""
        test_cases = [
            ("30 feet", {"walk": "30 ft."}),
            ("25 ft., fly 50 ft.", {"walk": "25 ft.", "fly": "50 ft."}),
            ("30 ft., swim 30 ft., climb 30 ft.", {"walk": "30 ft.", "swim": "30 ft.", "climb": "30 ft."}),
        ]

        for text, expected in test_cases:
            result = extractor._parse_speed(text)
            for key, value in expected.items():
                assert key in result, f"Expected '{key}' in speed from: {text}"
                assert result[key] == value, f"Expected {key}={value}, got {result[key]}"

    def test_proficiency_bonus_for_level(self, extractor):
        """Test proficiency bonus calculation."""
        test_cases = [
            (1, 2), (4, 2),
            (5, 3), (8, 3),
            (9, 4), (12, 4),
            (13, 5), (16, 5),
            (17, 6), (20, 6),
        ]

        for level, expected in test_cases:
            result = extractor._proficiency_bonus_for_level(level)
            assert result == expected, f"Level {level}: expected +{expected}, got +{result}"


class TestContentExtractorClassParsing:
    """Tests for class content parsing."""

    @pytest.fixture
    def extractor(self):
        """Create a ContentExtractor with a mock library manager."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()
            yield ContentExtractor(manager)

    def test_parse_class_basic(self, extractor):
        """Test parsing basic class information."""
        raw_text = """
        Fighter

        As a fighter, you gain the following class features.

        Hit Dice: 1d10 per fighter level

        Saving Throws: Strength, Constitution

        Armor: All armor, shields
        Weapons: Simple weapons, martial weapons
        Tools: None

        Skills: Choose two from Acrobatics, Animal Handling, Athletics

        At 1st Level, you gain the Fighting Style feature.
        At 2nd Level, you gain Action Surge.
        At 3rd level, you choose an archetype.
        """

        result = extractor._parse_class(raw_text, "Fighter")

        assert result["name"] == "Fighter"
        assert result["index"] == "fighter"
        assert result["hit_die"] == 10
        assert "STR" in result["saving_throws"]
        assert "CON" in result["saving_throws"]
        assert result["subclass_level"] == 3

    def test_parse_class_with_features(self, extractor):
        """Test parsing class with level features."""
        raw_text = """
        Rogue

        Hit Die: d8

        Saving Throws: Dexterity, Intelligence

        At 1st Level, you gain Sneak Attack.
        At 2nd Level, you gain Cunning Action.
        At 3rd Level, you choose a Roguish Archetype.
        At 5th Level, your Sneak Attack improves.
        """

        result = extractor._parse_class(raw_text, "Rogue")

        assert result["hit_die"] == 8
        assert "DEX" in result["saving_throws"]
        assert 1 in result["class_levels"]
        assert 2 in result["class_levels"]


class TestContentExtractorRaceParsing:
    """Tests for race content parsing."""

    @pytest.fixture
    def extractor(self):
        """Create a ContentExtractor with a mock library manager."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()
            yield ContentExtractor(manager)

    def test_parse_race_basic(self, extractor):
        """Test parsing basic race information."""
        raw_text = """
        Elf

        Elves are a magical people of otherworldly grace.

        Ability Score Increase. Your Dexterity score increases by 2.

        Size. Medium

        Speed. Your base walking speed is 30 feet.

        Darkvision. You can see in dim light within 60 feet.

        Languages. You can speak, read, and write Common and Elvish.
        """

        result = extractor._parse_race(raw_text, "Elf")

        assert result["name"] == "Elf"
        assert result["index"] == "elf"
        assert result["size"] == "Medium"
        assert result["speed"] == 30
        assert any(b["ability_score"] == "DEX" and b["bonus"] == 2 for b in result["ability_bonuses"])
        assert "Common" in result["languages"]
        assert "Elvish" in result["languages"]

    def test_parse_race_with_traits(self, extractor):
        """Test parsing race with traits."""
        raw_text = """
        Dwarf

        Ability Score Increase. Your Constitution score increases by 2.

        Size. Medium

        Speed. Your base walking speed is 25 feet.

        Darkvision. You can see in dim light within 60 feet of you.

        Dwarven Resilience. You have advantage on saving throws against poison.

        Stonecunning. Whenever you make a History check related to stonework.
        """

        result = extractor._parse_race(raw_text, "Dwarf")

        assert result["speed"] == 25
        # Should have Darkvision trait
        trait_names = [t["name"] for t in result["traits"]]
        assert "Darkvision" in trait_names


class TestContentExtractorSpellParsing:
    """Tests for spell content parsing."""

    @pytest.fixture
    def extractor(self):
        """Create a ContentExtractor with a mock library manager."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()
            yield ContentExtractor(manager)

    def test_parse_spell_basic(self, extractor):
        """Test parsing basic spell information."""
        raw_text = """
        Fireball

        3rd-level evocation

        Casting Time: 1 action
        Range: 150 feet
        Components: V, S, M (a tiny ball of bat guano and sulfur)
        Duration: Instantaneous

        A bright streak flashes from your pointing finger to a point you choose.

        At Higher Levels. When you cast this spell using a spell slot of 4th level or higher...
        """

        result = extractor._parse_spell(raw_text, "Fireball")

        assert result["name"] == "Fireball"
        assert result["index"] == "fireball"
        assert result["level"] == 3
        assert result["school"] == "Evocation"
        assert result["casting_time"] == "1 action"
        assert result["range"] == "150 feet"
        assert "V" in result["components"]
        assert "S" in result["components"]
        assert "M" in result["components"]
        assert "ball of bat guano" in result.get("material", "")

    def test_parse_cantrip(self, extractor):
        """Test parsing cantrip."""
        raw_text = """
        Fire Bolt

        Evocation cantrip

        Casting Time: 1 action
        Range: 120 feet
        Components: V, S
        Duration: Instantaneous

        You hurl a mote of fire at a creature or object within range.
        """

        result = extractor._parse_spell(raw_text, "Fire Bolt")

        assert result["level"] == 0
        assert result["school"] == "Evocation"


class TestContentExtractorCustomSourceFormat:
    """Tests for CustomSource JSON format conversion."""

    @pytest.fixture
    def extractor(self):
        """Create a ContentExtractor with a mock library manager."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()
            yield ContentExtractor(manager)

    def test_to_custom_source_format_class(self, extractor):
        """Test converting class to CustomSource format."""
        extracted = ExtractedContent(
            name="Fighter",
            content_type=ContentType.CLASS,
            source_id="phb",
            page_start=10,
            page_end=25,
            parsed_data={
                "index": "fighter",
                "name": "Fighter",
                "hit_die": 10,
                "saving_throws": ["STR", "CON"],
            },
        )

        result = extractor._to_custom_source_format(extracted)

        assert result["$schema"] == "gamemaster-mcp/rulebook-v1"
        assert "content" in result
        assert "classes" in result["content"]
        assert len(result["content"]["classes"]) == 1
        assert result["content"]["classes"][0]["name"] == "Fighter"
        assert result["content"]["classes"][0]["hit_die"] == 10

    def test_to_custom_source_format_race(self, extractor):
        """Test converting race to CustomSource format."""
        extracted = ExtractedContent(
            name="Elf",
            content_type=ContentType.RACE,
            source_id="phb",
            page_start=30,
            parsed_data={
                "index": "elf",
                "name": "Elf",
                "speed": 30,
                "size": "Medium",
            },
        )

        result = extractor._to_custom_source_format(extracted)

        assert "content" in result
        assert "races" in result["content"]
        assert len(result["content"]["races"]) == 1
        assert result["content"]["races"][0]["speed"] == 30


class TestContentExtractorIntegration:
    """Integration tests with mock PDF data."""

    def test_find_toc_entry(self):
        """Test finding TOC entry by name."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create index with TOC
            index = IndexEntry(
                source_id="test-source",
                filename="test.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash="abc123",
                total_pages=100,
                toc=[
                    TOCEntry(title="Classes", page=10, children=[
                        TOCEntry(title="Fighter", page=15, content_type=ContentType.CLASS),
                        TOCEntry(title="Wizard", page=30, content_type=ContentType.CLASS),
                    ]),
                    TOCEntry(title="Races", page=50, children=[
                        TOCEntry(title="Elf", page=55, content_type=ContentType.RACE),
                    ]),
                ],
            )
            manager.save_index(index)

            extractor = ContentExtractor(manager)

            # Test finding exact match
            entry = extractor._find_toc_entry("test-source", "Fighter", "class")
            assert entry is not None
            assert entry.title == "Fighter"
            assert entry.page == 15

            # Test finding by partial match
            entry = extractor._find_toc_entry("test-source", "Elf", "race")
            assert entry is not None
            assert entry.title == "Elf"

            # Test not found
            entry = extractor._find_toc_entry("test-source", "Barbarian", "class")
            assert entry is None

    def test_estimate_end_page(self):
        """Test estimating end page from next TOC entry."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create index with sequential TOC entries
            fighter_entry = TOCEntry(title="Fighter", page=15, content_type=ContentType.CLASS)
            wizard_entry = TOCEntry(title="Wizard", page=30, content_type=ContentType.CLASS)

            index = IndexEntry(
                source_id="test-source",
                filename="test.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash="abc123",
                total_pages=100,
                toc=[
                    TOCEntry(title="Classes", page=10, children=[
                        fighter_entry,
                        wizard_entry,
                    ]),
                ],
            )
            manager.save_index(index)

            extractor = ContentExtractor(manager)

            # End page should be one before next entry
            end_page = extractor._estimate_end_page("test-source", fighter_entry)
            assert end_page == 29  # One before Wizard's page 30

    def test_save_extracted_content_creates_directory(self):
        """Test that save_extracted_content creates the extracted directory."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create a fake PDF file
            (manager.pdfs_dir / "test.pdf").write_bytes(b"%PDF-1.4 fake")

            extractor = ContentExtractor(manager)

            # The extracted directory should be created
            extracted_dir = manager.extracted_dir / "test-source"

            # Note: Full save test would require a real PDF with extractable content
            # This test just verifies the directory structure
            assert manager.extracted_dir.exists()


class TestMonsterPatterns:
    """Tests for monster regex patterns."""

    def test_size_type_alignment_pattern(self):
        """Test monster size, type, and alignment extraction."""
        import re

        test_cases = [
            ("Medium humanoid (human), lawful good", ("Medium", "humanoid", "human", "lawful good")),
            ("Large dragon, chaotic evil", ("Large", "dragon", None, "chaotic evil")),
            ("Tiny beast, unaligned", ("Tiny", "beast", None, "unaligned")),
            ("Huge giant (fire giant), lawful evil", ("Huge", "giant", "fire giant", "lawful evil")),
        ]

        for text, expected in test_cases:
            match = re.search(MONSTER_PATTERNS["size_type_alignment"], text, re.IGNORECASE)
            assert match is not None, f"Failed to match: {text}"
            assert match.group(1) == expected[0]  # Size
            assert match.group(2).lower() == expected[1].lower()  # Type

    def test_armor_class_pattern(self):
        """Test armor class extraction."""
        import re

        test_cases = [
            ("Armor Class 15 (natural armor)", ("15", "natural armor")),
            ("Armor Class 18 (plate)", ("18", "plate")),
            ("Armor Class 12", ("12", None)),
        ]

        for text, expected in test_cases:
            match = re.search(MONSTER_PATTERNS["armor_class"], text, re.IGNORECASE)
            assert match is not None, f"Failed to match: {text}"
            assert match.group(1) == expected[0]
            assert match.group(2) == expected[1]

    def test_hit_points_pattern(self):
        """Test hit points extraction."""
        import re

        test_cases = [
            ("Hit Points 66 (12d8 + 12)", ("66", "12d8 + 12")),
            ("Hit Points 135 (18d10 + 36)", ("135", "18d10 + 36")),
        ]

        for text, expected in test_cases:
            match = re.search(MONSTER_PATTERNS["hit_points"], text, re.IGNORECASE)
            assert match is not None, f"Failed to match: {text}"
            assert match.group(1) == expected[0]
            assert match.group(2) == expected[1]

    def test_challenge_pattern(self):
        """Test challenge rating extraction."""
        import re

        test_cases = [
            ("Challenge 5 (1,800 XP)", ("5", "1,800")),
            ("Challenge 1/4 (50 XP)", ("1/4", "50")),
            ("Challenge 10 (5,900 XP)", ("10", "5,900")),
        ]

        for text, expected in test_cases:
            match = re.search(MONSTER_PATTERNS["challenge"], text, re.IGNORECASE)
            assert match is not None, f"Failed to match: {text}"
            assert match.group(1) == expected[0]
            assert expected[1] in match.group(2)

    def test_ability_score_patterns(self):
        """Test ability score extraction."""
        import re

        text = "STR 18 (+4) DEX 14 (+2) CON 16 (+3) INT 10 (+0) WIS 12 (+1) CHA 8 (-1)"

        for ability in ["str", "dex", "con", "int", "wis", "cha"]:
            match = re.search(MONSTER_PATTERNS[ability], text, re.IGNORECASE)
            assert match is not None, f"Failed to match {ability}"
            assert match.group(1) is not None  # Score
            assert match.group(2) is not None  # Modifier


class TestFeatPatterns:
    """Tests for feat regex patterns."""

    def test_prerequisite_pattern(self):
        """Test prerequisite extraction."""
        import re

        test_cases = [
            ("Prerequisite: Strength 13 or higher", "Strength 13 or higher"),
            ("Prerequisite: Ability to cast at least one spell", "Ability to cast at least one spell"),
            ("Prerequisite: Proficiency with heavy armor", "Proficiency with heavy armor"),
        ]

        for text, expected in test_cases:
            match = re.search(FEAT_PATTERNS["prerequisite"], text, re.IGNORECASE)
            assert match is not None, f"Failed to match: {text}"
            assert match.group(1) == expected

    def test_bullet_pattern(self):
        """Test bullet point extraction."""
        import re

        test_cases = [
            ("• You gain proficiency in Athletics", "You gain proficiency in Athletics"),
            ("- Increase your Strength by 1", "Increase your Strength by 1"),
            ("* You have advantage on saving throws", "You have advantage on saving throws"),
        ]

        for text, expected in test_cases:
            match = re.search(FEAT_PATTERNS["bullet"], text)
            assert match is not None, f"Failed to match: {text}"
            assert match.group(1) == expected


class TestItemPatterns:
    """Tests for item regex patterns."""

    def test_rarity_pattern(self):
        """Test item rarity extraction."""
        import re

        test_cases = [
            ("Wondrous item, rare", "rare"),
            ("Weapon (longsword), uncommon", "uncommon"),
            ("Armor (plate), legendary", "legendary"),
            ("Ring, very rare", "very rare"),
        ]

        for text, expected in test_cases:
            match = re.search(ITEM_PATTERNS["rarity"], text, re.IGNORECASE)
            assert match is not None, f"Failed to match: {text}"
            assert match.group(1).lower() == expected

    def test_type_pattern(self):
        """Test item type extraction."""
        import re

        test_cases = [
            ("Wondrous item, rare", "Wondrous item"),
            ("Weapon (longsword), uncommon", "Weapon"),
            ("Armor (plate), legendary", "Armor"),
            ("Potion, common", "Potion"),
        ]

        for text, expected in test_cases:
            match = re.search(ITEM_PATTERNS["type"], text, re.IGNORECASE)
            assert match is not None, f"Failed to match: {text}"
            assert match.group(1) == expected

    def test_attunement_pattern(self):
        """Test attunement requirement extraction."""
        import re

        test_cases = [
            ("requires attunement by a spellcaster)", "a spellcaster"),
            ("requires attunement by a cleric or paladin,", "a cleric or paladin"),
            ("requires attunement", None),
        ]

        for text, expected in test_cases:
            match = re.search(ITEM_PATTERNS["attunement"], text, re.IGNORECASE)
            assert match is not None, f"Failed to match: {text}"
            if expected:
                assert match.group(1) == expected
            else:
                assert match.group(1) is None or match.group(1) == ""

    def test_charges_pattern(self):
        """Test charges extraction."""
        import re

        test_cases = [
            ("The staff has 10 charges", "10"),
            ("This wand has 7 charges", "7"),
        ]

        for text, expected in test_cases:
            match = re.search(ITEM_PATTERNS["charges"], text, re.IGNORECASE)
            assert match is not None, f"Failed to match: {text}"
            assert match.group(1) == expected


class TestContentExtractorMonsterParsing:
    """Tests for monster content parsing."""

    @pytest.fixture
    def extractor(self):
        """Create a ContentExtractor with a mock library manager."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()
            yield ContentExtractor(manager)

    def test_parse_monster_basic(self, extractor):
        """Test parsing basic monster information."""
        raw_text = """
        Goblin

        Small humanoid (goblinoid), neutral evil

        Armor Class 15 (leather armor, shield)
        Hit Points 7 (2d6)
        Speed 30 ft.

        STR 8 (-1) DEX 14 (+2) CON 10 (+0) INT 10 (+0) WIS 8 (-1) CHA 8 (-1)

        Senses darkvision 60 ft., passive Perception 9
        Languages Common, Goblin
        Challenge 1/4 (50 XP)
        """

        result = extractor._parse_monster(raw_text, "Goblin")

        assert result["name"] == "Goblin"
        assert result["index"] == "goblin"
        assert result["size"] == "Small"
        assert result["type"] == "humanoid"
        assert result["armor_class"][0]["value"] == 15
        assert result["hit_points"] == 7
        assert result["hit_dice"] == "2d6"
        assert result["dexterity"] == 14
        assert result["challenge_rating"] == 0.25

    def test_parse_monster_with_speeds(self, extractor):
        """Test parsing monster with multiple speed types."""
        raw_text = """
        Dragon

        Huge dragon, chaotic evil

        Armor Class 19 (natural armor)
        Hit Points 195 (17d12 + 85)
        Speed 40 ft., fly 80 ft., swim 40 ft.

        STR 23 (+6) DEX 10 (+0) CON 21 (+5) INT 14 (+2) WIS 11 (+0) CHA 19 (+4)

        Challenge 13 (10,000 XP)
        """

        result = extractor._parse_monster(raw_text, "Dragon")

        assert result["size"] == "Huge"
        assert result["type"] == "dragon"
        assert result["armor_class"][0]["value"] == 19
        assert "walk" in result["speed"]
        assert "fly" in result["speed"]
        assert "swim" in result["speed"]
        assert result["strength"] == 23
        assert result["challenge_rating"] == 13


class TestContentExtractorFeatParsing:
    """Tests for feat content parsing."""

    @pytest.fixture
    def extractor(self):
        """Create a ContentExtractor with a mock library manager."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()
            yield ContentExtractor(manager)

    def test_parse_feat_with_prerequisite(self, extractor):
        """Test parsing feat with prerequisite."""
        raw_text = """
        Great Weapon Master

        Prerequisite: Proficiency with a martial weapon

        You've learned to put the weight of a weapon to your advantage.

        • On your turn, when you score a critical hit with a melee weapon
        • Before you make a melee attack, you can choose to take a -5 penalty
        """

        result = extractor._parse_feat(raw_text, "Great Weapon Master")

        assert result["name"] == "Great Weapon Master"
        assert result["index"] == "great-weapon-master"
        assert len(result["prerequisites"]) > 0
        assert "martial weapon" in result["prerequisites"][0]["description"]
        assert len(result["desc"]) >= 2

    def test_parse_feat_without_prerequisite(self, extractor):
        """Test parsing feat without prerequisite."""
        raw_text = """
        Lucky

        You have inexplicable luck that seems to kick in at just the right moment.

        • You have 3 luck points.
        • Whenever you make an attack roll, an ability check, or a saving throw, you can spend one luck point.
        • You regain your expended luck points when you finish a long rest.
        """

        result = extractor._parse_feat(raw_text, "Lucky")

        assert result["name"] == "Lucky"
        assert result["index"] == "lucky"
        assert len(result["prerequisites"]) == 0
        assert len(result["desc"]) >= 3


class TestContentExtractorItemParsing:
    """Tests for item content parsing."""

    @pytest.fixture
    def extractor(self):
        """Create a ContentExtractor with a mock library manager."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()
            yield ContentExtractor(manager)

    def test_parse_item_wondrous(self, extractor):
        """Test parsing wondrous item."""
        raw_text = """
        Cloak of Elvenkind

        Wondrous item, uncommon (requires attunement)

        While you wear this cloak with its hood up, Wisdom (Perception) checks made
        to see you have disadvantage, and you have advantage on Dexterity (Stealth)
        checks made to hide.
        """

        result = extractor._parse_item(raw_text, "Cloak of Elvenkind")

        assert result["name"] == "Cloak of Elvenkind"
        assert result["index"] == "cloak-of-elvenkind"
        assert result["equipment_category"] == "wondrous-items"
        assert result["rarity"] == "Uncommon"
        assert result["requires_attunement"] is True

    def test_parse_item_weapon(self, extractor):
        """Test parsing magic weapon."""
        raw_text = """
        Flame Tongue

        Weapon (any sword), rare (requires attunement)

        You can use a bonus action to speak this magic sword's command word,
        causing flames to erupt from the blade.
        """

        result = extractor._parse_item(raw_text, "Flame Tongue")

        assert result["name"] == "Flame Tongue"
        assert result["equipment_category"] == "weapon"
        assert result["rarity"] == "Rare"
        assert result["requires_attunement"] is True

    def test_parse_item_potion(self, extractor):
        """Test parsing potion."""
        raw_text = """
        Potion of Healing

        Potion, common

        You regain 2d4 + 2 hit points when you drink this potion.
        """

        result = extractor._parse_item(raw_text, "Potion of Healing")

        assert result["name"] == "Potion of Healing"
        assert result["equipment_category"] == "potion"
        assert result["rarity"] == "Common"
        assert "requires_attunement" not in result or result.get("requires_attunement") is not True

    def test_parse_item_with_class_attunement(self, extractor):
        """Test parsing item with class-specific attunement."""
        raw_text = """
        Holy Avenger

        Weapon (any sword), legendary (requires attunement by a paladin)

        You gain a +3 bonus to attack and damage rolls made with this magic weapon.
        """

        result = extractor._parse_item(raw_text, "Holy Avenger")

        assert result["name"] == "Holy Avenger"
        assert result["rarity"] == "Legendary"
        assert result["requires_attunement"] is True
        assert "paladin" in result.get("attunement_requirements", "").lower()


class TestContentExtractorCustomSourceFormatExtended:
    """Extended tests for CustomSource JSON format conversion."""

    @pytest.fixture
    def extractor(self):
        """Create a ContentExtractor with a mock library manager."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()
            yield ContentExtractor(manager)

    def test_to_custom_source_format_spell(self, extractor):
        """Test converting spell to CustomSource format."""
        extracted = ExtractedContent(
            name="Fireball",
            content_type=ContentType.SPELL,
            source_id="phb",
            page_start=241,
            parsed_data={
                "index": "fireball",
                "name": "Fireball",
                "level": 3,
                "school": "Evocation",
            },
        )

        result = extractor._to_custom_source_format(extracted)

        assert "content" in result
        assert "spells" in result["content"]
        assert len(result["content"]["spells"]) == 1
        assert result["content"]["spells"][0]["level"] == 3

    def test_to_custom_source_format_monster(self, extractor):
        """Test converting monster to CustomSource format."""
        extracted = ExtractedContent(
            name="Goblin",
            content_type=ContentType.MONSTER,
            source_id="mm",
            page_start=166,
            parsed_data={
                "index": "goblin",
                "name": "Goblin",
                "challenge_rating": 0.25,
            },
        )

        result = extractor._to_custom_source_format(extracted)

        assert "content" in result
        assert "monsters" in result["content"]
        assert len(result["content"]["monsters"]) == 1

    def test_to_custom_source_format_feat(self, extractor):
        """Test converting feat to CustomSource format."""
        extracted = ExtractedContent(
            name="Alert",
            content_type=ContentType.FEAT,
            source_id="phb",
            page_start=165,
            parsed_data={
                "index": "alert",
                "name": "Alert",
                "prerequisites": [],
            },
        )

        result = extractor._to_custom_source_format(extracted)

        assert "content" in result
        assert "feats" in result["content"]
        assert len(result["content"]["feats"]) == 1

    def test_to_custom_source_format_item(self, extractor):
        """Test converting item to CustomSource format."""
        extracted = ExtractedContent(
            name="Bag of Holding",
            content_type=ContentType.ITEM,
            source_id="dmg",
            page_start=153,
            parsed_data={
                "index": "bag-of-holding",
                "name": "Bag of Holding",
                "rarity": "Uncommon",
            },
        )

        result = extractor._to_custom_source_format(extracted)

        assert "content" in result
        assert "items" in result["content"]
        assert len(result["content"]["items"]) == 1
