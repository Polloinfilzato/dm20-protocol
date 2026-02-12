"""
Tests for 5etools data source downloader.

Tests focus on the download infrastructure, caching, and error handling.
Model mapping tests will be added in Task #84.
"""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from dm20_protocol.rulebooks.sources.fivetools import (
    FiveToolsSource,
    FiveToolsSourceError,
    GITHUB_RAW_BASE,
    INDEXED_CATEGORIES,
    SINGLE_FILE_CATEGORIES,
)
from dm20_protocol.rulebooks.models import RulebookSource


def run_async(coro):
    """Helper to run async code in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# =============================================================================
# Sample 5etools Data Fixtures
# =============================================================================

SAMPLE_SPELL_INDEX = {
    "PHB": "spells-phb.json",
    "XGE": "spells-xge.json",
}

SAMPLE_SPELLS_PHB = {
    "spell": [
        {
            "name": "Fireball",
            "source": "PHB",
            "level": 3,
            "school": "V",
            "entries": ["A bright streak flashes..."],
        },
        {
            "name": "Magic Missile",
            "source": "PHB",
            "level": 1,
            "school": "V",
            "entries": ["You create three glowing darts..."],
        },
    ]
}

SAMPLE_SPELLS_XGE = {
    "spell": [
        {
            "name": "Shadow Blade",
            "source": "XGE",
            "level": 2,
            "school": "I",
            "entries": ["You weave together threads of shadow..."],
        },
    ]
}

SAMPLE_BESTIARY_INDEX = {
    "MM": "bestiary-mm.json",
}

SAMPLE_BESTIARY_MM = {
    "monster": [
        {
            "name": "Goblin",
            "source": "MM",
            "size": ["S"],
            "type": "humanoid",
            "cr": "1/4",
        },
        {
            "name": "Dragon, Adult Red",
            "source": "MM",
            "size": ["H"],
            "type": "dragon",
            "cr": "17",
        },
    ]
}

SAMPLE_CLASS_INDEX = {
    "fighter": "class-fighter.json",
}

SAMPLE_CLASS_FIGHTER = {
    "class": [
        {
            "name": "Fighter",
            "source": "PHB",
            "hd": {"number": 1, "faces": 10},
        },
    ],
    "subclass": [
        {"name": "Champion", "source": "PHB"},
    ],
}

SAMPLE_RACES = {
    "race": [
        {
            "name": "Elf",
            "source": "PHB",
            "size": ["M"],
            "speed": 30,
        },
        {
            "name": "Dwarf",
            "source": "PHB",
            "size": ["M"],
            "speed": 25,
        },
    ]
}

SAMPLE_FEATS = {
    "feat": [
        {"name": "Alert", "source": "PHB"},
        {"name": "Lucky", "source": "PHB"},
    ]
}

SAMPLE_ITEMS = {
    "item": [
        {"name": "Bag of Holding", "source": "DMG", "rarity": "uncommon"},
    ]
}

SAMPLE_ITEMS_BASE = {
    "baseitem": [
        {"name": "Longsword", "source": "PHB", "type": "M"},
    ]
}

SAMPLE_BACKGROUNDS = {
    "background": [
        {"name": "Acolyte", "source": "PHB"},
    ]
}


# =============================================================================
# Helper: Build a mock HTTP client
# =============================================================================

def _build_mock_client(url_responses: dict[str, dict]) -> AsyncMock:
    """
    Create a mock httpx.AsyncClient that returns predefined responses.

    Args:
        url_responses: Maps URL substring patterns to JSON response dicts.
    """
    mock_client = AsyncMock()

    def get_side_effect(url: str):
        for pattern, response_data in url_responses.items():
            if pattern in url:
                return MagicMock(
                    status_code=200,
                    json=MagicMock(return_value=response_data),
                    raise_for_status=MagicMock(),
                )
        # Default: 404
        mock_resp = MagicMock(status_code=404)

        def raise_status():
            raise httpx.HTTPStatusError(
                "404 Not Found", request=MagicMock(), response=mock_resp
            )

        mock_resp.raise_for_status = raise_status
        return mock_resp

    mock_client.get = AsyncMock(side_effect=get_side_effect)
    return mock_client


# =============================================================================
# Test: Initialization
# =============================================================================

class TestFiveToolsSourceInit:
    """Test FiveToolsSource initialization."""

    def test_default_source_id(self):
        source = FiveToolsSource()
        assert source.source_id == "5etools"

    def test_default_source_type(self):
        source = FiveToolsSource()
        assert source.source_type == RulebookSource.FIVETOOLS

    def test_default_name(self):
        source = FiveToolsSource()
        assert source.name == "5etools"

    def test_default_cache_dir(self):
        source = FiveToolsSource()
        assert source.cache_dir == Path("dnd_data/rulebook_cache/5etools")

    def test_custom_cache_dir(self, tmp_path):
        cache = tmp_path / "custom"
        source = FiveToolsSource(cache_dir=cache)
        assert source.cache_dir == cache

    def test_not_loaded_initially(self):
        source = FiveToolsSource()
        assert source.is_loaded is False
        assert source.loaded_at is None

    def test_raw_data_empty_initially(self):
        source = FiveToolsSource()
        assert source.raw_data_counts == {}

    def test_content_counts_zero_initially(self):
        source = FiveToolsSource()
        counts = source.content_counts()
        assert counts.classes == 0
        assert counts.spells == 0
        assert counts.monsters == 0


# =============================================================================
# Test: Indexed Category Download (spells, bestiary, classes)
# =============================================================================

class TestIndexedCategoryDownload:
    """Test downloading categories with index.json discovery."""

    def test_download_spells_from_index(self, tmp_path):
        """Test downloading spell files discovered via index.json."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        import httpx as httpx_mod  # for the error class

        url_responses = {
            "spells/index.json": SAMPLE_SPELL_INDEX,
            "spells/spells-phb.json": SAMPLE_SPELLS_PHB,
            "spells/spells-xge.json": SAMPLE_SPELLS_XGE,
        }

        async def run():
            source.cache_dir.mkdir(parents=True, exist_ok=True)
            (source.cache_dir / "raw").mkdir(exist_ok=True)
            (source.cache_dir / "merged").mkdir(exist_ok=True)

            source._client = _build_mock_client(url_responses)
            await source._download_indexed_category(
                "spells", INDEXED_CATEGORIES["spells"]
            )

            # Verify merged file
            merged = source.cache_dir / "merged" / "spells.json"
            assert merged.exists()
            data = json.loads(merged.read_text())
            assert data["count"] == 3  # 2 PHB + 1 XGE
            assert len(data["spell"]) == 3

            # Verify raw files
            raw_dir = source.cache_dir / "raw" / "spells"
            assert (raw_dir / "index.json").exists()
            assert (raw_dir / "spells-phb.json").exists()
            assert (raw_dir / "spells-xge.json").exists()

        run_async(run())

    def test_download_bestiary_from_index(self, tmp_path):
        """Test downloading bestiary files."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        url_responses = {
            "bestiary/index.json": SAMPLE_BESTIARY_INDEX,
            "bestiary/bestiary-mm.json": SAMPLE_BESTIARY_MM,
        }

        async def run():
            source.cache_dir.mkdir(parents=True, exist_ok=True)
            (source.cache_dir / "raw").mkdir(exist_ok=True)
            (source.cache_dir / "merged").mkdir(exist_ok=True)

            source._client = _build_mock_client(url_responses)
            await source._download_indexed_category(
                "bestiary", INDEXED_CATEGORIES["bestiary"]
            )

            merged = source.cache_dir / "merged" / "bestiary.json"
            data = json.loads(merged.read_text())
            assert data["count"] == 2
            names = [m["name"] for m in data["monster"]]
            assert "Goblin" in names
            assert "Dragon, Adult Red" in names

        run_async(run())

    def test_download_classes_from_index(self, tmp_path):
        """Test downloading class files (uses class name as key)."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        url_responses = {
            "class/index.json": SAMPLE_CLASS_INDEX,
            "class/class-fighter.json": SAMPLE_CLASS_FIGHTER,
        }

        async def run():
            source.cache_dir.mkdir(parents=True, exist_ok=True)
            (source.cache_dir / "raw").mkdir(exist_ok=True)
            (source.cache_dir / "merged").mkdir(exist_ok=True)

            source._client = _build_mock_client(url_responses)
            await source._download_indexed_category(
                "class", INDEXED_CATEGORIES["class"]
            )

            merged = source.cache_dir / "merged" / "class.json"
            data = json.loads(merged.read_text())
            assert data["count"] == 1
            assert data["class"][0]["name"] == "Fighter"

        run_async(run())

    def test_indexed_uses_cached_raw_files(self, tmp_path):
        """Test that pre-cached raw files are used without HTTP calls."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        # Pre-populate raw spell file
        raw_dir = source.cache_dir / "raw" / "spells"
        raw_dir.mkdir(parents=True)
        (raw_dir / "spells-phb.json").write_text(json.dumps(SAMPLE_SPELLS_PHB))

        # Only the index needs downloading; spells-phb.json should be cached
        url_responses = {
            "spells/index.json": {"PHB": "spells-phb.json"},
        }

        async def run():
            (source.cache_dir / "merged").mkdir(exist_ok=True)
            source._client = _build_mock_client(url_responses)
            await source._download_indexed_category(
                "spells", INDEXED_CATEGORIES["spells"]
            )

            merged = source.cache_dir / "merged" / "spells.json"
            data = json.loads(merged.read_text())
            assert data["count"] == 2  # From cached PHB

        run_async(run())

    def test_indexed_skips_non_json_entries(self, tmp_path):
        """Test that non-.json entries in index are skipped."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        # Index with a non-json entry
        index_with_extra = {
            "PHB": "spells-phb.json",
            "_meta": {"some": "metadata"},  # not a string filename
        }

        url_responses = {
            "spells/index.json": index_with_extra,
            "spells/spells-phb.json": SAMPLE_SPELLS_PHB,
        }

        async def run():
            source.cache_dir.mkdir(parents=True, exist_ok=True)
            (source.cache_dir / "raw").mkdir(exist_ok=True)
            (source.cache_dir / "merged").mkdir(exist_ok=True)

            source._client = _build_mock_client(url_responses)
            await source._download_indexed_category(
                "spells", INDEXED_CATEGORIES["spells"]
            )

            merged = source.cache_dir / "merged" / "spells.json"
            data = json.loads(merged.read_text())
            # Only the PHB file should be downloaded
            assert data["count"] == 2

        run_async(run())


