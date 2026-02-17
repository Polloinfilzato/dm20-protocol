"""
ASCII Tactical Map system for D&D 5e combat.

Provides a text-based tactical map that renders combat scenes as monospaced
ASCII art. Includes a grid model with terrain features, token placement for
combatants, movement validation with speed limits and difficult terrain,
opportunity attack detection, and a rendering function for CLI/chat display.

Grid convention:
- Each square is 5 feet.
- Position(0, 0) is the top-left corner of the grid.
- Columns are labelled A-Z, rows are labelled 1-N.
"""

from __future__ import annotations

import random as _random
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from dm20_protocol.combat.positioning import AoEShape, Position, distance


# ---------------------------------------------------------------------------
# Terrain enum
# ---------------------------------------------------------------------------

class Terrain(str, Enum):
    """Terrain types for grid cells."""

    OPEN = "open"
    WALL = "wall"
    DOOR = "door"
    DIFFICULT_TERRAIN = "difficult_terrain"
    OBSTACLE = "obstacle"
    WATER = "water"


# Map from terrain to single-/multi-char display symbol
TERRAIN_SYMBOLS: dict[Terrain, str] = {
    Terrain.OPEN: ".",
    Terrain.WALL: "#",
    Terrain.DOOR: "D",
    Terrain.DIFFICULT_TERRAIN: "~",
    Terrain.OBSTACLE: "X",
    Terrain.WATER: "~",  # water uses the same tilde; legend distinguishes
}

# Human-readable labels for the legend
TERRAIN_LABELS: dict[Terrain, str] = {
    Terrain.OPEN: "Open",
    Terrain.WALL: "Wall",
    Terrain.DOOR: "Door",
    Terrain.DIFFICULT_TERRAIN: "Difficult",
    Terrain.OBSTACLE: "Obstacle",
    Terrain.WATER: "Water",
}


# ---------------------------------------------------------------------------
# Cell model
# ---------------------------------------------------------------------------

class Cell(BaseModel):
    """A single cell on the tactical grid."""

    terrain: Terrain = Terrain.OPEN
    occupant: str | None = Field(
        default=None,
        description="Name of the combatant occupying this cell, or None.",
    )

    model_config = {"use_enum_values": False}


# ---------------------------------------------------------------------------
# Participant info (lightweight, for rendering)
# ---------------------------------------------------------------------------

class ParticipantInfo(BaseModel):
    """Lightweight participant descriptor for the map system.

    This decouples the map from the full Character model so that NPC stat
    blocks and monsters can also be placed on the grid.
    """

    name: str
    position: Position | None = None
    side: str = Field(
        default="player",
        description="Participant side: 'player', 'enemy', or 'ally'.",
    )
    label: str = Field(
        default="",
        description="Auto-assigned short label (e.g. P1, E2, A3).",
    )
    character_class: str = ""
    speed: int = 30
    has_disengage: bool = Field(
        default=False,
        description="True if the participant used the Disengage action this turn.",
    )


# ---------------------------------------------------------------------------
# TacticalGrid
# ---------------------------------------------------------------------------

