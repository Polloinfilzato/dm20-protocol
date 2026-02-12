"""Tests for inventory management: equip, unequip, remove item logic."""

import pytest

from dm20_protocol.models import (
    Character,
    CharacterClass,
    Item,
    Race,
)
from dm20_protocol.main import (
    _find_inventory_item,
    _equip_item_logic,
    _unequip_item_logic,
    _remove_item_logic,
    VALID_EQUIPMENT_SLOTS,
)


# ─── Helpers ───────────────────────────────────────────────────────────


def make_character(
    name: str = "Aldric",
    items: list[Item] | None = None,
    equipment: dict | None = None,
) -> Character:
    """Create a test character with inventory and equipment."""
    return Character(
        name=name,
        character_class=CharacterClass(name="Fighter", level=3, hit_dice="3d10"),
        race=Race(name="Human"),
        inventory=items or [],
        equipment=equipment
        or {
            "weapon_main": None,
            "weapon_off": None,
            "armor": None,
            "shield": None,
        },
    )


def make_item(
    name: str = "Longsword",
    item_type: str = "weapon",
    quantity: int = 1,
    item_id: str | None = None,
) -> Item:
    """Create a test item."""
    item = Item(name=name, item_type=item_type, quantity=quantity)
    if item_id:
        item.id = item_id
    return item


# ─── Test: _find_inventory_item ────────────────────────────────────────


class TestFindInventoryItem:

    def test_find_by_name_case_insensitive(self):
        sword = make_item("Longsword")
        char = make_character(items=[sword])
        assert _find_inventory_item(char, "longsword") is sword
        assert _find_inventory_item(char, "LONGSWORD") is sword
        assert _find_inventory_item(char, "Longsword") is sword

    def test_find_by_id(self):
        sword = make_item("Longsword", item_id="abc123")
        char = make_character(items=[sword])
        assert _find_inventory_item(char, "abc123") is sword

    def test_not_found(self):
        char = make_character(items=[make_item("Longsword")])
        assert _find_inventory_item(char, "Battleaxe") is None

    def test_name_match_priority_over_id(self):
        sword = make_item("Longsword")
        other = make_item("Dagger", item_id="Longsword")
        char = make_character(items=[sword, other])
        assert _find_inventory_item(char, "Longsword") is sword

    def test_empty_inventory(self):
        char = make_character(items=[])
        assert _find_inventory_item(char, "anything") is None


# ─── Test: _equip_item_logic ──────────────────────────────────────────


class TestEquipItemLogic:

    def test_equip_basic(self):
        sword = make_item("Longsword")
        char = make_character(items=[sword])

        result = _equip_item_logic(char, "Longsword", "weapon_main")

        assert "Equipped Longsword to weapon_main" in result
        assert char.equipment["weapon_main"] is sword
        assert sword not in char.inventory

    def test_equip_invalid_slot(self):
        char = make_character(items=[make_item("Longsword")])
        result = _equip_item_logic(char, "Longsword", "hat")
        assert "Invalid slot" in result
        assert "hat" in result

    def test_equip_item_not_found(self):
        char = make_character(items=[])
        result = _equip_item_logic(char, "Longsword", "weapon_main")
        assert "not found" in result

    def test_equip_auto_unequip(self):
        """Equipping to an occupied slot auto-unequips the current item."""
        old_sword = make_item("Shortsword", item_id="old1")
        new_sword = make_item("Longsword", item_id="new1")
        char = make_character(
            items=[new_sword],
            equipment={
                "weapon_main": old_sword,
                "weapon_off": None,
                "armor": None,
                "shield": None,
            },
        )

        result = _equip_item_logic(char, "Longsword", "weapon_main")

        assert "Unequipped Shortsword" in result
        assert "Equipped Longsword" in result
        assert char.equipment["weapon_main"] is new_sword
        assert old_sword in char.inventory
        assert new_sword not in char.inventory

    def test_equip_all_valid_slots(self):
        for slot in VALID_EQUIPMENT_SLOTS:
            item = make_item(f"Item_{slot}")
            char = make_character(items=[item])
            result = _equip_item_logic(char, f"Item_{slot}", slot)
            assert "Equipped" in result
            assert char.equipment[slot] is item

    def test_equip_by_id(self):
        sword = make_item("Longsword", item_id="sword42")
        char = make_character(items=[sword])
        result = _equip_item_logic(char, "sword42", "weapon_main")
        assert "Equipped Longsword" in result

    def test_equip_preserves_other_inventory(self):
        """Equipping one item doesn't affect other inventory items."""
        sword = make_item("Longsword")
        shield = make_item("Shield")
        char = make_character(items=[sword, shield])

        _equip_item_logic(char, "Longsword", "weapon_main")

        assert shield in char.inventory
        assert len(char.inventory) == 1


