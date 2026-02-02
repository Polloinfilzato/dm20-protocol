"""
TOC Extractor for PDF files.

Extracts table of contents from PDF files using PyMuPDF.
Supports both PDF bookmarks and heading detection fallback.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF

from ..manager import compute_file_hash, generate_source_id
from ..models import (
    ContentSummary,
    ContentType,
    IndexEntry,
    SourceType,
    TOCEntry,
)

logger = logging.getLogger("gamemaster-mcp")


# Patterns for identifying D&D content types from titles
CONTENT_TYPE_PATTERNS: dict[ContentType, list[str]] = {
    ContentType.CLASS: ["class", "classes", "tactician", "artificer", "barbarian",
                        "bard", "cleric", "druid", "fighter", "monk", "paladin",
                        "ranger", "rogue", "sorcerer", "warlock", "wizard"],
    ContentType.SUBCLASS: ["subclass", "archetype", "tradition", "path of", "circle of",
                           "college of", "domain", "oath of", "way of", "school of",
                           "pact of", "patron", "origin", "grandmaster", "mentalist",
                           "scholar", "war mind", "mechanic", "plague doctor"],
    ContentType.RACE: ["race", "races", "lineage", "lineages", "species", "ancestry",
                       "dwarf", "elf", "halfling", "human", "dragonborn", "gnome",
                       "half-elf", "half-orc", "tiefling", "aasimar", "genasi"],
    ContentType.SPELL: ["spell", "spells", "magic", "cantrip", "cantrips"],
    ContentType.MONSTER: ["monster", "monsters", "creature", "creatures", "bestiary",
                          "stat block", "stat blocks"],
    ContentType.FEAT: ["feat", "feats"],
    ContentType.ITEM: ["item", "items", "equipment", "magic item", "magic items",
                       "weapon", "weapons", "armor", "armors", "wondrous"],
    ContentType.BACKGROUND: ["background", "backgrounds"],
}

# Minimum font sizes for heading detection
CHAPTER_FONT_SIZE = 20.0  # Main chapters
SECTION_FONT_SIZE = 14.0  # Sections within chapters
SUBSECTION_FONT_SIZE = 12.0  # Subsections


class TOCExtractor:
    """Extracts table of contents from PDF files.

    Attempts to extract TOC in this order:
    1. PDF bookmarks/outlines (most reliable)
    2. Heading detection based on font size (fallback)

    Attributes:
        pdf_path: Path to the PDF file
    """

    def __init__(self, pdf_path: Path):
        """Initialize the TOC extractor.

        Args:
            pdf_path: Path to the PDF file to extract from
        """
        self.pdf_path = Path(pdf_path)

    def extract(self) -> IndexEntry:
        """Extract TOC and create an index entry.

        Returns:
            IndexEntry containing the extracted TOC and metadata
        """
        logger.debug(f"📖 Extracting TOC from {self.pdf_path.name}")

        # Calculate file hash for change detection
        file_hash = compute_file_hash(self.pdf_path)

        # Open the PDF
        doc = fitz.open(self.pdf_path)
        try:
            total_pages = doc.page_count

            # Try to extract bookmarks first
            toc_entries = self._extract_bookmarks(doc)

            if not toc_entries:
                # Fall back to heading detection
                logger.debug("📖 No bookmarks found, using heading detection")
                toc_entries = self._detect_headings(doc)

            # Calculate content summary
            content_summary = self._calculate_content_summary(toc_entries)

            # Create index entry
            index_entry = IndexEntry(
                source_id=generate_source_id(self.pdf_path.name),
                filename=self.pdf_path.name,
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash=file_hash,
                total_pages=total_pages,
                toc=toc_entries,
                content_summary=content_summary,
            )

            logger.debug(f"📖 Extracted {len(toc_entries)} TOC entries, {content_summary.total} content items")
            return index_entry

        finally:
            doc.close()

    def _extract_bookmarks(self, doc: fitz.Document) -> list[TOCEntry]:
        """Extract TOC from PDF bookmarks/outlines.

        Args:
            doc: PyMuPDF document object

        Returns:
            List of TOCEntry objects (hierarchical)
        """
        raw_toc = doc.get_toc()  # Returns [(level, title, page), ...]

        if not raw_toc:
            return []

        # Convert flat list to hierarchical structure
        return self._build_toc_hierarchy(raw_toc)

    def _build_toc_hierarchy(self, raw_toc: list[tuple[int, str, int]]) -> list[TOCEntry]:
        """Build hierarchical TOC from flat bookmark list.

        Args:
            raw_toc: List of (level, title, page) tuples

        Returns:
            Hierarchical list of TOCEntry objects
        """
        if not raw_toc:
            return []

        root_entries: list[TOCEntry] = []
        stack: list[tuple[int, TOCEntry]] = []  # (level, entry)

        for level, title, page in raw_toc:
            content_type = self._identify_content_type(title)
            entry = TOCEntry(
                title=title.strip(),
                page=page,
                content_type=content_type,
            )

            # Find the right parent based on level
            while stack and stack[-1][0] >= level:
                stack.pop()

            if stack:
                # Add as child of the last entry with lower level
                stack[-1][1].children.append(entry)
            else:
                # Top-level entry
                root_entries.append(entry)

            stack.append((level, entry))

        return root_entries

    def _detect_headings(self, doc: fitz.Document) -> list[TOCEntry]:
        """Detect headings when no bookmarks exist.

        Uses a hybrid approach:
        1. Font-size based heading detection
        2. D&D keyword-based content detection (for problematic PDFs)

        Args:
            doc: PyMuPDF document object

        Returns:
            List of TOCEntry objects
        """
        # Try font-based detection first
        entries = self._detect_headings_by_font(doc)

        # If we got very few meaningful entries, try keyword-based detection
        meaningful_entries = [e for e in entries if e.content_type != ContentType.UNKNOWN]
        if len(meaningful_entries) < 3:
            logger.debug("📖 Font detection yielded few results, trying keyword detection")
            keyword_entries = self._detect_dnd_content_by_keywords(doc)
            if len(keyword_entries) > len(meaningful_entries):
                entries = keyword_entries

        return entries

    def _detect_headings_by_font(self, doc: fitz.Document) -> list[TOCEntry]:
        """Detect headings from font sizes.

        Args:
            doc: PyMuPDF document object

        Returns:
            List of TOCEntry objects
        """
        entries: list[TOCEntry] = []
        current_chapter: TOCEntry | None = None

        for page_num in range(doc.page_count):
            page = doc[page_num]
            headings = self._extract_page_headings(page, page_num + 1)

            for heading in headings:
                if heading["level"] == 1:
                    # New chapter
                    if current_chapter:
                        entries.append(current_chapter)
                    current_chapter = TOCEntry(
                        title=heading["title"],
                        page=heading["page"],
                        content_type=self._identify_content_type(heading["title"]),
                    )
                elif heading["level"] == 2 and current_chapter:
                    # Section under current chapter
                    current_chapter.children.append(TOCEntry(
                        title=heading["title"],
                        page=heading["page"],
                        content_type=self._identify_content_type(heading["title"]),
                    ))
                elif heading["level"] == 2:
                    # Section without chapter parent
                    entries.append(TOCEntry(
                        title=heading["title"],
                        page=heading["page"],
                        content_type=self._identify_content_type(heading["title"]),
                    ))

        # Don't forget the last chapter
        if current_chapter:
            entries.append(current_chapter)

        return entries

    def _detect_dnd_content_by_keywords(self, doc: fitz.Document) -> list[TOCEntry]:
        """Detect D&D content by searching for known keywords.

        This is a fallback for PDFs with problematic fonts where
        heading detection doesn't work well.

        Args:
            doc: PyMuPDF document object

        Returns:
            List of TOCEntry objects for detected content
        """
        # Skip first pages (usually TOC, credits, intro)
        START_PAGE = 5  # Start searching from page 6 (0-indexed: 5)

        # Known D&D class names (these start class sections)
        dnd_classes = [
            "tactician", "artificer", "barbarian", "bard", "cleric",
            "druid", "fighter", "monk", "paladin", "ranger", "rogue",
            "sorcerer", "warlock", "wizard", "blood hunter"
        ]

        # Track which classes we've found (first occurrence after TOC = section start)
        found_classes: dict[str, int] = {}

        for page_num in range(START_PAGE, doc.page_count):
            page = doc[page_num]
            text = page.get_text().lower()

            for class_name in dnd_classes:
                if class_name in text and class_name not in found_classes:
                    # First occurrence of this class after TOC
                    found_classes[class_name] = page_num + 1

        # Create entries for found classes (sorted by page)
        entries: list[TOCEntry] = []
        for class_name, page in sorted(found_classes.items(), key=lambda x: x[1]):
            entries.append(TOCEntry(
                title=class_name.title(),
                page=page,
                content_type=ContentType.CLASS,
            ))

        # If we found classes, wrap them in a "Player Options" chapter
        if entries:
            player_options = TOCEntry(
                title="Player Options",
                page=entries[0].page,
                content_type=ContentType.UNKNOWN,
                children=entries,
            )
            return [player_options]

        return entries

    def _extract_page_headings(self, page: fitz.Page, page_num: int) -> list[dict]:
        """Extract potential headings from a page based on font size.

        Args:
            page: PyMuPDF page object
            page_num: 1-indexed page number

        Returns:
            List of heading dicts with title, page, and level
        """
        headings: list[dict] = []
        seen_titles: set[str] = set()

        try:
            blocks = page.get_text("dict")["blocks"]
        except Exception:
            return []

        for block in blocks:
            if "lines" not in block:
                continue

            for line in block["lines"]:
                # Collect text and max font size from the line
                line_text = ""
                max_font_size = 0.0

                for span in line["spans"]:
                    text = span["text"].strip()
                    if text:
                        line_text += text + " "
                        max_font_size = max(max_font_size, span["size"])

                line_text = line_text.strip()

                # Skip empty, too short, or already seen
                if not line_text or len(line_text) < 3:
                    continue
                if line_text in seen_titles:
                    continue

                # Skip lines that look like page numbers or metadata
                if self._is_noise(line_text):
                    continue

                # Determine heading level based on font size
                level = None
                if max_font_size >= CHAPTER_FONT_SIZE:
                    level = 1
                elif max_font_size >= SECTION_FONT_SIZE:
                    level = 2

                if level:
                    # Clean up the title
                    clean_title = self._clean_title(line_text)
                    if clean_title and len(clean_title) >= 3:
                        headings.append({
                            "title": clean_title,
                            "page": page_num,
                            "level": level,
                        })
                        seen_titles.add(line_text)

        return headings

    def _is_noise(self, text: str) -> bool:
        """Check if text is noise (page numbers, headers, etc.).

        Args:
            text: Text to check

        Returns:
            True if the text should be ignored
        """
        # Pure numbers
        if text.isdigit():
            return True

        # Very short non-word text
        if len(text) <= 2:
            return True

        # Common header/footer patterns
        noise_patterns = [
            r"^page\s*\d+$",
            r"^\d+$",
            r"^chapter\s*\d+\s*\|",  # Running headers like "CHAPTER 1 | PLAYER OPTIONS"
            r"^[•·\-–—]\s*$",  # Bullet points
        ]

        text_lower = text.lower()
        for pattern in noise_patterns:
            if re.match(pattern, text_lower):
                return True

        return False

    def _clean_title(self, title: str) -> str:
        """Clean up a title string.

        Args:
            title: Raw title string

        Returns:
            Cleaned title
        """
        # Remove excessive whitespace
        title = " ".join(title.split())

        # Remove trailing dots (from TOC entries like "Chapter 1 . . . . 5")
        title = re.sub(r"[\s.]+$", "", title)

        # Remove page number suffix
        title = re.sub(r"\s+\d+$", "", title)

        return title.strip()

    def _identify_content_type(self, title: str) -> ContentType:
        """Identify the D&D content type from a title.

        Args:
            title: The section/chapter title

        Returns:
            ContentType enum value, defaults to UNKNOWN
        """
        title_lower = title.lower()

        # Check for multi-word patterns first (more specific)
        # This ensures "magic items" matches ITEM, not SPELL
        specific_patterns = [
            ("magic item", ContentType.ITEM),
            ("stat block", ContentType.MONSTER),
            ("path of", ContentType.SUBCLASS),
            ("circle of", ContentType.SUBCLASS),
            ("college of", ContentType.SUBCLASS),
            ("oath of", ContentType.SUBCLASS),
            ("way of", ContentType.SUBCLASS),
            ("school of", ContentType.SUBCLASS),
        ]

        for pattern, content_type in specific_patterns:
            if pattern in title_lower:
                return content_type

        # Then check general patterns
        for content_type, patterns in CONTENT_TYPE_PATTERNS.items():
            for pattern in patterns:
                if pattern in title_lower:
                    return content_type

        return ContentType.UNKNOWN

    def _calculate_content_summary(self, entries: list[TOCEntry]) -> ContentSummary:
        """Calculate summary of content types from TOC entries.

        Args:
            entries: List of TOCEntry objects (hierarchical)

        Returns:
            ContentSummary with counts per content type
        """
        counts: dict[ContentType, int] = {ct: 0 for ct in ContentType}

        def count_entries(entries: list[TOCEntry]) -> None:
            for entry in entries:
                if entry.content_type != ContentType.UNKNOWN:
                    counts[entry.content_type] += 1
                count_entries(entry.children)

        count_entries(entries)

        return ContentSummary(
            classes=counts[ContentType.CLASS],
            races=counts[ContentType.RACE],
            spells=counts[ContentType.SPELL],
            monsters=counts[ContentType.MONSTER],
            feats=counts[ContentType.FEAT],
            items=counts[ContentType.ITEM],
            backgrounds=counts[ContentType.BACKGROUND],
            subclasses=counts[ContentType.SUBCLASS],
        )
