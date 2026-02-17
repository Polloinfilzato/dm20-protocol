"""
Tests for the Positioning and AoE Engine.

Covers:
- Position model creation and equality
- Distance calculation (straight, diagonal, Pythagorean)
- Proximity enum and conversion functions
- AoE shapes: Sphere, Cube, Cone, Line, Cylinder
- calculate_aoe_targets with grid positions and proximity fallback
- set_positions bulk assignment
- move_participant with speed validation
- Edge cases: zero distance, overlapping positions, None positions
"""

import math

import pytest

from dm20_protocol.combat.positioning import (
    Position,
    Proximity,
    AoEShape,
    Sphere,
    Cube,
    Cone,
    Line,
    Cylinder,
    MovementResult,
    distance,
    calculate_aoe_targets,
    set_positions,
    move_participant,
    proximity_from_distance,
    proximity_max_feet,
)
from dm20_protocol.models import Character, CharacterClass, Race


# ---------------------------------------------------------------------------
# Helper: create a minimal Character for testing
# ---------------------------------------------------------------------------

def _make_char(name: str, pos: Position | None = None, speed: int = 30) -> Character:
    """Create a minimal Character with optional position."""
    char = Character(
        name=name,
        character_class=CharacterClass(name="Fighter", level=1),
        race=Race(name="Human"),
        speed=speed,
        position=pos,
    )
    return char


class _ProximityParticipant:
    """Lightweight participant stand-in for proximity fallback tests.

    The calculate_aoe_targets function uses duck-typed access to ``name``,
    ``position``, and ``proximity`` attributes.  Character (Pydantic model)
    does not expose a ``proximity`` field, so we use this simple class to
    exercise the proximity code path without violating Pydantic's validation.
    """

    def __init__(self, name: str, proximity: Proximity | str | None = None):
        self.name = name
        self.position = None  # no grid position
        self.proximity = proximity


# ===================================================================
# Position model
# ===================================================================

class TestPosition:
    """Tests for the Position model."""

    def test_create_position(self):
        pos = Position(x=3, y=5)
        assert pos.x == 3
        assert pos.y == 5

    def test_position_origin(self):
        pos = Position(x=0, y=0)
        assert pos.x == 0 and pos.y == 0

    def test_position_negative_coords(self):
        pos = Position(x=-2, y=-3)
        assert pos.x == -2 and pos.y == -3

    def test_position_feet(self):
        pos = Position(x=2, y=3)
        fx, fy = pos.feet()
        assert fx == 12.5  # 2*5 + 2.5
        assert fy == 17.5  # 3*5 + 2.5

    def test_position_equality(self):
        a = Position(x=1, y=2)
        b = Position(x=1, y=2)
        assert a == b

    def test_position_inequality(self):
        a = Position(x=1, y=2)
        b = Position(x=2, y=1)
        assert a != b

    def test_position_hash(self):
        a = Position(x=1, y=2)
        b = Position(x=1, y=2)
        assert hash(a) == hash(b)
        assert len({a, b}) == 1

    def test_position_repr(self):
        pos = Position(x=5, y=10)
        assert "5" in repr(pos) and "10" in repr(pos)

    def test_position_serialization(self):
        """Position should serialize/deserialize as Pydantic model."""
        pos = Position(x=7, y=3)
        data = pos.model_dump()
        assert data == {"x": 7, "y": 3}
        restored = Position.model_validate(data)
        assert restored == pos


# ===================================================================
# Distance calculation
# ===================================================================