# ─── Test: _unequip_item_logic ────────────────────────────────────────


class TestUnequipItemLogic:

    def test_unequip_basic(self):
        sword = make_item("Longsword")
        char = make_character(
            equipment={
                "weapon_main": sword,
                "weapon_off": None,
                "armor": None,
                "shield": None,
            },
        )

        result = _unequip_item_logic(char, "weapon_main")

        assert "Unequipped Longsword" in result
        assert char.equipment["weapon_main"] is None
        assert sword in char.inventory

    def test_unequip_empty_slot(self):
        char = make_character()
        result = _unequip_item_logic(char, "weapon_main")
        assert "empty" in result

    def test_unequip_invalid_slot(self):
        char = make_character()
        result = _unequip_item_logic(char, "hat")
        assert "Invalid slot" in result

    def test_unequip_adds_to_inventory(self):
        sword = make_item("Longsword")
        potion = make_item("Healing Potion")
        char = make_character(
            items=[potion],
            equipment={
                "weapon_main": sword,
                "weapon_off": None,
                "armor": None,
                "shield": None,
            },
        )

        _unequip_item_logic(char, "weapon_main")

        assert len(char.inventory) == 2
        assert sword in char.inventory
        assert potion in char.inventory


# ─── Test: _remove_item_logic ─────────────────────────────────────────


class TestRemoveItemLogic:

    def test_remove_single_item(self):
        sword = make_item("Longsword", quantity=1)
        char = make_character(items=[sword])

        result = _remove_item_logic(char, "Longsword")

        assert "Removed" in result
        assert sword not in char.inventory

    def test_remove_partial_quantity(self):
        arrows = make_item("Arrow", quantity=20)
        char = make_character(items=[arrows])

        result = _remove_item_logic(char, "Arrow", quantity=5)

        assert "Removed 5x Arrow" in result
        assert "15 remaining" in result
        assert arrows.quantity == 15
        assert arrows in char.inventory

    def test_remove_all_quantity(self):
        arrows = make_item("Arrow", quantity=5)
        char = make_character(items=[arrows])

        result = _remove_item_logic(char, "Arrow", quantity=10)

        assert "Removed 5x Arrow" in result
        assert arrows not in char.inventory

    def test_remove_exact_quantity(self):
        potions = make_item("Healing Potion", quantity=3)
        char = make_character(items=[potions])

        result = _remove_item_logic(char, "Healing Potion", quantity=3)

        assert "Removed 3x Healing Potion" in result
        assert potions not in char.inventory

    def test_remove_item_not_found(self):
        char = make_character(items=[])
        result = _remove_item_logic(char, "Nonexistent")
        assert "not found" in result

    def test_remove_by_id(self):
        sword = make_item("Longsword", item_id="xyz789")
        char = make_character(items=[sword])

        result = _remove_item_logic(char, "xyz789")

        assert "Removed" in result
        assert sword not in char.inventory

    def test_remove_preserves_other_items(self):
        sword = make_item("Longsword")
        shield = make_item("Shield")
        char = make_character(items=[sword, shield])

        _remove_item_logic(char, "Longsword")

        assert shield in char.inventory
        assert len(char.inventory) == 1


# ─── Test: Round-Trip ─────────────────────────────────────────────────


class TestRoundTrip:

    def test_equip_unequip_round_trip(self):
        """Item goes inventory → equipment → inventory."""
        sword = make_item("Longsword")
        char = make_character(items=[sword])

        _equip_item_logic(char, "Longsword", "weapon_main")
        assert char.equipment["weapon_main"] is sword
        assert sword not in char.inventory

        _unequip_item_logic(char, "weapon_main")
        assert char.equipment["weapon_main"] is None
        assert sword in char.inventory

    def test_swap_equipped_items(self):
        old = make_item("Shortsword", item_id="old")
        new = make_item("Greatsword", item_id="new")
        char = make_character(
            items=[new],
            equipment={
                "weapon_main": old,
                "weapon_off": None,
                "armor": None,
                "shield": None,
            },
        )

        _equip_item_logic(char, "Greatsword", "weapon_main")

        assert char.equipment["weapon_main"] is new
        assert old in char.inventory
        assert new not in char.inventory

    def test_equip_remove_unequip_flow(self):
        """Full inventory workflow: add items, equip, remove, unequip."""
        sword = make_item("Longsword")
        arrows = make_item("Arrow", quantity=20)
        char = make_character(items=[sword, arrows])

        # Equip sword
        _equip_item_logic(char, "Longsword", "weapon_main")
        assert len(char.inventory) == 1  # only arrows

        # Remove some arrows
        _remove_item_logic(char, "Arrow", quantity=5)
        assert char.inventory[0].quantity == 15

        # Unequip sword
        _unequip_item_logic(char, "weapon_main")
        assert len(char.inventory) == 2  # arrows + sword back
