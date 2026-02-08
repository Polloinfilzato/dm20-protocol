"""Tests for element locking configuration system."""

import pytest

from dm20_protocol.claudmaster.element_locks import (
    ElementCategory,
    ElementLock,
    LockConfiguration,
    CATEGORY_HIERARCHY,
)
from dm20_protocol.claudmaster.improvisation import ImprovisationLevel


# Test ElementCategory
def test_all_categories_exist():
    """Verify all 8 categories are defined."""
    categories = list(ElementCategory)
    assert len(categories) == 8
    assert ElementCategory.NPC in categories
    assert ElementCategory.LOCATION in categories
    assert ElementCategory.EVENT in categories
    assert ElementCategory.DIALOGUE in categories
    assert ElementCategory.DESCRIPTION in categories
    assert ElementCategory.ITEM in categories
    assert ElementCategory.SECRET in categories
    assert ElementCategory.ENCOUNTER in categories


# Test ElementLock
def test_default_values():
    """Check ElementLock defaults (is_locked=True, inherit_to_children=True)."""
    lock = ElementLock(element_id="test-npc", category=ElementCategory.NPC)
    assert lock.is_locked is True
    assert lock.inherit_to_children is True
    assert lock.lock_reason is None
    assert lock.override_level is None


def test_custom_lock():
    """Create ElementLock with all fields."""
    lock = ElementLock(
        element_id="important-npc",
        category=ElementCategory.NPC,
        is_locked=True,
        lock_reason="Critical to main plot",
        override_level=ImprovisationLevel.LOW,
        inherit_to_children=False,
    )
    assert lock.element_id == "important-npc"
    assert lock.category == ElementCategory.NPC
    assert lock.is_locked is True
    assert lock.lock_reason == "Critical to main plot"
    assert lock.override_level == ImprovisationLevel.LOW
    assert lock.inherit_to_children is False


# Test LockConfiguration
def test_lock_element():
    """Lock element and verify."""
    config = LockConfiguration()
    lock = config.lock_element("npc-1", ElementCategory.NPC, reason="Plot critical")

    assert lock.element_id == "npc-1"
    assert lock.category == ElementCategory.NPC
    assert lock.is_locked is True
    assert lock.lock_reason == "Plot critical"
    assert "npc-1" in config.locks


def test_unlock_element():
    """Lock then unlock an element."""
    config = LockConfiguration()
    config.lock_element("npc-1", ElementCategory.NPC)
    assert "npc-1" in config.locks

    result = config.unlock_element("npc-1")
    assert result is True
    assert "npc-1" not in config.locks


def test_unlock_nonexistent():
    """Unlocking nonexistent element returns False."""
    config = LockConfiguration()
    result = config.unlock_element("nonexistent")
    assert result is False


def test_is_element_locked_direct():
    """Direct lock check."""
    config = LockConfiguration()
    config.lock_element("npc-1", ElementCategory.NPC)

    assert config.is_element_locked("npc-1") is True
    assert config.is_element_locked("npc-2") is False


def test_is_element_locked_inherited():
    """Parent inheritance works."""
    config = LockConfiguration()
    config.lock_element("tavern", ElementCategory.LOCATION, inherit_to_children=True)

    # Child should inherit lock from parent
    assert config.is_element_locked("bartender", parent_id="tavern") is True


def test_is_element_locked_no_inherit():
    """Parent with inherit=False doesn't propagate."""
    config = LockConfiguration()
    config.lock_element("tavern", ElementCategory.LOCATION, inherit_to_children=False)

    # Child should NOT inherit lock
    assert config.is_element_locked("bartender", parent_id="tavern") is False


def test_category_defaults():
    """Set and check category defaults."""
    config = LockConfiguration()

    # Initially no default
    assert config.is_category_locked_by_default(ElementCategory.NPC) is False

    # Set default
    config.set_category_default(ElementCategory.NPC, True)
    assert config.is_category_locked_by_default(ElementCategory.NPC) is True

    # Can be toggled
    config.set_category_default(ElementCategory.NPC, False)
    assert config.is_category_locked_by_default(ElementCategory.NPC) is False


def test_get_locked_elements():
    """Filter locked elements by category."""
    config = LockConfiguration()
    config.lock_element("npc-1", ElementCategory.NPC)
    config.lock_element("npc-2", ElementCategory.NPC)
    config.lock_element("location-1", ElementCategory.LOCATION)

    npc_locks = config.get_locked_elements(category=ElementCategory.NPC)
    assert len(npc_locks) == 2
    assert all(lock.category == ElementCategory.NPC for lock in npc_locks)


def test_get_locked_elements_all():
    """Get all locked elements without filter."""
    config = LockConfiguration()
    config.lock_element("npc-1", ElementCategory.NPC)
    config.lock_element("location-1", ElementCategory.LOCATION)

    all_locks = config.get_locked_elements()
    assert len(all_locks) == 2


