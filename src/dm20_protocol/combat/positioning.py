"""
Positioning and Area-of-Effect engine for D&D 5e combat.

Provides grid-based position tracking, distance calculations, AoE shape
definitions, and utility functions for determining which creatures are
affected by area effects. Also includes a relative positioning fallback
(Proximity enum) for when exact grid coordinates are not available.

Grid convention:
- Each square is 5 feet.
- Position(0, 0) is the top-left corner of the battle area.
- Diagonal movement costs 5ft per square (5e standard variant).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from dm20_protocol.models import Character


# ---------------------------------------------------------------------------
# Position model
# ---------------------------------------------------------------------------

class Position(BaseModel):
    """Grid-based position in a combat area.

    Coordinates are in grid squares. Multiply by 5 for feet.
    Position(0, 0) is the top-left of the battle area.
    """

    x: int = Field(description="Horizontal grid coordinate (0 = left edge)")
    y: int = Field(description="Vertical grid coordinate (0 = top edge)")

    def feet(self) -> tuple[float, float]:
        """Return position in feet (centre of the square)."""
        return (self.x * 5 + 2.5, self.y * 5 + 2.5)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Position):
            return NotImplemented
        return self.x == other.x and self.y == other.y

    def __hash__(self) -> int:
        return hash((self.x, self.y))

    def __repr__(self) -> str:
        return f"Position(x={self.x}, y={self.y})"


# ---------------------------------------------------------------------------
# Proximity enum (relative positioning fallback)
# ---------------------------------------------------------------------------

class Proximity(str, Enum):
    """Relative distance categories for when exact positions are unavailable.

    Used as a fallback so AoE and range checks still work without a grid.
    """

    ADJACENT = "adjacent"    # 0-5 ft  (melee range)
    NEARBY = "nearby"        # 10-20 ft
    FAR = "far"              # 25-60 ft
    DISTANT = "distant"      # 60+ ft


def proximity_from_distance(feet: float) -> Proximity:
    """Convert a distance in feet to a Proximity category."""
    if feet <= 5:
        return Proximity.ADJACENT
    elif feet <= 20:
        return Proximity.NEARBY
    elif feet <= 60:
        return Proximity.FAR
    else:
        return Proximity.DISTANT


def proximity_max_feet(prox: Proximity) -> float:
    """Return the maximum distance in feet for a given proximity band."""
    return {
        Proximity.ADJACENT: 5.0,
        Proximity.NEARBY: 20.0,
        Proximity.FAR: 60.0,
        Proximity.DISTANT: float("inf"),
    }[prox]


# ---------------------------------------------------------------------------
# Distance calculation
# ---------------------------------------------------------------------------

def distance(a: Position, b: Position) -> float:
    """Calculate the distance in feet between two grid positions.

    Uses Euclidean distance for accuracy, then rounds down to the nearest
    5-foot increment (consistent with how 5e measures distances on a grid).

    Args:
        a: First position.
        b: Second position.

    Returns:
        Distance in feet (always a multiple of 5, minimum 0).
    """
    dx = abs(a.x - b.x)
    dy = abs(a.y - b.y)
    # Euclidean distance in grid squares, then convert to feet
    raw_feet = math.sqrt(dx ** 2 + dy ** 2) * 5
    # Round to nearest 5ft increment
    return round(raw_feet / 5) * 5.0


# ---------------------------------------------------------------------------
# AoE shape base class and implementations
# ---------------------------------------------------------------------------

class AoEShape(ABC):
    """Abstract base class for Area-of-Effect shapes.

    All shapes define a region in grid space and expose a `contains(pos)`
    method that returns True if a given Position falls within the area.
    """

    @abstractmethod
    def contains(self, pos: Position) -> bool:
        """Check whether *pos* is inside this AoE area."""
        ...

    @abstractmethod
    def radius_feet(self) -> float:
        """Return the effective reach of this shape in feet (for proximity fallback)."""
        ...


class Sphere(AoEShape):
    """Spherical (circular on a 2D grid) area of effect.

    Defined by an origin point and a radius in feet. A position is inside
    the sphere if its distance from the origin is less than or equal to
    the radius.

    Args:
        origin: Centre of the sphere on the grid.
        radius: Radius in feet.
    """

    def __init__(self, origin: Position, radius: float) -> None:
        self.origin = origin
        self.radius = radius

    def contains(self, pos: Position) -> bool:
        return distance(self.origin, pos) <= self.radius

    def radius_feet(self) -> float:
        return self.radius

    def __repr__(self) -> str:
        return f"Sphere(origin={self.origin}, radius={self.radius}ft)"


class Cube(AoEShape):
    """Cube (square on a 2D grid) area of effect.

    Defined by an origin point (one corner or centre depending on spell)
    and a size (side length in feet). By default the origin is the centre
    of the cube, consistent with most 5e spell descriptions.

    Args:
        origin: Centre of the cube on the grid.
        size: Side length in feet.
    """

    def __init__(self, origin: Position, size: float) -> None:
        self.origin = origin
        self.size = size

    def contains(self, pos: Position) -> bool:
        half = self.size / 2.0
        ox_ft, oy_ft = self.origin.feet()
        px_ft, py_ft = pos.feet()
        return abs(px_ft - ox_ft) <= half and abs(py_ft - oy_ft) <= half

    def radius_feet(self) -> float:
        # Effective reach is half the diagonal
        return self.size / 2.0

    def __repr__(self) -> str:
        return f"Cube(origin={self.origin}, size={self.size}ft)"


class Cone(AoEShape):
    """Cone-shaped area of effect.

    Defined by an origin point, a direction (angle in degrees, 0 = right/east,
    counter-clockwise), and a length in feet. The cone fans out from the
    origin with a 53-degree half-angle (standard 5e cone: width at the far
    end equals the length).

    Args:
        origin: The point of the cone (where the caster stands).
        direction_degrees: Direction the cone points, in degrees. 0 = east,
            90 = north, 180 = west, 270 = south.
        length: Length of the cone in feet.
    """

    HALF_ANGLE_DEG: float = 53.0  # 5e cone: width at end == length

    def __init__(self, origin: Position, direction_degrees: float, length: float) -> None:
        self.origin = origin
        self.direction_degrees = direction_degrees
        self.length = length

    def contains(self, pos: Position) -> bool:
        if pos == self.origin:
            return True

        ox, oy = self.origin.feet()
        px, py = pos.feet()
        dx = px - ox
        dy = py - oy
        dist = math.sqrt(dx ** 2 + dy ** 2)

        if dist > self.length:
            return False

        # Angle from origin to pos (atan2 uses y,x)
        angle_to_pos = math.degrees(math.atan2(dy, dx)) % 360
        dir_norm = self.direction_degrees % 360

        # Angular difference (smallest arc)
        diff = abs(angle_to_pos - dir_norm)
        if diff > 180:
            diff = 360 - diff

        return diff <= self.HALF_ANGLE_DEG

    def radius_feet(self) -> float:
        return self.length

    def __repr__(self) -> str:
        return (
            f"Cone(origin={self.origin}, direction={self.direction_degrees}deg, "
            f"length={self.length}ft)"
        )


class Line(AoEShape):
    """Line-shaped area of effect.

    Defined by an origin, a direction (degrees), a length, and a width in
    feet. The line extends from the origin in the specified direction.

    Args:
        origin: Starting position of the line.
        direction_degrees: Direction the line extends. 0 = east, 90 = north.
        length: Length of the line in feet.
        width: Width of the line in feet (default 5).
    """

    def __init__(
        self,
        origin: Position,
        direction_degrees: float,
        length: float,
        width: float = 5.0,
    ) -> None:
        self.origin = origin
        self.direction_degrees = direction_degrees
        self.length = length
        self.width = width

    def contains(self, pos: Position) -> bool:
        ox, oy = self.origin.feet()
        px, py = pos.feet()
        dx = px - ox
        dy = py - oy

        # Rotate so the line direction becomes the positive x-axis
        rad = math.radians(self.direction_degrees)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        # Project onto line-local axes
        along = dx * cos_a + dy * sin_a   # distance along the line
        across = -dx * sin_a + dy * cos_a  # perpendicular distance

        half_w = self.width / 2.0
        return 0 <= along <= self.length and abs(across) <= half_w

    def radius_feet(self) -> float:
        return self.length

    def __repr__(self) -> str:
        return (
            f"Line(origin={self.origin}, direction={self.direction_degrees}deg, "
            f"length={self.length}ft, width={self.width}ft)"
        )


class Cylinder(AoEShape):
    """Cylindrical area of effect.

    Behaves identically to a Sphere on a 2D grid (height is recorded but
    does not affect 2D containment). Provided for completeness and future
    3D support.

    Args:
        origin: Centre of the cylinder base on the grid.
        radius: Radius in feet.
        height: Height in feet (stored but not used for 2D containment).
    """

    def __init__(self, origin: Position, radius: float, height: float = 20.0) -> None:
        self.origin = origin
        self.radius = radius
        self.height = height

    def contains(self, pos: Position) -> bool:
        return distance(self.origin, pos) <= self.radius

    def radius_feet(self) -> float:
        return self.radius

    def __repr__(self) -> str:
        return (
            f"Cylinder(origin={self.origin}, radius={self.radius}ft, "
            f"height={self.height}ft)"
        )


# ---------------------------------------------------------------------------
# Target calculation
# ---------------------------------------------------------------------------

def calculate_aoe_targets(
    shape: AoEShape,
    participants: list["Character"],
) -> list[str]:
    """Determine which participants are affected by an AoE shape.

    For participants **with** a position set, the shape's `contains()` method
    is used for precise geometric checking.

    For participants **without** a position, the relative proximity fallback
    is used: if the participant has a `proximity` attribute (set by the DM)
    and its maximum distance falls within the shape's effective radius, the
    participant is considered affected.

    Args:
        shape: The AoE shape to check against.
        participants: List of Character objects (or any object with `name`
            and optionally `position`/`proximity` attributes).

    Returns:
        A list of names of affected participants.
    """
    affected: list[str] = []
    effective_radius = shape.radius_feet()

    for participant in participants:
        pos = getattr(participant, "position", None)
        if pos is not None:
            if shape.contains(pos):
                affected.append(participant.name)
        else:
            # Proximity fallback
            prox = getattr(participant, "proximity", None)
            if prox is not None:
                if isinstance(prox, str):
                    try:
                        prox = Proximity(prox)
                    except ValueError:
                        continue
                max_ft = proximity_max_feet(prox)
                if max_ft <= effective_radius:
                    affected.append(participant.name)

    return affected


# ---------------------------------------------------------------------------
# Position management utilities
# ---------------------------------------------------------------------------

def set_positions(
    participants: list["Character"],
    positions: dict[str, Position],
) -> dict[str, Position | None]:
    """Bulk-set positions for combat participants.

    Args:
        participants: List of Character objects.
        positions: Mapping of character name -> Position.

    Returns:
        Dict of character name -> assigned Position (None if not in the map).
    """
    result: dict[str, Position | None] = {}
    for participant in participants:
        new_pos = positions.get(participant.name)
        if new_pos is not None:
            participant.position = new_pos  # type: ignore[attr-defined]
        result[participant.name] = getattr(participant, "position", None)
    return result


class MovementResult(BaseModel):
    """Result of a movement validation attempt."""

    success: bool
    name: str
    old_position: Position | None = None
    new_position: Position | None = None
    distance_moved: float = 0.0
    speed: float = 0.0
    message: str = ""


def move_participant(
    participant: "Character",
    new_position: Position,
    speed: float | None = None,
) -> MovementResult:
    """Move a participant to a new position, validating against their speed.

    If *speed* is not provided, the participant's own `speed` attribute is
    used (defaulting to 30 ft if not set).

    Args:
        participant: The character to move.
        new_position: Target grid position.
        speed: Maximum movement speed in feet. Overrides character speed.

    Returns:
        A MovementResult indicating success or failure with details.
    """
    current_pos: Position | None = getattr(participant, "position", None)
    char_speed = speed if speed is not None else getattr(participant, "speed", 30)

    if current_pos is None:
        # No current position -- just assign the new one
        participant.position = new_position  # type: ignore[attr-defined]
        return MovementResult(
            success=True,
            name=participant.name,
            old_position=None,
            new_position=new_position,
            distance_moved=0.0,
            speed=char_speed,
            message=f"{participant.name} placed at {new_position}.",
        )

    dist = distance(current_pos, new_position)

    if dist > char_speed:
        return MovementResult(
            success=False,
            name=participant.name,
            old_position=current_pos,
            new_position=new_position,
            distance_moved=dist,
            speed=char_speed,
            message=(
                f"{participant.name} cannot move {dist:.0f}ft "
                f"(speed {char_speed:.0f}ft). Movement denied."
            ),
        )

    participant.position = new_position  # type: ignore[attr-defined]
    return MovementResult(
        success=True,
        name=participant.name,
        old_position=current_pos,
        new_position=new_position,
        distance_moved=dist,
        speed=char_speed,
        message=(
            f"{participant.name} moved {dist:.0f}ft from "
            f"{current_pos} to {new_position}."
        ),
    )
