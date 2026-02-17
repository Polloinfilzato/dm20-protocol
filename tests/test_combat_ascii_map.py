"""
Tests for the ASCII Tactical Map system.

Covers:
- Cell model and terrain types
- TacticalGrid creation, accessors, bounds checking
- Token label assignment (P/E/A prefixes)
- AsciiMapRenderer rendering with coordinate labels, terrain, tokens, legend
- AoE highlight overlay
- Movement validation (speed, difficult terrain, walls, occupancy)
- Opportunity attack detection
- Auto-generated room layouts
- Grid serialization/deserialization (Pydantic persistence)
- Edge cases: empty grid, single cell, out-of-bounds, large grids
"""

import pytest

from dm20_protocol.combat.ascii_map import (
    AsciiMapRenderer,
    Cell,
    MoveValidationResult,
    ParticipantInfo,
    TacticalGrid,
    Terrain,
    TERRAIN_SYMBOLS,
    assign_labels,
    check_opportunity_attacks,
    generate_room,
    validate_move,
    _bresenham_line,
    _col_label,
)
from dm20_protocol.combat.positioning import Position, Sphere, Cube


# ===================================================================
# Cell model
# ===================================================================

class TestCell:
    """Tests for the Cell model."""

    def test_default_cell(self):
        cell = Cell()
        assert cell.terrain == Terrain.OPEN
        assert cell.occupant is None

    def test_cell_with_terrain(self):
        cell = Cell(terrain=Terrain.WALL)
        assert cell.terrain == Terrain.WALL

    def test_cell_with_occupant(self):
        cell = Cell(occupant="Aldric")
        assert cell.occupant == "Aldric"

    def test_cell_serialization(self):
        cell = Cell(terrain=Terrain.DIFFICULT_TERRAIN, occupant="Lyra")
        data = cell.model_dump()
        assert data["terrain"] == Terrain.DIFFICULT_TERRAIN
        assert data["occupant"] == "Lyra"
        restored = Cell.model_validate(data)
        assert restored.terrain == Terrain.DIFFICULT_TERRAIN
        assert restored.occupant == "Lyra"


# ===================================================================
# Terrain enum
# ===================================================================

class TestTerrain:
    """Tests for the Terrain enum."""

    def test_terrain_values(self):
        assert Terrain.OPEN == "open"
        assert Terrain.WALL == "wall"
        assert Terrain.DOOR == "door"
        assert Terrain.DIFFICULT_TERRAIN == "difficult_terrain"
        assert Terrain.OBSTACLE == "obstacle"
        assert Terrain.WATER == "water"

    def test_terrain_symbols_defined(self):
        for terrain in Terrain:
            assert terrain in TERRAIN_SYMBOLS

    def test_terrain_symbols_content(self):
        assert TERRAIN_SYMBOLS[Terrain.OPEN] == "."
        assert TERRAIN_SYMBOLS[Terrain.WALL] == "#"
        assert TERRAIN_SYMBOLS[Terrain.DOOR] == "D"
        assert TERRAIN_SYMBOLS[Terrain.OBSTACLE] == "X"


# ===================================================================
# TacticalGrid
# ===================================================================

