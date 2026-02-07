"""
Locked and Flexible Elements Configuration for Claudmaster AI DM.

This module provides a granular element locking system that allows DMs to lock
specific story elements (NPCs, locations, events, etc.) while allowing flexibility
in others. Elements can be locked individually or by category, with inheritance
support for hierarchical relationships.

The system integrates with the improvisation level system, allowing per-element
overrides of the global improvisation level.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .improvisation import ImprovisationLevel


class ElementCategory(str, Enum):
    """Categories of story elements that can be locked or made flexible."""
    NPC = "npc"
    LOCATION = "location"
    EVENT = "event"
    DIALOGUE = "dialogue"
    DESCRIPTION = "description"
    ITEM = "item"
    SECRET = "secret"
    ENCOUNTER = "encounter"


class ElementLock(BaseModel):
    """Configuration for a locked story element."""
    element_id: str = Field(description="Unique identifier of the element")
    category: ElementCategory = Field(description="Category of the element")
    is_locked: bool = Field(default=True, description="Whether the element is locked")
    lock_reason: Optional[str] = Field(default=None, description="Why this element is locked")
    override_level: Optional[ImprovisationLevel] = Field(
        default=None, description="Per-element improvisation level override"
    )
    inherit_to_children: bool = Field(
        default=True, description="Whether child elements inherit this lock"
    )


# Define parent-child relationships between categories
CATEGORY_HIERARCHY: dict[ElementCategory, list[ElementCategory]] = {
    ElementCategory.LOCATION: [
        ElementCategory.NPC,
        ElementCategory.ITEM,
        ElementCategory.EVENT,
        ElementCategory.DESCRIPTION,
        ElementCategory.ENCOUNTER,
    ],
    ElementCategory.NPC: [
        ElementCategory.DIALOGUE,
        ElementCategory.SECRET,
    ],
    ElementCategory.EVENT: [
        ElementCategory.DESCRIPTION,
        ElementCategory.ENCOUNTER,
    ],
}


class LockConfiguration(BaseModel):
    """Campaign-level lock configuration."""
    locks: dict[str, ElementLock] = Field(default_factory=dict)
    default_category_locks: dict[ElementCategory, bool] = Field(default_factory=dict)

    def lock_element(
        self,
        element_id: str,
        category: ElementCategory,
        reason: Optional[str] = None,
        override_level: Optional[ImprovisationLevel] = None,
        inherit_to_children: bool = True,
    ) -> ElementLock:
        """Lock a specific element."""
        lock = ElementLock(
            element_id=element_id,
            category=category,
            is_locked=True,
            lock_reason=reason,
            override_level=override_level,
            inherit_to_children=inherit_to_children,
        )
        self.locks[element_id] = lock
        return lock

    def unlock_element(self, element_id: str) -> bool:
        """Remove lock from an element. Returns True if lock existed."""
        if element_id in self.locks:
            del self.locks[element_id]
            return True
        return False

    def is_element_locked(self, element_id: str, parent_id: Optional[str] = None) -> bool:
        """Check if an element is locked (directly or via inheritance)."""
        # Direct lock check
        if element_id in self.locks:
            return self.locks[element_id].is_locked

        # Check parent inheritance
        if parent_id and parent_id in self.locks:
            parent_lock = self.locks[parent_id]
            if parent_lock.is_locked and parent_lock.inherit_to_children:
                return True

        # Check category default (would need category info, so we can't check here)
        return False

    def is_category_locked_by_default(self, category: ElementCategory) -> bool:
        """Check if a category is locked by default."""
        return self.default_category_locks.get(category, False)

    def set_category_default(self, category: ElementCategory, locked: bool) -> None:
        """Set the default lock state for a category."""
        self.default_category_locks[category] = locked

    def get_locked_elements(self, category: Optional[ElementCategory] = None) -> list[ElementLock]:
        """Get all locked elements, optionally filtered by category."""
        locks = [lock for lock in self.locks.values() if lock.is_locked]
        if category:
            locks = [lock for lock in locks if lock.category == category]
        return locks

    def get_element_override(self, element_id: str) -> Optional[ImprovisationLevel]:
        """Get the improvisation level override for an element, if any."""
        if element_id in self.locks:
            return self.locks[element_id].override_level
        return None

    def get_effective_level(
        self,
        element_id: str,
        global_level: ImprovisationLevel,
        parent_id: Optional[str] = None,
    ) -> ImprovisationLevel:
        """Get effective improvisation level for an element.

        Priority: element override > parent override > global level
        If element is locked with no override, returns ImprovisationLevel.NONE.
        """
        # Check direct element override
        if element_id in self.locks:
            lock = self.locks[element_id]
            if lock.override_level is not None:
                return lock.override_level
            if lock.is_locked:
                return ImprovisationLevel.NONE

        # Check parent override
        if parent_id and parent_id in self.locks:
            parent_lock = self.locks[parent_id]
            if parent_lock.inherit_to_children:
                if parent_lock.override_level is not None:
                    return parent_lock.override_level
                if parent_lock.is_locked:
                    return ImprovisationLevel.NONE

        return global_level

    def get_children_categories(self, category: ElementCategory) -> list[ElementCategory]:
        """Get child categories for a given parent category."""
        return CATEGORY_HIERARCHY.get(category, [])

    def validate_locks(self, known_element_ids: set[str]) -> list[str]:
        """Validate that locked elements exist in known elements.

        Returns list of error messages for invalid locks.
        """
        errors = []
        for element_id, lock in self.locks.items():
            if element_id not in known_element_ids:
                errors.append(f"Locked element '{element_id}' not found in module content")
        return errors


__all__ = [
    "ElementCategory",
    "ElementLock",
    "LockConfiguration",
    "CATEGORY_HIERARCHY",
]
