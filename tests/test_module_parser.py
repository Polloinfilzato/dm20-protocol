"""
Tests for adventure module parser.

Tests the ModuleParser and related data models with realistic
D&D adventure module TOC structures.
"""

import pytest
from pathlib import Path

from gamemaster_mcp.library.models import TOCEntry, ContentType as LibraryContentType
from gamemaster_mcp.claudmaster.models.module import (
    ContentType,
    ModuleElement,
    NPCReference,
    EncounterReference,
    LocationReference,
    ModuleStructure,
)


# Realistic sample TOC mimicking Curse of Strahd structure
SAMPLE_TOC_STRAHD = [
    TOCEntry(
        title="Chapter 1: Into the Mists",
        page=1,
        content_type=LibraryContentType.UNKNOWN,
        children=[
            TOCEntry(title="Death House", page=3, content_type=LibraryContentType.UNKNOWN),
            TOCEntry(title="Area 1. Entrance", page=5, content_type=LibraryContentType.UNKNOWN),
            TOCEntry(title="Area 2. Main Hall", page=6, content_type=LibraryContentType.UNKNOWN),
        ],
    ),
    TOCEntry(
        title="Chapter 2: The Village of Barovia",
        page=20,
        content_type=LibraryContentType.UNKNOWN,
        children=[
            TOCEntry(title="Encounter: Blood on the Vine", page=22, content_type=LibraryContentType.UNKNOWN),
            TOCEntry(title="Ismark the Lesser (NPC)", page=24, content_type=LibraryContentType.UNKNOWN),
            TOCEntry(title="Ireena Kolyana (NPC)", page=25, content_type=LibraryContentType.UNKNOWN),
        ],
    ),
    TOCEntry(
        title="Chapter 3: The Village of Vallaki",
        page=40,
        content_type=LibraryContentType.UNKNOWN,
        children=[
            TOCEntry(title="Areas of Vallaki", page=42, content_type=LibraryContentType.UNKNOWN),
            TOCEntry(title="The Blue Water Inn", page=45, content_type=LibraryContentType.UNKNOWN),
        ],
    ),
    TOCEntry(
        title="Appendix D: NPCs",
        page=200,
        content_type=LibraryContentType.UNKNOWN,
        children=[
            TOCEntry(title="Strahd von Zarovich", page=201, content_type=LibraryContentType.UNKNOWN),
            TOCEntry(title="Madam Eva", page=202, content_type=LibraryContentType.UNKNOWN),
        ],
    ),
]

# Sample TOC mimicking Lost Mine of Phandelver structure
SAMPLE_TOC_LMOP = [
    TOCEntry(
        title="Part 1: Goblin Arrows",
        page=1,
        content_type=LibraryContentType.UNKNOWN,
        children=[
            TOCEntry(title="Goblin Ambush", page=3, content_type=LibraryContentType.UNKNOWN),
            TOCEntry(title="Cragmaw Hideout", page=5, content_type=LibraryContentType.UNKNOWN),
            TOCEntry(title="Area 1. Cave Mouth", page=6, content_type=LibraryContentType.UNKNOWN),
            TOCEntry(title="Area 2. Goblin Den", page=7, content_type=LibraryContentType.UNKNOWN),
        ],
    ),
    TOCEntry(
        title="Part 2: Phandalin",
        page=20,
        content_type=LibraryContentType.UNKNOWN,
        children=[
            TOCEntry(title="Map of Phandalin", page=21, content_type=LibraryContentType.UNKNOWN),
            TOCEntry(title="Battle of the Sleeping Giant", page=25, content_type=LibraryContentType.UNKNOWN),
            TOCEntry(title="Sildar Hallwinter (NPC)", page=27, content_type=LibraryContentType.UNKNOWN),
        ],
    ),
    TOCEntry(
        title="Appendix: Dramatis Personae",
        page=100,
        content_type=LibraryContentType.UNKNOWN,
        children=[
            TOCEntry(title="Gundren Rockseeker", page=101, content_type=LibraryContentType.UNKNOWN),
        ],
    ),
]


