"""
Data models for the PDF Library System.

These dataclasses represent the core data structures for managing
PDF/Markdown rulebook sources in the library.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class SourceType(str, Enum):
    """Type of source file in the library."""
    PDF = "pdf"
    MARKDOWN = "markdown"


class ContentType(str, Enum):
    """Type of content that can be extracted from a source."""
    CLASS = "class"
    RACE = "race"
    SPELL = "spell"
    MONSTER = "monster"
    FEAT = "feat"
    ITEM = "item"
    BACKGROUND = "background"
    SUBCLASS = "subclass"
    UNKNOWN = "unknown"


@dataclass
class TOCEntry:
    """A single entry in a source's table of contents.

    Represents a chapter, section, or item that can be extracted
    from the source document.

    Attributes:
        title: Display name of the entry
        page: Page number where this entry starts (1-indexed)
        content_type: Type of content (class, race, spell, etc.)
        children: Nested TOC entries (for chapters with sub-sections)
        end_page: Optional page number where this entry ends
    """
    title: str
    page: int
    content_type: ContentType = ContentType.UNKNOWN
    children: list["TOCEntry"] = field(default_factory=list)
    end_page: int | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "title": self.title,
            "page": self.page,
            "type": self.content_type.value,
        }
        if self.end_page is not None:
            result["end_page"] = self.end_page
        if self.children:
            result["children"] = [child.to_dict() for child in self.children]
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "TOCEntry":
        """Create from dictionary."""
        children = [cls.from_dict(c) for c in data.get("children", [])]
        return cls(
            title=data["title"],
            page=data["page"],
            content_type=ContentType(data.get("type", "unknown")),
            children=children,
            end_page=data.get("end_page"),
        )


@dataclass
class ContentSummary:
    """Summary of content types available in a source.

    Provides a quick overview of what content has been indexed
    from a source document.

    Attributes:
        classes: Number of classes found
        races: Number of races found
        spells: Number of spells found
        monsters: Number of monsters found
        feats: Number of feats found
        items: Number of items found
        backgrounds: Number of backgrounds found
        subclasses: Number of subclasses found
    """
    classes: int = 0
    races: int = 0
    spells: int = 0
    monsters: int = 0
    feats: int = 0
    items: int = 0
    backgrounds: int = 0
    subclasses: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "classes": self.classes,
            "races": self.races,
            "spells": self.spells,
            "monsters": self.monsters,
            "feats": self.feats,
            "items": self.items,
            "backgrounds": self.backgrounds,
            "subclasses": self.subclasses,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContentSummary":
        """Create from dictionary."""
        return cls(
            classes=data.get("classes", 0),
            races=data.get("races", 0),
            spells=data.get("spells", 0),
            monsters=data.get("monsters", 0),
            feats=data.get("feats", 0),
            items=data.get("items", 0),
            backgrounds=data.get("backgrounds", 0),
            subclasses=data.get("subclasses", 0),
        )

    @property
    def total(self) -> int:
        """Total number of content items."""
        return (
            self.classes + self.races + self.spells + self.monsters +
            self.feats + self.items + self.backgrounds + self.subclasses
        )


@dataclass
class IndexEntry:
    """Index file data for a library source.

    Stored in dnd_data/library/index/{source_id}.index.json
    Contains TOC and metadata extracted from the source file.

    Attributes:
        source_id: Unique identifier (derived from filename)
        filename: Original filename of the source
        source_type: Type of source (PDF or Markdown)
        indexed_at: When the index was created/updated
        file_hash: SHA-256 hash for change detection
        total_pages: Total pages in document (PDF only)
        toc: Table of contents entries
        content_summary: Summary counts of content types
    """
    source_id: str
    filename: str
    source_type: SourceType
    indexed_at: datetime
    file_hash: str
    total_pages: int = 0
    toc: list[TOCEntry] = field(default_factory=list)
    content_summary: ContentSummary = field(default_factory=ContentSummary)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_id": self.source_id,
            "filename": self.filename,
            "source_type": self.source_type.value,
            "indexed_at": self.indexed_at.isoformat(),
            "file_hash": self.file_hash,
            "total_pages": self.total_pages,
            "toc": [entry.to_dict() for entry in self.toc],
            "content_summary": self.content_summary.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IndexEntry":
        """Create from dictionary."""
        toc = [TOCEntry.from_dict(t) for t in data.get("toc", [])]
        return cls(
            source_id=data["source_id"],
            filename=data["filename"],
            source_type=SourceType(data["source_type"]),
            indexed_at=datetime.fromisoformat(data["indexed_at"]),
            file_hash=data["file_hash"],
            total_pages=data.get("total_pages", 0),
            toc=toc,
            content_summary=ContentSummary.from_dict(data.get("content_summary", {})),
        )


@dataclass
class LibrarySource:
    """Represents a source in the library with its current state.

    Combines information about the source file and its index status.
    Used for listing and managing library sources.

    Attributes:
        source_id: Unique identifier
        filename: Original filename
        source_type: Type of source (PDF or Markdown)
        file_path: Full path to the source file
        is_indexed: Whether the source has been indexed
        index_entry: Index data if indexed, None otherwise
        file_size: Size of the source file in bytes
        last_modified: Last modification time of the source file
    """
    source_id: str
    filename: str
    source_type: SourceType
    file_path: Path
    is_indexed: bool = False
    index_entry: IndexEntry | None = None
    file_size: int = 0
    last_modified: datetime | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        result = {
            "source_id": self.source_id,
            "filename": self.filename,
            "source_type": self.source_type.value,
            "file_path": str(self.file_path),
            "is_indexed": self.is_indexed,
            "file_size": self.file_size,
        }
        if self.last_modified:
            result["last_modified"] = self.last_modified.isoformat()
        if self.index_entry:
            result["content_summary"] = self.index_entry.content_summary.to_dict()
            result["total_pages"] = self.index_entry.total_pages
        return result