# =============================================================================
# Test: Single File Download
# =============================================================================

class TestSingleFileDownload:
    """Test downloading single-file categories."""

    def test_download_races(self, tmp_path):
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        url_responses = {"races.json": SAMPLE_RACES}

        async def run():
            source.cache_dir.mkdir(parents=True, exist_ok=True)
            (source.cache_dir / "raw").mkdir(exist_ok=True)
            (source.cache_dir / "merged").mkdir(exist_ok=True)

            source._client = _build_mock_client(url_responses)
            await source._download_single_file(
                "races", SINGLE_FILE_CATEGORIES["races"]
            )

            # Raw file
            raw = source.cache_dir / "raw" / "races.json"
            assert raw.exists()

            # Merged file
            merged = source.cache_dir / "merged" / "races.json"
            data = json.loads(merged.read_text())
            assert data["count"] == 2
            names = [r["name"] for r in data["race"]]
            assert "Elf" in names
            assert "Dwarf" in names

        run_async(run())

    def test_download_feats(self, tmp_path):
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        url_responses = {"feats.json": SAMPLE_FEATS}

        async def run():
            source.cache_dir.mkdir(parents=True, exist_ok=True)
            (source.cache_dir / "raw").mkdir(exist_ok=True)
            (source.cache_dir / "merged").mkdir(exist_ok=True)

            source._client = _build_mock_client(url_responses)
            await source._download_single_file(
                "feats", SINGLE_FILE_CATEGORIES["feats"]
            )

            merged = source.cache_dir / "merged" / "feats.json"
            data = json.loads(merged.read_text())
            assert data["count"] == 2

        run_async(run())

    def test_download_backgrounds(self, tmp_path):
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        url_responses = {"backgrounds.json": SAMPLE_BACKGROUNDS}

        async def run():
            source.cache_dir.mkdir(parents=True, exist_ok=True)
            (source.cache_dir / "raw").mkdir(exist_ok=True)
            (source.cache_dir / "merged").mkdir(exist_ok=True)

            source._client = _build_mock_client(url_responses)
            await source._download_single_file(
                "backgrounds", SINGLE_FILE_CATEGORIES["backgrounds"]
            )

            merged = source.cache_dir / "merged" / "backgrounds.json"
            data = json.loads(merged.read_text())
            assert data["count"] == 1

        run_async(run())

    def test_single_file_uses_cache(self, tmp_path):
        """Test that cached raw files are used without HTTP calls."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        # Pre-populate cache
        raw_path = source.cache_dir / "raw" / "races.json"
        raw_path.parent.mkdir(parents=True)
        raw_path.write_text(json.dumps(SAMPLE_RACES))
        (source.cache_dir / "merged").mkdir(parents=True)

        async def run():
            # No client needed — should use cache
            source._client = None
            await source._download_single_file(
                "races", SINGLE_FILE_CATEGORIES["races"]
            )

            merged = source.cache_dir / "merged" / "races.json"
            data = json.loads(merged.read_text())
            assert data["count"] == 2

        run_async(run())


# =============================================================================
# Test: Cache Validation
# =============================================================================

class TestCacheValidation:
    """Test cache validity checking."""

    def test_no_metadata_means_invalid(self, tmp_path):
        source = FiveToolsSource(cache_dir=tmp_path / "cache")
        assert source._is_cache_valid() is False

    def test_valid_metadata(self, tmp_path):
        source = FiveToolsSource(cache_dir=tmp_path / "cache")
        source.cache_dir.mkdir(parents=True)
        metadata = {"downloaded_at": "2026-01-01T00:00:00"}
        (source.cache_dir / "metadata.json").write_text(json.dumps(metadata))
        assert source._is_cache_valid() is True

    def test_corrupt_metadata(self, tmp_path):
        source = FiveToolsSource(cache_dir=tmp_path / "cache")
        source.cache_dir.mkdir(parents=True)
        (source.cache_dir / "metadata.json").write_text("{invalid json")
        assert source._is_cache_valid() is False

    def test_metadata_without_downloaded_at(self, tmp_path):
        source = FiveToolsSource(cache_dir=tmp_path / "cache")
        source.cache_dir.mkdir(parents=True)
        (source.cache_dir / "metadata.json").write_text(json.dumps({"other": "data"}))
        assert source._is_cache_valid() is False

    def test_corrupt_raw_file_triggers_redownload(self, tmp_path):
        """Test that a corrupt raw file is deleted and re-fetched."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        # Create corrupt raw file
        raw_dir = source.cache_dir / "raw" / "spells"
        raw_dir.mkdir(parents=True)
        corrupt_file = raw_dir / "spells-phb.json"
        corrupt_file.write_text("{not valid json")

        url_responses = {
            "spells/index.json": {"PHB": "spells-phb.json"},
            "spells/spells-phb.json": SAMPLE_SPELLS_PHB,
        }

        async def run():
            (source.cache_dir / "merged").mkdir(exist_ok=True)
            source._client = _build_mock_client(url_responses)
            await source._download_indexed_category(
                "spells", INDEXED_CATEGORIES["spells"]
            )

            # Should have re-downloaded and written valid data
            data = json.loads(corrupt_file.read_text())
            assert "spell" in data
            assert len(data["spell"]) == 2

        run_async(run())

    def test_corrupt_single_file_triggers_redownload(self, tmp_path):
        """Test that a corrupt single-file cache is re-fetched."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        raw_path = source.cache_dir / "raw" / "races.json"
        raw_path.parent.mkdir(parents=True)
        raw_path.write_text("{corrupt!")

        url_responses = {"races.json": SAMPLE_RACES}

        async def run():
            (source.cache_dir / "merged").mkdir(exist_ok=True)
            source._client = _build_mock_client(url_responses)
            await source._download_single_file(
                "races", SINGLE_FILE_CATEGORIES["races"]
            )

            data = json.loads(raw_path.read_text())
            assert len(data["race"]) == 2

        run_async(run())


# =============================================================================
# Test: Merged Data Loading
# =============================================================================

class TestMergedDataLoading:
    """Test loading merged JSON files into raw_data."""

    def test_load_merged_spells(self, tmp_path):
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        merged_dir = source.cache_dir / "merged"
        merged_dir.mkdir(parents=True)
        merged_data = {"spell": SAMPLE_SPELLS_PHB["spell"], "count": 2}
        (merged_dir / "spells.json").write_text(json.dumps(merged_data))

        source._load_merged_data()

        assert "spells" in source._raw_data
        assert len(source._raw_data["spells"]) == 2

    def test_load_merged_multiple_categories(self, tmp_path):
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        merged_dir = source.cache_dir / "merged"
        merged_dir.mkdir(parents=True)

        (merged_dir / "spells.json").write_text(
            json.dumps({"spell": SAMPLE_SPELLS_PHB["spell"], "count": 2})
        )
        (merged_dir / "races.json").write_text(
            json.dumps({"race": SAMPLE_RACES["race"], "count": 2})
        )
        (merged_dir / "bestiary.json").write_text(
            json.dumps({"monster": SAMPLE_BESTIARY_MM["monster"], "count": 2})
        )

        source._load_merged_data()

        assert source.raw_data_counts == {
            "bestiary": 2,
            "races": 2,
            "spells": 2,
        }

    def test_load_merged_corrupt_file_skipped(self, tmp_path):
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        merged_dir = source.cache_dir / "merged"
        merged_dir.mkdir(parents=True)
        (merged_dir / "spells.json").write_text("{corrupt")
        (merged_dir / "races.json").write_text(
            json.dumps({"race": SAMPLE_RACES["race"], "count": 2})
        )

        source._load_merged_data()

        assert "spells" not in source._raw_data
        assert "races" in source._raw_data

    def test_load_merged_unknown_category_skipped(self, tmp_path):
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        merged_dir = source.cache_dir / "merged"
        merged_dir.mkdir(parents=True)
        (merged_dir / "unknown_category.json").write_text(
            json.dumps({"stuff": [1, 2, 3]})
        )

        source._load_merged_data()

        assert "unknown_category" not in source._raw_data


# =============================================================================
# Test: Metadata
# =============================================================================

class TestMetadata:
    """Test metadata writing and reading."""

    def test_write_metadata(self, tmp_path):
        source = FiveToolsSource(cache_dir=tmp_path / "cache")
        source.cache_dir.mkdir(parents=True)

        # Create some raw files
        raw_dir = source.cache_dir / "raw"
        raw_dir.mkdir()
        (raw_dir / "races.json").write_text(json.dumps(SAMPLE_RACES))

        source._write_metadata()

        metadata_path = source.cache_dir / "metadata.json"
        assert metadata_path.exists()

        metadata = json.loads(metadata_path.read_text())
        assert "downloaded_at" in metadata
        assert metadata["source_repo"] == "5etools-mirror-3/5etools-src"
        assert metadata["branch"] == "main"
        assert metadata["file_count"] == 1
        assert "races.json" in metadata["files"]

    def test_metadata_includes_nested_files(self, tmp_path):
        source = FiveToolsSource(cache_dir=tmp_path / "cache")
        raw_dir = source.cache_dir / "raw" / "spells"
        raw_dir.mkdir(parents=True)
        (raw_dir / "index.json").write_text("{}")
        (raw_dir / "spells-phb.json").write_text("{}")

        source._write_metadata()

        metadata = json.loads((source.cache_dir / "metadata.json").read_text())
        assert metadata["file_count"] == 2


# =============================================================================
# Test: HTTP Error Handling
# =============================================================================

class TestHTTPErrorHandling:
    """Test HTTP error handling and retries."""

    def test_rate_limit_triggers_retry(self, tmp_path):
        """Test that 429 status triggers retry."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        call_count = 0

        async def run():
            nonlocal call_count
            source.cache_dir.mkdir(parents=True, exist_ok=True)

            def get_side_effect(url):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return MagicMock(
                        status_code=429,
                        raise_for_status=MagicMock(),
                    )
                return MagicMock(
                    status_code=200,
                    json=MagicMock(return_value={"data": "ok"}),
                    raise_for_status=MagicMock(),
                )

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=get_side_effect)
            source._client = mock_client

            result = await source._fetch_json("https://example.com/test")
            assert result == {"data": "ok"}
            assert call_count == 2

        run_async(run())

    def test_timeout_triggers_retry(self, tmp_path):
        """Test that timeout triggers retry."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        import httpx

        call_count = 0

        async def run():
            nonlocal call_count

            def get_side_effect(url):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise httpx.ReadTimeout("timeout")
                return MagicMock(
                    status_code=200,
                    json=MagicMock(return_value={"data": "ok"}),
                    raise_for_status=MagicMock(),
                )

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=get_side_effect)
            source._client = mock_client

            result = await source._fetch_json("https://example.com/test")
            assert result == {"data": "ok"}
            assert call_count == 2

        run_async(run())

    def test_server_error_triggers_retry(self, tmp_path):
        """Test that 5xx errors trigger retry."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        import httpx

        call_count = 0

        async def run():
            nonlocal call_count

            def get_side_effect(url):
                nonlocal call_count
                call_count += 1
                mock_resp = MagicMock(status_code=500)

                def raise_status():
                    raise httpx.HTTPStatusError(
                        "500", request=MagicMock(), response=mock_resp
                    )

                if call_count == 1:
                    mock_resp.raise_for_status = raise_status
                    return mock_resp
                return MagicMock(
                    status_code=200,
                    json=MagicMock(return_value={"data": "ok"}),
                    raise_for_status=MagicMock(),
                )

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=get_side_effect)
            source._client = mock_client

            result = await source._fetch_json("https://example.com/test")
            assert result == {"data": "ok"}
            assert call_count == 2

        run_async(run())

    def test_client_error_raises_immediately(self, tmp_path):
        """Test that 4xx errors (non-429) raise immediately without retry."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        import httpx

        async def run():
            mock_resp = MagicMock(status_code=404)

            def raise_status():
                raise httpx.HTTPStatusError(
                    "404", request=MagicMock(), response=mock_resp
                )

            mock_resp.raise_for_status = raise_status

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            source._client = mock_client

            with pytest.raises(FiveToolsSourceError, match="HTTP error"):
                await source._fetch_json("https://example.com/missing")

        run_async(run())

    def test_all_retries_exhausted_raises(self, tmp_path):
        """Test that exhausting all retries raises FiveToolsSourceError."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        import httpx

        async def run():
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.ReadTimeout("timeout")
            )
            source._client = mock_client

            with pytest.raises(FiveToolsSourceError, match="Failed to fetch"):
                await source._fetch_json("https://example.com/test")

        run_async(run())

    def test_failed_index_skips_category(self, tmp_path):
        """Test that a failed index download doesn't crash — category is skipped."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        import httpx

        async def run():
            source.cache_dir.mkdir(parents=True, exist_ok=True)
            (source.cache_dir / "raw").mkdir(exist_ok=True)
            (source.cache_dir / "merged").mkdir(exist_ok=True)

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.ReadTimeout("timeout")
            )
            source._client = mock_client

            # Should not raise — just logs error and returns
            await source._download_indexed_category(
                "spells", INDEXED_CATEGORIES["spells"]
            )

            # No merged file created
            assert not (source.cache_dir / "merged" / "spells.json").exists()

        run_async(run())

    def test_failed_single_file_skips_category(self, tmp_path):
        """Test that a failed single-file download is handled gracefully."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        import httpx

        async def run():
            source.cache_dir.mkdir(parents=True, exist_ok=True)
            (source.cache_dir / "raw").mkdir(exist_ok=True)
            (source.cache_dir / "merged").mkdir(exist_ok=True)

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.ReadTimeout("timeout")
            )
            source._client = mock_client

            await source._download_single_file(
                "races", SINGLE_FILE_CATEGORIES["races"]
            )

            assert not (source.cache_dir / "merged" / "races.json").exists()

        run_async(run())