class TestDistance:
    """Tests for the distance() function."""

    def test_same_position(self):
        p = Position(x=3, y=4)
        assert distance(p, p) == 0.0

    def test_horizontal_distance(self):
        a = Position(x=0, y=0)
        b = Position(x=6, y=0)
        assert distance(a, b) == 30.0  # 6 squares * 5ft

    def test_vertical_distance(self):
        a = Position(x=0, y=0)
        b = Position(x=0, y=4)
        assert distance(a, b) == 20.0

    def test_diagonal_distance(self):
        """Diagonal 3-4-5 triangle: 3*5=15ft, 4*5=20ft, hyp=25ft."""
        a = Position(x=0, y=0)
        b = Position(x=3, y=4)
        d = distance(a, b)
        assert d == 25.0

    def test_single_square_diagonal(self):
        """One square diagonal ~ 7.07ft, rounds to 5ft."""
        a = Position(x=0, y=0)
        b = Position(x=1, y=1)
        d = distance(a, b)
        assert d == 5.0  # sqrt(2)*5 = 7.07, rounds to nearest 5 = 5

    def test_two_square_diagonal(self):
        """Two squares diagonal ~ 14.14ft, rounds to 15ft."""
        a = Position(x=0, y=0)
        b = Position(x=2, y=2)
        d = distance(a, b)
        assert d == 15.0  # sqrt(8)*5 = 14.14, rounds to 15

    def test_distance_is_symmetric(self):
        a = Position(x=1, y=2)
        b = Position(x=5, y=8)
        assert distance(a, b) == distance(b, a)

    def test_adjacent_positions(self):
        a = Position(x=5, y=5)
        b = Position(x=6, y=5)
        assert distance(a, b) == 5.0

    def test_long_range(self):
        a = Position(x=0, y=0)
        b = Position(x=12, y=0)
        assert distance(a, b) == 60.0


# ===================================================================
# Proximity enum
# ===================================================================

class TestProximity:
    """Tests for the Proximity enum and conversion functions."""

    def test_proximity_values(self):
        assert Proximity.ADJACENT == "adjacent"
        assert Proximity.NEARBY == "nearby"
        assert Proximity.FAR == "far"
        assert Proximity.DISTANT == "distant"

    def test_proximity_from_distance_adjacent(self):
        assert proximity_from_distance(0) == Proximity.ADJACENT
        assert proximity_from_distance(5) == Proximity.ADJACENT

    def test_proximity_from_distance_nearby(self):
        assert proximity_from_distance(10) == Proximity.NEARBY
        assert proximity_from_distance(15) == Proximity.NEARBY
        assert proximity_from_distance(20) == Proximity.NEARBY

    def test_proximity_from_distance_far(self):
        assert proximity_from_distance(25) == Proximity.FAR
        assert proximity_from_distance(60) == Proximity.FAR

    def test_proximity_from_distance_distant(self):
        assert proximity_from_distance(61) == Proximity.DISTANT
        assert proximity_from_distance(120) == Proximity.DISTANT

    def test_proximity_max_feet(self):
        assert proximity_max_feet(Proximity.ADJACENT) == 5.0
        assert proximity_max_feet(Proximity.NEARBY) == 20.0
        assert proximity_max_feet(Proximity.FAR) == 60.0
        assert proximity_max_feet(Proximity.DISTANT) == float("inf")


# ===================================================================
# AoE Shapes
# ===================================================================

class TestSphere:
    """Tests for Sphere AoE shape."""

    def test_origin_is_inside(self):
        s = Sphere(origin=Position(x=5, y=5), radius=20)
        assert s.contains(Position(x=5, y=5))

    def test_within_radius(self):
        s = Sphere(origin=Position(x=5, y=5), radius=15)
        # 2 squares away = 10ft, within 15ft radius
        assert s.contains(Position(x=7, y=5))

    def test_at_radius_boundary(self):
        s = Sphere(origin=Position(x=0, y=0), radius=25)
        # 3-4-5 triangle = 25ft exactly
        assert s.contains(Position(x=3, y=4))

    def test_outside_radius(self):
        s = Sphere(origin=Position(x=5, y=5), radius=10)
        # 4 squares away = 20ft, outside 10ft radius
        assert not s.contains(Position(x=9, y=5))

    def test_radius_feet(self):
        s = Sphere(origin=Position(x=0, y=0), radius=30)
        assert s.radius_feet() == 30

    def test_repr(self):
        s = Sphere(origin=Position(x=1, y=2), radius=20)
        assert "Sphere" in repr(s)


