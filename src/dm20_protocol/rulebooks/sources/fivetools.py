"""
5etools data source for loading D&D 5e content from the 5etools GitHub mirror.

This module handles:
- Data discovery, downloading, and caching of raw JSON files
- Parsing 5etools JSON into dm20-protocol Pydantic models
- Converting 5etools custom markup ({@spell fireball} → fireball)
"""

import asyncio
import json
import logging
import re
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
    ClassLevelInfo,
    SpellcastingInfo,
    AbilityBonus,
    RacialTrait,
    ArmorClassInfo,
    MonsterAbility,
    MonsterAction,
    BackgroundFeature,
    Prerequisite,
    RulebookSource as RulebookSourceType,
    SpellSchool,
    Size,
    ItemRarity,
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


# =============================================================================
# 5etools Schema Mapping Tables
# =============================================================================

SCHOOL_ABBREVIATIONS: dict[str, SpellSchool] = {
    "A": SpellSchool.ABJURATION,
    "C": SpellSchool.CONJURATION,
    "D": SpellSchool.DIVINATION,
    "E": SpellSchool.ENCHANTMENT,
    "V": SpellSchool.EVOCATION,
    "I": SpellSchool.ILLUSION,
    "N": SpellSchool.NECROMANCY,
    "T": SpellSchool.TRANSMUTATION,
}

SIZE_ABBREVIATIONS: dict[str, Size] = {
    "T": Size.TINY,
    "S": Size.SMALL,
    "M": Size.MEDIUM,
    "L": Size.LARGE,
    "H": Size.HUGE,
    "G": Size.GARGANTUAN,
}

ALIGNMENT_ABBREVIATIONS: dict[str, str] = {
    "L": "Lawful",
    "N": "Neutral",
    "C": "Chaotic",
    "G": "Good",
    "E": "Evil",
    "U": "Unaligned",
    "A": "Any",
}

ABILITY_ABBREVIATIONS: dict[str, str] = {
    "str": "STR",
    "dex": "DEX",
    "con": "CON",
    "int": "INT",
    "wis": "WIS",
    "cha": "CHA",
}

ITEM_TYPE_MAP: dict[str, str] = {
    "M": "weapon",
    "R": "weapon",
    "S": "armor",
    "HA": "armor",
    "MA": "armor",
    "LA": "armor",
    "A": "ammunition",
    "G": "adventuring-gear",
    "SCF": "adventuring-gear",
    "INS": "tool",
    "AT": "tool",
    "GS": "tool",
    "T": "tool",
    "P": "potion",
    "SC": "scroll",
    "W": "wondrous-item",
    "WD": "wand",
    "RD": "rod",
    "ST": "staff",
    "RG": "ring",
    "$": "trade-good",
}

# CR string to XP value lookup
XP_BY_CR: dict[float, int] = {
    0: 10, 0.125: 25, 0.25: 50, 0.5: 100,
    1: 200, 2: 450, 3: 700, 4: 1100, 5: 1800,
    6: 2300, 7: 2900, 8: 3900, 9: 5000, 10: 5900,
    11: 7200, 12: 8400, 13: 10000, 14: 11500, 15: 13000,
    16: 15000, 17: 18000, 18: 20000, 19: 22000, 20: 25000,
    21: 33000, 22: 41000, 23: 50000, 24: 62000, 25: 75000,
    26: 90000, 27: 105000, 28: 120000, 29: 135000, 30: 155000,
}

