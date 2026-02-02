"""
Content Extractor for PDF and Markdown library.

Extracts full content from PDF pages and Markdown sections,
converting it to CustomSource JSON format.
Supports extraction of classes, races, spells, monsters, feats, and items.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import fitz  # PyMuPDF

from ..manager import LibraryManager
from ..models import ContentType, TOCEntry

logger = logging.getLogger("gamemaster-mcp")


# =============================================================================
# Regex Patterns for D&D Content Parsing
# =============================================================================

CLASS_PATTERNS = {
    "hit_die": r"Hit Dice?:\s*(?:1)?d?(\d+)",
    "hit_die_alt": r"Hit Die:\s*d(\d+)",
    "primary_ability": r"Primary Abilit(?:y|ies):\s*(.+?)(?:\n|$)",
    "saving_throws": r"Saving Throws?:\s*(.+?)(?:\n|$)",
    "saving_throws_alt": r"Saves?:\s*(.+?)(?:\n|$)",
    "armor_proficiency": r"Armor(?:\s+Proficienc(?:y|ies))?:\s*(.+?)(?:\n|$)",
    "weapon_proficiency": r"Weapons?(?:\s+Proficienc(?:y|ies))?:\s*(.+?)(?:\n|$)",
    "tool_proficiency": r"Tools?(?:\s+Proficienc(?:y|ies))?:\s*(.+?)(?:\n|$)",
    "skills": r"Skills?:\s*(.+?)(?:\n|$)",
    "level_feature": r"(?:At\s+)?(\d+)(?:st|nd|rd|th)\s+[Ll]evel[,:]?\s*(.+?)(?:\.|$)",
    "subclass_level": r"(?:At\s+)?(\d+)(?:st|nd|rd|th)\s+level,?\s+(?:you\s+)?(?:choose|gain|select)\s+(?:a\s+|an\s+|your\s+)?(?:archetype|subclass|path|tradition|college|domain|oath|way|school|patron|origin|circle|primal path)",
}

RACE_PATTERNS = {
    "ability_score": r"Ability Score Increase\.?\s*(.+?)(?:\n\n|\n[A-Z]|$)",
    "ability_score_alt": r"Ability Scores?\.?\s*(.+?)(?:\n\n|\n[A-Z]|$)",
    "size": r"Size\.?\s*(Tiny|Small|Medium|Large|Huge|Gargantuan)",
    "size_desc": r"Size\.?\s*.+?(?:are\s+)?(Small|Medium|Large)",
    "speed": r"Speed\.?\s*(?:Your\s+(?:base\s+)?(?:walking\s+)?speed\s+is\s+)?(\d+)\s*(?:feet|ft)",
    "speed_alt": r"(?:base|walking)\s+speed\s+(?:is\s+|of\s+)?(\d+)",
    "age": r"Age\.?\s*(.+?)(?:\n\n|\n[A-Z]|$)",
    "alignment": r"Alignment\.?\s*(.+?)(?:\n\n|\n[A-Z]|$)",
    "darkvision": r"Darkvision\.?\s*(.+?)(?:\n\n|\n[A-Z]|$)",
    "languages": r"Languages?\.?\s*(.+?)(?:\n\n|\n[A-Z]|$)",
    "trait": r"([A-Z][a-zA-Z\s']+)\.[\s\n]+(.+?)(?=\n[A-Z][a-zA-Z\s']+\.|$)",
}

SPELL_PATTERNS = {
    "level_school": r"(\d+)(?:st|nd|rd|th)?[- ]level\s+(\w+)",
    "cantrip": r"(\w+)\s+cantrip",
    "casting_time": r"Casting Time:\s*(.+?)(?:\n|$)",
    "range": r"Range:\s*(.+?)(?:\n|$)",
    "components": r"Components?:\s*(.+?)(?:\n|$)",
    "duration": r"Duration:\s*(.+?)(?:\n|$)",
    "classes": r"Classes?:\s*(.+?)(?:\n|$)",
    "higher_level": r"At Higher Levels?\.?\s*(.+?)(?:\n\n|$)",
}

MONSTER_PATTERNS = {
    "size_type_alignment": r"(Tiny|Small|Medium|Large|Huge|Gargantuan)\s+(\w+)(?:\s*\(([^)]+)\))?,?\s*(.+?)(?:\n|$)",
    "armor_class": r"Armor Class\s+(\d+)(?:\s*\(([^)]+)\))?",
    "hit_points": r"Hit Points\s+(\d+)\s*\(([^)]+)\)",
    "speed": r"Speed\s+(.+?)(?:\n|$)",
    "str": r"STR\s+(\d+)\s*\(([+-]?\d+)\)",
    "dex": r"DEX\s+(\d+)\s*\(([+-]?\d+)\)",
    "con": r"CON\s+(\d+)\s*\(([+-]?\d+)\)",
    "int": r"INT\s+(\d+)\s*\(([+-]?\d+)\)",
    "wis": r"WIS\s+(\d+)\s*\(([+-]?\d+)\)",
    "cha": r"CHA\s+(\d+)\s*\(([+-]?\d+)\)",
    "challenge": r"Challenge\s+(\d+(?:/\d+)?)\s*\(([^)]+)\s*XP\)",
    "senses": r"Senses?\s+(.+?)(?:\n|$)",
    "languages": r"Languages?\s+(.+?)(?:\n|$)",
}

FEAT_PATTERNS = {
    "prerequisite": r"Prerequisite:?\s*(.+?)(?:\n|$)",
    "bullet": r"[•\-\*]\s*(.+?)(?:\n|$)",
}

ITEM_PATTERNS = {
    "rarity": r"(common|uncommon|rare|very rare|legendary|artifact)",
    "type": r"(Wondrous item|Weapon|Armor|Ring|Rod|Staff|Wand|Potion|Scroll)",
    "attunement": r"requires attunement(?:\s+by\s+(.+?))?(?:\)|,|$)",
    "charges": r"(\d+)\s+charges",
    "weight": r"Weight:\s*(\d+(?:\.\d+)?)\s*(?:lb|lbs?|pound)",
}


@dataclass
class ExtractedContent:
    """Container for extracted content data."""
    name: str
    content_type: ContentType
    source_id: str
    page_start: int
    page_end: int | None = None
    raw_text: str = ""
    parsed_data: dict[str, Any] = field(default_factory=dict)
    extraction_timestamp: datetime = field(default_factory=datetime.now)
    confidence: float = 1.0  # Confidence score for extraction quality


class ContentExtractor:
    """
    Extracts content from PDF pages and converts to CustomSource JSON format.

    Supports extraction of:
    - Classes (hit die, abilities, saving throws, proficiencies, level features, subclasses)
    - Races (ability scores, size, speed, traits, subraces)
    - Spells (level, school, components, range, duration)
    - Monsters (stats, abilities, actions)
    - Feats (prerequisites, effects)
    - Items (properties, rarity)

    Usage:
        extractor = ContentExtractor(library_manager)
        result = extractor.extract("tome-of-heroes", "Fighter", "class")
        # result contains the extracted content in CustomSource format
    """

    def __init__(self, library_manager: LibraryManager):
        """
        Initialize the content extractor.

        Args:
            library_manager: The library manager instance for accessing source files
        """
        self.library_manager = library_manager

    def extract(
        self,
        source_id: str,
        content_name: str,
        content_type: Literal["class", "race", "spell", "monster", "feat", "item"],
    ) -> ExtractedContent | None:
        """
        Extract content from a PDF source.

        Args:
            source_id: The source identifier (e.g., "tome-of-heroes")
            content_name: Name of the content to extract (e.g., "Fighter")
            content_type: Type of content to extract

        Returns:
            ExtractedContent with parsed data, or None if not found
        """
        logger.debug(f"Extracting {content_type} '{content_name}' from {source_id}")

        # Get source info
        source = self.library_manager.get_source(source_id)
        if not source:
            logger.warning(f"Source not found: {source_id}")
            return None

        if not source.is_indexed:
            logger.warning(f"Source not indexed: {source_id}")
            return None

        # Find the content in the TOC
        toc_entry = self._find_toc_entry(source_id, content_name, content_type)
        if not toc_entry:
            logger.warning(f"Content not found in TOC: {content_name}")
            return None

        # Determine page range
        page_start = toc_entry.page
        page_end = toc_entry.end_page or self._estimate_end_page(source_id, toc_entry)

        # Extract text from pages
        raw_text = self._extract_text_from_pages(source.file_path, page_start, page_end)
        if not raw_text:
            logger.warning(f"No text extracted from pages {page_start}-{page_end}")
            return None

        # Parse the content based on type
        content_type_enum = ContentType(content_type)
        parsed_data = self._parse_content(raw_text, content_type_enum, content_name)

        # Create result
        result = ExtractedContent(
            name=content_name,
            content_type=content_type_enum,
            source_id=source_id,
            page_start=page_start,
            page_end=page_end,
            raw_text=raw_text,
            parsed_data=parsed_data,
        )

        return result

    def extract_to_json(
        self,
        source_id: str,
        content_name: str,
        content_type: Literal["class", "race", "spell", "monster", "feat", "item"],
    ) -> dict[str, Any] | None:
        """
        Extract content and return as CustomSource-compatible JSON.

        Args:
            source_id: The source identifier
            content_name: Name of the content to extract
            content_type: Type of content to extract

        Returns:
            Dictionary in CustomSource JSON format, or None if extraction failed
        """
        extracted = self.extract(source_id, content_name, content_type)
        if not extracted:
            return None

        return self._to_custom_source_format(extracted)

    def save_extracted_content(
        self,
        source_id: str,
        content_name: str,
        content_type: Literal["class", "race", "spell", "monster", "feat", "item"],
    ) -> Path | None:
        """
        Extract content and save to the library's extracted directory.

        Args:
            source_id: The source identifier
            content_name: Name of the content to extract
            content_type: Type of content to extract

        Returns:
            Path to the saved JSON file, or None if extraction failed
        """
        json_data = self.extract_to_json(source_id, content_name, content_type)
        if not json_data:
            return None

        # Ensure extracted directory exists
        extracted_dir = self.library_manager.extracted_dir / source_id
        extracted_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        index = content_name.lower().replace(" ", "-").replace("'", "")
        filename = f"{content_type}-{index}.json"
        output_path = extracted_dir / filename

        # Save JSON
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, default=str)

        logger.info(f"Saved extracted content to {output_path}")
        return output_path

    def _find_toc_entry(
        self,
        source_id: str,
        content_name: str,
        content_type: str,
    ) -> TOCEntry | None:
        """Find a TOC entry matching the content name and type."""
        index = self.library_manager.get_index(source_id)
        if not index:
            return None

        name_lower = content_name.lower()

        def search_entries(entries: list[TOCEntry]) -> TOCEntry | None:
            for entry in entries:
                # Check if title matches
                if entry.title.lower() == name_lower:
                    return entry
                # Also check for partial matches
                if name_lower in entry.title.lower():
                    # Verify content type matches
                    if entry.content_type.value == content_type or entry.content_type == ContentType.UNKNOWN:
                        return entry
                # Search children
                result = search_entries(entry.children)
                if result:
                    return result
            return None

        return search_entries(index.toc)

    def _estimate_end_page(self, source_id: str, current_entry: TOCEntry) -> int | None:
        """Estimate the end page based on the next TOC entry."""
        index = self.library_manager.get_index(source_id)
        if not index:
            return None

        # Flatten TOC to find next entry
        flat_entries = self.library_manager._flatten_toc(index.toc)

        # Find current entry position
        for i, entry in enumerate(flat_entries):
            if entry.title == current_entry.title and entry.page == current_entry.page:
                # Found current entry, get next entry's page
                if i + 1 < len(flat_entries):
                    next_page = flat_entries[i + 1].page
                    # End page is one before next entry starts
                    return next_page - 1 if next_page > current_entry.page else next_page
                break

        # No next entry found, use a reasonable limit (10 pages max)
        return min(current_entry.page + 10, index.total_pages)

    def _extract_text_from_pages(
        self,
        pdf_path: Path,
        page_start: int,
        page_end: int | None,
    ) -> str:
        """Extract text from a range of PDF pages."""
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            logger.error(f"Failed to open PDF: {e}")
            return ""

        try:
            # Convert to 0-indexed
            start_idx = page_start - 1
            end_idx = (page_end or page_start) - 1

            # Clamp to valid range
            start_idx = max(0, min(start_idx, doc.page_count - 1))
            end_idx = max(start_idx, min(end_idx, doc.page_count - 1))

            text_parts = []
            for page_num in range(start_idx, end_idx + 1):
                page = doc[page_num]
                text = page.get_text()
                text_parts.append(text)

            return "\n\n".join(text_parts)
        finally:
            doc.close()

    def _parse_content(
        self,
        raw_text: str,
        content_type: ContentType,
        content_name: str,
    ) -> dict[str, Any]:
        """Parse raw text into structured data based on content type."""
        parsers = {
            ContentType.CLASS: self._parse_class,
            ContentType.RACE: self._parse_race,
            ContentType.SPELL: self._parse_spell,
            ContentType.MONSTER: self._parse_monster,
            ContentType.FEAT: self._parse_feat,
            ContentType.ITEM: self._parse_item,
        }

        parser = parsers.get(content_type, self._parse_generic)
        return parser(raw_text, content_name)

    def _parse_class(self, raw_text: str, name: str) -> dict[str, Any]:
        """Parse class content from raw text."""
        data: dict[str, Any] = {
            "index": name.lower().replace(" ", "-"),
            "name": name,
            "hit_die": 8,  # Default
            "proficiencies": [],
            "saving_throws": [],
            "class_levels": {},
            "subclasses": [],
            "desc": [],
        }

        # Extract hit die
        for pattern_key in ["hit_die", "hit_die_alt"]:
            match = re.search(CLASS_PATTERNS[pattern_key], raw_text, re.IGNORECASE)
            if match:
                data["hit_die"] = int(match.group(1))
                break

        # Extract saving throws
        for pattern_key in ["saving_throws", "saving_throws_alt"]:
            match = re.search(CLASS_PATTERNS[pattern_key], raw_text, re.IGNORECASE)
            if match:
                saves_text = match.group(1)
                # Parse ability names (STR, DEX, CON, INT, WIS, CHA)
                abilities = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
                ability_names = {
                    "strength": "STR", "dexterity": "DEX", "constitution": "CON",
                    "intelligence": "INT", "wisdom": "WIS", "charisma": "CHA",
                }
                found_saves = []
                saves_lower = saves_text.lower()
                for full_name, abbrev in ability_names.items():
                    if full_name in saves_lower or abbrev.lower() in saves_lower:
                        found_saves.append(abbrev)
                if found_saves:
                    data["saving_throws"] = found_saves
                break

        # Extract proficiencies
        for prof_type in ["armor_proficiency", "weapon_proficiency", "tool_proficiency"]:
            match = re.search(CLASS_PATTERNS[prof_type], raw_text, re.IGNORECASE)
            if match:
                profs = match.group(1).strip()
                if profs.lower() not in ["none", "—", "-"]:
                    data["proficiencies"].append(profs)

        # Extract skills
        match = re.search(CLASS_PATTERNS["skills"], raw_text, re.IGNORECASE)
        if match:
            data["skill_choices"] = match.group(1).strip()

        # Extract level features
        level_features: dict[int, list[str]] = {}
        for match in re.finditer(CLASS_PATTERNS["level_feature"], raw_text, re.IGNORECASE):
            level = int(match.group(1))
            feature = match.group(2).strip()
            if level not in level_features:
                level_features[level] = []
            level_features[level].append(feature)

        # Convert to class_levels format
        for level, features in level_features.items():
            data["class_levels"][level] = {
                "level": level,
                "proficiency_bonus": self._proficiency_bonus_for_level(level),
                "features": features,
            }

        # Try to find subclass level
        match = re.search(CLASS_PATTERNS["subclass_level"], raw_text, re.IGNORECASE)
        if match:
            data["subclass_level"] = int(match.group(1))
        else:
            data["subclass_level"] = 3  # Default for most classes

        # Extract description (first paragraph that looks like description)
        desc_match = re.search(
            rf"{re.escape(name)}[\s\n]+([A-Z][^.]+\.(?:[^.]+\.)*)",
            raw_text,
            re.IGNORECASE
        )
        if desc_match:
            data["desc"] = [desc_match.group(1).strip()]

        return data

    def _parse_race(self, raw_text: str, name: str) -> dict[str, Any]:
        """Parse race content from raw text."""
        data: dict[str, Any] = {
            "index": name.lower().replace(" ", "-"),
            "name": name,
            "speed": 30,  # Default
            "size": "Medium",  # Default
            "ability_bonuses": [],
            "traits": [],
            "languages": [],
            "subraces": [],
            "desc": [],
        }

        # Extract ability score increases
        for pattern_key in ["ability_score", "ability_score_alt"]:
            match = re.search(RACE_PATTERNS[pattern_key], raw_text, re.IGNORECASE | re.DOTALL)
            if match:
                ability_text = match.group(1)
                data["ability_bonuses"] = self._parse_ability_bonuses(ability_text)
                break

        # Extract size
        for pattern_key in ["size", "size_desc"]:
            match = re.search(RACE_PATTERNS[pattern_key], raw_text, re.IGNORECASE)
            if match:
                data["size"] = match.group(1).capitalize()
                break

        # Extract speed
        for pattern_key in ["speed", "speed_alt"]:
            match = re.search(RACE_PATTERNS[pattern_key], raw_text, re.IGNORECASE)
            if match:
                data["speed"] = int(match.group(1))
                break

        # Extract age
        match = re.search(RACE_PATTERNS["age"], raw_text, re.IGNORECASE | re.DOTALL)
        if match:
            data["age"] = match.group(1).strip()

        # Extract alignment
        match = re.search(RACE_PATTERNS["alignment"], raw_text, re.IGNORECASE | re.DOTALL)
        if match:
            data["alignment"] = match.group(1).strip()

        # Extract darkvision
        match = re.search(RACE_PATTERNS["darkvision"], raw_text, re.IGNORECASE | re.DOTALL)
        if match:
            data["traits"].append({
                "index": "darkvision",
                "name": "Darkvision",
                "desc": [match.group(1).strip()],
            })

        # Extract languages
        match = re.search(RACE_PATTERNS["languages"], raw_text, re.IGNORECASE | re.DOTALL)
        if match:
            lang_text = match.group(1).strip()
            # Parse common language names
            common_languages = [
                "Common", "Dwarvish", "Elvish", "Giant", "Gnomish", "Goblin",
                "Halfling", "Orc", "Abyssal", "Celestial", "Draconic", "Deep Speech",
                "Infernal", "Primordial", "Sylvan", "Undercommon"
            ]
            for lang in common_languages:
                if lang.lower() in lang_text.lower():
                    data["languages"].append(lang)

        # Extract other traits
        for match in re.finditer(RACE_PATTERNS["trait"], raw_text, re.DOTALL):
            trait_name = match.group(1).strip()
            trait_desc = match.group(2).strip()

            # Skip if this is a standard section header
            skip_headers = ["age", "alignment", "size", "speed", "languages", "ability score"]
            if any(header in trait_name.lower() for header in skip_headers):
                continue

            data["traits"].append({
                "index": trait_name.lower().replace(" ", "-").replace("'", ""),
                "name": trait_name,
                "desc": [trait_desc],
            })

        return data

    def _parse_spell(self, raw_text: str, name: str) -> dict[str, Any]:
        """Parse spell content from raw text."""
        data: dict[str, Any] = {
            "index": name.lower().replace(" ", "-"),
            "name": name,
            "level": 1,  # Default
            "school": "Evocation",  # Default
            "casting_time": "1 action",
            "range": "Self",
            "duration": "Instantaneous",
            "components": ["V"],
            "desc": [],
            "classes": [],
        }

        # Extract level and school
        match = re.search(SPELL_PATTERNS["level_school"], raw_text, re.IGNORECASE)
        if match:
            data["level"] = int(match.group(1))
            data["school"] = match.group(2).capitalize()
        else:
            # Check for cantrip
            match = re.search(SPELL_PATTERNS["cantrip"], raw_text, re.IGNORECASE)
            if match:
                data["level"] = 0
                data["school"] = match.group(1).capitalize()

        # Extract casting time
        match = re.search(SPELL_PATTERNS["casting_time"], raw_text, re.IGNORECASE)
        if match:
            data["casting_time"] = match.group(1).strip()

        # Extract range
        match = re.search(SPELL_PATTERNS["range"], raw_text, re.IGNORECASE)
        if match:
            data["range"] = match.group(1).strip()

        # Extract components
        match = re.search(SPELL_PATTERNS["components"], raw_text, re.IGNORECASE)
        if match:
            comp_text = match.group(1)
            components = []
            if "V" in comp_text.upper() or "verbal" in comp_text.lower():
                components.append("V")
            if "S" in comp_text.upper() or "somatic" in comp_text.lower():
                components.append("S")
            if "M" in comp_text.upper() or "material" in comp_text.lower():
                components.append("M")
                # Try to extract material component description
                material_match = re.search(r"\(([^)]+)\)", comp_text)
                if material_match:
                    data["material"] = material_match.group(1)
            data["components"] = components if components else ["V"]

        # Extract duration
        match = re.search(SPELL_PATTERNS["duration"], raw_text, re.IGNORECASE)
        if match:
            duration_text = match.group(1).strip()
            data["duration"] = duration_text
            data["concentration"] = "concentration" in duration_text.lower()

        # Extract classes
        match = re.search(SPELL_PATTERNS["classes"], raw_text, re.IGNORECASE)
        if match:
            classes_text = match.group(1)
            class_names = ["bard", "cleric", "druid", "paladin", "ranger", "sorcerer", "warlock", "wizard"]
            for class_name in class_names:
                if class_name in classes_text.lower():
                    data["classes"].append(class_name.capitalize())

        # Extract higher level
        match = re.search(SPELL_PATTERNS["higher_level"], raw_text, re.IGNORECASE | re.DOTALL)
        if match:
            data["higher_level"] = [match.group(1).strip()]

        # Extract description (main spell text)
        # Look for text after the stat block but before "At Higher Levels"
        lines = raw_text.split("\n")
        in_description = False
        desc_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Check if we've passed the stat block
            if any(x in line for x in ["Casting Time:", "Range:", "Components:", "Duration:"]):
                in_description = True
                continue
            if in_description:
                if "At Higher Levels" in line:
                    break
                desc_lines.append(line)

        if desc_lines:
            data["desc"] = [" ".join(desc_lines)]

        return data

    def _parse_monster(self, raw_text: str, name: str) -> dict[str, Any]:
        """Parse monster content from raw text."""
        data: dict[str, Any] = {
            "index": name.lower().replace(" ", "-"),
            "name": name,
            "size": "Medium",
            "type": "humanoid",
            "alignment": "neutral",
            "armor_class": [{"type": "natural", "value": 10}],
            "hit_points": 10,
            "hit_dice": "2d8",
            "speed": {"walk": "30 ft."},
            "strength": 10,
            "dexterity": 10,
            "constitution": 10,
            "intelligence": 10,
            "wisdom": 10,
            "charisma": 10,
            "challenge_rating": 0,
            "xp": 0,
            "actions": [],
            "special_abilities": [],
        }

        # Extract size, type, and alignment
        match = re.search(MONSTER_PATTERNS["size_type_alignment"], raw_text, re.IGNORECASE)
        if match:
            data["size"] = match.group(1).capitalize()
            data["type"] = match.group(2).lower()
            if match.group(3):
                data["subtype"] = match.group(3)
            if match.group(4):
                data["alignment"] = match.group(4).strip()

        # Extract armor class
        match = re.search(MONSTER_PATTERNS["armor_class"], raw_text, re.IGNORECASE)
        if match:
            ac_value = int(match.group(1))
            ac_type = match.group(2) if match.group(2) else "natural"
            data["armor_class"] = [{"type": ac_type, "value": ac_value}]

        # Extract hit points
        match = re.search(MONSTER_PATTERNS["hit_points"], raw_text, re.IGNORECASE)
        if match:
            data["hit_points"] = int(match.group(1))
            data["hit_dice"] = match.group(2)

        # Extract speed
        match = re.search(MONSTER_PATTERNS["speed"], raw_text, re.IGNORECASE)
        if match:
            speed_text = match.group(1)
            data["speed"] = self._parse_speed(speed_text)

        # Extract ability scores
        for ability in ["str", "dex", "con", "int", "wis", "cha"]:
            match = re.search(MONSTER_PATTERNS[ability], raw_text, re.IGNORECASE)
            if match:
                ability_map = {"str": "strength", "dex": "dexterity", "con": "constitution",
                              "int": "intelligence", "wis": "wisdom", "cha": "charisma"}
                data[ability_map[ability]] = int(match.group(1))

        # Extract challenge rating
        match = re.search(MONSTER_PATTERNS["challenge"], raw_text, re.IGNORECASE)
        if match:
            cr_text = match.group(1)
            if "/" in cr_text:
                num, denom = cr_text.split("/")
                data["challenge_rating"] = float(num) / float(denom)
            else:
                data["challenge_rating"] = float(cr_text)
            xp_text = match.group(2).replace(",", "")
            data["xp"] = int(xp_text)

        # Extract senses
        match = re.search(MONSTER_PATTERNS["senses"], raw_text, re.IGNORECASE)
        if match:
            data["senses"] = {"raw": match.group(1).strip()}

        # Extract languages
        match = re.search(MONSTER_PATTERNS["languages"], raw_text, re.IGNORECASE)
        if match:
            data["languages"] = match.group(1).strip()

        return data

    def _parse_feat(self, raw_text: str, name: str) -> dict[str, Any]:
        """Parse feat content from raw text."""
        data: dict[str, Any] = {
            "index": name.lower().replace(" ", "-"),
            "name": name,
            "desc": [],
            "prerequisites": [],
        }

        # Extract prerequisite
        match = re.search(FEAT_PATTERNS["prerequisite"], raw_text, re.IGNORECASE)
        if match:
            prereq_text = match.group(1).strip()
            data["prerequisites"].append({"type": "custom", "description": prereq_text})

        # Extract bullet points as description
        desc_parts = []
        for match in re.finditer(FEAT_PATTERNS["bullet"], raw_text):
            desc_parts.append(match.group(1).strip())

        if desc_parts:
            data["desc"] = desc_parts
        else:
            # If no bullets, use the whole text as description
            # Clean up the text
            clean_text = re.sub(r"\s+", " ", raw_text).strip()
            if clean_text:
                data["desc"] = [clean_text[:500]]  # Limit length

        return data

    def _parse_item(self, raw_text: str, name: str) -> dict[str, Any]:
        """Parse item content from raw text."""
        data: dict[str, Any] = {
            "index": name.lower().replace(" ", "-"),
            "name": name,
            "equipment_category": "misc",
            "desc": [],
        }

        # Try to determine item type
        raw_lower = raw_text.lower()
        if "weapon" in raw_lower:
            data["equipment_category"] = "weapon"
        elif "armor" in raw_lower:
            data["equipment_category"] = "armor"
        elif "wondrous item" in raw_lower:
            data["equipment_category"] = "wondrous-items"
        elif "potion" in raw_lower:
            data["equipment_category"] = "potion"
        elif "scroll" in raw_lower:
            data["equipment_category"] = "scroll"

        # Try to extract rarity (ordered from most specific to least specific)
        # "very rare" before "rare", "uncommon" before "common"
        rarities = ["very rare", "legendary", "artifact", "uncommon", "rare", "common"]
        for rarity in rarities:
            if rarity in raw_lower:
                data["rarity"] = rarity.title()
                break

        # Check for attunement
        if "requires attunement" in raw_lower:
            data["requires_attunement"] = True
            # Try to extract attunement requirements
            attune_match = re.search(r"requires attunement\s+(?:by\s+)?(.+?)(?:\)|$)", raw_text, re.IGNORECASE)
            if attune_match:
                data["attunement_requirements"] = attune_match.group(1).strip()

        # Extract description
        clean_text = re.sub(r"\s+", " ", raw_text).strip()
        if clean_text:
            data["desc"] = [clean_text]

        return data

    def _parse_generic(self, raw_text: str, name: str) -> dict[str, Any]:
        """Generic parser for unknown content types."""
        return {
            "index": name.lower().replace(" ", "-"),
            "name": name,
            "desc": [raw_text[:1000]],  # Truncate for safety
        }

    def _parse_ability_bonuses(self, text: str) -> list[dict[str, Any]]:
        """Parse ability score bonuses from text."""
        bonuses = []
        ability_map = {
            "strength": "STR", "str": "STR",
            "dexterity": "DEX", "dex": "DEX",
            "constitution": "CON", "con": "CON",
            "intelligence": "INT", "int": "INT",
            "wisdom": "WIS", "wis": "WIS",
            "charisma": "CHA", "cha": "CHA",
        }

        text_lower = text.lower()

        # Pattern: "Your X score increases by Y"
        for ability, abbrev in ability_map.items():
            # Match patterns like "Strength score increases by 2" or "Dexterity +2"
            patterns = [
                rf"{ability}\s+(?:score\s+)?increases?\s+by\s+(\d+)",
                rf"{ability}\s*\+(\d+)",
                rf"\+(\d+)\s+(?:to\s+)?{ability}",
            ]
            for pattern in patterns:
                match = re.search(pattern, text_lower)
                if match:
                    bonus_value = int(match.group(1))
                    bonuses.append({
                        "ability_score": abbrev,
                        "bonus": bonus_value,
                    })
                    break

        # Pattern: "all ability scores increase by 1"
        if "all ability scores" in text_lower and "increase" in text_lower:
            match = re.search(r"increase[sd]?\s+by\s+(\d+)", text_lower)
            if match:
                bonus_value = int(match.group(1))
                for abbrev in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
                    bonuses.append({
                        "ability_score": abbrev,
                        "bonus": bonus_value,
                    })

        return bonuses

    def _parse_speed(self, text: str) -> dict[str, str]:
        """Parse speed from text."""
        speed: dict[str, str] = {}

        # Basic walking speed
        walk_match = re.search(r"(\d+)\s*(?:feet|ft\.?)", text)
        if walk_match:
            speed["walk"] = f"{walk_match.group(1)} ft."

        # Flying speed
        fly_match = re.search(r"fly\s+(\d+)\s*(?:feet|ft\.?)", text, re.IGNORECASE)
        if fly_match:
            speed["fly"] = f"{fly_match.group(1)} ft."

        # Swimming speed
        swim_match = re.search(r"swim\s+(\d+)\s*(?:feet|ft\.?)", text, re.IGNORECASE)
        if swim_match:
            speed["swim"] = f"{swim_match.group(1)} ft."

        # Climbing speed
        climb_match = re.search(r"climb\s+(\d+)\s*(?:feet|ft\.?)", text, re.IGNORECASE)
        if climb_match:
            speed["climb"] = f"{climb_match.group(1)} ft."

        # Burrowing speed
        burrow_match = re.search(r"burrow\s+(\d+)\s*(?:feet|ft\.?)", text, re.IGNORECASE)
        if burrow_match:
            speed["burrow"] = f"{burrow_match.group(1)} ft."

        return speed if speed else {"walk": "30 ft."}

    def _proficiency_bonus_for_level(self, level: int) -> int:
        """Calculate proficiency bonus for a given level."""
        if level <= 4:
            return 2
        elif level <= 8:
            return 3
        elif level <= 12:
            return 4
        elif level <= 16:
            return 5
        else:
            return 6

    def _to_custom_source_format(self, extracted: ExtractedContent) -> dict[str, Any]:
        """Convert extracted content to CustomSource JSON format."""
        # Create the CustomSource structure
        content_key = f"{extracted.content_type.value}s"  # "class" -> "classes"
        if extracted.content_type == ContentType.CLASS:
            content_key = "classes"
        elif extracted.content_type == ContentType.RACE:
            content_key = "races"

        return {
            "$schema": "gamemaster-mcp/rulebook-v1",
            "name": f"Extracted from {extracted.source_id}",
            "version": "1.0",
            "extracted_at": extracted.extraction_timestamp.isoformat(),
            "source_info": {
                "source_id": extracted.source_id,
                "page_start": extracted.page_start,
                "page_end": extracted.page_end,
                "confidence": extracted.confidence,
            },
            "content": {
                content_key: [extracted.parsed_data],
            },
        }


class MarkdownContentExtractor:
    """Extracts content sections from Markdown files.

    Uses the indexed TOC structure to locate and extract specific
    sections from Markdown documents.

    Attributes:
        md_path: Path to the Markdown file
        index: IndexEntry containing the TOC
    """

    def __init__(self, md_path: Path, index: "IndexEntry"):
        """Initialize the Markdown content extractor.

        Args:
            md_path: Path to the Markdown file
            index: IndexEntry containing the indexed TOC
        """
        from ..models import IndexEntry  # Avoid circular import at top level

        self.md_path = Path(md_path)
        self.index = index
        self._content = md_path.read_text(encoding="utf-8")
        self._lines = self._content.split("\n")

    def get_section(self, entry: "TOCEntry") -> str:
        """Extract text for a specific TOC entry.

        Extracts content from the entry's line number up to (but not including)
        the next header at the same or higher level.

        Args:
            entry: TOCEntry to extract content for

        Returns:
            The section content as a string
        """
        from ..models import TOCEntry  # Avoid circular import

        start_line = entry.page - 1  # Convert from 1-indexed to 0-indexed

        # Validate start line
        if start_line < 0 or start_line >= len(self._lines):
            return ""

        # Find the end line (next header at same or higher level)
        end_line = self._find_section_end(start_line, entry)

        # Extract and join the lines
        section_lines = self._lines[start_line:end_line]
        return "\n".join(section_lines)

    def get_section_by_title(self, title: str) -> str | None:
        """Extract text for a section by its title.

        Searches the TOC for a matching entry and extracts its content.

        Args:
            title: Title of the section to extract (case-insensitive)

        Returns:
            The section content as a string, or None if not found
        """
        entry = self._find_entry_by_title(title)
        if entry:
            return self.get_section(entry)
        return None

    def get_all_sections(self) -> dict[str, str]:
        """Extract all sections as a dictionary.

        Returns:
            Dictionary mapping section titles to their content
        """
        sections: dict[str, str] = {}

        def extract_entries(entries: list) -> None:
            for entry in entries:
                sections[entry.title] = self.get_section(entry)
                if entry.children:
                    extract_entries(entry.children)

        extract_entries(self.index.toc)
        return sections

    def _find_section_end(self, start_line: int, entry: "TOCEntry") -> int:
        """Find the line number where this section ends.

        Looks for the next header at the same level or higher (fewer #).

        Args:
            start_line: 0-indexed starting line
            entry: The TOCEntry being extracted

        Returns:
            The 0-indexed line number where the section ends
        """
        import re
        header_pattern = re.compile(r"^(#{1,6})\s+")

        # Get the level of the current header
        current_line = self._lines[start_line]
        match = header_pattern.match(current_line)
        if not match:
            # Not a valid header, return to end of file
            return len(self._lines)

        current_level = len(match.group(1))

        # Search for next header at same or higher level
        in_code_block = False
        for i in range(start_line + 1, len(self._lines)):
            line = self._lines[i]

            # Track code blocks
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                continue

            # Check if this is a header
            match = header_pattern.match(line)
            if match:
                header_level = len(match.group(1))
                # Stop if we hit a header at same or higher level
                if header_level <= current_level:
                    return i

        # No ending header found, return end of file
        return len(self._lines)

    def _find_entry_by_title(self, title: str) -> "TOCEntry | None":
        """Find a TOC entry by its title.

        Args:
            title: Title to search for (case-insensitive)

        Returns:
            Matching TOCEntry or None
        """
        title_lower = title.lower()

        def search_entries(entries: list) -> "TOCEntry | None":
            for entry in entries:
                if entry.title.lower() == title_lower:
                    return entry
                if title_lower in entry.title.lower():
                    return entry
                if entry.children:
                    result = search_entries(entry.children)
                    if result:
                        return result
            return None

        return search_entries(self.index.toc)

    def _flatten_toc(self) -> list:
        """Flatten the hierarchical TOC into a flat list.

        Returns:
            Flat list of all TOCEntry objects
        """
        flat: list = []

        def flatten(entries: list) -> None:
            for entry in entries:
                flat.append(entry)
                if entry.children:
                    flatten(entry.children)

        flatten(self.index.toc)
        return flat


__all__ = [
    "ContentExtractor",
    "ExtractedContent",
    "MarkdownContentExtractor",
    "CLASS_PATTERNS",
    "RACE_PATTERNS",
    "SPELL_PATTERNS",
    "MONSTER_PATTERNS",
    "FEAT_PATTERNS",
    "ITEM_PATTERNS",
]