class TestModuleElement:
    """Test ModuleElement data model."""

    def test_create_chapter(self):
        """Test creating a chapter element."""
        element = ModuleElement(
            name="Chapter 1: The Beginning",
            content_type=ContentType.CHAPTER,
            page_start=1,
            page_end=20,
        )
        assert element.name == "Chapter 1: The Beginning"
        assert element.content_type == ContentType.CHAPTER
        assert element.page_start == 1
        assert element.page_end == 20
        assert element.parent is None
        assert element.children == []

    def test_create_section_with_parent(self):
        """Test creating a section with parent relationship."""
        element = ModuleElement(
            name="Section 1.1",
            content_type=ContentType.SECTION,
            page_start=5,
            parent="Chapter 1",
            children=["Subsection 1.1.1"],
        )
        assert element.parent == "Chapter 1"
        assert element.children == ["Subsection 1.1.1"]

    def test_to_dict(self):
        """Test serialization to dictionary."""
        element = ModuleElement(
            name="Test Chapter",
            content_type=ContentType.CHAPTER,
            page_start=10,
            page_end=20,
            children=["Section A"],
        )
        data = element.to_dict()
        assert data["name"] == "Test Chapter"
        assert data["content_type"] == "chapter"
        assert data["page_start"] == 10
        assert data["page_end"] == 20
        assert data["children"] == ["Section A"]

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "name": "Test Chapter",
            "content_type": "chapter",
            "page_start": 10,
            "page_end": 20,
            "parent": "Part 1",
            "children": ["Section A"],
        }
        element = ModuleElement.from_dict(data)
        assert element.name == "Test Chapter"
        assert element.content_type == ContentType.CHAPTER
        assert element.page_start == 10
        assert element.page_end == 20
        assert element.parent == "Part 1"
        assert element.children == ["Section A"]

    def test_roundtrip(self):
        """Test to_dict/from_dict roundtrip."""
        original = ModuleElement(
            name="Chapter X",
            content_type=ContentType.SECTION,
            page_start=42,
            page_end=50,
            parent="Part 2",
            children=["Sub A", "Sub B"],
        )
        data = original.to_dict()
        restored = ModuleElement.from_dict(data)
        assert restored.name == original.name
        assert restored.content_type == original.content_type
        assert restored.page_start == original.page_start
        assert restored.page_end == original.page_end
        assert restored.parent == original.parent
        assert restored.children == original.children


class TestNPCReference:
    """Test NPCReference data model."""

    def test_create_basic_npc(self):
        """Test creating a basic NPC reference."""
        npc = NPCReference(
            name="Strahd von Zarovich",
            chapter="Chapter 1",
            page=15,
        )
        assert npc.name == "Strahd von Zarovich"
        assert npc.chapter == "Chapter 1"
        assert npc.page == 15
        assert npc.location is None

    def test_create_npc_with_location(self):
        """Test creating NPC with location."""
        npc = NPCReference(
            name="Ireena Kolyana",
            location="Village of Barovia",
            chapter="Chapter 2",
            page=25,
            description_preview="Daughter of the burgomaster",
        )
        assert npc.location == "Village of Barovia"
        assert npc.description_preview == "Daughter of the burgomaster"

    def test_to_dict(self):
        """Test serialization."""
        npc = NPCReference(
            name="Ismark",
            location="Barovia",
            chapter="Chapter 2",
            page=24,
        )
        data = npc.to_dict()
        assert data["name"] == "Ismark"
        assert data["location"] == "Barovia"
        assert data["chapter"] == "Chapter 2"
        assert data["page"] == 24

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "name": "Madam Eva",
            "location": "Tser Pool",
            "chapter": "Chapter 2",
            "page": 30,
            "description_preview": "Vistani seer",
        }
        npc = NPCReference.from_dict(data)
        assert npc.name == "Madam Eva"
        assert npc.location == "Tser Pool"

    def test_roundtrip(self):
        """Test to_dict/from_dict roundtrip."""
        original = NPCReference(
            name="Test NPC",
            location="Test Location",
            chapter="Chapter X",
            page=99,
            description_preview="A test character",
        )
        data = original.to_dict()
        restored = NPCReference.from_dict(data)
        assert restored.name == original.name
        assert restored.location == original.location
        assert restored.chapter == original.chapter
        assert restored.page == original.page


