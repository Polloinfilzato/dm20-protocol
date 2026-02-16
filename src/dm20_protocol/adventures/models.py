"""
Data models for D&D 5e adventure module integration.

Models for indexing, searching, and presenting adventures from the
5etools data source without revealing spoilers.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing import Any


class AdventureIndexEntry(BaseModel):
    """A single adventure from the 5etools adventure index.

    Maps from the 5etools adventures.json schema, flattening nested
    structures like level ranges into top-level fields.
    """

    id: str = Field(description="Short identifier (e.g. 'CoS', 'SCC-CK')")
    name: str = Field(description="Full adventure name")
    source: str = Field(description="Source book identifier")
    storyline: str = Field(default="", description="Campaign storyline category")
    level_start: int | None = Field(default=None, description="Starting level")
    level_end: int | None = Field(default=None, description="Ending level")
    group: str = Field(default="other", description="Navigation grouping")
    published: str = Field(default="", description="Publication date (ISO)")
    chapter_count: int = Field(default=0, description="Number of chapters")
    contents: list[dict[str, Any]] = Field(
        default_factory=list, description="Raw TOC structure"
    )

    @model_validator(mode="before")
    @classmethod
    def flatten_5etools_fields(cls, data: Any) -> Any:
        """Flatten nested 5etools JSON into flat model fields."""
        if not isinstance(data, dict):
            return data

        # Flatten level.start / level.end
        level = data.get("level")
        if isinstance(level, dict):
            if "level_start" not in data:
                data["level_start"] = level.get("start")
            if "level_end" not in data:
                data["level_end"] = level.get("end")

        # Derive chapter_count from contents
        contents = data.get("contents", [])
        if contents and "chapter_count" not in data:
            data["chapter_count"] = len(contents)

        return data

    @property
    def level_range(self) -> str:
        """Human-readable level range string."""
        if self.level_start and self.level_end:
            return f"{self.level_start}-{self.level_end}"
        if self.level_start:
            return f"{self.level_start}+"
        return "Any"


class StorylineGroup(BaseModel):
    """A group of adventures sharing the same storyline.

    Used for presenting multi-part adventure series together,
    sorted by level progression.
    """

    storyline: str = Field(description="Storyline name")
    adventures: list[AdventureIndexEntry] = Field(
        default_factory=list, description="Adventures in this storyline"
    )

    @property
    def is_multi_part(self) -> bool:
        """Whether this storyline contains multiple adventures."""
        return len(self.adventures) > 1

    @property
    def level_range(self) -> str:
        """Combined level range across all adventures in the group."""
        starts = [a.level_start for a in self.adventures if a.level_start]
        ends = [a.level_end for a in self.adventures if a.level_end]
        if starts and ends:
            return f"{min(starts)}-{max(ends)}"
        if starts:
            return f"{min(starts)}+"
        return "Any"


class AdventureSearchResult(BaseModel):
    """Result from an adventure search/discovery query.

    Contains grouped results with relevance information,
    formatted for spoiler-free presentation.
    """

    query: str = Field(default="", description="Original search query")
    total_matches: int = Field(default=0, description="Total matching adventures")
    groups: list[StorylineGroup] = Field(
        default_factory=list, description="Results grouped by storyline"
    )

    @property
    def storyline_count(self) -> int:
        """Number of distinct storylines in results."""
        return len(self.groups)


__all__ = [
    "AdventureIndexEntry",
    "AdventureSearchResult",
    "StorylineGroup",
]