class TestTacticalGrid:
    """Tests for the TacticalGrid model."""

    def test_default_grid(self):
        grid = TacticalGrid()
        assert grid.width == 20
        assert grid.height == 20
        assert len(grid.cells) == 400

    def test_custom_size(self):
        grid = TacticalGrid(width=8, height=7)
        assert grid.width == 8
        assert grid.height == 7
        assert len(grid.cells) == 56

    def test_all_cells_open_by_default(self):
        grid = TacticalGrid(width=5, height=5)
        for cell in grid.cells:
            assert cell.terrain == Terrain.OPEN
            assert cell.occupant is None

    def test_at_accessor(self):
        grid = TacticalGrid(width=5, height=5)
        grid.set_terrain(2, 3, Terrain.WALL)
        cell = grid.at(2, 3)
        assert cell.terrain == Terrain.WALL

    def test_set_accessor(self):
        grid = TacticalGrid(width=5, height=5)
        new_cell = Cell(terrain=Terrain.DOOR, occupant="Guard")
        grid.set(1, 1, new_cell)
        assert grid.at(1, 1).terrain == Terrain.DOOR
        assert grid.at(1, 1).occupant == "Guard"

    def test_bounds_checking_at(self):
        grid = TacticalGrid(width=5, height=5)
        with pytest.raises(IndexError):
            grid.at(5, 0)
        with pytest.raises(IndexError):
            grid.at(0, 5)
        with pytest.raises(IndexError):
            grid.at(-1, 0)

    def test_place_and_clear_occupant(self):
        grid = TacticalGrid(width=5, height=5)
        grid.place_occupant(2, 2, "Hero")
        assert grid.at(2, 2).occupant == "Hero"
        grid.clear_occupant(2, 2)
        assert grid.at(2, 2).occupant is None

    def test_is_passable_open(self):
        grid = TacticalGrid(width=5, height=5)
        assert grid.is_passable(2, 2) is True

    def test_is_passable_wall(self):
        grid = TacticalGrid(width=5, height=5)
        grid.set_terrain(2, 2, Terrain.WALL)
        assert grid.is_passable(2, 2) is False

    def test_is_passable_obstacle(self):
        grid = TacticalGrid(width=5, height=5)
        grid.set_terrain(2, 2, Terrain.OBSTACLE)
        assert grid.is_passable(2, 2) is False

    def test_is_passable_door(self):
        grid = TacticalGrid(width=5, height=5)
        grid.set_terrain(2, 2, Terrain.DOOR)
        assert grid.is_passable(2, 2) is True

    def test_is_passable_out_of_bounds(self):
        grid = TacticalGrid(width=5, height=5)
        assert grid.is_passable(-1, 0) is False
        assert grid.is_passable(5, 0) is False

    def test_is_difficult(self):
        grid = TacticalGrid(width=5, height=5)
        grid.set_terrain(1, 1, Terrain.DIFFICULT_TERRAIN)
        grid.set_terrain(2, 2, Terrain.WATER)
        assert grid.is_difficult(1, 1) is True
        assert grid.is_difficult(2, 2) is True
        assert grid.is_difficult(0, 0) is False

    def test_grid_serialization(self):
        """Grid should be fully serializable for persistence."""
        grid = TacticalGrid(width=4, height=3)
        grid.set_terrain(1, 1, Terrain.WALL)
        grid.place_occupant(2, 1, "Test")

        data = grid.model_dump()
        restored = TacticalGrid.model_validate(data)

        assert restored.width == 4
        assert restored.height == 3
        assert restored.at(1, 1).terrain == Terrain.WALL
        assert restored.at(2, 1).occupant == "Test"
        assert len(restored.cells) == 12

    def test_invalid_cell_count(self):
        """Providing wrong number of cells should raise ValueError."""
        with pytest.raises(ValueError, match="Expected"):
            TacticalGrid(width=3, height=3, cells=[Cell() for _ in range(5)])

    def test_minimum_grid_size(self):
        grid = TacticalGrid(width=3, height=3)
        assert grid.width == 3
        assert grid.height == 3


# ===================================================================
# Token label assignment
# ===================================================================

class TestAssignLabels:
    """Tests for the assign_labels function."""

    def test_player_labels(self):
        participants = [
            ParticipantInfo(name="Aldric", side="player"),
            ParticipantInfo(name="Lyra", side="player"),
        ]
        assign_labels(participants)
        assert participants[0].label == "P1"
        assert participants[1].label == "P2"

    def test_enemy_labels(self):
        participants = [
            ParticipantInfo(name="Goblin 1", side="enemy"),
            ParticipantInfo(name="Goblin 2", side="enemy"),
            ParticipantInfo(name="Hobgoblin", side="enemy"),
        ]
        assign_labels(participants)
        assert participants[0].label == "E1"
        assert participants[1].label == "E2"
        assert participants[2].label == "E3"

    def test_ally_labels(self):
        participants = [
            ParticipantInfo(name="Guard", side="ally"),
        ]
        assign_labels(participants)
        assert participants[0].label == "A1"

    def test_mixed_labels(self):
        participants = [
            ParticipantInfo(name="Player1", side="player"),
            ParticipantInfo(name="Enemy1", side="enemy"),
            ParticipantInfo(name="Ally1", side="ally"),
            ParticipantInfo(name="Player2", side="player"),
            ParticipantInfo(name="Enemy2", side="enemy"),
        ]
        assign_labels(participants)
        assert participants[0].label == "P1"
        assert participants[1].label == "E1"
        assert participants[2].label == "A1"
        assert participants[3].label == "P2"
        assert participants[4].label == "E2"

    def test_pre_assigned_labels_preserved(self):
        participants = [
            ParticipantInfo(name="Boss", side="enemy", label="BOSS"),
            ParticipantInfo(name="Minion", side="enemy"),
        ]
        assign_labels(participants)
        assert participants[0].label == "BOSS"
        assert participants[1].label == "E1"

    def test_unknown_side_defaults_to_ally(self):
        participants = [
            ParticipantInfo(name="Unknown", side="neutral"),
        ]
        assign_labels(participants)
        assert participants[0].label == "A1"