# Regex for stripping 5etools markup tags
_MARKUP_DC_RE = re.compile(r"\{@dc\s+(\d+)\}")
_MARKUP_HIT_RE = re.compile(r"\{@hit\s+(\d+)\}")
_MARKUP_GENERIC_RE = re.compile(r"\{@\w+\s+([^}|]+?)(?:\|[^}]*)?\}")
_MARKUP_EMPTY_RE = re.compile(r"\{@\w+\}")


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
        self._parse_all_data()
        self._loaded = True
        self.loaded_at = datetime.now()
        logger.info(f"Loaded 5etools: {self.content_counts()}")

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
    # 5etools Markup Conversion
    # =========================================================================

    @staticmethod
    def _convert_5etools_markup(text: str) -> str:
        """Convert 5etools markup tags to plain text.

        Handles tags like {@dice 1d6}, {@spell fireball}, {@dc 15}, etc.
        """
        if not text:
            return ""
        # Special cases: {@dc 15} → DC 15, {@hit 5} → +5
        text = _MARKUP_DC_RE.sub(r"DC \1", text)
        text = _MARKUP_HIT_RE.sub(r"+\1", text)
        # Generic: {@tag content} or {@tag content|source} → content
        text = _MARKUP_GENERIC_RE.sub(r"\1", text)
        # Empty tags with no content: {@h} → ""
        text = _MARKUP_EMPTY_RE.sub("", text)
        return text

    @classmethod
    def _render_entries(cls, entries: list | None) -> list[str]:
        """Render 5etools entries array to list of plain text paragraphs.

        5etools entries can be strings or nested objects with sub-entries.
        This method recursively flattens them into readable text.
        """
        if not entries:
            return []
        result: list[str] = []
        for entry in entries:
            if isinstance(entry, str):
                result.append(cls._convert_5etools_markup(entry))
            elif isinstance(entry, dict):
                entry_type = entry.get("type", "")
                if entry_type in ("entries", "inset", "insetReadaloud"):
                    name = entry.get("name", "")
                    sub = cls._render_entries(entry.get("entries", []))
                    if name and sub:
                        result.append(f"{name}. {sub[0]}")
                        result.extend(sub[1:])
                    elif name:
                        result.append(name)
                    else:
                        result.extend(sub)
                elif entry_type == "list":
                    for item in entry.get("items", []):
                        if isinstance(item, str):
                            result.append(
                                f"- {cls._convert_5etools_markup(item)}"
                            )
                        elif isinstance(item, dict):
                            sub = cls._render_entries([item])
                            for s in sub:
                                result.append(f"- {s}")
                elif entry_type == "table":
                    caption = entry.get("caption", "")
                    if caption:
                        result.append(f"[Table: {caption}]")
                else:
                    # Other types — try to extract nested entries
                    sub = cls._render_entries(entry.get("entries", []))
                    result.extend(sub)
        return result

    @staticmethod
    def _make_index(name: str) -> str:
        """Generate a URL-safe index from a name."""
        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

    @staticmethod
    def _parse_alignment(alignment: Any) -> str:
        """Parse 5etools alignment array to human-readable string."""
        if not alignment:
            return "Unaligned"
        if isinstance(alignment, str):
            return alignment
        if isinstance(alignment, list):
            parts = []
            for code in alignment:
                if isinstance(code, str):
                    parts.append(ALIGNMENT_ABBREVIATIONS.get(code, code))
                elif isinstance(code, dict):
                    # Complex alignment (e.g., {"special": "..."})
                    return str(code.get("special", "Unaligned"))
            return " ".join(parts) if parts else "Unaligned"
        return "Unaligned"

    @staticmethod
    def _parse_cr(cr: Any) -> float:
        """Parse 5etools CR value to float."""
        if isinstance(cr, (int, float)):
            return float(cr)
        if isinstance(cr, str):
            if "/" in cr:
                num, denom = cr.split("/", 1)
                try:
                    return float(num) / float(denom)
                except (ValueError, ZeroDivisionError):
                    return 0.0
            try:
                return float(cr)
            except ValueError:
                return 0.0
        if isinstance(cr, dict):
            return FiveToolsSource._parse_cr(cr.get("cr", 0))
        return 0.0

    @staticmethod
    def _parse_speed(speed: Any) -> dict[str, str]:
        """Parse 5etools speed object to dict of movement types."""
        if not speed:
            return {"walk": "30 ft."}
        if isinstance(speed, (int, float)):
            return {"walk": f"{int(speed)} ft."}
        if isinstance(speed, dict):
            result: dict[str, str] = {}
            for key, value in speed.items():
                if key == "canHover":
                    continue
                if isinstance(value, (int, float)):
                    result[key] = f"{int(value)} ft."
                elif isinstance(value, bool):
                    if value:
                        result[key] = "true"
                elif isinstance(value, dict):
                    amount = value.get("number", value.get("amount", 0))
                    result[key] = f"{int(amount)} ft."
                else:
                    result[key] = str(value)
            return result or {"walk": "30 ft."}
        return {"walk": "30 ft."}

    # =========================================================================
    # Model Mapping — Parse raw 5etools JSON into dm20-protocol models
    # =========================================================================

    def _parse_all_data(self) -> None:
        """Parse all raw 5etools data into Pydantic model instances."""
        self._parse_spells()
        self._parse_monsters()
        self._parse_classes()
        self._parse_races()
        self._parse_feats()
        self._parse_items()
        self._parse_backgrounds()

        total = sum(self.content_counts().to_dict().values())
        logger.info(f"Mapped {total} 5etools entries to models")

    def _parse_spells(self) -> None:
        """Parse raw spell data into SpellDefinition models."""
        for raw in self._raw_data.get("spells", []):
            try:
                spell = self._map_spell(raw)
                self._spells[spell.index] = spell
            except Exception as e:
                name = raw.get("name", "unknown")
                logger.warning(f"Failed to map 5etools spell '{name}': {e}")

    def _parse_monsters(self) -> None:
        """Parse raw monster data into MonsterDefinition models."""
        for raw in self._raw_data.get("bestiary", []):
            try:
                monster = self._map_monster(raw)
                self._monsters[monster.index] = monster
            except Exception as e:
                name = raw.get("name", "unknown")
                logger.warning(f"Failed to map 5etools monster '{name}': {e}")

    def _parse_classes(self) -> None:
        """Parse raw class data into ClassDefinition models."""
        for raw in self._raw_data.get("class", []):
            try:
                class_def = self._map_class(raw)
                self._classes[class_def.index] = class_def
            except Exception as e:
                name = raw.get("name", "unknown")
                logger.warning(f"Failed to map 5etools class '{name}': {e}")

    def _parse_races(self) -> None:
        """Parse raw race data into RaceDefinition models."""
        for raw in self._raw_data.get("races", []):
            try:
                race = self._map_race(raw)
                self._races[race.index] = race
            except Exception as e:
                name = raw.get("name", "unknown")
                logger.warning(f"Failed to map 5etools race '{name}': {e}")

    def _parse_feats(self) -> None:
        """Parse raw feat data into FeatDefinition models."""
        for raw in self._raw_data.get("feats", []):
            try:
                feat = self._map_feat(raw)
                self._feats[feat.index] = feat
            except Exception as e:
                name = raw.get("name", "unknown")
                logger.warning(f"Failed to map 5etools feat '{name}': {e}")

    def _parse_items(self) -> None:
        """Parse raw item data (both magic items and base items)."""
        for raw in self._raw_data.get("items", []):
            try:
                item = self._map_item(raw)
                self._items[item.index] = item
            except Exception as e:
                name = raw.get("name", "unknown")
                logger.warning(f"Failed to map 5etools item '{name}': {e}")
        # Also parse base items (weapons, armor, etc.)
        for raw in self._raw_data.get("items-base", []):
            try:
                item = self._map_item(raw)
                self._items[item.index] = item
            except Exception as e:
                name = raw.get("name", "unknown")
                logger.warning(f"Failed to map 5etools base item '{name}': {e}")

    def _parse_backgrounds(self) -> None:
        """Parse raw background data into BackgroundDefinition models."""
        for raw in self._raw_data.get("backgrounds", []):
            try:
                bg = self._map_background(raw)
                self._backgrounds[bg.index] = bg
            except Exception as e:
                name = raw.get("name", "unknown")
                logger.warning(f"Failed to map 5etools background '{name}': {e}")

    # =========================================================================
    # Individual Mapping Methods
    # =========================================================================

    def _map_spell(self, data: dict) -> SpellDefinition:
        """Map a 5etools spell JSON object to SpellDefinition."""
        name = data["name"]
        index = self._make_index(name)

        # School: single letter → SpellSchool enum
        school_code = data.get("school", "V")
        school = SCHOOL_ABBREVIATIONS.get(school_code, SpellSchool.EVOCATION)

        # Casting time
        time_data = data.get("time", [{}])
        if time_data:
            t = time_data[0]
            number = t.get("number", 1)
            unit = t.get("unit", "action")
            casting_time = f"{number} {unit}" if number != 1 else f"1 {unit}"
        else:
            casting_time = "1 action"

        # Range
        range_data = data.get("range", {})
        spell_range = self._parse_spell_range(range_data)

        # Duration
        duration_data = data.get("duration", [{}])
        duration, concentration = self._parse_spell_duration(duration_data)

        # Components
        comp_data = data.get("components", {})
        components: list[str] = []
        material = None
        if comp_data.get("v"):
            components.append("V")
        if comp_data.get("s"):
            components.append("S")
        if comp_data.get("m"):
            components.append("M")
            m = comp_data["m"]
            if isinstance(m, str):
                material = m
            elif isinstance(m, dict):
                material = m.get("text", "")

        # Entries → description
        desc = self._render_entries(data.get("entries", []))

        # Higher level
        higher_level = self._render_entries(
            data.get("entriesHigherLevel", [])
        ) or None

        # Ritual
        ritual = bool(data.get("meta", {}).get("ritual", False))

        # Damage type
        damage_type = None
        damage_inflict = data.get("damageInflict", [])
        if damage_inflict:
            damage_type = damage_inflict[0]

        # DC type
        dc_type = None
        saving_throws = data.get("savingThrow", [])
        if saving_throws:
            dc_type = saving_throws[0].upper()

        return SpellDefinition(
            index=index,
            name=name,
            level=data.get("level", 0),
            school=school,
            casting_time=casting_time,
            range=spell_range,
            duration=duration,
            components=components,
            material=material,
            ritual=ritual,
            concentration=concentration,
            desc=desc,
            higher_level=higher_level,
            classes=[],  # 5etools stores class-spell mapping separately
            subclasses=[],
            damage_type=damage_type,
            dc_type=dc_type,
            source=self.source_id,
        )

    @staticmethod
    def _parse_spell_range(range_data: dict) -> str:
        """Parse 5etools spell range object to string."""
        if not range_data:
            return "Self"
        range_type = range_data.get("type", "point")
        distance = range_data.get("distance", {})
        dist_type = distance.get("type", "self")

        if dist_type == "self":
            if range_type == "sphere":
                amount = distance.get("amount", 0)
                return f"Self ({amount}-foot radius)"
            elif range_type == "cone":
                amount = distance.get("amount", 0)
                return f"Self ({amount}-foot cone)"
            elif range_type == "line":
                amount = distance.get("amount", 0)
                return f"Self ({amount}-foot line)"
            return "Self"
        elif dist_type == "touch":
            return "Touch"
        elif dist_type == "sight":
            return "Sight"
        elif dist_type == "unlimited":
            return "Unlimited"
        else:
            amount = distance.get("amount", 0)
            return f"{amount} {dist_type}"

    @staticmethod
    def _parse_spell_duration(
        duration_data: list[dict],
    ) -> tuple[str, bool]:
        """Parse 5etools duration array to (duration_string, is_concentration)."""
        if not duration_data:
            return "Instantaneous", False

        d = duration_data[0]
        d_type = d.get("type", "instant")
        concentration = bool(d.get("concentration", False))

        if d_type == "instant":
            return "Instantaneous", False
        elif d_type == "permanent":
            ends = d.get("ends", [])
            if "dispel" in ends:
                return "Until dispelled", False
            return "Permanent", False
        elif d_type == "special":
            return "Special", False
        elif d_type == "timed":
            dur = d.get("duration", {})
            amount = dur.get("amount", 1)
            unit = dur.get("type", "minute")
            # Pluralize
            unit_str = unit + ("s" if amount > 1 else "")
            base = f"{amount} {unit_str}"
            if concentration:
                return f"Concentration, up to {base}", True
            return base, False

        return "Instantaneous", False

    def _map_monster(self, data: dict) -> MonsterDefinition:
        """Map a 5etools monster JSON object to MonsterDefinition."""
        name = data["name"]
        index = self._make_index(name)

        # Size: array of abbreviations, take first
        size_arr = data.get("size", ["M"])
        size_code = size_arr[0] if isinstance(size_arr, list) else size_arr
        size = SIZE_ABBREVIATIONS.get(size_code, Size.MEDIUM)

        # Type: can be string or object
        type_data = data.get("type", "")
        if isinstance(type_data, dict):
            creature_type = type_data.get("type", "")
            subtype = ", ".join(type_data.get("tags", []))
            # Tags can be strings or objects
            tag_parts = []
            for tag in type_data.get("tags", []):
                if isinstance(tag, str):
                    tag_parts.append(tag)
                elif isinstance(tag, dict):
                    tag_parts.append(tag.get("tag", ""))
            subtype = ", ".join(tag_parts) if tag_parts else None
        else:
            creature_type = str(type_data)
            subtype = None

        # Alignment
        alignment = self._parse_alignment(data.get("alignment"))

        # AC: array of ints or objects
        armor_class = self._parse_monster_ac(data.get("ac", [10]))

        # HP
        hp_data = data.get("hp", {})
        if isinstance(hp_data, dict):
            hit_points = hp_data.get("average", 1)
            hit_dice = hp_data.get("formula", "1d8")
        else:
            hit_points = int(hp_data) if hp_data else 1
            hit_dice = "1d8"

        # Speed
        speed = self._parse_speed(data.get("speed"))

        # CR → float + XP
        cr = self._parse_cr(data.get("cr", "0"))
        xp = XP_BY_CR.get(cr, 0)

        # Special abilities (trait)
        special_abilities = []
        for trait in data.get("trait", []):
            entries = self._render_entries(trait.get("entries", []))
            special_abilities.append(MonsterAbility(
                name=trait.get("name", ""),
                desc="\n".join(entries),
            ))

        # Actions
        actions = []
        for action in data.get("action", []):
            entries = self._render_entries(action.get("entries", []))
            actions.append(MonsterAction(
                name=self._convert_5etools_markup(action.get("name", "")),
                desc="\n".join(entries),
            ))

        # Reactions
        reactions = []
        for reaction in data.get("reaction", []):
            entries = self._render_entries(reaction.get("entries", []))
            reactions.append(MonsterAction(
                name=reaction.get("name", ""),
                desc="\n".join(entries),
            ))

        # Legendary actions
        legendary_actions = None
        if data.get("legendary"):
            legendary_actions = []
            for la in data["legendary"]:
                entries = self._render_entries(la.get("entries", []))
                legendary_actions.append(MonsterAction(
                    name=la.get("name", ""),
                    desc="\n".join(entries),
                ))

        # Senses
        senses: dict[str, str] = {}
        for sense_str in data.get("senses", []):
            if isinstance(sense_str, str):
                senses[sense_str.split()[0].lower()] = sense_str

        passive = data.get("passive")
        if passive:
            senses["passive_perception"] = str(passive)

        # Languages
        languages_data = data.get("languages", [])
        if isinstance(languages_data, list):
            languages = ", ".join(languages_data)
        else:
            languages = str(languages_data)

        # Immunities, resistances, vulnerabilities
        damage_immunities = data.get("immune", [])
        if damage_immunities:
            damage_immunities = [
                i if isinstance(i, str) else str(i)
                for i in damage_immunities
            ]
        damage_resistances = data.get("resist", [])
        if damage_resistances:
            damage_resistances = [
                r if isinstance(r, str) else str(r)
                for r in damage_resistances
            ]
        damage_vulnerabilities = data.get("vulnerable", [])
        if damage_vulnerabilities:
            damage_vulnerabilities = [
                v if isinstance(v, str) else str(v)
                for v in damage_vulnerabilities
            ]
        condition_immunities = data.get("conditionImmune", [])
        if condition_immunities:
            condition_immunities = [
                c if isinstance(c, str) else str(c)
                for c in condition_immunities
            ]

        return MonsterDefinition(
            index=index,
            name=name,
            size=size,
            type=creature_type,
            subtype=subtype,
            alignment=alignment,
            armor_class=armor_class,
            hit_points=hit_points,
            hit_dice=hit_dice,
            speed=speed,
            strength=data.get("str", 10),
            dexterity=data.get("dex", 10),
            constitution=data.get("con", 10),
            intelligence=data.get("int", 10),
            wisdom=data.get("wis", 10),
            charisma=data.get("cha", 10),
            proficiencies=[],
            damage_vulnerabilities=damage_vulnerabilities,
            damage_resistances=damage_resistances,
            damage_immunities=damage_immunities,
            condition_immunities=condition_immunities,
            senses=senses,
            languages=languages,
            challenge_rating=cr,
            xp=xp,
            special_abilities=special_abilities,
            actions=actions,
            reactions=reactions,
            legendary_actions=legendary_actions,
            source=self.source_id,
        )

    @staticmethod
    def _parse_monster_ac(ac_data: list) -> list[ArmorClassInfo]:
        """Parse 5etools AC array to list of ArmorClassInfo."""
        result = []
        for ac in ac_data:
            if isinstance(ac, int):
                result.append(ArmorClassInfo(type="natural", value=ac))
            elif isinstance(ac, dict):
                value = ac.get("ac", 10)
                from_list = ac.get("from", [])
                ac_type = from_list[0] if from_list else "natural"
                result.append(ArmorClassInfo(type=ac_type, value=value))
        return result or [ArmorClassInfo(type="natural", value=10)]

    def _map_class(self, data: dict) -> ClassDefinition:
        """Map a 5etools class JSON object to ClassDefinition."""
        name = data["name"]
        index = self._make_index(name)

        # Hit die
        hd = data.get("hd", {})
        hit_die = hd.get("faces", 8)

        # Proficiencies
        start_prof = data.get("startingProficiencies", {})
        proficiencies: list[str] = []
        for armor in start_prof.get("armor", []):
            if isinstance(armor, str):
                proficiencies.append(f"{armor} armor")
            elif isinstance(armor, dict) and armor.get("full"):
                proficiencies.append(armor["full"])
        for weapon in start_prof.get("weapons", []):
            if isinstance(weapon, str):
                proficiencies.append(f"{weapon} weapons")

        # Saving throws
        saving_throws = [
            ABILITY_ABBREVIATIONS.get(p, p.upper())
            for p in data.get("proficiency", [])
        ]

        # Starting equipment
        equip_data = data.get("startingEquipment", {})
        starting_equipment = equip_data.get("default", [])
        if isinstance(starting_equipment, list):
            starting_equipment = [
                str(e) for e in starting_equipment if isinstance(e, str)
            ]

        # Spellcasting
        spellcasting = None
        sc_data = data.get("casterProgression")
        if sc_data:
            sc_ability_data = data.get("spellcastingAbility")
            sc_ability = ABILITY_ABBREVIATIONS.get(
                sc_ability_data, "INT"
            ) if sc_ability_data else "INT"
            caster_type = "full"
            if sc_data == "1/2":
                caster_type = "half"
            elif sc_data == "1/3":
                caster_type = "third"
            elif sc_data == "pact":
                caster_type = "pact"
            spellcasting = SpellcastingInfo(
                level=1,
                spellcasting_ability=sc_ability,
                caster_type=caster_type,
            )

        # Class features → level info (extract from reference strings)
        class_levels: dict[int, ClassLevelInfo] = {}
        for feature_ref in data.get("classFeatures", []):
            if isinstance(feature_ref, str):
                parts = feature_ref.split("|")
                if len(parts) >= 4:
                    feat_name = parts[0]
                    try:
                        level = int(parts[-1])
                    except ValueError:
                        continue
                    if level not in class_levels:
                        class_levels[level] = ClassLevelInfo(
                            level=level,
                            proficiency_bonus=self._prof_bonus_for_level(
                                level
                            ),
                            features=[],
                        )
                    class_levels[level].features.append(feat_name)

        return ClassDefinition(
            index=index,
            name=name,
            hit_die=hit_die,
            proficiencies=proficiencies,
            saving_throws=saving_throws,
            starting_equipment=starting_equipment,
            spellcasting=spellcasting,
            class_levels=class_levels,
            subclasses=[],
            source=self.source_id,
        )

    @staticmethod
    def _prof_bonus_for_level(level: int) -> int:
        """Calculate proficiency bonus for a given character level."""
        return (level - 1) // 4 + 2

    def _map_race(self, data: dict) -> RaceDefinition:
        """Map a 5etools race JSON object to RaceDefinition."""
        name = data["name"]
        index = self._make_index(name)

        # Size
        size_arr = data.get("size", ["M"])
        size_code = size_arr[0] if isinstance(size_arr, list) else size_arr
        size = SIZE_ABBREVIATIONS.get(size_code, Size.MEDIUM)

        # Speed
        speed_data = data.get("speed", 30)
        if isinstance(speed_data, dict):
            speed = speed_data.get("walk", 30)
        elif isinstance(speed_data, (int, float)):
            speed = int(speed_data)
        else:
            speed = 30

        # Ability bonuses
        ability_bonuses = []
        for ab in data.get("ability", []):
            if isinstance(ab, dict):
                for key, value in ab.items():
                    if key == "choose":
                        continue  # Skip flexible choices for now
                    ability_bonuses.append(AbilityBonus(
                        ability_score=ABILITY_ABBREVIATIONS.get(
                            key, key.upper()
                        ),
                        bonus=value,
                    ))

        # Languages
        languages: list[str] = []
        for lang_prof in data.get("languageProficiencies", []):
            if isinstance(lang_prof, dict):
                for lang, val in lang_prof.items():
                    if val is True:
                        languages.append(lang.capitalize())

        # Traits from entries
        traits: list[RacialTrait] = []
        for entry in data.get("entries", []):
            if isinstance(entry, dict) and entry.get("type") == "entries":
                trait_name = entry.get("name", "")
                trait_desc = self._render_entries(entry.get("entries", []))
                if trait_name:
                    traits.append(RacialTrait(
                        index=self._make_index(trait_name),
                        name=trait_name,
                        desc=trait_desc,
                    ))

        return RaceDefinition(
            index=index,
            name=name,
            speed=speed,
            ability_bonuses=ability_bonuses,
            size=size,
            languages=languages,
            traits=traits,
            subraces=[],
            source=self.source_id,
        )

    def _map_feat(self, data: dict) -> FeatDefinition:
        """Map a 5etools feat JSON object to FeatDefinition."""
        name = data["name"]
        index = self._make_index(name)

        # Description
        desc = self._render_entries(data.get("entries", []))

        # Prerequisites
        prerequisites: list[Prerequisite] = []
        for prereq in data.get("prerequisite", []):
            if isinstance(prereq, dict):
                if prereq.get("ability"):
                    for ab in prereq["ability"]:
                        if isinstance(ab, dict):
                            for key, value in ab.items():
                                prerequisites.append(Prerequisite(
                                    type="ability_score",
                                    ability_score=ABILITY_ABBREVIATIONS.get(
                                        key, key.upper()
                                    ),
                                    minimum_score=value,
                                ))
                if prereq.get("level"):
                    prerequisites.append(Prerequisite(
                        type="level",
                        level=prereq["level"],
                    ))

        return FeatDefinition(
            index=index,
            name=name,
            desc=desc,
            prerequisites=prerequisites,
            source=self.source_id,
        )

    def _map_item(self, data: dict) -> ItemDefinition:
        """Map a 5etools item JSON object to ItemDefinition."""
        name = data["name"]
        index = self._make_index(name)

        # Description
        desc = self._render_entries(data.get("entries", []))

        # Equipment category from type code
        type_code = data.get("type", "")
        equipment_category = ITEM_TYPE_MAP.get(type_code, "gear")

        # Weight and value
        weight = data.get("weight")
        cost = None
        if data.get("value"):
            # 5etools stores value in copper pieces
            cp = data["value"]
            if cp >= 100:
                cost = {"quantity": cp // 100, "unit": "gp"}
            elif cp >= 10:
                cost = {"quantity": cp // 10, "unit": "sp"}
            else:
                cost = {"quantity": cp, "unit": "cp"}

        # Weapon properties
        weapon_category = data.get("weaponCategory")
        weapon_range = None
        if type_code == "R":
            weapon_range = "Ranged"
        elif type_code == "M":
            weapon_range = "Melee"

        damage = None
        if data.get("dmg1"):
            damage = {
                "damage_dice": data["dmg1"],
                "damage_type": {"index": data.get("dmgType", "")},
            }

        # Armor properties
        armor_category = None
        armor_class_data = None
        if type_code in ("HA", "MA", "LA", "S"):
            armor_category = {
                "HA": "Heavy",
                "MA": "Medium",
                "LA": "Light",
                "S": "Shield",
            }.get(type_code)
            if data.get("ac"):
                armor_class_data = {"base": data["ac"]}

        # Rarity
        rarity = None
        rarity_str = data.get("rarity", "")
        if rarity_str and rarity_str != "none":
            rarity_map = {
                "common": ItemRarity.COMMON,
                "uncommon": ItemRarity.UNCOMMON,
                "rare": ItemRarity.RARE,
                "very rare": ItemRarity.VERY_RARE,
                "legendary": ItemRarity.LEGENDARY,
                "artifact": ItemRarity.ARTIFACT,
            }
            rarity = rarity_map.get(rarity_str.lower())

        # Attunement
        requires_attunement = bool(data.get("reqAttune"))
        attunement_req = None
        if isinstance(data.get("reqAttune"), str):
            attunement_req = data["reqAttune"]

        # Properties
        properties = []
        for prop in data.get("property", []):
            if isinstance(prop, str):
                properties.append(prop)

        return ItemDefinition(
            index=index,
            name=name,
            desc=desc,
            equipment_category=equipment_category,
            cost=cost,
            weight=weight,
            weapon_category=weapon_category,
            weapon_range=weapon_range,
            damage=damage,
            properties=properties,
            armor_category=armor_category,
            armor_class=armor_class_data,
            rarity=rarity,
            requires_attunement=requires_attunement,
            attunement_requirements=attunement_req,
            source=self.source_id,
        )

    def _map_background(self, data: dict) -> BackgroundDefinition:
        """Map a 5etools background JSON object to BackgroundDefinition."""
        name = data["name"]
        index = self._make_index(name)

        # Description
        desc = self._render_entries(data.get("entries", []))

        # Skill proficiencies
        starting_proficiencies: list[str] = []
        for sp in data.get("skillProficiencies", []):
            if isinstance(sp, dict):
                for skill, val in sp.items():
                    if val is True and skill != "choose":
                        starting_proficiencies.append(skill.capitalize())

        # Tool proficiencies
        for tp in data.get("toolProficiencies", []):
            if isinstance(tp, dict):
                for tool, val in tp.items():
                    if val is True and tool != "choose":
                        starting_proficiencies.append(tool)

        # Feature — extract from entries with "Feature:" prefix
        feature = None
        for entry in data.get("entries", []):
            if isinstance(entry, dict):
                entry_name = entry.get("name", "")
                if "feature" in entry_name.lower() or entry.get(
                    "type"
                ) == "entries":
                    sub_entries = self._render_entries(
                        entry.get("entries", [])
                    )
                    if sub_entries and not feature:
                        feature = BackgroundFeature(
                            name=entry_name,
                            desc=sub_entries,
                        )

        return BackgroundDefinition(
            index=index,
            name=name,
            desc=desc,
            starting_proficiencies=starting_proficiencies,
            feature=feature,
            source=self.source_id,
        )

    # =========================================================================
    # Query Methods
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
