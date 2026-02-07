"""
Adventure module parser for extracting structure from PDF TOC.

Uses the existing library index system to parse adventure module PDFs
and extract structured information about chapters, NPCs, encounters,
and locations using pattern matching on TOC entries.
"""

import logging
import re
from pathlib import Path

from ..library.manager import LibraryManager
from ..library.models import TOCEntry
from .models.module import (
    ContentType,
    ModuleElement,
    NPCReference,
    EncounterReference,
    LocationReference,
    ModuleStructure,
)

logger = logging.getLogger("gamemaster-mcp")


class ModuleParser:
    """Parses adventure module PDFs into structured data.

    Uses the existing library index TOC extraction system to understand
    adventure module organization. Identifies chapters, encounters, NPCs,
    and locations from TOC entries using pattern matching.
    """

    # Regex patterns for detecting different content types
    NPC_PATTERNS = [
        r"\(NPC\)$",  # Explicit (NPC) suffix
    ]

    ENCOUNTER_PATTERNS = [
        r"^Encounter:",  # Explicit encounter prefix
        r"^Area\s+\d+",  # "Area 12"
        r"^Room\s+\d+",  # "Room 5"
        r"^[A-Z]\d+\.",  # "K1.", "E3."
        r"^Battle\s+of",  # "Battle of..."
        r"^Fight\s+at",  # "Fight at..."
    ]

    LOCATION_PATTERNS = [
        r"^Areas?\s+of",  # "Area of X", "Areas of X"
        r"^Map\s+of",  # "Map of X"
        r"^The\s+[A-Z][a-z]+\s+(Castle|Village|Town|Tavern|Temple|Dungeon)",  # Location names
    ]

    # Patterns for appendix detection
    APPENDIX_PATTERNS = [
        r"^Appendix",
        r"^Dramatis\s+Personae",
        r"^NPCs$",
    ]

    def __init__(self, library_path: str):
        """Initialize with path to the library directory.

        Args:
            library_path: Path to the library root directory
        """
        self.library_manager = LibraryManager(Path(library_path))
        logger.debug(f"ModuleParser initialized with library at {library_path}")

    def parse_module(self, source_id: str) -> ModuleStructure | None:
        """Parse a module from the library index.

        Loads the index for the given source_id and extracts
        structural information from its TOC.

        Args:
            source_id: The library source identifier

        Returns:
            ModuleStructure if successful, None if source not found or not indexed
        """
        # Load the index
        index = self.library_manager.get_index(source_id)
        if not index:
            logger.warning(f"No index found for source_id: {source_id}")
            return None

        logger.debug(f"Parsing module structure for {source_id}")

        # Extract structural components
        chapters = self.extract_chapters(index.toc)
        npcs = self.extract_npcs(index.toc)
        encounters = self.extract_encounters(index.toc)
        locations = self.extract_locations(index.toc)

        structure = ModuleStructure(
            module_id=source_id,
            title=index.filename.replace(".pdf", "").replace(".PDF", ""),
            source_file=index.filename,
            chapters=chapters,
            npcs=npcs,
            encounters=encounters,
            locations=locations,
        )

        logger.debug(
            f"Parsed module: {len(chapters)} chapters, "
            f"{len(npcs)} NPCs, {len(encounters)} encounters, "
            f"{len(locations)} locations"
        )

        return structure

    def extract_chapters(self, toc_entries: list[TOCEntry]) -> list[ModuleElement]:
        """Extract chapter hierarchy from TOC entries.

        Builds a tree of chapters -> sections -> subsections.
        Calculates page_end from next entry's page_start.

        Args:
            toc_entries: List of TOC entries from the library index

        Returns:
            Flat list of ModuleElement objects with parent-child relationships
        """
        elements: list[ModuleElement] = []

        def process_entries(
            entries: list[TOCEntry],
            parent_name: str | None = None,
            depth: int = 0
        ) -> None:
            for i, entry in enumerate(entries):
                # Determine content type - check appendix pattern first
                if self._matches_patterns(entry.title, self.APPENDIX_PATTERNS):
                    content_type = ContentType.APPENDIX
                elif depth == 0:
                    content_type = ContentType.CHAPTER
                else:
                    content_type = ContentType.SECTION

                # Calculate page_end from next sibling
                page_end = None
                if i + 1 < len(entries):
                    page_end = entries[i + 1].page - 1
                elif entry.end_page is not None:
                    page_end = entry.end_page

                # Create element
                element = ModuleElement(
                    name=entry.title,
                    content_type=content_type,
                    page_start=entry.page,
                    page_end=page_end,
                    parent=parent_name,
                    children=[child.title for child in entry.children],
                )
                elements.append(element)

                # Process children recursively
                if entry.children:
                    process_entries(entry.children, entry.title, depth + 1)

        process_entries(toc_entries)
        return elements

    def extract_npcs(self, toc_entries: list[TOCEntry]) -> list[NPCReference]:
        """Identify NPC entries in TOC.

        Patterns to detect:
        - Entries containing "(NPC)" suffix
        - Proper-cased names in encounter sections
        - "Appendix: NPCs" or "Dramatis Personae" sections

        Args:
            toc_entries: List of TOC entries from the library index

        Returns:
            List of NPCReference objects
        """
        npcs: list[NPCReference] = []
        chapter_stack: list[str] = []

        def process_entries(entries: list[TOCEntry], depth: int = 0) -> None:
            for entry in entries:
                # Track chapter context
                if depth == 0:
                    # Top-level entry - update chapter
                    if len(chapter_stack) == 0:
                        chapter_stack.append(entry.title)
                    else:
                        chapter_stack[0] = entry.title

                # Check if this entry looks like an NPC
                if self._matches_patterns(entry.title, self.NPC_PATTERNS):
                    # Extract NPC name (remove (NPC) suffix if present)
                    name = re.sub(r"\s*\(NPC\)\s*$", "", entry.title).strip()

                    current_chapter = chapter_stack[0] if chapter_stack else ""

                    npc = NPCReference(
                        name=name,
                        chapter=current_chapter,
                        page=entry.page,
                    )
                    npcs.append(npc)
                    logger.debug(f"Found NPC: {name} at page {entry.page}")

                # Process children
                if entry.children:
                    process_entries(entry.children, depth + 1)

        process_entries(toc_entries)
        return npcs

    def extract_encounters(self, toc_entries: list[TOCEntry]) -> list[EncounterReference]:
        """Identify encounter entries in TOC.

        Patterns to detect:
        - "Encounter:" prefix
        - Area numbers (K1., Area 12, Room 5)
        - "Battle of X", "Fight at Y"

        Args:
            toc_entries: List of TOC entries from the library index

        Returns:
            List of EncounterReference objects
        """
        encounters: list[EncounterReference] = []
        chapter_stack: list[str] = []
        location_stack: list[str] = []

        def process_entries(entries: list[TOCEntry], depth: int = 0) -> None:
            for entry in entries:
                # Track chapter context
                if depth == 0:
                    if len(chapter_stack) == 0:
                        chapter_stack.append(entry.title)
                    else:
                        chapter_stack[0] = entry.title

                # Update current location if this looks like a location
                if self._matches_patterns(entry.title, self.LOCATION_PATTERNS):
                    if len(location_stack) == 0:
                        location_stack.append(entry.title)
                    else:
                        location_stack[0] = entry.title

                # Check if this entry looks like an encounter
                if self._matches_patterns(entry.title, self.ENCOUNTER_PATTERNS):
                    # Determine encounter type
                    encounter_type = "combat"
                    if "social" in entry.title.lower():
                        encounter_type = "social"
                    elif "puzzle" in entry.title.lower():
                        encounter_type = "puzzle"
                    elif "exploration" in entry.title.lower():
                        encounter_type = "exploration"

                    current_chapter = chapter_stack[0] if chapter_stack else ""
                    current_location = location_stack[0] if location_stack else current_chapter

                    encounter = EncounterReference(
                        name=entry.title,
                        location=current_location,
                        chapter=current_chapter,
                        page=entry.page,
                        encounter_type=encounter_type,
                    )
                    encounters.append(encounter)
                    logger.debug(f"Found encounter: {entry.title} at page {entry.page}")

                # Process children
                if entry.children:
                    process_entries(entry.children, depth + 1)

        process_entries(toc_entries)
        return encounters

    def extract_locations(self, toc_entries: list[TOCEntry]) -> list[LocationReference]:
        """Identify location/area entries in TOC.

        Patterns to detect:
        - "Areas of X"
        - "Map of X"
        - Chapter titles that are location names
        - Numbered areas within location chapters

        Args:
            toc_entries: List of TOC entries from the library index

        Returns:
            List of LocationReference objects
        """
        locations: list[LocationReference] = []
        chapter_stack: list[str] = []

        def process_entries(
            entries: list[TOCEntry],
            parent_location: str | None = None,
            depth: int = 0
        ) -> None:
            for entry in entries:
                # Track chapter context
                if depth == 0:
                    if len(chapter_stack) == 0:
                        chapter_stack.append(entry.title)
                    else:
                        chapter_stack[0] = entry.title

                # Check if this entry looks like a location
                if self._matches_patterns(entry.title, self.LOCATION_PATTERNS):
                    current_chapter = chapter_stack[0] if chapter_stack else ""

                    location = LocationReference(
                        name=entry.title,
                        chapter=current_chapter,
                        page=entry.page,
                        parent_location=parent_location,
                        sub_locations=[child.title for child in entry.children],
                    )
                    locations.append(location)
                    logger.debug(f"Found location: {entry.title} at page {entry.page}")

                    # Process children with this location as parent
                    if entry.children:
                        process_entries(entry.children, entry.title, depth + 1)
                else:
                    # Process children without changing parent
                    if entry.children:
                        process_entries(entry.children, parent_location, depth + 1)

        process_entries(toc_entries)
        return locations

    def _matches_patterns(self, text: str, patterns: list[str]) -> bool:
        """Check if text matches any of the given regex patterns.

        Args:
            text: Text to check
            patterns: List of regex patterns

        Returns:
            True if any pattern matches
        """
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
