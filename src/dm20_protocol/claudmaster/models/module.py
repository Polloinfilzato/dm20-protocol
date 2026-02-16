"""
Data models for adventure module structure.

These dataclasses represent the structure of D&D adventure modules
extracted from PDF table of contents, including chapters, NPCs,
encounters, and locations.
"""

from dataclasses import dataclass, field
from enum import Enum


class ContentType(str, Enum):
    """Type of content element in an adventure module."""
    CHAPTER = "chapter"
    SECTION = "section"
    ENCOUNTER = "encounter"
    NPC = "npc"
    LOCATION = "location"
    ITEM = "item"
    APPENDIX = "appendix"


@dataclass
class ModuleElement:
    """Base element in module structure.

    Represents a chapter, section, or subsection in the adventure
    module's organizational hierarchy.

    Attributes:
        name: Display name of the element
        content_type: Type of content (chapter, section, etc.)
        page_start: Page number where this element starts (1-indexed)
        page_end: Optional page number where this element ends
        parent: Name of parent element (None for top-level chapters)
        children: List of child element names
    """
    name: str
    content_type: ContentType
    page_start: int
    page_end: int | None = None
    parent: str | None = None
    children: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "name": self.name,
            "content_type": self.content_type.value,
            "page_start": self.page_start,
        }
        if self.page_end is not None:
            result["page_end"] = self.page_end
        if self.parent is not None:
            result["parent"] = self.parent
        if self.children:
            result["children"] = self.children
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleElement":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            content_type=ContentType(data["content_type"]),
            page_start=data["page_start"],
            page_end=data.get("page_end"),
            parent=data.get("parent"),
            children=data.get("children", []),
        )


@dataclass
class NPCReference:
    """NPC found in module.

    Represents a named NPC character referenced in the adventure module,
    typically found in encounter sections or appendices.

    Attributes:
        name: Character name
        location: Where the NPC is located (if specified)
        chapter: Chapter where the NPC is introduced
        page: Page number where the NPC appears
        description_preview: Brief description snippet (if available)
    """
    name: str
    location: str | None = None
    chapter: str = ""
    page: int = 0
    description_preview: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "name": self.name,
            "chapter": self.chapter,
            "page": self.page,
        }
        if self.location is not None:
            result["location"] = self.location
        if self.description_preview:
            result["description_preview"] = self.description_preview
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "NPCReference":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            location=data.get("location"),
            chapter=data.get("chapter", ""),
            page=data.get("page", 0),
            description_preview=data.get("description_preview", ""),
        )


@dataclass
class EncounterReference:
    """Encounter found in module.

    Represents a specific encounter (combat, social, exploration, puzzle)
    in the adventure module.

    Attributes:
        name: Encounter name or title
        location: Where the encounter takes place
        chapter: Chapter containing the encounter
        page: Page number of the encounter
        encounter_type: Type of encounter (combat, social, exploration, puzzle)
    """
    name: str
    location: str
    chapter: str
    page: int
    encounter_type: str = "combat"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "location": self.location,
            "chapter": self.chapter,
            "page": self.page,
            "encounter_type": self.encounter_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EncounterReference":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            location=data["location"],
            chapter=data["chapter"],
            page=data["page"],
            encounter_type=data.get("encounter_type", "combat"),
        )


@dataclass
class LocationReference:
    """Location/area found in module.

    Represents a geographic location or area in the adventure module,
    which may contain sub-locations or numbered areas.

    Attributes:
        name: Location name
        chapter: Chapter where the location is described
        page: Page number where the location appears
        parent_location: Parent location (if this is a sub-location)
        sub_locations: List of child location names
    """
    name: str
    chapter: str
    page: int
    parent_location: str | None = None
    sub_locations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "name": self.name,
            "chapter": self.chapter,
            "page": self.page,
        }
        if self.parent_location is not None:
            result["parent_location"] = self.parent_location
        if self.sub_locations:
            result["sub_locations"] = self.sub_locations
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "LocationReference":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            chapter=data["chapter"],
            page=data["page"],
            parent_location=data.get("parent_location"),
            sub_locations=data.get("sub_locations", []),
        )


@dataclass
class ModuleStructure:
    """Complete parsed structure of an adventure module.

    Aggregates all structural information extracted from an adventure
    module including chapters, NPCs, encounters, and locations.

    Attributes:
        module_id: Unique identifier for the module (source_id from library)
        title: Module title
        source_file: Original filename
        chapters: Hierarchical list of chapter/section elements
        npcs: List of NPC references found in the module
        encounters: List of encounter references
        locations: List of location references
        metadata: Additional metadata (e.g., publisher, adventure level)
    """
    module_id: str
    title: str
    source_file: str
    chapters: list[ModuleElement] = field(default_factory=list)
    npcs: list[NPCReference] = field(default_factory=list)
    encounters: list[EncounterReference] = field(default_factory=list)
    locations: list[LocationReference] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    read_aloud: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "module_id": self.module_id,
            "title": self.title,
            "source_file": self.source_file,
            "chapters": [ch.to_dict() for ch in self.chapters],
            "npcs": [npc.to_dict() for npc in self.npcs],
            "encounters": [enc.to_dict() for enc in self.encounters],
            "locations": [loc.to_dict() for loc in self.locations],
            "metadata": self.metadata,
        }
        if self.read_aloud:
            result["read_aloud"] = self.read_aloud
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleStructure":
        """Create from dictionary."""
        return cls(
            module_id=data["module_id"],
            title=data["title"],
            source_file=data["source_file"],
            chapters=[ModuleElement.from_dict(ch) for ch in data.get("chapters", [])],
            npcs=[NPCReference.from_dict(npc) for npc in data.get("npcs", [])],
            encounters=[EncounterReference.from_dict(enc) for enc in data.get("encounters", [])],
            locations=[LocationReference.from_dict(loc) for loc in data.get("locations", [])],
            metadata=data.get("metadata", {}),
            read_aloud=data.get("read_aloud", {}),
        )