class TestEncounterReference:
    """Test EncounterReference data model."""

    def test_create_combat_encounter(self):
        """Test creating a combat encounter."""
        encounter = EncounterReference(
            name="Goblin Ambush",
            location="Road to Phandalin",
            chapter="Part 1",
            page=3,
            encounter_type="combat",
        )
        assert encounter.name == "Goblin Ambush"
        assert encounter.encounter_type == "combat"

    def test_create_social_encounter(self):
        """Test creating a social encounter."""
        encounter = EncounterReference(
            name="Negotiation with the Mayor",
            location="Town Hall",
            chapter="Chapter 2",
            page=25,
            encounter_type="social",
        )
        assert encounter.encounter_type == "social"

    def test_to_dict(self):
        """Test serialization."""
        encounter = EncounterReference(
            name="Area 5. Puzzle Door",
            location="Dungeon Level 1",
            chapter="Chapter 3",
            page=45,
            encounter_type="puzzle",
        )
        data = encounter.to_dict()
        assert data["name"] == "Area 5. Puzzle Door"
        assert data["encounter_type"] == "puzzle"

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "name": "Encounter: Dragon Fight",
            "location": "Dragon Lair",
            "chapter": "Chapter 5",
            "page": 100,
            "encounter_type": "combat",
        }
        encounter = EncounterReference.from_dict(data)
        assert encounter.name == "Encounter: Dragon Fight"
        assert encounter.encounter_type == "combat"

    def test_roundtrip(self):
        """Test to_dict/from_dict roundtrip."""
        original = EncounterReference(
            name="Test Encounter",
            location="Test Place",
            chapter="Chapter Y",
            page=77,
            encounter_type="exploration",
        )
        data = original.to_dict()
        restored = EncounterReference.from_dict(data)
        assert restored.name == original.name
        assert restored.location == original.location
        assert restored.chapter == original.chapter
        assert restored.page == original.page
        assert restored.encounter_type == original.encounter_type


class TestLocationReference:
    """Test LocationReference data model."""

    def test_create_location(self):
        """Test creating a location."""
        location = LocationReference(
            name="Village of Barovia",
            chapter="Chapter 2",
            page=20,
        )
        assert location.name == "Village of Barovia"
        assert location.chapter == "Chapter 2"
        assert location.page == 20
        assert location.parent_location is None

    def test_create_sublocation(self):
        """Test creating a sub-location."""
        location = LocationReference(
            name="The Blue Water Inn",
            chapter="Chapter 3",
            page=45,
            parent_location="Village of Vallaki",
            sub_locations=["Taproom", "Upstairs"],
        )
        assert location.parent_location == "Village of Vallaki"
        assert len(location.sub_locations) == 2

    def test_to_dict(self):
        """Test serialization."""
        location = LocationReference(
            name="Castle Ravenloft",
            chapter="Chapter 4",
            page=50,
            sub_locations=["K1. Front Gate", "K2. Courtyard"],
        )
        data = location.to_dict()
        assert data["name"] == "Castle Ravenloft"
        assert len(data["sub_locations"]) == 2

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "name": "Death House",
            "chapter": "Chapter 1",
            "page": 3,
            "parent_location": None,
            "sub_locations": ["Area 1", "Area 2"],
        }
        location = LocationReference.from_dict(data)
        assert location.name == "Death House"
        assert len(location.sub_locations) == 2

    def test_roundtrip(self):
        """Test to_dict/from_dict roundtrip."""
        original = LocationReference(
            name="Test Dungeon",
            chapter="Chapter Z",
            page=88,
            parent_location="Test Region",
            sub_locations=["Room 1", "Room 2", "Room 3"],
        )
        data = original.to_dict()
        restored = LocationReference.from_dict(data)
        assert restored.name == original.name
        assert restored.chapter == original.chapter
        assert restored.page == original.page
        assert restored.parent_location == original.parent_location
        assert restored.sub_locations == original.sub_locations


