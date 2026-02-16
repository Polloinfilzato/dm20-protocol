"""
Tests for adventure index caching and loading.

Tests AdventureIndex cache hit/miss logic, expiration, download failure
scenarios, and index parsing using fixture data.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from dm20_protocol.adventures.index import (
    AdventureIndex,
    AdventureIndexError,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "adventures"

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def sample_index_json() -> dict:
    """Load index fixture data."""
    with open(FIXTURES_DIR / "adventures_index_sample.json") as f:
        return json.load(f)


@pytest.fixture
def index_with_cache(tmp_path: Path, sample_index_json: dict) -> AdventureIndex:
    """AdventureIndex with pre-populated fresh cache."""
    cache_dir = tmp_path / "adventures" / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "adventures.json").write_text(json.dumps(sample_index_json))
    metadata = {"downloaded_at": datetime.now(timezone.utc).isoformat()}
    (cache_dir / "metadata.json").write_text(json.dumps(metadata))
    return AdventureIndex(cache_dir=tmp_path)


@pytest.fixture
def index_with_stale_cache(
    tmp_path: Path, sample_index_json: dict
) -> AdventureIndex:
    """AdventureIndex with stale (expired) cache."""
    cache_dir = tmp_path / "adventures" / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "adventures.json").write_text(json.dumps(sample_index_json))
    old_date = datetime.now(timezone.utc) - timedelta(days=10)
    metadata = {"downloaded_at": old_date.isoformat()}
    (cache_dir / "metadata.json").write_text(json.dumps(metadata))
    return AdventureIndex(cache_dir=tmp_path)


@pytest.fixture
def index_no_cache(tmp_path: Path) -> AdventureIndex:
    """AdventureIndex with no cache at all."""
    return AdventureIndex(cache_dir=tmp_path)


# --- Cache freshness tests ---


class TestCacheFreshness:
    """Test cache TTL and freshness detection."""

    def test_no_metadata_is_not_fresh(self, index_no_cache: AdventureIndex):
        assert not index_no_cache._is_cache_fresh()

    def test_fresh_metadata_is_fresh(self, index_with_cache: AdventureIndex):
        assert index_with_cache._is_cache_fresh()

    def test_stale_metadata_is_not_fresh(
        self, index_with_stale_cache: AdventureIndex
    ):
        assert not index_with_stale_cache._is_cache_fresh()

    def test_corrupt_metadata_is_not_fresh(self, tmp_path: Path):
        cache_dir = tmp_path / "adventures" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "metadata.json").write_text("not valid json")
        idx = AdventureIndex(cache_dir=tmp_path)
        assert not idx._is_cache_fresh()

    def test_custom_ttl(self, tmp_path: Path):
        """Custom TTL of 1 day makes 2-day-old cache stale."""
        cache_dir = tmp_path / "adventures" / "cache"
        cache_dir.mkdir(parents=True)
        old_date = datetime.now(timezone.utc) - timedelta(days=2)
        metadata = {"downloaded_at": old_date.isoformat()}
        (cache_dir / "metadata.json").write_text(json.dumps(metadata))

        idx = AdventureIndex(cache_dir=tmp_path, cache_ttl_days=1)
        assert not idx._is_cache_fresh()

        idx2 = AdventureIndex(cache_dir=tmp_path, cache_ttl_days=5)
        assert idx2._is_cache_fresh()


# --- Cache loading tests ---


class TestCacheLoading:
    """Test loading index from cached files."""

    def test_load_from_fresh_cache(self, index_with_cache: AdventureIndex):
        index_with_cache._load_from_cache()
        assert index_with_cache.loaded
        assert len(index_with_cache.entries) == 10

    def test_load_from_cache_no_file(self, index_no_cache: AdventureIndex):
        with pytest.raises(AdventureIndexError, match="No cached index"):
            index_no_cache._load_from_cache()

    def test_load_from_corrupt_cache(self, tmp_path: Path):
        cache_dir = tmp_path / "adventures" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "adventures.json").write_text("{{invalid json!!")
        idx = AdventureIndex(cache_dir=tmp_path)

        with pytest.raises(AdventureIndexError, match="Corrupt cache"):
            idx._load_from_cache()

    def test_parse_populates_entries_correctly(
        self, index_with_cache: AdventureIndex
    ):
        index_with_cache._load_from_cache()
        cos = index_with_cache.get_by_id("CoS")
        assert cos is not None
        assert cos.name == "Curse of Strahd"
        assert cos.level_start == 1


# --- Load method (cache hit/miss routing) ---


class TestLoadMethod:
    """Test the main load() method routing."""

    async def test_load_uses_fresh_cache(
        self, index_with_cache: AdventureIndex
    ):
        """Fresh cache should be used directly, no download."""
        with patch.object(
            index_with_cache, "_download_index", new_callable=AsyncMock
        ) as mock_download:
            await index_with_cache.load()
            mock_download.assert_not_called()

        assert index_with_cache.loaded
        assert len(index_with_cache.entries) == 10

    async def test_load_downloads_when_stale(
        self, index_with_stale_cache: AdventureIndex, sample_index_json: dict
    ):
        """Stale cache triggers download attempt."""
        with patch.object(
            index_with_stale_cache,
            "_download_index",
            new_callable=AsyncMock,
        ) as mock_download:
            mock_download.side_effect = lambda: (
                index_with_stale_cache._parse_raw_index(sample_index_json)
            )
            await index_with_stale_cache.load()
            mock_download.assert_called_once()


# --- Download failure scenarios ---


class TestDownloadFailure:
    """Test download failure with and without cache fallback."""

    async def test_download_failure_with_stale_cache_falls_back(
        self, index_with_stale_cache: AdventureIndex
    ):
        """Download failure with existing stale cache should use stale cache."""
        with patch.object(
            index_with_stale_cache,
            "_download_index",
            new_callable=AsyncMock,
            side_effect=AdventureIndexError("Network error"),
        ):
            await index_with_stale_cache.load()

        # Should have fallen back to stale cache
        assert index_with_stale_cache.loaded
        assert len(index_with_stale_cache.entries) == 10

    async def test_download_failure_without_cache_raises(
        self, index_no_cache: AdventureIndex
    ):
        """Download failure without any cache should raise error."""
        with patch.object(
            index_no_cache,
            "_download_index",
            new_callable=AsyncMock,
            side_effect=AdventureIndexError("Network error"),
        ):
            with pytest.raises(AdventureIndexError, match="Network error"):
                await index_no_cache.load()

    async def test_download_timeout_retries(self, tmp_path: Path):
        """Timeout triggers retry with backoff."""
        idx = AdventureIndex(cache_dir=tmp_path)
        call_count = 0

        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_success.json.return_value = {
            "adventure": [
                {"id": "T", "name": "Test", "source": "T"}
            ]
        }
        mock_success.raise_for_status = MagicMock()
        mock_success.headers = {"etag": "test"}

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.TimeoutException("Timeout")
            return mock_success

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = mock_get
            await idx._download_index()

        assert call_count == 2
        assert idx.loaded

    async def test_download_server_error_retries(self, tmp_path: Path):
        """Server errors (5xx) trigger retry."""
        idx = AdventureIndex(cache_dir=tmp_path)
        call_count = 0

        mock_error = MagicMock()
        mock_error.status_code = 503
        mock_error.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=mock_error,
        )

        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_success.json.return_value = {
            "adventure": [{"id": "T", "name": "Test", "source": "T"}]
        }
        mock_success.raise_for_status = MagicMock()
        mock_success.headers = {}

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return mock_error
            return mock_success

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = mock_get
            await idx._download_index()

        assert call_count == 2
        assert idx.loaded

    async def test_download_client_error_no_retry(self, tmp_path: Path):
        """Client errors (4xx, not 429) should not retry."""
        idx = AdventureIndex(cache_dir=tmp_path)

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden",
            request=MagicMock(),
            response=mock_response,
        )

        async def mock_get(*args, **kwargs):
            return mock_response

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = mock_get
            with pytest.raises(AdventureIndexError, match="HTTP error"):
                await idx._download_index()


# --- Lookup methods ---


class TestLookupMethods:
    """Test get_by_id, get_by_name, get_storylines."""

    def test_get_by_id_case_insensitive(
        self, index_with_cache: AdventureIndex
    ):
        index_with_cache._load_from_cache()
        assert index_with_cache.get_by_id("cos") is not None
        assert index_with_cache.get_by_id("COS") is not None
        assert index_with_cache.get_by_id("CoS") is not None

    def test_get_by_id_not_found(self, index_with_cache: AdventureIndex):
        index_with_cache._load_from_cache()
        assert index_with_cache.get_by_id("NONEXISTENT") is None

    def test_get_by_name_case_insensitive(
        self, index_with_cache: AdventureIndex
    ):
        index_with_cache._load_from_cache()
        result = index_with_cache.get_by_name("curse of strahd")
        assert result is not None
        assert result.id == "CoS"

    def test_get_by_name_not_found(self, index_with_cache: AdventureIndex):
        index_with_cache._load_from_cache()
        assert index_with_cache.get_by_name("Nonexistent Adventure") is None

    def test_get_storylines_groups_correctly(
        self, index_with_cache: AdventureIndex
    ):
        index_with_cache._load_from_cache()
        storylines = index_with_cache.get_storylines()

        assert "Ravenloft" in storylines
        assert "Strixhaven" in storylines
        assert "Tyranny of Dragons" in storylines
        assert "Waterdeep" in storylines
        assert "Uncategorized" in storylines

        # Strixhaven should have 4 adventures
        assert len(storylines["Strixhaven"]) == 4

        # Uncategorized should have LMoP and TftYP
        assert len(storylines["Uncategorized"]) == 2

    def test_get_storylines_sorted_by_level(
        self, index_with_cache: AdventureIndex
    ):
        """Adventures within a storyline should be sorted by level_start."""
        index_with_cache._load_from_cache()
        storylines = index_with_cache.get_storylines()

        tyranny = storylines["Tyranny of Dragons"]
        assert tyranny[0].id == "HotDQ"  # Level 1-7
        assert tyranny[1].id == "RoT"  # Level 8-15

        strix = storylines["Strixhaven"]
        assert strix[0].level_start <= strix[-1].level_start