class TacticalGrid(BaseModel):
    """A 2D grid of cells representing a tactical combat map.

    Stored as a flat list in row-major order for efficient serialisation.
    Access individual cells with ``at(x, y)`` and ``set(x, y, cell)``.

    Args:
        width: Number of columns (x-axis).
        height: Number of rows (y-axis).
        cells: Flat list of Cell objects (row-major). Auto-populated with
            open terrain if not provided.
    """

    width: int = Field(default=20, ge=3, le=52, description="Grid width in squares")
    height: int = Field(default=20, ge=3, le=52, description="Grid height in squares")
    cells: list[Cell] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        """Populate cells with open terrain if empty."""
        expected = self.width * self.height
        if len(self.cells) == 0:
            self.cells = [Cell() for _ in range(expected)]
        elif len(self.cells) != expected:
            raise ValueError(
                f"Expected {expected} cells for {self.width}x{self.height} grid, "
                f"got {len(self.cells)}."
            )

    # -- Accessors -----------------------------------------------------------

    def _idx(self, x: int, y: int) -> int:
        """Convert (x, y) to flat index with bounds checking."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError(f"Position ({x}, {y}) out of bounds for {self.width}x{self.height} grid.")
        return y * self.width + x

    def at(self, x: int, y: int) -> Cell:
        """Return the Cell at grid position (x, y)."""
        return self.cells[self._idx(x, y)]

    def set(self, x: int, y: int, cell: Cell) -> None:
        """Replace the Cell at grid position (x, y)."""
        self.cells[self._idx(x, y)] = cell

    def set_terrain(self, x: int, y: int, terrain: Terrain) -> None:
        """Set the terrain type for a cell, preserving its occupant."""
        cell = self.at(x, y)
        cell.terrain = terrain

    def place_occupant(self, x: int, y: int, name: str) -> None:
        """Place a named occupant in a cell, clearing the previous occupant if any."""
        cell = self.at(x, y)
        cell.occupant = name

    def clear_occupant(self, x: int, y: int) -> None:
        """Remove the occupant from a cell."""
        cell = self.at(x, y)
        cell.occupant = None

    def is_passable(self, x: int, y: int) -> bool:
        """Return True if a creature can pass through this cell.

        Walls and obstacles block movement. Doors are passable (assumed open
        unless stated otherwise). Occupied cells are conditionally passable
        (checked separately in movement validation).
        """
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        terrain = self.at(x, y).terrain
        return terrain not in (Terrain.WALL, Terrain.OBSTACLE)

    def is_difficult(self, x: int, y: int) -> bool:
        """Return True if the cell has difficult terrain or water."""
        terrain = self.at(x, y).terrain
        return terrain in (Terrain.DIFFICULT_TERRAIN, Terrain.WATER)


# ---------------------------------------------------------------------------
# Token label assignment
# ---------------------------------------------------------------------------

def assign_labels(participants: list[ParticipantInfo]) -> None:
    """Auto-assign short labels (P1, E1, A1, ...) to participants.

    Labels are assigned based on side:
    - ``player`` -> P1, P2, ...
    - ``enemy``  -> E1, E2, ...
    - ``ally``   -> A1, A2, ...

    Labels are assigned in the order participants appear in the list.
    Already-assigned labels (non-empty) are left untouched.
    """
    counters: dict[str, int] = {"player": 0, "enemy": 0, "ally": 0}
    prefix_map: dict[str, str] = {"player": "P", "enemy": "E", "ally": "A"}

    for p in participants:
        if p.label:
            continue
        side = p.side if p.side in prefix_map else "ally"
        counters[side] += 1
        p.label = f"{prefix_map[side]}{counters[side]}"


# ---------------------------------------------------------------------------
# AsciiMapRenderer
# ---------------------------------------------------------------------------

class AsciiMapRenderer:
    """Renders a TacticalGrid and its participants as an ASCII string.

    The output includes:
    - Column headers (A, B, C, ...)
    - Row numbers (1, 2, 3, ...)
    - Terrain symbols and participant tokens
    - Optional AoE overlay (``*`` marker)
    - A legend explaining all symbols present on the map
    """

    AOE_MARKER = "*"

    @classmethod
    def render(
        cls,
        grid: TacticalGrid,
        participants: list[ParticipantInfo] | None = None,
        highlight_aoe: AoEShape | None = None,
    ) -> str:
        """Render the grid to a formatted ASCII string.

        Args:
            grid: The tactical grid to render.
            participants: List of combatants to display. Labels are
                auto-assigned if not already set.
            highlight_aoe: Optional AoE shape to overlay on the map.

        Returns:
            A single string with embedded newlines, suitable for
            monospaced display.
        """
        if participants is None:
            participants = []

        # Ensure labels are assigned
        assign_labels(participants)

        # Build a position -> label lookup
        pos_to_label: dict[tuple[int, int], str] = {}
        for p in participants:
            if p.position is not None:
                pos_to_label[(p.position.x, p.position.y)] = p.label

        # Build AoE set
        aoe_positions: set[tuple[int, int]] = set()
        if highlight_aoe is not None:
            for y in range(grid.height):
                for x in range(grid.width):
                    if highlight_aoe.contains(Position(x=x, y=y)):
                        aoe_positions.add((x, y))

        # Track which terrain types and labels appear for the legend
        used_terrains: set[Terrain] = set()
        used_labels: list[ParticipantInfo] = []

        # Determine column width: labels are 2-char, terrain is 1-char,
        # but we pad everything to 3 chars for alignment.
        col_width = 3

        # Row-number width (for alignment)
        row_num_width = max(2, len(str(grid.height)))

        lines: list[str] = []

        # --- Column header ---
        header_parts: list[str] = [" " * row_num_width]
        for x in range(grid.width):
            col_label = _col_label(x)
            header_parts.append(col_label.center(col_width))
        lines.append("".join(header_parts))

        # --- Grid rows ---
        for y in range(grid.height):
            row_num = str(y + 1).rjust(row_num_width)
            row_parts: list[str] = [row_num]
            for x in range(grid.width):
                cell = grid.at(x, y)
                used_terrains.add(cell.terrain)

                # Determine display content
                if (x, y) in pos_to_label:
                    display = pos_to_label[(x, y)]
                elif (x, y) in aoe_positions:
                    display = cls.AOE_MARKER
                else:
                    display = TERRAIN_SYMBOLS[cell.terrain]

                row_parts.append(display.center(col_width))
            lines.append("".join(row_parts))

        # --- Legend ---
        legend_parts: list[str] = []

        # Terrain entries (skip OPEN if it would just add clutter)
        for terrain in Terrain:
            if terrain in used_terrains and terrain != Terrain.OPEN:
                symbol = TERRAIN_SYMBOLS[terrain]
                legend_parts.append(f"{symbol} {TERRAIN_LABELS[terrain]}")

        if highlight_aoe is not None:
            legend_parts.append(f"{cls.AOE_MARKER} AoE")

        # Participant entries
        for p in participants:
            if p.position is not None:
                class_info = f" ({p.character_class})" if p.character_class else ""
                legend_parts.append(f"{p.label} {p.name}{class_info}")
                used_labels.append(p)

        if legend_parts:
            lines.append("")
            lines.append("Legend: " + " | ".join(legend_parts))

        return "\n".join(lines)


def _col_label(index: int) -> str:
    """Convert a column index (0-based) to a letter label (A, B, ..., Z, AA, ...)."""
    if index < 26:
        return chr(ord("A") + index)
    # For grids wider than 26, use double letters
    return chr(ord("A") + index // 26 - 1) + chr(ord("A") + index % 26)


# ---------------------------------------------------------------------------
# Movement validation
# ---------------------------------------------------------------------------

class MoveValidationResult(BaseModel):
    """Result of a grid-aware movement validation."""

    valid: bool
    reason: str = ""
    distance_feet: float = 0.0
    difficult_terrain_squares: int = 0
    effective_cost_feet: float = 0.0
    opportunity_attacks: list[str] = Field(default_factory=list)


def validate_move(
    participant: ParticipantInfo,
    from_pos: Position,
    to_pos: Position,
    grid: TacticalGrid,
    participants: list[ParticipantInfo] | None = None,
) -> MoveValidationResult:
    """Validate a proposed move on the tactical grid.

    Checks:
    1. Target cell is within grid bounds.
    2. Target cell is passable (not a wall or obstacle).
    3. Target cell is not occupied by an enemy.
    4. Path is not blocked by walls/obstacles (straight-line check).
    5. Total movement cost (including difficult terrain) does not exceed speed.
    6. Opportunity attacks triggered by leaving enemy threat range.

    Difficult terrain costs double movement (10ft per square instead of 5ft).

    Args:
        participant: The participant attempting to move.
        from_pos: Starting position.
        to_pos: Destination position.
        grid: The tactical grid.
        participants: All participants (for occupancy and OA checks).

    Returns:
        A MoveValidationResult with validity, reason, and details.
    """
    if participants is None:
        participants = []

    # Bounds check
    if not (0 <= to_pos.x < grid.width and 0 <= to_pos.y < grid.height):
        return MoveValidationResult(
            valid=False,
            reason=f"Destination ({to_pos.x}, {to_pos.y}) is out of bounds.",
        )

    # Passability check
    if not grid.is_passable(to_pos.x, to_pos.y):
        terrain = grid.at(to_pos.x, to_pos.y).terrain
        return MoveValidationResult(
            valid=False,
            reason=f"Destination ({to_pos.x}, {to_pos.y}) is blocked by {terrain.value}.",
        )

    # Occupancy check (enemies block, allies don't)
    dest_cell = grid.at(to_pos.x, to_pos.y)
    if dest_cell.occupant is not None and dest_cell.occupant != participant.name:
        # Determine if the occupant is an enemy
        occupant_info = _find_participant(dest_cell.occupant, participants)
        if occupant_info is not None and occupant_info.side != participant.side:
            return MoveValidationResult(
                valid=False,
                reason=f"Destination ({to_pos.x}, {to_pos.y}) is occupied by enemy {dest_cell.occupant}.",
            )

    # Path check: walk along the straight line from from_pos to to_pos
    path = _bresenham_line(from_pos.x, from_pos.y, to_pos.x, to_pos.y)

    # Check intermediate cells for walls/obstacles (skip start and end)
    for px, py in path[1:-1]:
        if not grid.is_passable(px, py):
            return MoveValidationResult(
                valid=False,
                reason=f"Path blocked by {grid.at(px, py).terrain.value} at ({px}, {py}).",
            )

    # Calculate movement cost
    dist_feet = distance(from_pos, to_pos)

    # Count difficult terrain squares along the path (excluding start)
    difficult_count = 0
    for px, py in path[1:]:
        if grid.is_difficult(px, py):
            difficult_count += 1

    # Effective cost: each difficult terrain square adds 5ft extra
    effective_cost = dist_feet + (difficult_count * 5.0)

    if effective_cost > participant.speed:
        return MoveValidationResult(
            valid=False,
            reason=(
                f"Movement cost {effective_cost:.0f}ft exceeds speed {participant.speed}ft"
                f" ({difficult_count} difficult terrain square(s))."
            ),
            distance_feet=dist_feet,
            difficult_terrain_squares=difficult_count,
            effective_cost_feet=effective_cost,
        )

    # Opportunity attack check
    oa_list = check_opportunity_attacks(
        mover=participant,
        from_pos=from_pos,
        to_pos=to_pos,
        participants=participants,
    )

    return MoveValidationResult(
        valid=True,
        reason="Move is valid.",
        distance_feet=dist_feet,
        difficult_terrain_squares=difficult_count,
        effective_cost_feet=effective_cost,
        opportunity_attacks=oa_list,
    )


# ---------------------------------------------------------------------------
# Opportunity attack detection
# ---------------------------------------------------------------------------

def check_opportunity_attacks(
    mover: ParticipantInfo,
    from_pos: Position,
    to_pos: Position,
    participants: list[ParticipantInfo],
    reach_feet: float = 5.0,
) -> list[str]:
    """Detect which enemies can make opportunity attacks on this move.

    A creature provokes an opportunity attack when it moves out of an
    enemy's reach **without** using the Disengage action. In 5e, this
    means leaving a threatened square (within ``reach_feet`` of the
    enemy) to a non-threatened square.

    Args:
        mover: The participant who is moving.
        from_pos: Starting position.
        to_pos: Destination position.
        participants: All combat participants.
        reach_feet: Melee reach of threatening enemies (default 5ft).

    Returns:
        List of names of enemies that can make an opportunity attack.
    """
    if mover.has_disengage:
        return []

    threats: list[str] = []

    for p in participants:
        # Skip self, allies, and participants without positions
        if p.name == mover.name or p.position is None:
            continue
        if p.side == mover.side:
            continue

        # Was in reach at start, not in reach at end?
        dist_before = distance(p.position, from_pos)
        dist_after = distance(p.position, to_pos)

        if dist_before <= reach_feet and dist_after > reach_feet:
            threats.append(p.name)

    return threats


# ---------------------------------------------------------------------------
# Auto-generation
# ---------------------------------------------------------------------------

def generate_room(
    width: int = 20,
    height: int = 20,
    obstacle_ratio: float = 0.12,
    seed: int | None = None,
) -> TacticalGrid:
    """Generate a simple rectangular room with random obstacles.

    Creates a grid with walls around the perimeter and random wall/obstacle
    cells in the interior. The centre of the room (roughly 40% of the area)
    is guaranteed to be clear for combat.

    Args:
        width: Grid width in squares (default 20).
        height: Grid height in squares (default 20).
        obstacle_ratio: Fraction of *interior* cells to fill with
            walls/obstacles (default 0.12, i.e. ~12%).
        seed: Optional random seed for reproducible layouts.

    Returns:
        A TacticalGrid representing the generated room.
    """
    rng = _random.Random(seed)

    grid = TacticalGrid(width=width, height=height)

    # Perimeter walls
    for x in range(width):
        grid.set_terrain(x, 0, Terrain.WALL)
        grid.set_terrain(x, height - 1, Terrain.WALL)
    for y in range(height):
        grid.set_terrain(0, y, Terrain.WALL)
        grid.set_terrain(width - 1, y, Terrain.WALL)

    # Add a door on a random edge
    edge = rng.choice(["top", "bottom", "left", "right"])
    if edge == "top":
        dx = rng.randint(1, width - 2)
        grid.set_terrain(dx, 0, Terrain.DOOR)
    elif edge == "bottom":
        dx = rng.randint(1, width - 2)
        grid.set_terrain(dx, height - 1, Terrain.DOOR)
    elif edge == "left":
        dy = rng.randint(1, height - 2)
        grid.set_terrain(0, dy, Terrain.DOOR)
    else:
        dy = rng.randint(1, height - 2)
        grid.set_terrain(width - 1, dy, Terrain.DOOR)

    # Define the protected centre region (clear for combat)
    cx, cy = width // 2, height // 2
    clear_x_min = max(1, cx - width // 5)
    clear_x_max = min(width - 2, cx + width // 5)
    clear_y_min = max(1, cy - height // 5)
    clear_y_max = min(height - 2, cy + height // 5)

    # Interior cells eligible for obstacles
    interior: list[tuple[int, int]] = []
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            if clear_x_min <= x <= clear_x_max and clear_y_min <= y <= clear_y_max:
                continue  # protected centre
            interior.append((x, y))

    # Place random obstacles/difficult terrain
    n_obstacles = int(len(interior) * obstacle_ratio)
    chosen = rng.sample(interior, min(n_obstacles, len(interior)))

    terrain_choices = [Terrain.WALL, Terrain.OBSTACLE, Terrain.DIFFICULT_TERRAIN, Terrain.WATER]
    terrain_weights = [0.4, 0.3, 0.2, 0.1]

    for x, y in chosen:
        terrain = rng.choices(terrain_choices, weights=terrain_weights, k=1)[0]
        grid.set_terrain(x, y, terrain)

    return grid


# ---------------------------------------------------------------------------
# Utility: Bresenham's line algorithm
# ---------------------------------------------------------------------------

def _bresenham_line(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Return a list of grid cells along a straight line from (x0,y0) to (x1,y1).

    Uses Bresenham's line algorithm for efficient integer-only computation.
    The result includes both endpoints.
    """
    points: list[tuple[int, int]] = []

    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    cx, cy = x0, y0

    while True:
        points.append((cx, cy))
        if cx == x1 and cy == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy

    return points


# ---------------------------------------------------------------------------
# Utility: find participant by name
# ---------------------------------------------------------------------------

def _find_participant(
    name: str, participants: list[ParticipantInfo]
) -> ParticipantInfo | None:
    """Find a participant by name in a list."""
    for p in participants:
        if p.name == name:
            return p
    return None