class TestModuleStructure:
    """Test ModuleStructure data model."""

    def test_create_empty_structure(self):
        """Test creating an empty module structure."""
        structure = ModuleStructure(
            module_id="test-module",
            title="Test Module",
            source_file="test.pdf",
        )
        assert structure.module_id == "test-module"
        assert structure.title == "Test Module"
        assert len(structure.chapters) == 0
        assert len(structure.npcs) == 0

    def test_create_full_structure(self):
        """Test creating a complete module structure."""
        chapter = ModuleElement(
            name="Chapter 1",
            content_type=ContentType.CHAPTER,
            page_start=1,
        )
        npc = NPCReference(
            name="Test NPC",
            chapter="Chapter 1",
            page=5,
        )
        encounter = EncounterReference(
            name="Test Encounter",
            location="Test Place",
            chapter="Chapter 1",
            page=10,
        )
        location = LocationReference(
            name="Test Location",
            chapter="Chapter 1",
            page=15,
        )

        structure = ModuleStructure(
            module_id="test-module",
            title="Test Module",
            source_file="test.pdf",
            chapters=[chapter],
            npcs=[npc],
            encounters=[encounter],
            locations=[location],
            metadata={"level": "1-5", "setting": "Forgotten Realms"},
        )

        assert len(structure.chapters) == 1
        assert len(structure.npcs) == 1
        assert len(structure.encounters) == 1
        assert len(structure.locations) == 1
        assert structure.metadata["level"] == "1-5"

    def test_to_dict(self):
        """Test serialization."""
        structure = ModuleStructure(
            module_id="curse-of-strahd",
            title="Curse of Strahd",
            source_file="cos.pdf",
            metadata={"level": "1-10"},
        )
        data = structure.to_dict()
        assert data["module_id"] == "curse-of-strahd"
        assert data["title"] == "Curse of Strahd"
        assert data["metadata"]["level"] == "1-10"

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "module_id": "lmop",
            "title": "Lost Mine of Phandelver",
            "source_file": "lmop.pdf",
            "chapters": [],
            "npcs": [],
            "encounters": [],
            "locations": [],
            "metadata": {"level": "1-5"},
        }
        structure = ModuleStructure.from_dict(data)
        assert structure.module_id == "lmop"
        assert structure.title == "Lost Mine of Phandelver"

    def test_roundtrip_with_all_components(self):
        """Test full to_dict/from_dict roundtrip with all components."""
        original = ModuleStructure(
            module_id="test-id",
            title="Test Title",
            source_file="test.pdf",
            chapters=[
                ModuleElement(
                    name="Chapter 1",
                    content_type=ContentType.CHAPTER,
                    page_start=1,
                    page_end=10,
                )
            ],
            npcs=[
                NPCReference(
                    name="Test NPC",
                    chapter="Chapter 1",
                    page=5,
                )
            ],
            encounters=[
                EncounterReference(
                    name="Test Encounter",
                    location="Test Place",
                    chapter="Chapter 1",
                    page=7,
                )
            ],
            locations=[
                LocationReference(
                    name="Test Location",
                    chapter="Chapter 1",
                    page=8,
                )
            ],
            metadata={"test": "value"},
        )

        data = original.to_dict()
        restored = ModuleStructure.from_dict(data)

        assert restored.module_id == original.module_id
        assert restored.title == original.title
        assert restored.source_file == original.source_file
        assert len(restored.chapters) == len(original.chapters)
        assert len(restored.npcs) == len(original.npcs)
        assert len(restored.encounters) == len(original.encounters)
        assert len(restored.locations) == len(original.locations)
        assert restored.metadata == original.metadata


