"""
Turn Distribution and Management system for the Claudmaster multi-agent framework.

This module provides turn-based gameplay management for multi-player sessions,
including round management, turn distribution modes, combat initiative, and
simultaneous action resolution.

Key components:
- TurnPhase: Game phases (combat, exploration, roleplay, downtime)
- TurnDistribution: Turn order modes (round-robin, free-form, spotlight, popcorn)
- TurnState: Current round and turn state tracking
- TurnManager: Main turn management engine
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .pc_tracking import PCRegistry, MultiPlayerConfig


class TurnPhase(str, Enum):
    """Game phase types for turn management."""
    COMBAT = "combat"
    EXPLORATION = "exploration"
    ROLEPLAY = "roleplay"
    DOWNTIME = "downtime"


class TurnDistribution(str, Enum):
    """Turn distribution modes for managing player order."""
    ROUND_ROBIN = "round_robin"  # Strict sequential order
    FREE_FORM = "free_form"      # Anyone can act anytime
    SPOTLIGHT = "spotlight"       # Only one PC can act (GM-controlled)
    POPCORN = "popcorn"          # Current player chooses next


class TurnRecord(BaseModel):
    """Record of a completed turn."""
    turn_number: int = Field(description="Turn number within the current round")
    round_number: int = Field(description="Round number in the session")
    character_id: str = Field(description="Character who took the turn")
    phase: TurnPhase = Field(description="Game phase during this turn")
    action_summary: Optional[str] = Field(
        default=None,
        description="Brief summary of the action taken"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When the turn was recorded"
    )


class ActionResult(BaseModel):
    """Result of a simultaneous action resolution."""
    character_id: str = Field(description="Character who performed the action")
    action: str = Field(description="Description of the action")
    success: bool = Field(description="Whether the action succeeded")
    result_description: str = Field(description="Detailed result of the action")
    priority: int = Field(description="Action priority for resolution order")


class SimultaneousAction(BaseModel):
    """Queued action for simultaneous resolution."""
    pc_id: str = Field(description="Character performing the action")
    action: str = Field(description="Action description")
    target: Optional[str] = Field(
        default=None,
        description="Target of the action (character ID or object)"
    )
    priority: int = Field(
        default=0,
        description="Priority for resolution order (higher = resolved first)"
    )


class TurnState(BaseModel):
    """Current state of turn management."""
    phase: TurnPhase = Field(description="Current game phase")
    current_round: int = Field(
        default=1,
        description="Current round number"
    )
    current_pc_id: Optional[str] = Field(
        default=None,
        description="Character ID of the current active PC"
    )
    turn_order: list[str] = Field(
        default_factory=list,
        description="Ordered list of character IDs for turn sequence"
    )
    held_actions: dict[str, str] = Field(
        default_factory=dict,
        description="Map of PC ID to held action trigger condition"
    )
    completed_turns: list[str] = Field(
        default_factory=list,
        description="Set of PCs who have completed their turn this round"
    )
    round_start_time: datetime = Field(
        default_factory=datetime.now,
        description="When the current round started"
    )
    turn_start_time: Optional[datetime] = Field(
        default=None,
        description="When the current turn started"
    )
    distribution_mode: TurnDistribution = Field(
        default=TurnDistribution.ROUND_ROBIN,
        description="Current turn distribution mode"
    )


class TurnManager:
    """
    Main turn management engine for multi-player sessions.

    Manages turn order, round progression, combat initiative, held actions,
    and simultaneous action resolution. Supports multiple distribution modes
    for different gameplay styles.
    """

    def __init__(self, pc_registry: PCRegistry, config: MultiPlayerConfig):
        """
        Initialize the turn manager.

        Args:
            pc_registry: PC registry for tracking active characters
            config: Multi-player configuration settings
        """
        self.pc_registry = pc_registry
        self.config = config
        self.state: Optional[TurnState] = None
        self.turn_history: list[TurnRecord] = []
        self._simultaneous_queue: list[SimultaneousAction] = []
        self._last_round_number: int = 0
        self._combat_initiatives: dict[str, int] = {}

    def start_round(
        self,
        phase: TurnPhase,
        distribution: TurnDistribution = TurnDistribution.ROUND_ROBIN
    ) -> TurnState:
        """
        Start a new round of turns.

        Args:
            phase: Game phase for this round
            distribution: Turn distribution mode to use

        Returns:
            The newly created turn state

        Raises:
            ValueError: If no active PCs available
        """
        active_pcs = self.pc_registry.get_all_active()
        if not active_pcs:
            raise ValueError("Cannot start round: no active PCs")

        # Build turn order from active PCs
        turn_order = [pc.character_id for pc in active_pcs]

        # Calculate round number from last round (persists across end_round)
        round_number = self._last_round_number + 1
        self._last_round_number = round_number

        self.state = TurnState(
            phase=phase,
            current_round=round_number,
            current_pc_id=turn_order[0] if distribution != TurnDistribution.FREE_FORM else None,
            turn_order=turn_order,
            held_actions={},
            completed_turns=[],
            round_start_time=datetime.now(),
            turn_start_time=datetime.now() if distribution != TurnDistribution.FREE_FORM else None,
            distribution_mode=distribution
        )

        return self.state

    def get_current_turn(self) -> Optional[str]:
        """
        Get the character ID of the PC whose turn it is.

        Returns:
            Character ID of current PC, or None if no active round
        """
        if self.state is None:
            return None
        return self.state.current_pc_id

    def advance_turn(self, next_pc: Optional[str] = None) -> Optional[str]:
        """
        Advance to the next turn.

        Args:
            next_pc: For POPCORN mode, the character ID chosen as next.
                     Ignored for other distribution modes.

        Returns:
            Character ID of the new current PC, or None if round ended

        Raises:
            RuntimeError: If no active round
            ValueError: If next_pc is invalid (POPCORN mode)
        """
        if self.state is None:
            raise RuntimeError("No active round. Call start_round() first.")

        # Mark current PC as completed
        if self.state.current_pc_id:
            if self.state.current_pc_id not in self.state.completed_turns:
                self.state.completed_turns.append(self.state.current_pc_id)

        # Determine next PC based on distribution mode
        if self.state.distribution_mode == TurnDistribution.FREE_FORM:
            # Free-form has no strict "next" - return None
            self.state.current_pc_id = None
            self.state.turn_start_time = None
            return None

        elif self.state.distribution_mode == TurnDistribution.POPCORN:
            # Popcorn: next player chooses
            if next_pc is None:
                raise ValueError("POPCORN mode requires next_pc parameter")
            if next_pc not in self.state.turn_order:
                raise ValueError(f"Character {next_pc} not in turn order")

            self.state.current_pc_id = next_pc
            self.state.turn_start_time = datetime.now()
            return next_pc

        elif self.state.distribution_mode == TurnDistribution.SPOTLIGHT:
            # Spotlight: GM controls, stays on current until changed
            # advance_turn in spotlight mode just clears the turn, GM must set next
            self.state.current_pc_id = None
            self.state.turn_start_time = None
            return None

        else:  # ROUND_ROBIN
            # Find next PC in order
            if not self.state.current_pc_id:
                # First turn
                next_pc_id = self.state.turn_order[0] if self.state.turn_order else None
            else:
                try:
                    current_idx = self.state.turn_order.index(self.state.current_pc_id)
                    next_idx = (current_idx + 1) % len(self.state.turn_order)
                    next_pc_id = self.state.turn_order[next_idx]

                    # If we've wrapped around, all PCs have gone
                    if next_idx == 0:
                        # Round complete
                        next_pc_id = None
                except ValueError:
                    # Current PC not in order, start from beginning
                    next_pc_id = self.state.turn_order[0] if self.state.turn_order else None

            self.state.current_pc_id = next_pc_id
            self.state.turn_start_time = datetime.now() if next_pc_id else None
            return next_pc_id

    def end_round(self) -> list[TurnRecord]:
        """
        End the current round and return all turn records from it.

        Returns:
            List of turn records from the completed round

        Raises:
            RuntimeError: If no active round
        """
        if self.state is None:
            raise RuntimeError("No active round to end")

        round_number = self.state.current_round

        # Get all records from this round
        round_records = [
            record for record in self.turn_history
            if record.round_number == round_number
        ]

        # Clear state
        self.state = None

        return round_records

    def hold_action(self, pc_id: str, trigger: str) -> None:
        """
        Hold an action for later trigger.

        Args:
            pc_id: Character ID holding the action
            trigger: Condition that will trigger the held action

        Raises:
            RuntimeError: If no active round
            ValueError: If PC is not in turn order
        """
        if self.state is None:
            raise RuntimeError("No active round")

        if pc_id not in self.state.turn_order:
            raise ValueError(f"Character {pc_id} not in turn order")

        self.state.held_actions[pc_id] = trigger

    def resolve_held_action(self, pc_id: str) -> Optional[str]:
        """
        Resolve a held action and return the trigger.

        Args:
            pc_id: Character ID whose held action to resolve

        Returns:
            The trigger condition, or None if no held action

        Raises:
            RuntimeError: If no active round
        """
        if self.state is None:
            raise RuntimeError("No active round")

        return self.state.held_actions.pop(pc_id, None)

    def queue_simultaneous(
        self,
        pc_id: str,
        action: str,
        target: Optional[str] = None
    ) -> None:
        """
        Queue an action for simultaneous resolution.

        Args:
            pc_id: Character performing the action
            action: Action description
            target: Optional target of the action

        Raises:
            RuntimeError: If simultaneous actions are disabled in config
            ValueError: If PC is not active
        """
        if not self.config.simultaneous_actions:
            raise RuntimeError("Simultaneous actions are disabled in configuration")

        # Verify PC is active
        active_ids = [pc.character_id for pc in self.pc_registry.get_all_active()]
        if pc_id not in active_ids:
            raise ValueError(f"Character {pc_id} is not active")

        # Default priority is 0, can be adjusted later
        self._simultaneous_queue.append(
            SimultaneousAction(
                pc_id=pc_id,
                action=action,
                target=target,
                priority=0
            )
        )

    def resolve_simultaneous_batch(self) -> list[ActionResult]:
        """
        Resolve all queued simultaneous actions in priority order.

        Returns:
            List of action results, ordered by priority (highest first)

        Raises:
            RuntimeError: If no actions queued
        """
        if not self._simultaneous_queue:
            raise RuntimeError("No simultaneous actions queued")

        # Sort by priority (highest first)
        sorted_actions = sorted(
            self._simultaneous_queue,
            key=lambda a: a.priority,
            reverse=True
        )

        # Create results (placeholder logic - actual resolution would be complex)
        results: list[ActionResult] = []
        for action in sorted_actions:
            # Simplified result - real implementation would involve dice rolls,
            # state checks, etc.
            result = ActionResult(
                character_id=action.pc_id,
                action=action.action,
                success=True,  # Placeholder
                result_description=f"{action.pc_id} performs: {action.action}",
                priority=action.priority
            )
            results.append(result)

        # Clear queue
        self._simultaneous_queue.clear()

        return results

    def can_act(self, pc_id: str) -> bool:
        """
        Check if a PC can act based on current distribution mode.

        Args:
            pc_id: Character ID to check

        Returns:
            True if PC can act, False otherwise
        """
        if self.state is None:
            return False

        # Must be in turn order
        if pc_id not in self.state.turn_order:
            return False

        # Check by distribution mode
        if self.state.distribution_mode == TurnDistribution.FREE_FORM:
            # Anyone can act anytime
            return True

        elif self.state.distribution_mode == TurnDistribution.ROUND_ROBIN:
            # Only current PC can act
            return pc_id == self.state.current_pc_id

        elif self.state.distribution_mode == TurnDistribution.SPOTLIGHT:
            # Only spotlighted PC can act
            return pc_id == self.state.current_pc_id

        elif self.state.distribution_mode == TurnDistribution.POPCORN:
            # Only current PC can act
            return pc_id == self.state.current_pc_id

        return False

    def set_distribution_mode(self, mode: TurnDistribution) -> None:
        """
        Change the turn distribution mode mid-round.

        Args:
            mode: New distribution mode

        Raises:
            RuntimeError: If no active round
        """
        if self.state is None:
            raise RuntimeError("No active round")

        self.state.distribution_mode = mode

        # Adjust state based on new mode
        if mode == TurnDistribution.FREE_FORM:
            # Clear current turn
            self.state.current_pc_id = None
            self.state.turn_start_time = None
        elif mode != TurnDistribution.FREE_FORM and self.state.current_pc_id is None:
            # Switching from free-form, set first PC as current
            if self.state.turn_order:
                self.state.current_pc_id = self.state.turn_order[0]
                self.state.turn_start_time = datetime.now()

    def check_timeout(self) -> Optional[str]:
        """
        Check if the current turn has exceeded the timeout.

        Returns:
            Character ID of timed-out PC, or None if no timeout

        Raises:
            RuntimeError: If no active round
        """
        if self.state is None:
            raise RuntimeError("No active round")

        # Free-form mode has no timeouts
        if self.state.distribution_mode == TurnDistribution.FREE_FORM:
            return None

        # No current turn
        if not self.state.current_pc_id or not self.state.turn_start_time:
            return None

        # Check elapsed time
        elapsed = datetime.now() - self.state.turn_start_time
        timeout = timedelta(seconds=self.config.turn_timeout_seconds)

        if elapsed > timeout:
            return self.state.current_pc_id

        return None

    def handle_timeout(self, pc_id: str) -> None:
        """
        Handle a turn timeout by automatically passing the turn.

        Args:
            pc_id: Character ID that timed out

        Raises:
            RuntimeError: If no active round
            ValueError: If pc_id doesn't match current PC
        """
        if self.state is None:
            raise RuntimeError("No active round")

        if pc_id != self.state.current_pc_id:
            raise ValueError(f"Character {pc_id} is not the current PC")

        # Record a timeout action
        record = TurnRecord(
            turn_number=len(self.state.completed_turns) + 1,
            round_number=self.state.current_round,
            character_id=pc_id,
            phase=self.state.phase,
            action_summary="[Turn timed out - auto-passed]",
            timestamp=datetime.now()
        )
        self.turn_history.append(record)

        # Advance to next turn
        self.advance_turn()

    def build_combat_order(
        self,
        participants: list[str],
        initiative_rolls: dict[str, int]
    ) -> list[str]:
        """
        Build combat turn order based on initiative rolls.

        Args:
            participants: List of character IDs participating in combat
            initiative_rolls: Map of character ID to initiative roll result

        Returns:
            Ordered list of character IDs (highest initiative first)

        Raises:
            ValueError: If participants is empty or missing initiative rolls
        """
        if not participants:
            raise ValueError("Participants list cannot be empty")

        # Verify all participants have initiative rolls
        missing = [p for p in participants if p not in initiative_rolls]
        if missing:
            raise ValueError(f"Missing initiative rolls for: {missing}")

        # Store initiatives for later use (e.g., inserting mid-combat)
        self._combat_initiatives.update(initiative_rolls)

        # Sort by initiative (highest first)
        sorted_participants = sorted(
            participants,
            key=lambda pc: initiative_rolls[pc],
            reverse=True
        )

        return sorted_participants

    def insert_into_initiative(self, character_id: str, initiative: int) -> None:
        """
        Insert a character into the combat order mid-combat.

        Args:
            character_id: Character ID to insert
            initiative: Initiative value for the character

        Raises:
            RuntimeError: If no active round or not in combat phase
            ValueError: If character already in turn order
        """
        if self.state is None:
            raise RuntimeError("No active round")

        if self.state.phase != TurnPhase.COMBAT:
            raise RuntimeError("Can only insert into initiative during combat")

        if character_id in self.state.turn_order:
            raise ValueError(f"Character {character_id} already in turn order")

        # Add new character to initiatives
        self._combat_initiatives[character_id] = initiative

        # Rebuild order with all current participants
        all_participants = list(self._combat_initiatives.keys())
        new_order = self.build_combat_order(all_participants, self._combat_initiatives)

        self.state.turn_order = new_order

    def record_action(self, character_id: str, action_summary: str) -> TurnRecord:
        """
        Record an action in the turn history.

        Args:
            character_id: Character who performed the action
            action_summary: Brief description of the action

        Returns:
            The created turn record

        Raises:
            RuntimeError: If no active round
        """
        if self.state is None:
            raise RuntimeError("No active round")

        turn_number = len(self.state.completed_turns) + 1

        record = TurnRecord(
            turn_number=turn_number,
            round_number=self.state.current_round,
            character_id=character_id,
            phase=self.state.phase,
            action_summary=action_summary,
            timestamp=datetime.now()
        )

        self.turn_history.append(record)
        return record

    def get_turn_history(
        self,
        character_id: Optional[str] = None,
        limit: int = 50
    ) -> list[TurnRecord]:
        """
        Get turn history, optionally filtered by character.

        Args:
            character_id: If provided, filter to only this character's turns
            limit: Maximum number of records to return (most recent first)

        Returns:
            List of turn records (newest first)
        """
        # Filter by character if specified
        if character_id:
            filtered = [
                record for record in self.turn_history
                if record.character_id == character_id
            ]
        else:
            filtered = self.turn_history

        # Return most recent first, up to limit
        return list(reversed(filtered[-limit:]))


__all__ = [
    "TurnPhase",
    "TurnDistribution",
    "TurnRecord",
    "ActionResult",
    "SimultaneousAction",
    "TurnState",
    "TurnManager",
]