# ===================================================================
# AsciiMapRenderer
# ===================================================================

class TestAsciiMapRenderer:
    """Tests for the AsciiMapRenderer."""

    def _small_grid(self) -> TacticalGrid:
        """Create a small 5x5 grid with walls around the perimeter."""
        grid = TacticalGrid(width=5, height=5)
        for x in range(5):
            grid.set_terrain(x, 0, Terrain.WALL)
            grid.set_terrain(x, 4, Terrain.WALL)
        for y in range(5):
            grid.set_terrain(0, y, Terrain.WALL)
            grid.set_terrain(4, y, Terrain.WALL)
        return grid

    def test_render_empty_grid(self):
        grid = TacticalGrid(width=3, height=3)
        output = AsciiMapRenderer.render(grid)
        assert isinstance(output, str)
        assert "\n" in output

    def test_render_contains_column_headers(self):
        grid = TacticalGrid(width=5, height=3)
        output = AsciiMapRenderer.render(grid)
        # Should contain A through E
        for letter in "ABCDE":
            assert letter in output

    def test_render_contains_row_numbers(self):
        grid = TacticalGrid(width=3, height=5)
        output = AsciiMapRenderer.render(grid)
        for num in ["1", "2", "3", "4", "5"]:
            assert num in output

    def test_render_terrain_symbols(self):
        grid = self._small_grid()
        grid.set_terrain(2, 2, Terrain.DIFFICULT_TERRAIN)
        output = AsciiMapRenderer.render(grid)
        assert "#" in output  # walls
        assert "~" in output  # difficult terrain
        assert "." in output  # open cells

    def test_render_with_participants(self):
        grid = self._small_grid()
        participants = [
            ParticipantInfo(
                name="Aldric",
                position=Position(x=2, y=2),
                side="player",
                character_class="Fighter",
            ),
            ParticipantInfo(
                name="Goblin",
                position=Position(x=3, y=2),
                side="enemy",
            ),
        ]
        output = AsciiMapRenderer.render(grid, participants)
        assert "P1" in output
        assert "E1" in output
        assert "Aldric" in output  # in legend
        assert "Goblin" in output  # in legend

    def test_render_legend_includes_terrain(self):
        grid = self._small_grid()
        grid.set_terrain(2, 2, Terrain.DIFFICULT_TERRAIN)
        output = AsciiMapRenderer.render(grid)
        assert "Legend:" in output
        assert "Wall" in output
        assert "Difficult" in output

    def test_render_legend_excludes_open(self):
        """Open terrain should not appear in the legend (too common)."""
        grid = TacticalGrid(width=3, height=3)
        output = AsciiMapRenderer.render(grid)
        # Only open terrain, so no legend at all
        assert "Legend:" not in output

    def test_render_aoe_highlight(self):
        grid = TacticalGrid(width=8, height=8)
        # Place a sphere AoE at (4, 4) with radius 10ft (2 squares)
        aoe = Sphere(origin=Position(x=4, y=4), radius=10)
        output = AsciiMapRenderer.render(grid, highlight_aoe=aoe)
        assert "*" in output
        assert "AoE" in output  # in legend

    def test_render_aoe_does_not_override_tokens(self):
        grid = TacticalGrid(width=8, height=8)
        participants = [
            ParticipantInfo(
                name="Wizard",
                position=Position(x=4, y=4),
                side="player",
            ),
        ]
        aoe = Sphere(origin=Position(x=4, y=4), radius=10)
        output = AsciiMapRenderer.render(grid, participants, highlight_aoe=aoe)
        # The wizard's token should appear, not the AoE marker
        assert "P1" in output

    def test_render_door_symbol(self):
        grid = TacticalGrid(width=5, height=5)
        grid.set_terrain(2, 0, Terrain.DOOR)
        output = AsciiMapRenderer.render(grid)
        assert "D" in output

    def test_render_output_is_single_string(self):
        grid = TacticalGrid(width=4, height=4)
        output = AsciiMapRenderer.render(grid)
        assert isinstance(output, str)
        lines = output.split("\n")
        # At least header row + 4 data rows
        assert len(lines) >= 5

    def test_render_example_from_spec(self):
        """Render a layout similar to the one in the task specification."""
        grid = TacticalGrid(width=8, height=7)

        # Perimeter walls
        for x in range(8):
            grid.set_terrain(x, 0, Terrain.WALL)
            grid.set_terrain(x, 6, Terrain.WALL)
        for y in range(7):
            grid.set_terrain(0, y, Terrain.WALL)
            grid.set_terrain(7, y, Terrain.WALL)

        # Door at column E (index 5), row 1 (index 0)
        grid.set_terrain(5, 0, Terrain.DOOR)

        # Difficult terrain
        grid.set_terrain(3, 3, Terrain.DIFFICULT_TERRAIN)
        grid.set_terrain(4, 3, Terrain.DIFFICULT_TERRAIN)
        grid.set_terrain(3, 4, Terrain.DIFFICULT_TERRAIN)
        grid.set_terrain(4, 4, Terrain.DIFFICULT_TERRAIN)

        participants = [
            ParticipantInfo(name="Aldric", position=Position(x=2, y=2), side="player", character_class="Fighter"),
            ParticipantInfo(name="Lyra", position=Position(x=2, y=4), side="player", character_class="Wizard"),
            ParticipantInfo(name="Goblin", position=Position(x=5, y=2), side="enemy"),
            ParticipantInfo(name="Goblin 2", position=Position(x=5, y=4), side="enemy"),
            ParticipantInfo(name="Hobgoblin", position=Position(x=6, y=5), side="enemy"),
        ]

        output = AsciiMapRenderer.render(grid, participants)

        # Verify key elements present
        assert "P1" in output
        assert "P2" in output
        assert "E1" in output
        assert "E2" in output
        assert "E3" in output
        assert "#" in output
        assert "D" in output
        assert "~" in output
        assert "Legend:" in output
        assert "Aldric" in output
        assert "Fighter" in output