class TestModuleParserPatterns:
    """Test pattern matching logic in ModuleParser (without file I/O)."""

    def test_npc_pattern_with_suffix(self):
        """Test NPC pattern matching with (NPC) suffix.

        Note: Only explicit (NPC) suffix is supported to avoid false positives
        with regular text that looks like proper names.
        """
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        assert parser._matches_patterns("Ismark the Lesser (NPC)", parser.NPC_PATTERNS)
        assert parser._matches_patterns("Strahd von Zarovich (NPC)", parser.NPC_PATTERNS)

        # Should NOT match regular proper names without (NPC) suffix
        assert not parser._matches_patterns("Ismark Kolyanovich", parser.NPC_PATTERNS)
        assert not parser._matches_patterns("Madam Eva", parser.NPC_PATTERNS)

    def test_encounter_patterns(self):
        """Test encounter pattern matching."""
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        assert parser._matches_patterns("Encounter: Blood on the Vine", parser.ENCOUNTER_PATTERNS)
        assert parser._matches_patterns("Area 12. Throne Room", parser.ENCOUNTER_PATTERNS)
        assert parser._matches_patterns("Room 5", parser.ENCOUNTER_PATTERNS)
        assert parser._matches_patterns("K1. Entrance", parser.ENCOUNTER_PATTERNS)
        assert parser._matches_patterns("Battle of Phandalin", parser.ENCOUNTER_PATTERNS)
        assert parser._matches_patterns("Fight at the Inn", parser.ENCOUNTER_PATTERNS)

    def test_location_patterns(self):
        """Test location pattern matching."""
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        assert parser._matches_patterns("Areas of Vallaki", parser.LOCATION_PATTERNS)
        assert parser._matches_patterns("Area of Death House", parser.LOCATION_PATTERNS)
        assert parser._matches_patterns("Map of Barovia", parser.LOCATION_PATTERNS)
        assert parser._matches_patterns("The Blue Castle", parser.LOCATION_PATTERNS)
        assert parser._matches_patterns("The Old Village", parser.LOCATION_PATTERNS)

    def test_appendix_patterns(self):
        """Test appendix pattern matching."""
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        assert parser._matches_patterns("Appendix D: NPCs", parser.APPENDIX_PATTERNS)
        assert parser._matches_patterns("Dramatis Personae", parser.APPENDIX_PATTERNS)
        assert parser._matches_patterns("Appendix: Magic Items", parser.APPENDIX_PATTERNS)