def test_get_element_override():
    """Get override level for an element."""
    config = LockConfiguration()
    config.lock_element("npc-1", ElementCategory.NPC, override_level=ImprovisationLevel.LOW)

    override = config.get_element_override("npc-1")
    assert override == ImprovisationLevel.LOW

    # No override
    assert config.get_element_override("nonexistent") is None


def test_get_effective_level_override():
    """Element override wins over global level."""
    config = LockConfiguration()
    config.lock_element("npc-1", ElementCategory.NPC, override_level=ImprovisationLevel.LOW)

    level = config.get_effective_level("npc-1", ImprovisationLevel.HIGH)
    assert level == ImprovisationLevel.LOW


def test_get_effective_level_locked_no_override():
    """Locked element with no override returns NONE."""
    config = LockConfiguration()
    config.lock_element("npc-1", ElementCategory.NPC)

    level = config.get_effective_level("npc-1", ImprovisationLevel.HIGH)
    assert level == ImprovisationLevel.NONE


def test_get_effective_level_parent_override():
    """Parent override is inherited."""
    config = LockConfiguration()
    config.lock_element(
        "tavern",
        ElementCategory.LOCATION,
        override_level=ImprovisationLevel.LOW,
        inherit_to_children=True,
    )

    level = config.get_effective_level("bartender", ImprovisationLevel.HIGH, parent_id="tavern")
    assert level == ImprovisationLevel.LOW


def test_get_effective_level_global_fallback():
    """Falls back to global level when no locks or overrides."""
    config = LockConfiguration()

    level = config.get_effective_level("npc-1", ImprovisationLevel.MEDIUM)
    assert level == ImprovisationLevel.MEDIUM


def test_get_children_categories():
    """Check hierarchy relationships."""
    config = LockConfiguration()

    # LOCATION has children
    location_children = config.get_children_categories(ElementCategory.LOCATION)
    assert ElementCategory.NPC in location_children
    assert ElementCategory.ITEM in location_children
    assert ElementCategory.EVENT in location_children
    assert ElementCategory.DESCRIPTION in location_children
    assert ElementCategory.ENCOUNTER in location_children

    # NPC has children
    npc_children = config.get_children_categories(ElementCategory.NPC)
    assert ElementCategory.DIALOGUE in npc_children
    assert ElementCategory.SECRET in npc_children

    # EVENT has children
    event_children = config.get_children_categories(ElementCategory.EVENT)
    assert ElementCategory.DESCRIPTION in event_children
    assert ElementCategory.ENCOUNTER in event_children


def test_validate_locks_valid():
    """All locked elements exist in known elements."""
    config = LockConfiguration()
    config.lock_element("npc-1", ElementCategory.NPC)
    config.lock_element("location-1", ElementCategory.LOCATION)

    known_elements = {"npc-1", "location-1", "other-element"}
    errors = config.validate_locks(known_elements)
    assert len(errors) == 0


def test_validate_locks_invalid():
    """Some locked elements are missing from known elements."""
    config = LockConfiguration()
    config.lock_element("npc-1", ElementCategory.NPC)
    config.lock_element("missing-npc", ElementCategory.NPC)

    known_elements = {"npc-1", "location-1"}
    errors = config.validate_locks(known_elements)
    assert len(errors) == 1
    assert "missing-npc" in errors[0]
    assert "not found" in errors[0]


# Test CATEGORY_HIERARCHY
def test_location_children():
    """LOCATION has correct children."""
    children = CATEGORY_HIERARCHY[ElementCategory.LOCATION]
    assert len(children) == 5
    assert ElementCategory.NPC in children
    assert ElementCategory.ITEM in children
    assert ElementCategory.EVENT in children
    assert ElementCategory.DESCRIPTION in children
    assert ElementCategory.ENCOUNTER in children


def test_npc_children():
    """NPC has correct children."""
    children = CATEGORY_HIERARCHY[ElementCategory.NPC]
    assert len(children) == 2
    assert ElementCategory.DIALOGUE in children
    assert ElementCategory.SECRET in children


def test_event_children():
    """EVENT has correct children."""
    children = CATEGORY_HIERARCHY[ElementCategory.EVENT]
    assert len(children) == 2
    assert ElementCategory.DESCRIPTION in children
    assert ElementCategory.ENCOUNTER in children


def test_leaf_categories():
    """Items, secrets, dialogue, description, and encounter have no children."""
    assert ElementCategory.ITEM not in CATEGORY_HIERARCHY
    assert ElementCategory.SECRET not in CATEGORY_HIERARCHY
    assert ElementCategory.DIALOGUE not in CATEGORY_HIERARCHY
    # DESCRIPTION and ENCOUNTER appear as children but don't have their own children
    assert ElementCategory.DESCRIPTION not in CATEGORY_HIERARCHY
    assert ElementCategory.ENCOUNTER not in CATEGORY_HIERARCHY