class TestCube:
    """Tests for Cube AoE shape."""

    def test_origin_is_inside(self):
        c = Cube(origin=Position(x=5, y=5), size=20)
        assert c.contains(Position(x=5, y=5))

    def test_within_cube(self):
        c = Cube(origin=Position(x=5, y=5), size=20)
        # 1 square away from centre, well within 10ft half-size
        assert c.contains(Position(x=6, y=5))

    def test_at_cube_edge(self):
        c = Cube(origin=Position(x=5, y=5), size=20)
        # 2 squares = 10ft from centre, half-size is 10ft
        assert c.contains(Position(x=7, y=5))

    def test_outside_cube(self):
        c = Cube(origin=Position(x=5, y=5), size=10)
        # 4 squares = 20ft from centre, half-size is 5ft
        assert not c.contains(Position(x=9, y=5))

    def test_corner_within(self):
        """A position at the corner of the cube should be inside."""
        c = Cube(origin=Position(x=5, y=5), size=20)
        # Diagonal 2 squares in each direction = within 10ft half-size on each axis
        assert c.contains(Position(x=7, y=7))

    def test_corner_outside(self):
        """Position far from the corner should be outside."""
        c = Cube(origin=Position(x=5, y=5), size=10)
        assert not c.contains(Position(x=8, y=8))


class TestCone:
    """Tests for Cone AoE shape."""

    def test_origin_is_inside(self):
        c = Cone(origin=Position(x=5, y=5), direction_degrees=0, length=30)
        assert c.contains(Position(x=5, y=5))

    def test_straight_ahead(self):
        """Position directly in the cone's direction should be inside."""
        c = Cone(origin=Position(x=0, y=0), direction_degrees=0, length=30)
        # 4 squares east = 20ft, within 30ft cone pointing east
        assert c.contains(Position(x=4, y=0))

    def test_within_angle(self):
        """Position slightly off-axis but within the cone angle."""
        c = Cone(origin=Position(x=0, y=0), direction_degrees=0, length=30)
        # 3 squares east, 2 north: angle ~33.7 deg, within 53 deg half-angle
        assert c.contains(Position(x=3, y=2))

    def test_outside_angle(self):
        """Position outside the cone angle."""
        c = Cone(origin=Position(x=0, y=0), direction_degrees=0, length=30)
        # Directly north (90 degrees off-axis)
        assert not c.contains(Position(x=0, y=3))

    def test_beyond_length(self):
        """Position in the right direction but past the cone's length."""
        c = Cone(origin=Position(x=0, y=0), direction_degrees=0, length=15)
        # 6 squares east = 30ft, past 15ft cone
        assert not c.contains(Position(x=6, y=0))

    def test_cone_north(self):
        """Cone pointing north (90 degrees)."""
        c = Cone(origin=Position(x=5, y=5), direction_degrees=90, length=30)
        # Position north of origin (positive y in screen coords = higher on grid)
        # But direction 90 = north in math coords (positive y)
        assert c.contains(Position(x=5, y=9))

    def test_cone_south(self):
        """Cone pointing south (270 degrees)."""
        c = Cone(origin=Position(x=5, y=5), direction_degrees=270, length=30)
        assert c.contains(Position(x=5, y=1))


class TestLine:
    """Tests for Line AoE shape."""

    def test_along_line(self):
        """Position directly along the line should be inside."""
        line = Line(origin=Position(x=0, y=0), direction_degrees=0, length=30, width=5)
        assert line.contains(Position(x=3, y=0))

    def test_at_edge_of_width(self):
        """Position at the edge of the line's width."""
        line = Line(origin=Position(x=0, y=5), direction_degrees=0, length=60, width=10)
        # 1 square north, 3 squares east: perpendicular dist = 2.5ft (centre of square)
        # Width/2 = 5ft, 2.5ft < 5ft, so inside
        assert line.contains(Position(x=3, y=6))

    def test_outside_width(self):
        """Position outside the line's width."""
        line = Line(origin=Position(x=0, y=0), direction_degrees=0, length=60, width=5)
        # 3 squares north = 17.5ft perpendicular, width/2 = 2.5ft
        assert not line.contains(Position(x=3, y=3))

    def test_beyond_length(self):
        """Position beyond the line's length."""
        line = Line(origin=Position(x=0, y=0), direction_degrees=0, length=15, width=5)
        # 5 squares east = 27.5ft from centre of origin square, past 15ft
        assert not line.contains(Position(x=5, y=0))

    def test_behind_origin(self):
        """Position behind the origin (negative along-direction) should be outside."""
        line = Line(origin=Position(x=5, y=5), direction_degrees=0, length=30, width=5)
        # Position west of origin
        assert not line.contains(Position(x=2, y=5))

    def test_line_diagonal(self):
        """Line pointing at 45 degrees."""
        line = Line(origin=Position(x=0, y=0), direction_degrees=45, length=50, width=10)
        # Position at (3, 3) is along the 45-degree direction
        assert line.contains(Position(x=3, y=3))


