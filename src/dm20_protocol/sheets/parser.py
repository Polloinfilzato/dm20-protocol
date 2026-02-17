"""Parse Markdown character sheets and extract YAML frontmatter.

Reads MD files produced by the renderer, extracts the YAML frontmatter,
and validates the resulting dict against Character model constraints.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """Raised when a character sheet cannot be parsed."""


class CharacterSheetParser:
    """Parses Markdown character sheets and extracts YAML frontmatter."""

    @staticmethod
    def parse_string(content: str) -> dict[str, Any]:
        """Extract YAML frontmatter from a Markdown string.

        Args:
            content: Full Markdown file content.

        Returns:
            Parsed frontmatter as a dict.

        Raises:
            ParseError: If frontmatter delimiters are missing or YAML is invalid.
        """
        stripped = content.lstrip()
        if not stripped.startswith("---"):
            raise ParseError("Missing opening frontmatter delimiter '---'")

        # Find the closing delimiter
        # Skip the first '---' and find the next one
        rest = stripped[3:]
        closing_idx = rest.find("\n---")
        if closing_idx == -1:
            raise ParseError("Missing closing frontmatter delimiter '---'")

        yaml_text = rest[:closing_idx]

        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            raise ParseError(f"Invalid YAML in frontmatter: {e}") from e

        if not isinstance(data, dict):
            raise ParseError(f"Frontmatter must be a mapping, got {type(data).__name__}")

        return data

    @staticmethod
    def parse_file(path: Path) -> dict[str, Any]:
        """Extract YAML frontmatter from a Markdown file.

        Args:
            path: Path to the .md file.

        Returns:
            Parsed frontmatter as a dict.

        Raises:
            ParseError: If file cannot be read or frontmatter is invalid.
        """
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            raise ParseError(f"Cannot read file: {e}") from e

        return CharacterSheetParser.parse_string(content)

    @staticmethod
    def frontmatter_hash(content: str) -> str:
        """Compute SHA-256 hash of the YAML frontmatter portion.

        Used for feedback loop prevention: if the hash matches what
        dm20 last wrote, the change was dm20-initiated.
        """
        stripped = content.lstrip()
        if not stripped.startswith("---"):
            return hashlib.sha256(content.encode("utf-8")).hexdigest()

        rest = stripped[3:]
        closing_idx = rest.find("\n---")
        if closing_idx == -1:
            return hashlib.sha256(content.encode("utf-8")).hexdigest()

        yaml_text = rest[:closing_idx]
        return hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()

    @staticmethod
    def validate_frontmatter(data: dict[str, Any]) -> list[str]:
        """Validate frontmatter values against basic Character constraints.

        Returns a list of warning messages (empty = valid).
        Does NOT raise — invalid values are reported, not rejected.
        """
        warnings: list[str] = []

        # Ability scores must be 1-30
        for ability in ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]:
            val = data.get(ability)
            if val is not None and isinstance(val, int):
                if val < 1 or val > 30:
                    warnings.append(f"{ability} must be 1-30, got {val}")

        # Level must be 1-20
        level = data.get("level")
        if level is not None and isinstance(level, int):
            if level < 1 or level > 20:
                warnings.append(f"level must be 1-20, got {level}")

        # HP must be non-negative
        for hp_field in ["hit_points_current", "hit_points_max", "temporary_hit_points"]:
            val = data.get(hp_field)
            if val is not None and isinstance(val, int) and val < 0:
                warnings.append(f"{hp_field} must be non-negative, got {val}")

        # dm20_id should be present
        if "dm20_id" not in data:
            warnings.append("Missing dm20_id — this sheet may not be linked to a character")

        return warnings

    @staticmethod
    def extract_sync_metadata(data: dict[str, Any]) -> tuple[str, int, str]:
        """Extract sync metadata from frontmatter.

        Returns:
            (dm20_id, dm20_version, dm20_last_sync)
        """
        dm20_id = data.get("dm20_id", "")
        dm20_version = data.get("dm20_version", 0)
        dm20_last_sync = data.get("dm20_last_sync", "")
        return str(dm20_id), int(dm20_version), str(dm20_last_sync)
