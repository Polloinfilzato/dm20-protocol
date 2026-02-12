"""
5etools data source for loading D&D 5e content from the 5etools GitHub mirror.

This module handles data discovery, downloading, and caching of raw JSON files
from the 5etools repository. Model mapping (parsing 5etools JSON into
dm20-protocol Pydantic models) will be implemented in a separate task (#84).
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import httpx

from ..models import (
    ClassDefinition,
    SubclassDefinition,
    RaceDefinition,
    SubraceDefinition,
    SpellDefinition,
    MonsterDefinition,
    FeatDefinition,
    BackgroundDefinition,
    ItemDefinition,
    RulebookSource as RulebookSourceType,
)
from .base import RulebookSourceBase, SearchResult, ContentCounts


logger = logging.getLogger("dm20-protocol")


# =============================================================================
# Configuration
# =============================================================================

GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/5etools-mirror-3/5etools-src/main/data"
)
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0
DOWNLOAD_CONCURRENCY = 5

# Categories whose data is split across multiple files, discovered via index.json
INDEXED_CATEGORIES: dict[str, dict[str, str]] = {
    "spells": {
        "index_path": "spells/index.json",
        "subdir": "spells",
        "data_key": "spell",
    },
    "bestiary": {
        "index_path": "bestiary/index.json",
        "subdir": "bestiary",
        "data_key": "monster",
    },
    "class": {
        "index_path": "class/index.json",
        "subdir": "class",
        "data_key": "class",
    },
}

# Categories stored as single top-level JSON files
SINGLE_FILE_CATEGORIES: dict[str, dict[str, str]] = {
    "races": {"file_path": "races.json", "data_key": "race"},
    "feats": {"file_path": "feats.json", "data_key": "feat"},
    "items": {"file_path": "items.json", "data_key": "item"},
    "items-base": {"file_path": "items-base.json", "data_key": "baseitem"},
    "backgrounds": {"file_path": "backgrounds.json", "data_key": "background"},
}


class FiveToolsSourceError(Exception):
    """Error fetching or parsing 5etools data."""

    pass


class FiveToolsSource(RulebookSourceBase):
    """
    Rulebook source for 5etools JSON data files.

    Downloads data from the 5etools GitHub mirror repository and caches
    raw JSON locally. Data is organized in two patterns:

    - **Split files** (spells, bestiary, classes): discovered via index.json,
      one file per source book, merged into a single dataset per category.
    - **Single files** (races, feats, items, backgrounds): downloaded directly.

    Cache structure::

        {cache_dir}/
        ├── raw/           # Individual downloaded JSON files
        │   ├── spells/
        │   ├── bestiary/
        │   ├── class/
        │   ├── races.json
        │   └── ...
        ├── merged/        # Merged datasets by category
        │   ├── spells.json
        │   ├── bestiary.json
        │   └── ...
        └── metadata.json  # Download timestamps, file manifest
    """

    def __init__(self, cache_dir: Path | None = None):
        super().__init__(
            source_id="5etools",
            source_type=RulebookSourceType.FIVETOOLS,
            name="5etools",
        )
        self.cache_dir = cache_dir or Path("dnd_data/rulebook_cache/5etools")
        self._client: httpx.AsyncClient | None = None

        # Raw data loaded from merged cache (populated by download step)
        self._raw_data: dict[str, list[dict]] = {}

        # Content storage (populated by model mapping in Task #84)
        self._classes: dict[str, ClassDefinition] = {}
        self._subclasses: dict[str, SubclassDefinition] = {}
        self._races: dict[str, RaceDefinition] = {}
        self._subraces: dict[str, SubraceDefinition] = {}
        self._spells: dict[str, SpellDefinition] = {}
        self._monsters: dict[str, MonsterDefinition] = {}
        self._feats: dict[str, FeatDefinition] = {}
        self._backgrounds: dict[str, BackgroundDefinition] = {}
        self._items: dict[str, ItemDefinition] = {}

    # =========================================================================
    # Load / Download
    # =========================================================================

    async def load(self) -> None:
        """Load 5etools data from cache or by downloading from GitHub."""
        await self._ensure_data_downloaded()
        self._load_merged_data()
        # Model mapping will be added in Task #84:
        # self._parse_all_data()
        self._loaded = True
        self.loaded_at = datetime.now()
        counts = self.raw_data_counts
        total = sum(counts.values())
        logger.info(f"Loaded 5etools: {total} raw entries across {len(counts)} categories")

    async def _ensure_data_downloaded(self, force: bool = False) -> None:
        """
        Download all data files if not already cached.

        Args:
            force: If True, re-download even if cache exists.
        """
        if not force and self._is_cache_valid():
            logger.info("5etools cache is valid, skipping download")
            return

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "raw").mkdir(exist_ok=True)
        (self.cache_dir / "merged").mkdir(exist_ok=True)

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            self._client = client
            try:
                for cat_name, config in INDEXED_CATEGORIES.items():
                    await self._download_indexed_category(cat_name, config)

                for cat_name, config in SINGLE_FILE_CATEGORIES.items():
                    await self._download_single_file(cat_name, config)

                self._write_metadata()
            finally:
                self._client = None

    def _is_cache_valid(self) -> bool:
        """Check if cache exists and has valid metadata."""
        metadata_path = self.cache_dir / "metadata.json"
        if not metadata_path.exists():
            return False
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            return bool(metadata.get("downloaded_at"))
        except (json.JSONDecodeError, KeyError):
            return False

    # =========================================================================
    # Indexed Category Download (spells, bestiary, classes)
    # =========================================================================

    async def _download_indexed_category(
        self, category: str, config: dict[str, str]
    ) -> None:
        """
        Download a category that uses index.json for file discovery.

        Steps:
        1. Fetch index.json to get file listing
        2. Download each data file with bounded concurrency
        3. Merge all entries into a single file per category
        """
        index_url = f"{GITHUB_RAW_BASE}/{config['index_path']}"
        logger.info(f"Downloading 5etools {category} index...")

        try:
            index_data = await self._fetch_json(index_url)
        except FiveToolsSourceError as e:
            logger.error(f"Failed to fetch {category} index: {e}")
            return

        # Save raw index
        raw_dir = self.cache_dir / "raw" / config["subdir"]
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / "index.json").write_text(
            json.dumps(index_data, indent=2), encoding="utf-8"
        )

        # Download files with bounded concurrency
        semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
        data_key = config["data_key"]

        async def _download_one(filename: str) -> list[dict]:
            async with semaphore:
                file_url = f"{GITHUB_RAW_BASE}/{config['subdir']}/{filename}"
                raw_path = raw_dir / filename

                # Use cached raw file if available
                if raw_path.exists():
                    try:
                        data = json.loads(raw_path.read_text(encoding="utf-8"))
                        return data.get(data_key, [])
                    except json.JSONDecodeError:
                        logger.warning(f"Corrupt cache: {raw_path}, re-downloading")
                        raw_path.unlink()

                try:
                    data = await self._fetch_json(file_url)
                    raw_path.write_text(
                        json.dumps(data, indent=2), encoding="utf-8"
                    )
                    return data.get(data_key, [])
                except FiveToolsSourceError as e:
                    logger.warning(f"Failed to download {filename}: {e}")
                    return []

        # Filter to valid JSON filenames and run downloads
        filenames = [
            fname
            for fname in index_data.values()
            if isinstance(fname, str) and fname.endswith(".json")
        ]
        tasks = [_download_one(fname) for fname in filenames]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_entries: list[dict] = []
        for result in results:
            if isinstance(result, list):
                all_entries.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"Download task failed: {result}")

        # Write merged file
        merged_path = self.cache_dir / "merged" / f"{category}.json"
        merged_data = {data_key: all_entries, "count": len(all_entries)}
        merged_path.write_text(
            json.dumps(merged_data, indent=2), encoding="utf-8"
        )

        logger.info(
            f"Downloaded 5etools {category}: "
            f"{len(all_entries)} entries from {len(filenames)} files"
        )

    # =========================================================================
    # Single File Download (races, feats, items, backgrounds)
    # =========================================================================

    async def _download_single_file(
        self, category: str, config: dict[str, str]
    ) -> None:
        """Download a single-file category and write its merged output."""
        file_url = f"{GITHUB_RAW_BASE}/{config['file_path']}"
        raw_path = self.cache_dir / "raw" / config["file_path"]
        data_key = config["data_key"]

        # Try loading from cache
        if raw_path.exists():
            try:
                data = json.loads(raw_path.read_text(encoding="utf-8"))
                entries = data.get(data_key, [])
                self._write_merged(category, data_key, entries)
                logger.info(f"Loaded cached 5etools {category}: {len(entries)} entries")
                return
            except json.JSONDecodeError:
                logger.warning(f"Corrupt cache: {raw_path}, re-downloading")
                raw_path.unlink()

        logger.info(f"Downloading 5etools {category}...")
        try:
            data = await self._fetch_json(file_url)
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

            entries = data.get(data_key, [])
            self._write_merged(category, data_key, entries)
            logger.info(f"Downloaded 5etools {category}: {len(entries)} entries")
        except FiveToolsSourceError as e:
            logger.error(f"Failed to download {category}: {e}")

    def _write_merged(
        self, category: str, data_key: str, entries: list[dict]
    ) -> None:
        """Write a merged category file."""
        merged_path = self.cache_dir / "merged" / f"{category}.json"
        merged_path.parent.mkdir(parents=True, exist_ok=True)
        merged_data = {data_key: entries, "count": len(entries)}
        merged_path.write_text(
            json.dumps(merged_data, indent=2), encoding="utf-8"
        )

    # =========================================================================
    # HTTP Fetch with Retry
    # =========================================================================

    async def _fetch_json(self, url: str) -> dict[str, Any]:
        """
        Fetch JSON from a URL with retry logic.

        Retries on timeouts and 5xx errors with exponential backoff.
        Rate-limit responses (429) trigger a wait-and-retry cycle.

        Raises:
            FiveToolsSourceError: If fetch fails after all retries.
        """
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._client.get(url)

                if response.status_code == 429:
                    wait = RETRY_BACKOFF ** attempt
                    logger.warning(f"Rate limited, waiting {wait}s")
                    await asyncio.sleep(wait)
                    continue

                response.raise_for_status()
                return response.json()

            except httpx.TimeoutException as e:
                logger.warning(
                    f"Timeout fetching {url}, attempt {attempt + 1}/{MAX_RETRIES}"
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
                    raise FiveToolsSourceError(f"HTTP error: {e}") from e

        raise FiveToolsSourceError(
            f"Failed to fetch {url} after {MAX_RETRIES} retries: {last_error}"
        )

    # =========================================================================
    # Cache Loading
    # =========================================================================

    def _load_merged_data(self) -> None:
        """Load merged JSON files into the _raw_data dict."""
        merged_dir = self.cache_dir / "merged"
        if not merged_dir.exists():
            return

        for merged_file in sorted(merged_dir.glob("*.json")):
            category = merged_file.stem
            data_key = self._resolve_data_key(category)
            if not data_key:
                continue

            try:
                data = json.loads(merged_file.read_text(encoding="utf-8"))
                if data_key in data:
                    self._raw_data[category] = data[data_key]
                    logger.debug(
                        f"Loaded {len(data[data_key])} {category} entries from merged cache"
                    )
            except json.JSONDecodeError:
                logger.warning(f"Corrupt merged file: {merged_file}")

    def _resolve_data_key(self, category: str) -> str | None:
        """Resolve the JSON data key for a given category name."""
        if category in INDEXED_CATEGORIES:
            return INDEXED_CATEGORIES[category]["data_key"]
        if category in SINGLE_FILE_CATEGORIES:
            return SINGLE_FILE_CATEGORIES[category]["data_key"]
        return None

    # =========================================================================
    # Metadata
    # =========================================================================

    def _write_metadata(self) -> None:
        """Write download metadata to metadata.json."""
        manifest: dict[str, dict[str, int]] = {}
        raw_dir = self.cache_dir / "raw"
        if raw_dir.exists():
            for f in raw_dir.rglob("*.json"):
                rel_path = str(f.relative_to(raw_dir))
                manifest[rel_path] = {"size": f.stat().st_size}

        metadata = {
            "downloaded_at": datetime.now().isoformat(),
            "source_repo": "5etools-mirror-3/5etools-src",
            "branch": "main",
            "file_count": len(manifest),
            "files": manifest,
        }
        metadata_path = self.cache_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

    @property
    def raw_data_counts(self) -> dict[str, int]:
        """Get counts of raw (unparsed) data entries per category."""
        return {cat: len(entries) for cat, entries in self._raw_data.items()}

    # =========================================================================
    # Query Methods (stubs — model mapping in Task #84)
    # =========================================================================

    def get_class(self, index: str) -> ClassDefinition | None:
        return self._classes.get(index.lower())

    def get_subclass(self, index: str) -> SubclassDefinition | None:
        return self._subclasses.get(index.lower())

    def get_race(self, index: str) -> RaceDefinition | None:
        return self._races.get(index.lower())

    def get_subrace(self, index: str) -> SubraceDefinition | None:
        return self._subraces.get(index.lower())

    def get_spell(self, index: str) -> SpellDefinition | None:
        return self._spells.get(index.lower())

    def get_monster(self, index: str) -> MonsterDefinition | None:
        return self._monsters.get(index.lower())

    def get_feat(self, index: str) -> FeatDefinition | None:
        return self._feats.get(index.lower())

    def get_background(self, index: str) -> BackgroundDefinition | None:
        return self._backgrounds.get(index.lower())

    def get_item(self, index: str) -> ItemDefinition | None:
        return self._items.get(index.lower())

    def search(
        self,
        query: str,
        categories: list[str] | None = None,
        limit: int = 20,
        class_filter: str | None = None,
    ) -> Iterator[SearchResult]:
        """Search across all content (populated after model mapping in #84)."""
        query_lower = query.lower()
        class_filter_lower = class_filter.lower() if class_filter else None
        count = 0

        category_map = {
            "class": (self._classes, "class"),
            "subclass": (self._subclasses, "subclass"),
            "race": (self._races, "race"),
            "subrace": (self._subraces, "subrace"),
            "spell": (self._spells, "spell"),
            "monster": (self._monsters, "monster"),
            "feat": (self._feats, "feat"),
            "background": (self._backgrounds, "background"),
            "item": (self._items, "item"),
        }

        if categories:
            search_categories = [
                (k, v) for k, v in category_map.items() if k in categories
            ]
        else:
            search_categories = list(category_map.items())

        for _category_name, (storage, cat) in search_categories:
            for index, item in storage.items():
                if count >= limit:
                    return

                if class_filter_lower and cat == "spell":
                    spell_classes = getattr(item, "classes", [])
                    if class_filter_lower not in [c.lower() for c in spell_classes]:
                        continue

                if query_lower:
                    if (
                        query_lower not in index
                        and query_lower not in item.name.lower()
                    ):
                        continue
                elif not class_filter_lower:
                    continue

                yield SearchResult(
                    index=item.index,
                    name=item.name,
                    category=cat,  # type: ignore[arg-type]
                    source=self.source_id,
                    summary=(
                        getattr(item, "desc", [None])[0]
                        if hasattr(item, "desc") and item.desc
                        else None
                    ),
                )
                count += 1

    def content_counts(self) -> ContentCounts:
        """Get model content counts (populated after mapping in #84)."""
        return ContentCounts(
            classes=len(self._classes),
            subclasses=len(self._subclasses),
            races=len(self._races),
            subraces=len(self._subraces),
            spells=len(self._spells),
            monsters=len(self._monsters),
            feats=len(self._feats),
            backgrounds=len(self._backgrounds),
            items=len(self._items),
        )

    async def close(self) -> None:
        """Close HTTP client if open."""
        if self._client:
            await self._client.aclose()
            self._client = None


__all__ = [
    "FiveToolsSource",
    "FiveToolsSourceError",
]