class TestCylinder:
    """Tests for Cylinder AoE shape."""

    def test_within_radius(self):
        cyl = Cylinder(origin=Position(x=5, y=5), radius=20, height=40)
        assert cyl.contains(Position(x=7, y=5))

    def test_at_radius_boundary(self):
        cyl = Cylinder(origin=Position(x=0, y=0), radius=25, height=20)
        assert cyl.contains(Position(x=3, y=4))

    def test_outside_radius(self):
        cyl = Cylinder(origin=Position(x=5, y=5), radius=10, height=20)
        assert not cyl.contains(Position(x=10, y=10))

    def test_height_stored(self):
        cyl = Cylinder(origin=Position(x=0, y=0), radius=15, height=40)
        assert cyl.height == 40

    def test_default_height(self):
        cyl = Cylinder(origin=Position(x=0, y=0), radius=15)
        assert cyl.height == 20.0

    def test_radius_feet(self):
        cyl = Cylinder(origin=Position(x=0, y=0), radius=30, height=20)
        assert cyl.radius_feet() == 30


# ===================================================================
# calculate_aoe_targets
# ===================================================================

class TestCalculateAoeTargets:
    """Tests for the calculate_aoe_targets function."""

    def test_targets_within_sphere(self):
        chars = [
            _make_char("Alice", Position(x=5, y=5)),
            _make_char("Bob", Position(x=6, y=5)),
            _make_char("Eve", Position(x=20, y=20)),
        ]
        sphere = Sphere(origin=Position(x=5, y=5), radius=10)
        targets = calculate_aoe_targets(sphere, chars)
        assert "Alice" in targets
        assert "Bob" in targets
        assert "Eve" not in targets

    def test_no_targets(self):
        chars = [
            _make_char("Alice", Position(x=0, y=0)),
        ]
        sphere = Sphere(origin=Position(x=20, y=20), radius=5)
        targets = calculate_aoe_targets(sphere, chars)
        assert targets == []

    def test_all_targets(self):
        chars = [
            _make_char("Alice", Position(x=5, y=5)),
            _make_char("Bob", Position(x=5, y=6)),
        ]
        sphere = Sphere(origin=Position(x=5, y=5), radius=20)
        targets = calculate_aoe_targets(sphere, chars)
        assert len(targets) == 2

    def test_proximity_fallback_adjacent(self):
        """Participants without positions use proximity fallback."""
        p = _ProximityParticipant("No-Grid", Proximity.ADJACENT)
        sphere = Sphere(origin=Position(x=0, y=0), radius=10)
        targets = calculate_aoe_targets(sphere, [p])
        # Adjacent max = 5ft, within 10ft radius
        assert "No-Grid" in targets

    def test_proximity_fallback_distant(self):
        """Distant creatures should not be caught by a small AoE."""
        p = _ProximityParticipant("Far-Away", Proximity.DISTANT)
        sphere = Sphere(origin=Position(x=0, y=0), radius=20)
        targets = calculate_aoe_targets(sphere, [p])
        # Distant max = inf, not <= 20ft
        assert "Far-Away" not in targets

    def test_proximity_fallback_string(self):
        """Proximity can be a plain string value."""
        p = _ProximityParticipant("Str-Prox", "nearby")
        sphere = Sphere(origin=Position(x=0, y=0), radius=30)
        targets = calculate_aoe_targets(sphere, [p])
        # Nearby max = 20ft, within 30ft
        assert "Str-Prox" in targets

    def test_no_position_no_proximity(self):
        """Characters without position or proximity are skipped."""
        char = _make_char("Ghost", None)
        sphere = Sphere(origin=Position(x=0, y=0), radius=100)
        targets = calculate_aoe_targets(sphere, [char])
        assert targets == []

    def test_mixed_positioned_and_proximity(self):
        """Mix of characters with grid positions and proximity participants."""
        alice = _make_char("Alice", Position(x=5, y=5))
        bob = _ProximityParticipant("Bob", Proximity.ADJACENT)
        eve = _make_char("Eve", Position(x=100, y=100))

        sphere = Sphere(origin=Position(x=5, y=5), radius=15)
        targets = calculate_aoe_targets(sphere, [alice, bob, eve])
        assert "Alice" in targets
        assert "Bob" in targets
        assert "Eve" not in targets

    def test_cube_targets(self):
        chars = [
            _make_char("Inside", Position(x=5, y=5)),
            _make_char("Outside", Position(x=20, y=20)),
        ]
        cube = Cube(origin=Position(x=5, y=5), size=20)
        targets = calculate_aoe_targets(cube, chars)
        assert "Inside" in targets
        assert "Outside" not in targets

    def test_line_targets(self):
        chars = [
            _make_char("InLine", Position(x=3, y=0)),
            _make_char("Beside", Position(x=3, y=5)),
        ]
        line = Line(origin=Position(x=0, y=0), direction_degrees=0, length=30, width=5)
        targets = calculate_aoe_targets(line, chars)
        assert "InLine" in targets
        assert "Beside" not in targets


