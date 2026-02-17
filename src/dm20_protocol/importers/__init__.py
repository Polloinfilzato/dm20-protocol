"""
Character import from external platforms.

Currently supports:
- D&D Beyond (public characters via URL, or local JSON file)
"""

from .dndbeyond.fetcher import fetch_character, read_character_file
from .dndbeyond.mapper import map_ddb_to_character
from .base import ImportResult, ImportError

__all__ = [
    "fetch_character",
    "read_character_file",
    "map_ddb_to_character",
    "ImportResult",
    "ImportError",
]