# =============================================================================
# Test: Full Load (integration with mocks)
# =============================================================================

class TestFullLoad:
    """Test the full load() workflow with mocked HTTP."""

    def test_full_load_downloads_and_caches(self, tmp_path):
        """Test that load() downloads all categories and sets loaded state."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        url_responses = {
            "spells/index.json": SAMPLE_SPELL_INDEX,
            "spells/spells-phb.json": SAMPLE_SPELLS_PHB,
            "spells/spells-xge.json": SAMPLE_SPELLS_XGE,
            "bestiary/index.json": SAMPLE_BESTIARY_INDEX,
            "bestiary/bestiary-mm.json": SAMPLE_BESTIARY_MM,
            "class/index.json": SAMPLE_CLASS_INDEX,
            "class/class-fighter.json": SAMPLE_CLASS_FIGHTER,
            "races.json": SAMPLE_RACES,
            "feats.json": SAMPLE_FEATS,
            "items.json": SAMPLE_ITEMS,
            "items-base.json": SAMPLE_ITEMS_BASE,
            "backgrounds.json": SAMPLE_BACKGROUNDS,
        }

        async def run():
            import httpx as httpx_mod

            # Patch AsyncClient to return our mock
            mock_client = _build_mock_client(url_responses)

            original_init = httpx_mod.AsyncClient.__init__
            original_aenter = httpx_mod.AsyncClient.__aenter__
            original_aexit = httpx_mod.AsyncClient.__aexit__

            # We need to intercept the async context manager
            from unittest.mock import patch, AsyncMock as AM

            with patch("dm20_protocol.rulebooks.sources.fivetools.httpx.AsyncClient") as MockClientClass:
                mock_instance = _build_mock_client(url_responses)
                MockClientClass.return_value.__aenter__ = AM(
                    return_value=mock_instance
                )
                MockClientClass.return_value.__aexit__ = AM(return_value=None)

                await source.load()

            assert source.is_loaded is True
            assert source.loaded_at is not None

            # Check raw data was loaded
            counts = source.raw_data_counts
            assert counts.get("spells", 0) == 3
            assert counts.get("bestiary", 0) == 2
            assert counts.get("class", 0) == 1
            assert counts.get("races", 0) == 2
            assert counts.get("feats", 0) == 2
            assert counts.get("items", 0) == 1
            assert counts.get("items-base", 0) == 1
            assert counts.get("backgrounds", 0) == 1

            # Metadata should exist
            assert (source.cache_dir / "metadata.json").exists()

        run_async(run())

    def test_load_from_existing_cache(self, tmp_path):
        """Test that load() uses cache when metadata exists."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        # Pre-populate cache
        source.cache_dir.mkdir(parents=True)
        (source.cache_dir / "metadata.json").write_text(
            json.dumps({"downloaded_at": "2026-01-01T00:00:00"})
        )
        merged_dir = source.cache_dir / "merged"
        merged_dir.mkdir()
        (merged_dir / "spells.json").write_text(
            json.dumps({"spell": SAMPLE_SPELLS_PHB["spell"], "count": 2})
        )
        (merged_dir / "races.json").write_text(
            json.dumps({"race": SAMPLE_RACES["race"], "count": 2})
        )

        async def run():
            # No HTTP mock needed — should load entirely from cache
            await source.load()
            assert source.is_loaded is True
            assert source.raw_data_counts["spells"] == 2
            assert source.raw_data_counts["races"] == 2

        run_async(run())

    def test_force_redownload(self, tmp_path):
        """Test that force=True re-downloads even with valid cache."""
        source = FiveToolsSource(cache_dir=tmp_path / "cache")

        # Pre-populate cache with old data
        source.cache_dir.mkdir(parents=True)
        (source.cache_dir / "metadata.json").write_text(
            json.dumps({"downloaded_at": "2020-01-01T00:00:00"})
        )

        url_responses = {
            "spells/index.json": {"PHB": "spells-phb.json"},
            "spells/spells-phb.json": SAMPLE_SPELLS_PHB,
            "bestiary/index.json": {},
            "class/index.json": {},
            "races.json": SAMPLE_RACES,
            "feats.json": SAMPLE_FEATS,
            "items.json": SAMPLE_ITEMS,
            "items-base.json": SAMPLE_ITEMS_BASE,
            "backgrounds.json": SAMPLE_BACKGROUNDS,
        }

        async def run():
            (source.cache_dir / "raw").mkdir(exist_ok=True)
            (source.cache_dir / "merged").mkdir(exist_ok=True)

            source._client = _build_mock_client(url_responses)
            # Call _ensure_data_downloaded with force=True directly
            await source._ensure_data_downloaded(force=True)

            # Should have re-downloaded
            merged = source.cache_dir / "merged" / "spells.json"
            assert merged.exists()

        run_async(run())