# ===================================================================
# Column label helper
# ===================================================================

class TestColLabel:
    """Tests for the _col_label helper."""

    def test_first_letters(self):
        assert _col_label(0) == "A"
        assert _col_label(1) == "B"
        assert _col_label(25) == "Z"

    def test_double_letters(self):
        assert _col_label(26) == "AA"
        assert _col_label(27) == "AB"


# ===================================================================
# Movement validation
# ===================================================================

class TestValidateMove:
    """Tests for the validate_move function."""

    def _make_grid_with_room(self) -> TacticalGrid:
        """Create a 10x10 grid with wall perimeter."""
        grid = TacticalGrid(width=10, height=10)
        for x in range(10):
            grid.set_terrain(x, 0, Terrain.WALL)
            grid.set_terrain(x, 9, Terrain.WALL)
        for y in range(10):
            grid.set_terrain(0, y, Terrain.WALL)
            grid.set_terrain(9, y, Terrain.WALL)
        return grid

    def test_valid_move(self):
        grid = self._make_grid_with_room()
        mover = ParticipantInfo(name="Hero", position=Position(x=2, y=2), side="player", speed=30)
        result = validate_move(mover, Position(x=2, y=2), Position(x=4, y=2), grid)
        assert result.valid is True
        assert result.distance_feet == 10.0
        assert result.effective_cost_feet == 10.0

    def test_move_blocked_by_wall(self):
        grid = self._make_grid_with_room()
        mover = ParticipantInfo(name="Hero", position=Position(x=2, y=2), side="player", speed=30)
        # Try to move to a wall cell
        result = validate_move(mover, Position(x=2, y=2), Position(x=0, y=2), grid)
        assert result.valid is False
        assert "wall" in result.reason.lower()

    def test_move_blocked_by_obstacle(self):
        grid = self._make_grid_with_room()
        grid.set_terrain(3, 2, Terrain.OBSTACLE)
        mover = ParticipantInfo(name="Hero", position=Position(x=2, y=2), side="player", speed=30)
        result = validate_move(mover, Position(x=2, y=2), Position(x=3, y=2), grid)
        assert result.valid is False
        assert "obstacle" in result.reason.lower()

    def test_move_exceeds_speed(self):
        grid = self._make_grid_with_room()
        mover = ParticipantInfo(name="Slow", position=Position(x=1, y=1), side="player", speed=10)
        # Try to move 4 squares (20ft) with only 10ft speed
        result = validate_move(mover, Position(x=1, y=1), Position(x=5, y=1), grid)
        assert result.valid is False
        assert "exceeds speed" in result.reason.lower()

    def test_difficult_terrain_costs_double(self):
        grid = self._make_grid_with_room()
        grid.set_terrain(3, 2, Terrain.DIFFICULT_TERRAIN)
        mover = ParticipantInfo(name="Hero", position=Position(x=2, y=2), side="player", speed=15)
        # Move from (2,2) to (4,2): 10ft base + 5ft extra for difficult = 15ft
        result = validate_move(mover, Position(x=2, y=2), Position(x=4, y=2), grid)
        assert result.valid is True
        assert result.difficult_terrain_squares == 1
        assert result.effective_cost_feet == 15.0

    def test_difficult_terrain_exceeds_speed(self):
        grid = self._make_grid_with_room()
        grid.set_terrain(3, 2, Terrain.DIFFICULT_TERRAIN)
        grid.set_terrain(4, 2, Terrain.DIFFICULT_TERRAIN)
        mover = ParticipantInfo(name="Hero", position=Position(x=2, y=2), side="player", speed=15)
        # Move from (2,2) to (5,2): 15ft base + 10ft extra for 2 difficult = 25ft
        result = validate_move(mover, Position(x=2, y=2), Position(x=5, y=2), grid)
        assert result.valid is False
        assert result.difficult_terrain_squares == 2

    def test_water_is_difficult(self):
        grid = self._make_grid_with_room()
        grid.set_terrain(3, 2, Terrain.WATER)
        mover = ParticipantInfo(name="Hero", position=Position(x=2, y=2), side="player", speed=30)
        result = validate_move(mover, Position(x=2, y=2), Position(x=4, y=2), grid)
        assert result.valid is True
        assert result.difficult_terrain_squares == 1

    def test_move_blocked_by_enemy(self):
        grid = self._make_grid_with_room()
        enemy = ParticipantInfo(name="Goblin", position=Position(x=4, y=2), side="enemy")
        grid.place_occupant(4, 2, "Goblin")
        mover = ParticipantInfo(name="Hero", position=Position(x=2, y=2), side="player", speed=30)
        result = validate_move(mover, Position(x=2, y=2), Position(x=4, y=2), grid, [mover, enemy])
        assert result.valid is False
        assert "occupied" in result.reason.lower()

    def test_move_through_ally_allowed(self):
        grid = self._make_grid_with_room()
        ally = ParticipantInfo(name="Friend", position=Position(x=3, y=2), side="player")
        grid.place_occupant(3, 2, "Friend")
        mover = ParticipantInfo(name="Hero", position=Position(x=2, y=2), side="player", speed=30)
        # Moving to a cell occupied by an ally is allowed (ending in their square)
        # Note: in strict 5e you can move through but not end in an ally's space,
        # but for simplicity we allow it in this implementation
        result = validate_move(mover, Position(x=2, y=2), Position(x=3, y=2), grid, [mover, ally])
        assert result.valid is True

    def test_move_out_of_bounds(self):
        grid = TacticalGrid(width=5, height=5)
        mover = ParticipantInfo(name="Hero", position=Position(x=4, y=4), side="player", speed=30)
        result = validate_move(mover, Position(x=4, y=4), Position(x=5, y=4), grid)
        assert result.valid is False
        assert "out of bounds" in result.reason.lower()

    def test_path_blocked_by_wall_intermediate(self):
        grid = self._make_grid_with_room()
        # Place a wall in the middle of the path
        grid.set_terrain(3, 2, Terrain.WALL)
        mover = ParticipantInfo(name="Hero", position=Position(x=1, y=2), side="player", speed=30)
        # Try to move through the wall
        result = validate_move(mover, Position(x=1, y=2), Position(x=5, y=2), grid)
        assert result.valid is False
        assert "blocked" in result.reason.lower()

    def test_move_to_same_position(self):
        grid = self._make_grid_with_room()
        mover = ParticipantInfo(name="Hero", position=Position(x=3, y=3), side="player", speed=30)
        result = validate_move(mover, Position(x=3, y=3), Position(x=3, y=3), grid)
        assert result.valid is True
        assert result.distance_feet == 0.0

    def test_move_through_door(self):
        grid = self._make_grid_with_room()
        grid.set_terrain(5, 0, Terrain.DOOR)
        mover = ParticipantInfo(name="Hero", position=Position(x=5, y=1), side="player", speed=30)
        result = validate_move(mover, Position(x=5, y=1), Position(x=5, y=0), grid)
        assert result.valid is True

    def test_opportunity_attacks_in_result(self):
        grid = self._make_grid_with_room()
        enemy = ParticipantInfo(name="Goblin", position=Position(x=3, y=3), side="enemy")
        mover = ParticipantInfo(name="Hero", position=Position(x=3, y=2), side="player", speed=30)
        # Move away from the enemy (currently adjacent at 5ft, moving to 10ft+)
        result = validate_move(mover, Position(x=3, y=2), Position(x=3, y=1), grid, [mover, enemy])
        assert result.valid is True
        assert "Goblin" in result.opportunity_attacks


