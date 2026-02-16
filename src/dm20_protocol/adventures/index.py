"""
Adventure index download, caching, and lookup.

Downloads the 5etools adventures.json index and caches it locally
with configurable TTL. Provides lookup methods for adventure entries.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .models import AdventureIndexEntry

logger = logging.getLogger("dm20-protocol")

ADVENTURES_INDEX_URL = (
    "https://raw.githubusercontent.com/5etools-mirror-3/"
    "5etools-src/main/data/adventures.json"
)
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
DEFAULT_CACHE_TTL_DAYS = 7


class AdventureIndexError(Exception):
    """Error downloading or parsing adventure index."""

    pass


class AdventureIndex:
    """Manages the 5etools adventure index with local caching.

    Downloads adventures.json from the 5etools GitHub mirror and
    caches it locally with a configurable TTL. Provides methods
    to load and query adventure entries.

    Args:
        cache_dir: Directory for cached files.
        cache_ttl_days: Days before cache is considered stale.
    """

    def __init__(
        self,
        cache_dir: Path,
        cache_ttl_days: int = DEFAULT_CACHE_TTL_DAYS,
    ):
        self.cache_dir = cache_dir / "adventures" / "cache"
        self.cache_ttl_days = cache_ttl_days
        self._entries: list[AdventureIndexEntry] = []
        self._loaded = False

    @property
    def entries(self) -> list[AdventureIndexEntry]:
        """All loaded adventure index entries."""
        return self._entries

    @property
    def loaded(self) -> bool:
        """Whether the index has been loaded."""
        return self._loaded

    async def load(self) -> None:
        """Load the adventure index from cache or by downloading.

        Checks cache freshness first. If cache is stale or missing,
        downloads a fresh copy. Falls back to stale cache on download
        failure.
        """
        if self._is_cache_fresh():
            self._load_from_cache()
            return

        try:
            await self._download_index()
        except AdventureIndexError:
            # Fall back to stale cache if available
            cache_file = self.cache_dir / "adventures.json"
            if cache_file.exists():
                logger.warning(
                    "Download failed, using stale cache"
                )
                self._load_from_cache()
                return
            raise

    def _is_cache_fresh(self) -> bool:
        """Check if the cached index exists and is within TTL."""
        metadata_path = self.cache_dir / "metadata.json"
        if not metadata_path.exists():
            return False

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            downloaded_at = datetime.fromisoformat(metadata["downloaded_at"])
            age_days = (datetime.now(timezone.utc) - downloaded_at).days
            return age_days < self.cache_ttl_days
        except (json.JSONDecodeError, KeyError, ValueError):
            return False

    def _load_from_cache(self) -> None:
        """Parse the cached adventures.json into model instances."""
        cache_file = self.cache_dir / "adventures.json"
        if not cache_file.exists():
            raise AdventureIndexError("No cached index file found")

        try:
            raw = json.loads(cache_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise AdventureIndexError(f"Corrupt cache file: {e}") from e

        self._parse_raw_index(raw)

    def _parse_raw_index(self, raw: dict[str, Any]) -> None:
        """Parse raw JSON data into AdventureIndexEntry models."""
        adventures = raw.get("adventure", [])
        self._entries = []
        for item in adventures:
            try:
                entry = AdventureIndexEntry.model_validate(item)
                self._entries.append(entry)
            except Exception as e:
                name = item.get("name", "unknown")
                logger.warning(f"Failed to parse adventure '{name}': {e}")

        self._loaded = True
        logger.info(f"Loaded {len(self._entries)} adventures from index")

    async def _download_index(self) -> None:
        """Download adventures.json with retry logic.

        Uses exponential backoff matching FiveToolsSource patterns.
        """
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            for attempt in range(MAX_RETRIES):
                try:
                    response = await client.get(ADVENTURES_INDEX_URL)

                    if response.status_code == 429:
                        wait = RETRY_BACKOFF ** attempt
                        logger.warning(f"Rate limited, waiting {wait}s")
                        await asyncio.sleep(wait)
                        continue

                    response.raise_for_status()
                    data = response.json()

                    # Write cache files
                    cache_file = self.cache_dir / "adventures.json"
                    cache_file.write_text(
                        json.dumps(data, indent=2), encoding="utf-8"
                    )

                    metadata = {
                        "downloaded_at": datetime.now(timezone.utc).isoformat(),
                        "source_url": ADVENTURES_INDEX_URL,
                        "etag": response.headers.get("etag", ""),
                    }
                    metadata_path = self.cache_dir / "metadata.json"
                    metadata_path.write_text(
                        json.dumps(metadata, indent=2), encoding="utf-8"
                    )

                    self._parse_raw_index(data)
                    logger.info("Downloaded fresh adventure index")
                    return

                except httpx.TimeoutException as e:
                    logger.warning(
                        f"Timeout downloading adventure index, "
                        f"attempt {attempt + 1}/{MAX_RETRIES}"
                    )
                    last_error = e
                    await asyncio.sleep(RETRY_BACKOFF ** attempt)

                except httpx.HTTPStatusError as e:
                    if e.response.status_code >= 500:
                        logger.warning(
                            f"Server error {e.response.status_code}, "
                            f"attempt {attempt + 1}/{MAX_RETRIES}"
                        )
                        last_error = e
                        await asyncio.sleep(RETRY_BACKOFF ** attempt)
                    else:
                        raise AdventureIndexError(
                            f"HTTP error: {e}"
                        ) from e

        raise AdventureIndexError(
            f"Failed to download adventure index after {MAX_RETRIES} "
            f"retries: {last_error}"
        )

    def get_by_id(self, adventure_id: str) -> AdventureIndexEntry | None:
        """Look up an adventure by its short ID (case-insensitive)."""
        adventure_id_lower = adventure_id.lower()
        for entry in self._entries:
            if entry.id.lower() == adventure_id_lower:
                return entry
        return None

    def get_by_name(self, name: str) -> AdventureIndexEntry | None:
        """Look up an adventure by exact name (case-insensitive)."""
        name_lower = name.lower()
        for entry in self._entries:
            if entry.name.lower() == name_lower:
                return entry
        return None

    def get_storylines(self) -> dict[str, list[AdventureIndexEntry]]:
        """Group all adventures by storyline."""
        groups: dict[str, list[AdventureIndexEntry]] = {}
        for entry in self._entries:
            storyline = entry.storyline or "Uncategorized"
            groups.setdefault(storyline, []).append(entry)
        # Sort each group by level_start
        for entries in groups.values():
            entries.sort(key=lambda e: e.level_start or 0)
        return groups


__all__ = [
    "AdventureIndex",
    "AdventureIndexError",
]