class TestModuleParserExtraction:
    """Test extraction methods with realistic sample data."""

    def test_extract_chapters_strahd(self):
        """Test chapter extraction with Curse of Strahd structure."""
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        chapters = parser.extract_chapters(SAMPLE_TOC_STRAHD)

        # Check we got chapters
        assert len(chapters) > 0

        # Check first chapter
        chapter1 = [ch for ch in chapters if ch.name == "Chapter 1: Into the Mists"][0]
        assert chapter1.content_type == ContentType.CHAPTER
        assert chapter1.page_start == 1
        assert chapter1.parent is None

        # Check child section
        death_house = [ch for ch in chapters if ch.name == "Death House"][0]
        assert death_house.content_type == ContentType.SECTION
        assert death_house.parent == "Chapter 1: Into the Mists"

        # Check appendix is marked correctly
        appendix = [ch for ch in chapters if ch.name == "Appendix D: NPCs"][0]
        assert appendix.content_type == ContentType.APPENDIX

    def test_extract_chapters_lmop(self):
        """Test chapter extraction with Lost Mine structure."""
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        chapters = parser.extract_chapters(SAMPLE_TOC_LMOP)

        assert len(chapters) > 0

        # Check part structure
        part1 = [ch for ch in chapters if ch.name == "Part 1: Goblin Arrows"][0]
        assert part1.content_type == ContentType.CHAPTER
        assert "Goblin Ambush" in part1.children or "Cragmaw Hideout" in part1.children

    def test_extract_npcs_strahd(self):
        """Test NPC extraction from Curse of Strahd structure."""
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        npcs = parser.extract_npcs(SAMPLE_TOC_STRAHD)

        # Should find NPCs with (NPC) suffix
        npc_names = [npc.name for npc in npcs]
        assert "Ismark the Lesser" in npc_names
        assert "Ireena Kolyana" in npc_names

        # Check NPC details
        ismark = [npc for npc in npcs if npc.name == "Ismark the Lesser"][0]
        assert ismark.page == 24
        assert "Chapter 2" in ismark.chapter

    def test_extract_npcs_lmop(self):
        """Test NPC extraction from Lost Mine structure."""
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        npcs = parser.extract_npcs(SAMPLE_TOC_LMOP)

        npc_names = [npc.name for npc in npcs]
        assert "Sildar Hallwinter" in npc_names

    def test_extract_encounters_strahd(self):
        """Test encounter extraction from Curse of Strahd structure."""
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        encounters = parser.extract_encounters(SAMPLE_TOC_STRAHD)

        encounter_names = [enc.name for enc in encounters]
        assert "Encounter: Blood on the Vine" in encounter_names

        # Check encounter with Area number
        area_encounters = [enc for enc in encounters if enc.name.startswith("Area")]
        assert len(area_encounters) >= 2  # Area 1, Area 2

    def test_extract_encounters_lmop(self):
        """Test encounter extraction from Lost Mine structure."""
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        encounters = parser.extract_encounters(SAMPLE_TOC_LMOP)

        encounter_names = [enc.name for enc in encounters]

        # Check for Battle encounter
        assert "Battle of the Sleeping Giant" in encounter_names

        # Check for Area encounters
        area_encounters = [enc for enc in encounters if enc.name.startswith("Area")]
        assert len(area_encounters) >= 2

    def test_extract_locations_strahd(self):
        """Test location extraction from Curse of Strahd structure."""
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        locations = parser.extract_locations(SAMPLE_TOC_STRAHD)

        location_names = [loc.name for loc in locations]
        assert "Areas of Vallaki" in location_names

    def test_extract_locations_lmop(self):
        """Test location extraction from Lost Mine structure."""
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        locations = parser.extract_locations(SAMPLE_TOC_LMOP)

        location_names = [loc.name for loc in locations]
        assert "Map of Phandalin" in location_names


class TestModuleParserEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_toc(self):
        """Test parsing with empty TOC."""
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        chapters = parser.extract_chapters([])
        npcs = parser.extract_npcs([])
        encounters = parser.extract_encounters([])
        locations = parser.extract_locations([])

        assert len(chapters) == 0
        assert len(npcs) == 0
        assert len(encounters) == 0
        assert len(locations) == 0

    def test_no_matching_patterns(self):
        """Test TOC with no recognizable patterns."""
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        toc = [
            TOCEntry(title="Random Text", page=1, content_type=LibraryContentType.UNKNOWN),
            TOCEntry(title="More Random Text", page=2, content_type=LibraryContentType.UNKNOWN),
        ]

        npcs = parser.extract_npcs(toc)
        encounters = parser.extract_encounters(toc)
        locations = parser.extract_locations(toc)

        # Should not find any NPCs, encounters, or locations
        # (but chapters should still be created)
        assert len(npcs) == 0
        assert len(encounters) == 0
        assert len(locations) == 0

    def test_deeply_nested_toc(self):
        """Test with deeply nested TOC structure."""
        from gamemaster_mcp.claudmaster.module_parser import ModuleParser
        parser = ModuleParser("/tmp/fake")

        toc = [
            TOCEntry(
                title="Chapter 1",
                page=1,
                content_type=LibraryContentType.UNKNOWN,
                children=[
                    TOCEntry(
                        title="Section 1.1",
                        page=2,
                        content_type=LibraryContentType.UNKNOWN,
                        children=[
                            TOCEntry(
                                title="Subsection 1.1.1",
                                page=3,
                                content_type=LibraryContentType.UNKNOWN,
                                children=[
                                    TOCEntry(
                                        title="Area 1. Deep Room",
                                        page=4,
                                        content_type=LibraryContentType.UNKNOWN,
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ]

        chapters = parser.extract_chapters(toc)
        encounters = parser.extract_encounters(toc)

        # Should handle all nesting levels
        assert len(chapters) == 4  # Chapter, Section, Subsection, Area
        assert len(encounters) >= 1  # Area 1 should be detected