# ===================================================================
# Opportunity attack detection
# ===================================================================

class TestOpportunityAttacks:
    """Tests for the check_opportunity_attacks function."""

    def test_leaving_enemy_reach(self):
        mover = ParticipantInfo(name="Hero", side="player")
        enemy = ParticipantInfo(name="Goblin", position=Position(x=5, y=5), side="enemy")
        # Moving from adjacent (5,4) to away (5,2)
        oa = check_opportunity_attacks(
            mover, Position(x=5, y=4), Position(x=5, y=2), [mover, enemy]
        )
        assert "Goblin" in oa

    def test_staying_in_reach(self):
        mover = ParticipantInfo(name="Hero", side="player")
        enemy = ParticipantInfo(name="Goblin", position=Position(x=5, y=5), side="enemy")
        # Moving from (5,4) to (4,5): both within 5ft
        oa = check_opportunity_attacks(
            mover, Position(x=5, y=4), Position(x=4, y=5), [mover, enemy]
        )
        assert oa == []

    def test_disengage_prevents_oa(self):
        mover = ParticipantInfo(name="Hero", side="player", has_disengage=True)
        enemy = ParticipantInfo(name="Goblin", position=Position(x=5, y=5), side="enemy")
        oa = check_opportunity_attacks(
            mover, Position(x=5, y=4), Position(x=5, y=0), [mover, enemy]
        )
        assert oa == []

    def test_no_oa_from_allies(self):
        mover = ParticipantInfo(name="Hero", side="player")
        ally = ParticipantInfo(name="Friend", position=Position(x=5, y=5), side="player")
        oa = check_opportunity_attacks(
            mover, Position(x=5, y=4), Position(x=5, y=0), [mover, ally]
        )
        assert oa == []

    def test_multiple_enemies_oa(self):
        mover = ParticipantInfo(name="Hero", side="player")
        enemy1 = ParticipantInfo(name="Goblin 1", position=Position(x=5, y=5), side="enemy")
        enemy2 = ParticipantInfo(name="Goblin 2", position=Position(x=4, y=4), side="enemy")
        # Moving from (5,4) -- adjacent to both -- to (5,0) -- far from both
        oa = check_opportunity_attacks(
            mover, Position(x=5, y=4), Position(x=5, y=0), [mover, enemy1, enemy2]
        )
        assert "Goblin 1" in oa
        assert "Goblin 2" in oa

    def test_approaching_enemy_no_oa(self):
        mover = ParticipantInfo(name="Hero", side="player")
        enemy = ParticipantInfo(name="Goblin", position=Position(x=5, y=5), side="enemy")
        # Moving from far (5,0) to adjacent (5,4): entering reach, not leaving
        oa = check_opportunity_attacks(
            mover, Position(x=5, y=0), Position(x=5, y=4), [mover, enemy]
        )
        assert oa == []

    def test_custom_reach(self):
        mover = ParticipantInfo(name="Hero", side="player")
        # Enemy with 10ft reach (e.g., polearm)
        enemy = ParticipantInfo(name="Bugbear", position=Position(x=5, y=5), side="enemy")
        # Move from 2 squares away (10ft) to 3 squares away (15ft)
        oa = check_opportunity_attacks(
            mover, Position(x=5, y=3), Position(x=5, y=1), [mover, enemy],
            reach_feet=10.0,
        )
        assert "Bugbear" in oa

    def test_enemy_without_position_no_oa(self):
        mover = ParticipantInfo(name="Hero", side="player")
        enemy = ParticipantInfo(name="Ghost", side="enemy")  # no position
        oa = check_opportunity_attacks(
            mover, Position(x=5, y=4), Position(x=5, y=0), [mover, enemy]
        )
        assert oa == []