# ===================================================================
# set_positions
# ===================================================================

class TestSetPositions:
    """Tests for the set_positions function."""

    def test_bulk_set(self):
        chars = [_make_char("A"), _make_char("B"), _make_char("C")]
        positions = {
            "A": Position(x=0, y=0),
            "B": Position(x=5, y=5),
        }
        result = set_positions(chars, positions)
        assert result["A"] == Position(x=0, y=0)
        assert result["B"] == Position(x=5, y=5)
        assert result["C"] is None

    def test_overwrites_existing(self):
        char = _make_char("Hero", Position(x=1, y=1))
        positions = {"Hero": Position(x=10, y=10)}
        result = set_positions([char], positions)
        assert result["Hero"] == Position(x=10, y=10)
        assert char.position == Position(x=10, y=10)

    def test_empty_positions_dict(self):
        chars = [_make_char("A", Position(x=3, y=3))]
        result = set_positions(chars, {})
        # Position unchanged
        assert result["A"] == Position(x=3, y=3)


# ===================================================================
# move_participant
# ===================================================================

class TestMoveParticipant:
    """Tests for the move_participant function."""

    def test_valid_move(self):
        char = _make_char("Runner", Position(x=0, y=0), speed=30)
        result = move_participant(char, Position(x=6, y=0))
        assert result.success is True
        assert result.distance_moved == 30.0
        assert char.position == Position(x=6, y=0)

    def test_move_exceeds_speed(self):
        char = _make_char("Slow", Position(x=0, y=0), speed=20)
        result = move_participant(char, Position(x=6, y=0))
        assert result.success is False
        assert "cannot move" in result.message
        # Position should NOT change
        assert char.position == Position(x=0, y=0)

    def test_move_exact_speed(self):
        char = _make_char("Exact", Position(x=0, y=0), speed=30)
        result = move_participant(char, Position(x=6, y=0))
        assert result.success is True
        assert result.distance_moved == 30.0

    def test_move_from_none(self):
        """Moving a character with no position should place them."""
        char = _make_char("New", None, speed=30)
        result = move_participant(char, Position(x=5, y=5))
        assert result.success is True
        assert result.old_position is None
        assert char.position == Position(x=5, y=5)

    def test_move_to_same_position(self):
        char = _make_char("Stay", Position(x=3, y=3), speed=30)
        result = move_participant(char, Position(x=3, y=3))
        assert result.success is True
        assert result.distance_moved == 0.0

    def test_override_speed(self):
        """The speed parameter should override character's speed."""
        char = _make_char("Dashing", Position(x=0, y=0), speed=30)
        # With Dash action, speed doubles
        result = move_participant(char, Position(x=12, y=0), speed=60)
        assert result.success is True
        assert result.distance_moved == 60.0

    def test_override_speed_denied(self):
        char = _make_char("Dashing", Position(x=0, y=0), speed=30)
        result = move_participant(char, Position(x=12, y=0), speed=50)
        assert result.success is False

    def test_movement_result_fields(self):
        char = _make_char("Test", Position(x=2, y=2), speed=30)
        result = move_participant(char, Position(x=4, y=2))
        assert result.name == "Test"
        assert result.old_position == Position(x=2, y=2)
        assert result.new_position == Position(x=4, y=2)
        assert result.speed == 30