# =============================================================================
# Test: Query Stubs (pre-mapping)
# =============================================================================

class TestQueryStubs:
    """Test that query methods return None/empty before model mapping."""

    def test_get_class_returns_none(self):
        source = FiveToolsSource()
        assert source.get_class("fighter") is None

    def test_get_spell_returns_none(self):
        source = FiveToolsSource()
        assert source.get_spell("fireball") is None

    def test_get_monster_returns_none(self):
        source = FiveToolsSource()
        assert source.get_monster("goblin") is None

    def test_get_race_returns_none(self):
        source = FiveToolsSource()
        assert source.get_race("elf") is None

    def test_get_feat_returns_none(self):
        source = FiveToolsSource()
        assert source.get_feat("alert") is None

    def test_get_background_returns_none(self):
        source = FiveToolsSource()
        assert source.get_background("acolyte") is None

    def test_get_item_returns_none(self):
        source = FiveToolsSource()
        assert source.get_item("longsword") is None

    def test_get_subclass_returns_none(self):
        source = FiveToolsSource()
        assert source.get_subclass("champion") is None

    def test_get_subrace_returns_none(self):
        source = FiveToolsSource()
        assert source.get_subrace("high-elf") is None

    def test_search_returns_empty(self):
        source = FiveToolsSource()
        results = list(source.search("fireball"))
        assert results == []

    def test_content_counts_all_zero(self):
        source = FiveToolsSource()
        counts = source.content_counts()
        assert counts.classes == 0
        assert counts.spells == 0
        assert counts.monsters == 0
        assert counts.races == 0
        assert counts.feats == 0
        assert counts.backgrounds == 0
        assert counts.items == 0


# =============================================================================
# Test: Data Key Resolution
# =============================================================================

class TestDataKeyResolution:
    """Test _resolve_data_key helper."""

    def test_indexed_categories(self):
        source = FiveToolsSource()
        assert source._resolve_data_key("spells") == "spell"
        assert source._resolve_data_key("bestiary") == "monster"
        assert source._resolve_data_key("class") == "class"

    def test_single_file_categories(self):
        source = FiveToolsSource()
        assert source._resolve_data_key("races") == "race"
        assert source._resolve_data_key("feats") == "feat"
        assert source._resolve_data_key("items") == "item"
        assert source._resolve_data_key("items-base") == "baseitem"
        assert source._resolve_data_key("backgrounds") == "background"

    def test_unknown_category_returns_none(self):
        source = FiveToolsSource()
        assert source._resolve_data_key("unknown") is None