# ===================================================================
# Auto-generation
# ===================================================================

class TestGenerateRoom:
    """Tests for the generate_room function."""

    def test_default_size(self):
        grid = generate_room()
        assert grid.width == 20
        assert grid.height == 20

    def test_custom_size(self):
        grid = generate_room(width=10, height=8)
        assert grid.width == 10
        assert grid.height == 8

    def test_perimeter_walls(self):
        grid = generate_room(width=10, height=10, seed=42)
        # Check all perimeter cells are walls (except doors)
        for x in range(10):
            assert grid.at(x, 0).terrain in (Terrain.WALL, Terrain.DOOR)
            assert grid.at(x, 9).terrain in (Terrain.WALL, Terrain.DOOR)
        for y in range(10):
            assert grid.at(0, y).terrain in (Terrain.WALL, Terrain.DOOR)
            assert grid.at(9, y).terrain in (Terrain.WALL, Terrain.DOOR)

    def test_has_at_least_one_door(self):
        grid = generate_room(width=10, height=10, seed=42)
        door_count = sum(
            1 for cell in grid.cells if cell.terrain == Terrain.DOOR
        )
        assert door_count >= 1

    def test_centre_is_clear(self):
        """Centre of the room should be open for combat."""
        grid = generate_room(width=20, height=20, seed=42)
        cx, cy = 10, 10
        # Check a 4x4 area around centre is all open
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                cell = grid.at(cx + dx, cy + dy)
                assert cell.terrain == Terrain.OPEN, (
                    f"Centre cell ({cx+dx}, {cy+dy}) should be open, "
                    f"got {cell.terrain}"
                )

    def test_seed_reproducibility(self):
        grid1 = generate_room(width=10, height=10, seed=123)
        grid2 = generate_room(width=10, height=10, seed=123)
        for i in range(len(grid1.cells)):
            assert grid1.cells[i].terrain == grid2.cells[i].terrain

    def test_different_seeds_different_layouts(self):
        grid1 = generate_room(width=15, height=15, seed=1)
        grid2 = generate_room(width=15, height=15, seed=2)
        # At least some cells should differ
        differences = sum(
            1 for i in range(len(grid1.cells))
            if grid1.cells[i].terrain != grid2.cells[i].terrain
        )
        assert differences > 0

    def test_obstacle_ratio(self):
        """Interior obstacle count should be roughly in range."""
        grid = generate_room(width=20, height=20, obstacle_ratio=0.15, seed=42)
        interior_count = 0
        obstacle_count = 0
        for y in range(1, 19):
            for x in range(1, 19):
                interior_count += 1
                if grid.at(x, y).terrain != Terrain.OPEN:
                    obstacle_count += 1
        # Should be less than 20% (allowing some margin above 15%)
        assert obstacle_count <= interior_count * 0.20