# ===================================================================
# Character model integration
# ===================================================================

class TestCharacterPositionField:
    """Tests for Position field on the Character model."""

    def test_position_defaults_to_none(self):
        char = Character(
            name="Default",
            character_class=CharacterClass(name="Wizard", level=1),
            race=Race(name="Elf"),
        )
        assert char.position is None

    def test_position_can_be_set(self):
        char = Character(
            name="Placed",
            character_class=CharacterClass(name="Wizard", level=1),
            race=Race(name="Elf"),
        )
        char.position = Position(x=5, y=10)
        assert char.position == Position(x=5, y=10)

    def test_position_serialization(self):
        """Character with position should serialize correctly."""
        char = Character(
            name="Serial",
            character_class=CharacterClass(name="Wizard", level=1),
            race=Race(name="Elf"),
        )
        char.position = Position(x=3, y=7)
        data = char.model_dump()
        assert data["position"] == {"x": 3, "y": 7}

    def test_position_none_serialization(self):
        """Character without position should serialize to None."""
        char = Character(
            name="NoPos",
            character_class=CharacterClass(name="Wizard", level=1),
            race=Race(name="Elf"),
        )
        data = char.model_dump()
        assert data["position"] is None

    def test_position_deserialization(self):
        """Character should deserialize position from dict."""
        data = {
            "name": "FromDict",
            "character_class": {"name": "Fighter", "level": 1},
            "race": {"name": "Dwarf"},
            "position": {"x": 8, "y": 12},
        }
        char = Character.model_validate(data)
        assert char.position == Position(x=8, y=12)

    def test_backward_compatibility_no_position_key(self):
        """Old character data without 'position' key should default to None."""
        data = {
            "name": "OldChar",
            "character_class": {"name": "Rogue", "level": 3},
            "race": {"name": "Halfling"},
        }
        char = Character.model_validate(data)
        assert char.position is None


# ===================================================================
# Edge cases
# ===================================================================

class TestEdgeCases:
    """Edge case tests for positioning system."""

    def test_distance_large_coordinates(self):
        a = Position(x=0, y=0)
        b = Position(x=100, y=0)
        assert distance(a, b) == 500.0

    def test_sphere_zero_radius(self):
        s = Sphere(origin=Position(x=5, y=5), radius=0)
        assert s.contains(Position(x=5, y=5))
        assert not s.contains(Position(x=6, y=5))

    def test_cube_zero_size(self):
        """A zero-size cube should only contain positions at the exact centre."""
        c = Cube(origin=Position(x=5, y=5), size=0)
        # The centre of square (5,5) is (27.5, 27.5), and half=0,
        # so only exact centre matches -- which (5,5) itself is
        assert c.contains(Position(x=5, y=5))
        assert not c.contains(Position(x=6, y=5))

    def test_empty_participants_list(self):
        sphere = Sphere(origin=Position(x=0, y=0), radius=100)
        assert calculate_aoe_targets(sphere, []) == []

    def test_all_participants_no_position(self):
        chars = [_make_char("A"), _make_char("B")]
        sphere = Sphere(origin=Position(x=0, y=0), radius=100)
        assert calculate_aoe_targets(sphere, chars) == []

    def test_proximity_invalid_string(self):
        """Invalid proximity string should be skipped gracefully."""
        p = _ProximityParticipant("Bad-Prox", "invalid_value")
        sphere = Sphere(origin=Position(x=0, y=0), radius=100)
        targets = calculate_aoe_targets(sphere, [p])
        assert targets == []

    def test_set_positions_unknown_character(self):
        """Positions for characters not in the list should be ignored."""
        chars = [_make_char("A")]
        result = set_positions(chars, {"A": Position(x=1, y=1), "Z": Position(x=9, y=9)})
        assert "A" in result
        assert "Z" not in result

    def test_move_zero_speed(self):
        """Character with 0 speed should not be able to move."""
        char = _make_char("Frozen", Position(x=0, y=0), speed=0)
        result = move_participant(char, Position(x=1, y=0))
        assert result.success is False

    def test_move_zero_speed_stay(self):
        """Character with 0 speed staying in place should succeed."""
        char = _make_char("Frozen", Position(x=0, y=0), speed=0)
        result = move_participant(char, Position(x=0, y=0))
        assert result.success is True
