"""
Data models for Claudmaster adventure module parsing.

This package contains data structures for representing parsed adventure
module content including chapters, NPCs, encounters, and locations.
"""

from .module import (
    ContentType,
    ModuleElement,
    NPCReference,
    EncounterReference,
    LocationReference,
    ModuleStructure,
)

__all__ = [
    "ContentType",
    "ModuleElement",
    "NPCReference",
    "EncounterReference",
    "LocationReference",
    "ModuleStructure",
]