# ===================================================================
# Bresenham line algorithm
# ===================================================================

class TestBresenhamLine:
    """Tests for the _bresenham_line helper."""

    def test_horizontal_line(self):
        points = _bresenham_line(0, 0, 4, 0)
        assert points == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]

    def test_vertical_line(self):
        points = _bresenham_line(0, 0, 0, 3)
        assert points == [(0, 0), (0, 1), (0, 2), (0, 3)]

    def test_diagonal_line(self):
        points = _bresenham_line(0, 0, 3, 3)
        assert (0, 0) in points
        assert (3, 3) in points
        assert len(points) == 4

    def test_single_point(self):
        points = _bresenham_line(5, 5, 5, 5)
        assert points == [(5, 5)]

    def test_reverse_direction(self):
        points = _bresenham_line(4, 0, 0, 0)
        assert (0, 0) in points
        assert (4, 0) in points
        assert len(points) == 5


# ===================================================================
# ParticipantInfo model
# ===================================================================

class TestParticipantInfo:
    """Tests for the ParticipantInfo model."""

    def test_default_values(self):
        p = ParticipantInfo(name="Test")
        assert p.side == "player"
        assert p.label == ""
        assert p.speed == 30
        assert p.has_disengage is False
        assert p.position is None

    def test_full_creation(self):
        p = ParticipantInfo(
            name="Aldric",
            position=Position(x=3, y=4),
            side="player",
            label="P1",
            character_class="Fighter",
            speed=30,
            has_disengage=False,
        )
        assert p.name == "Aldric"
        assert p.position == Position(x=3, y=4)
        assert p.label == "P1"

    def test_serialization(self):
        p = ParticipantInfo(
            name="Goblin",
            position=Position(x=5, y=5),
            side="enemy",
        )
        data = p.model_dump()
        restored = ParticipantInfo.model_validate(data)
        assert restored.name == "Goblin"
        assert restored.position == Position(x=5, y=5)
        assert restored.side == "enemy"


