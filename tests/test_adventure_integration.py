"""
Integration tests for the complete adventure module pipeline.

Tests the full flow: discover_adventures → select → load_adventure → verify
campaign entities. Uses fixture data for offline CI testing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dm20_protocol.adventures.discovery import (
    format_search_results,
    search_adventures,
)
from dm20_protocol.adventures.index import AdventureIndex
from dm20_protocol.adventures.models import AdventureIndexEntry
from dm20_protocol.adventures.parser import AdventureParser
from dm20_protocol.adventures.tools import load_adventure_flow
from dm20_protocol.claudmaster.models.module import ContentType, ModuleStructure
from dm20_protocol.claudmaster.module_binding import BindingResult
from dm20_protocol.models import Campaign, GameState

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "adventures"

pytestmark = pytest.mark.anyio

MARKUP_TAG_RE = re.compile(r"\{@\w+")


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def index_json() -> dict:
    """Load the adventure index fixture."""
    with open(FIXTURES_DIR / "adventures_index_sample.json") as f:
        return json.load(f)


@pytest.fixture
def adventure_json() -> dict:
    """Load the SCC-CK adventure fixture."""
    with open(FIXTURES_DIR / "adventure-scc-ck-sample.json") as f:
        return json.load(f)


@pytest.fixture
def loaded_index(tmp_path: Path, index_json: dict) -> AdventureIndex:
    """AdventureIndex loaded from fixture data."""
    cache_dir = tmp_path / "adventures" / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "adventures.json").write_text(json.dumps(index_json))
    idx = AdventureIndex(cache_dir=tmp_path)
    idx._load_from_cache()
    return idx


@pytest.fixture
def parser(tmp_path: Path) -> AdventureParser:
    """AdventureParser with fixture cache directory."""
    return AdventureParser(cache_dir=tmp_path)


@pytest.fixture
def mock_storage():
    """Mock DnDStorage for integration tests."""
    storage = MagicMock()
    storage._current_campaign = None
    storage.list_campaigns.return_value = []
    storage._split_backend = MagicMock()
    storage._split_backend._get_campaign_dir.return_value = Path(
        "/fake/campaign/dir"
    )
    return storage


# --- Full Pipeline Integration Tests ---


class TestFullPipelineIntegration:
    """Test the complete discover → select → load flow."""

    async def test_discover_strixhaven_select_scc_ck_and_load(
        self,
        loaded_index: AdventureIndex,
        parser: AdventureParser,
        adventure_json: dict,
        mock_storage: MagicMock,
    ):
        """Full flow: discover Strixhaven → select SCC-CK → load → verify."""

        # Step 1: Discover adventures matching "strixhaven"
        result = search_adventures(loaded_index, query="strixhaven")

        assert result.total_matches >= 1
        assert any(
            g.storyline == "Strixhaven" for g in result.groups
        ), "Should find Strixhaven storyline"

        # Find SCC-CK in results
        scc_ck = None
        for group in result.groups:
            for adv in group.adventures:
                if adv.id == "SCC-CK":
                    scc_ck = adv
                    break

        assert scc_ck is not None, "SCC-CK should be in discovery results"
        assert scc_ck.name == "Strixhaven: Campus Kerfuffle"

        # Step 2: Parse the adventure
        with patch.object(
            parser, "_get_adventure_data", return_value=adventure_json
        ):
            module = await parser.parse_adventure("SCC-CK")

        # Step 3: Verify ModuleStructure completeness
        assert module.module_id == "SCC-CK"
        assert module.title == "Strixhaven: Campus Kerfuffle"
        assert len(module.chapters) == 2
        assert len(module.npcs) > 0
        assert len(module.locations) > 0
        assert len(module.read_aloud) > 0

        # Step 4: Load into campaign
        with patch(
            "dm20_protocol.adventures.tools.AdventureParser"
        ) as mock_parser_class:
            mock_parser = AsyncMock()
            mock_parser.parse_adventure.return_value = module
            mock_parser_class.return_value = mock_parser

            with patch(
                "dm20_protocol.adventures.tools.CampaignModuleManager"
            ) as mock_manager_class:
                mock_manager = MagicMock()
                mock_manager.bind_module.return_value = BindingResult(
                    success=True,
                    module_id="SCC-CK",
                    message="Success",
                )
                mock_manager_class.return_value = mock_manager

                flow_result = await load_adventure_flow(
                    storage=mock_storage,
                    data_path=Path("/fake/data"),
                    adventure_id="SCC-CK",
                    campaign_name="Strixhaven Campaign",
                    populate_chapter_1=True,
                )

        # Step 5: Verify campaign was created with correct entities
        assert flow_result["adventure_name"] == "Strixhaven: Campus Kerfuffle"
        assert flow_result["campaign_name"] == "Strixhaven Campaign"
        assert flow_result["module_bound"] is True
        assert flow_result["chapter_1_populated"] is True
        assert flow_result["entities_created"]["npcs"] > 0
        assert flow_result["entities_created"]["locations"] > 0
        assert flow_result["entities_created"]["quests"] == 1


# --- ModuleStructure Validation ---


class TestModuleStructureValidation:
    """Verify parsed ModuleStructure has all expected components."""

    async def test_chapters_are_correct_type(
        self, parser: AdventureParser, adventure_json: dict
    ):
        """All chapters should have ContentType.CHAPTER."""
        with patch.object(
            parser, "_get_adventure_data", return_value=adventure_json
        ):
            module = await parser.parse_adventure("SCC-CK")

        for chapter in module.chapters:
            assert chapter.content_type == ContentType.CHAPTER

    async def test_chapters_have_names(
        self, parser: AdventureParser, adventure_json: dict
    ):
        """All chapters should have non-empty names."""
        with patch.object(
            parser, "_get_adventure_data", return_value=adventure_json
        ):
            module = await parser.parse_adventure("SCC-CK")

        assert all(ch.name for ch in module.chapters)
        chapter_names = [ch.name for ch in module.chapters]
        assert "Chapter 1: Orientation" in chapter_names
        assert "Chapter 2: The Campus Kerfuffle" in chapter_names

    async def test_npcs_have_chapter_context(
        self, parser: AdventureParser, adventure_json: dict
    ):
        """All NPCs should have chapter attribution."""
        with patch.object(
            parser, "_get_adventure_data", return_value=adventure_json
        ):
            module = await parser.parse_adventure("SCC-CK")

        for npc in module.npcs:
            assert npc.name, f"NPC should have a name"
            assert npc.chapter, f"NPC {npc.name} should have chapter context"

    async def test_locations_extracted(
        self, parser: AdventureParser, adventure_json: dict
    ):
        """Numbered locations should be extracted."""
        with patch.object(
            parser, "_get_adventure_data", return_value=adventure_json
        ):
            module = await parser.parse_adventure("SCC-CK")

        location_names = {loc.name for loc in module.locations}
        assert "1. The Biblioplex" in location_names
        assert "2. The Firejolt Cafe" in location_names

    async def test_read_aloud_sections_exist(
        self, parser: AdventureParser, adventure_json: dict
    ):
        """Read-aloud text should be extracted from insetReadaloud entries."""
        with patch.object(
            parser, "_get_adventure_data", return_value=adventure_json
        ):
            module = await parser.parse_adventure("SCC-CK")

        assert len(module.read_aloud) > 0
        all_texts = []
        for texts in module.read_aloud.values():
            all_texts.extend(texts)

        assert any("grand archway" in t for t in all_texts)

    async def test_encounters_detected(
        self, parser: AdventureParser, adventure_json: dict
    ):
        """Encounter tables should be detected."""
        with patch.object(
            parser, "_get_adventure_data", return_value=adventure_json
        ):
            module = await parser.parse_adventure("SCC-CK")

        assert len(module.encounters) > 0
        encounter_names = [e.name for e in module.encounters]
        assert any("Encounter" in name for name in encounter_names)


# --- Markup-Free Validation ---


class TestMarkupFreeOutput:
    """Verify all output text is free of 5etools markup tags."""

    async def test_read_aloud_markup_free(
        self, parser: AdventureParser, adventure_json: dict
    ):
        """Read-aloud text should contain zero {@...} tags."""
        with patch.object(
            parser, "_get_adventure_data", return_value=adventure_json
        ):
            module = await parser.parse_adventure("SCC-CK")

        for section_id, texts in module.read_aloud.items():
            for text in texts:
                assert not MARKUP_TAG_RE.search(text), (
                    f"Markup found in read_aloud[{section_id}]: {text[:80]}"
                )

    async def test_parser_text_buffer_markup_free(
        self, parser: AdventureParser, adventure_json: dict
    ):
        """All text processed by the parser should be markup-free."""
        from dm20_protocol.adventures.parser import ParserContext

        with patch.object(
            parser, "_get_adventure_data", return_value=adventure_json
        ):
            module = await parser.parse_adventure("SCC-CK")

        # Check all text in read_aloud sections
        for texts in module.read_aloud.values():
            for text in texts:
                assert "{@" not in text, f"Markup in read-aloud: {text[:80]}"

    def test_discovery_format_markup_free(
        self, loaded_index: AdventureIndex
    ):
        """Formatted search results should contain zero markup tags."""
        result = search_adventures(loaded_index, query="strixhaven")
        formatted = format_search_results(result)

        assert not MARKUP_TAG_RE.search(formatted), (
            f"Markup found in formatted output: {formatted[:200]}"
        )


# --- Spoiler Boundary Tests ---


class TestSpoilerBoundary:
    """Verify only Chapter 1 content is revealed during loading."""

    async def test_only_chapter_1_npcs_populated(
        self,
        parser: AdventureParser,
        adventure_json: dict,
        mock_storage: MagicMock,
    ):
        """Only Chapter 1 NPCs should be created in the campaign."""
        with patch.object(
            parser, "_get_adventure_data", return_value=adventure_json
        ):
            module = await parser.parse_adventure("SCC-CK")

        ch1_name = module.chapters[0].name
        ch1_npcs = [npc for npc in module.npcs if npc.chapter == ch1_name]
        ch2_npcs = [npc for npc in module.npcs if npc.chapter != ch1_name]

        # Verify there ARE chapter 2 NPCs (so the boundary matters)
        assert len(ch2_npcs) > 0, "Fixture should have Ch2 NPCs to test boundary"

        # Load adventure
        with patch(
            "dm20_protocol.adventures.tools.AdventureParser"
        ) as mock_parser_class:
            mock_parser = AsyncMock()
            mock_parser.parse_adventure.return_value = module
            mock_parser_class.return_value = mock_parser

            with patch(
                "dm20_protocol.adventures.tools.CampaignModuleManager"
            ) as mock_manager_class:
                mock_manager = MagicMock()
                mock_manager.bind_module.return_value = BindingResult(
                    success=True, module_id="SCC-CK", message="Success"
                )
                mock_manager_class.return_value = mock_manager

                await load_adventure_flow(
                    storage=mock_storage,
                    data_path=Path("/fake/data"),
                    adventure_id="SCC-CK",
                    campaign_name="Test",
                    populate_chapter_1=True,
                )

        # Verify only Ch1 NPCs were added
        created_npc_names = [
            call[0][0].name for call in mock_storage.add_npc.call_args_list
        ]
        ch1_npc_names = {npc.name for npc in ch1_npcs}
        ch2_npc_names = {npc.name for npc in ch2_npcs}

        for name in created_npc_names:
            assert name in ch1_npc_names, (
                f"NPC '{name}' created but not in Chapter 1"
            )
        for name in ch2_npc_names:
            assert name not in created_npc_names, (
                f"Chapter 2 NPC '{name}' should NOT be created"
            )

    async def test_only_chapter_1_locations_populated(
        self,
        parser: AdventureParser,
        adventure_json: dict,
        mock_storage: MagicMock,
    ):
        """Only Chapter 1 locations should be created in the campaign."""
        with patch.object(
            parser, "_get_adventure_data", return_value=adventure_json
        ):
            module = await parser.parse_adventure("SCC-CK")

        ch1_name = module.chapters[0].name

        with patch(
            "dm20_protocol.adventures.tools.AdventureParser"
        ) as mock_parser_class:
            mock_parser = AsyncMock()
            mock_parser.parse_adventure.return_value = module
            mock_parser_class.return_value = mock_parser

            with patch(
                "dm20_protocol.adventures.tools.CampaignModuleManager"
            ) as mock_manager_class:
                mock_manager = MagicMock()
                mock_manager.bind_module.return_value = BindingResult(
                    success=True, module_id="SCC-CK", message="Success"
                )
                mock_manager_class.return_value = mock_manager

                await load_adventure_flow(
                    storage=mock_storage,
                    data_path=Path("/fake/data"),
                    adventure_id="SCC-CK",
                    campaign_name="Test",
                    populate_chapter_1=True,
                )

        created_location_names = [
            call[0][0].name
            for call in mock_storage.add_location.call_args_list
        ]
        ch1_locations = {
            loc.name for loc in module.locations if loc.chapter == ch1_name
        }
        ch2_locations = {
            loc.name
            for loc in module.locations
            if loc.chapter != ch1_name
        }

        for name in created_location_names:
            assert name in ch1_locations, (
                f"Location '{name}' created but not in Chapter 1"
            )
        for name in ch2_locations:
            assert name not in created_location_names, (
                f"Chapter 2 location '{name}' should NOT be created"
            )


# --- Discovery integration with fixture index ---


class TestDiscoveryWithFixtures:
    """Test discovery functionality against fixture index data."""

    def test_search_vampire_finds_ravenloft(
        self, loaded_index: AdventureIndex
    ):
        """'vampire' keyword should expand to find Ravenloft."""
        result = search_adventures(loaded_index, query="vampire")
        assert any(g.storyline == "Ravenloft" for g in result.groups)

    def test_search_strixhaven_multi_part(
        self, loaded_index: AdventureIndex
    ):
        """Strixhaven search should return multi-part series."""
        result = search_adventures(loaded_index, query="strixhaven")
        strix = next(
            (g for g in result.groups if g.storyline == "Strixhaven"), None
        )
        assert strix is not None
        assert strix.is_multi_part

    def test_level_filter_excludes_high_level(
        self, loaded_index: AdventureIndex
    ):
        """Level max=5 should exclude RoT (8-15)."""
        result = search_adventures(loaded_index, level_max=5)
        for group in result.groups:
            for adv in group.adventures:
                if adv.level_start is not None:
                    assert adv.level_start <= 5

    def test_empty_query_returns_all_storylines(
        self, loaded_index: AdventureIndex
    ):
        """Empty query should return storyline summary."""
        result = search_adventures(loaded_index)
        assert result.storyline_count > 0
        assert result.query == ""

    def test_no_chapter_content_in_results(
        self, loaded_index: AdventureIndex
    ):
        """Discovery results should not leak chapter content."""
        result = search_adventures(loaded_index, query="strixhaven")
        formatted = format_search_results(result)

        # Ensure only safe fields are shown: name, level, chapters, published
        # No plot details, no NPC names, no spoilers
        assert "Orientation" not in formatted  # chapter name = spoiler
        assert "Kerfuffle" in formatted  # adventure name = OK