# ===================================================================
# MoveValidationResult model
# ===================================================================

class TestMoveValidationResult:
    """Tests for the MoveValidationResult model."""

    def test_valid_result(self):
        r = MoveValidationResult(
            valid=True,
            reason="Move is valid.",
            distance_feet=10.0,
            effective_cost_feet=10.0,
        )
        assert r.valid is True
        assert r.opportunity_attacks == []

    def test_invalid_result(self):
        r = MoveValidationResult(
            valid=False,
            reason="Blocked by wall.",
        )
        assert r.valid is False

    def test_result_with_oa(self):
        r = MoveValidationResult(
            valid=True,
            reason="Move is valid.",
            opportunity_attacks=["Goblin", "Orc"],
        )
        assert len(r.opportunity_attacks) == 2


# ===================================================================
# Integration: full combat scenario
# ===================================================================

class TestIntegrationScenario:
    """Integration test simulating a mini combat scenario."""

    def test_full_combat_turn(self):
        """Simulate placing creatures, rendering, moving, and checking OAs."""
        # 1. Generate a room
        grid = generate_room(width=10, height=10, seed=42)

        # 2. Place participants
        participants = [
            ParticipantInfo(
                name="Aldric",
                position=Position(x=2, y=5),
                side="player",
                character_class="Fighter",
                speed=30,
            ),
            ParticipantInfo(
                name="Lyra",
                position=Position(x=3, y=5),
                side="player",
                character_class="Wizard",
                speed=30,
            ),
            ParticipantInfo(
                name="Goblin",
                position=Position(x=5, y=5),
                side="enemy",
                speed=30,
            ),
        ]

        # Place occupants on grid
        for p in participants:
            if p.position:
                grid.place_occupant(p.position.x, p.position.y, p.name)

        # 3. Render the map
        output = AsciiMapRenderer.render(grid, participants)
        assert "P1" in output
        assert "P2" in output
        assert "E1" in output
        assert "Legend:" in output

        # 4. Validate a move for Aldric (away from Goblin)
        result = validate_move(
            participants[0],
            Position(x=2, y=5),
            Position(x=2, y=3),
            grid,
            participants,
        )
        assert result.valid is True
        # No OA because Aldric was not adjacent to Goblin (3 squares away)
        assert result.opportunity_attacks == []

        # 5. Validate a move for Goblin (should trigger OA if moving away from Aldric who is adjacent)
        # First, move Goblin adjacent to Aldric
        participants[2].position = Position(x=3, y=4)
        grid.place_occupant(3, 4, "Goblin")

        # Now check if Goblin moving away triggers OA from Lyra (at 3,5)
        result_goblin = validate_move(
            participants[2],
            Position(x=3, y=4),
            Position(x=3, y=2),
            grid,
            participants,
        )
        assert result_goblin.valid is True
        # Lyra at (3,5) is 5ft from Goblin at (3,4), Goblin moves to (3,2) which is 15ft from Lyra
        assert "Lyra" in result_goblin.opportunity_attacks

    def test_aoe_overlay_on_generated_room(self):
        """Render a generated room with an AoE overlay."""
        grid = generate_room(width=12, height=12, seed=99)
        participants = [
            ParticipantInfo(
                name="Wizard",
                position=Position(x=3, y=3),
                side="player",
                character_class="Wizard",
            ),
        ]
        # Fireball centered at (6, 6)
        fireball = Sphere(origin=Position(x=6, y=6), radius=20)
        output = AsciiMapRenderer.render(grid, participants, highlight_aoe=fireball)

        assert "P1" in output
        assert "*" in output
        assert "AoE" in output
        assert "Wizard" in output
