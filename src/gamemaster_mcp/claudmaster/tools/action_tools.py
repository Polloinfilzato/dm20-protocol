"""
Action processing tools for Claudmaster AI DM system.

This module provides the player_action MCP tool for processing player input
through the multi-agent orchestrator pipeline, returning structured responses
with narrative, state changes, dice rolls, and NPC interactions.
"""

import logging
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..orchestrator import Orchestrator, IntentType, PlayerIntent, OrchestratorResponse
from ..session import ClaudmasterSession
from .session_tools import _session_manager

logger = logging.getLogger("gamemaster-mcp")


# ============================================================================
# Response Models
# ============================================================================

class DiceRoll(BaseModel):
    """Represents a dice roll that occurred during action processing."""
    dice: str = Field(description="Dice notation (e.g., '1d20+5', '2d6')")
    result: int = Field(description="The numeric result of the dice roll")
    purpose: str = Field(description="Why this roll was made (e.g., 'attack roll', 'perception check')")


class NPCResponse(BaseModel):
    """Represents an NPC's reaction or response to player action."""
    npc_name: str = Field(description="Name of the NPC responding")
    dialogue: Optional[str] = Field(default=None, description="NPC dialogue, if any")
    reaction: Optional[str] = Field(default=None, description="NPC's reaction (e.g., 'surprised', 'hostile')")
    attitude_change: Optional[str] = Field(
        default=None,
        description="Change in NPC attitude (e.g., 'friendly -> neutral')"
    )


class StateChange(BaseModel):
    """Represents a change to game state resulting from player action."""
    entity: str = Field(description="What changed (character name, location, quest, etc.)")
    field: str = Field(description="What field changed (e.g., 'hp', 'location', 'inventory')")
    old_value: Optional[str] = Field(default=None, description="Previous value (if applicable)")
    new_value: str = Field(description="New value after the change")


class ActionType(str, Enum):
    """Classification of player action type."""
    COMBAT = "combat"
    ROLEPLAY = "roleplay"
    EXPLORATION = "exploration"
    PUZZLE = "puzzle"
    SKILL_CHECK = "skill_check"
    REST = "rest"
    INVENTORY = "inventory"
    MIXED = "mixed"


class ActionResponse(BaseModel):
    """Complete response from processing a player action."""
    narrative: str = Field(description="The DM's narrative response to the action")
    action_type: ActionType = Field(description="Type of action that was processed")
    state_changes: list[StateChange] = Field(
        default_factory=list,
        description="List of game state changes resulting from the action"
    )
    dice_rolls: list[DiceRoll] = Field(
        default_factory=list,
        description="List of dice rolls made during action resolution"
    )
    npc_responses: list[NPCResponse] = Field(
        default_factory=list,
        description="List of NPC reactions or responses"
    )
    follow_up_options: Optional[list[str]] = Field(
        default=None,
        description="Suggested follow-up actions or options for the player"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="List of warnings or error messages"
    )
    character_name: Optional[str] = Field(
        default=None,
        description="Name of the character who performed the action"
    )
    turn_number: int = Field(
        default=0,
        description="Turn number when this action was processed"
    )


# ============================================================================
# Action Processor
# ============================================================================

class ActionProcessor:
    """
    Processes player actions through the orchestrator pipeline.

    This class handles the translation of player input into structured action
    responses, coordinating intent classification, agent execution, and response
    aggregation.
    """

    def __init__(self, session_manager) -> None:
        """
        Initialize the ActionProcessor.

        Args:
            session_manager: The SessionManager instance managing active sessions
        """
        self.session_manager = session_manager

    def _get_active_session(self, session_id: str) -> tuple[Orchestrator, ClaudmasterSession]:
        """
        Get orchestrator and session for active session_id.

        Args:
            session_id: The session ID to retrieve

        Returns:
            Tuple of (Orchestrator, ClaudmasterSession)

        Raises:
            ValueError: If session_id is not found in active sessions
        """
        if session_id not in self.session_manager._active_sessions:
            raise ValueError(f"Session {session_id} not found in active sessions")

        return self.session_manager._active_sessions[session_id]

    def _map_intent_to_action_type(self, intent: PlayerIntent) -> ActionType:
        """
        Map IntentType to ActionType enum.

        Args:
            intent: The classified player intent

        Returns:
            Corresponding ActionType
        """
        mapping = {
            IntentType.COMBAT: ActionType.COMBAT,
            IntentType.ROLEPLAY: ActionType.ROLEPLAY,
            IntentType.EXPLORATION: ActionType.EXPLORATION,
            IntentType.QUESTION: ActionType.SKILL_CHECK,
            IntentType.SYSTEM: ActionType.INVENTORY,
            IntentType.ACTION: ActionType.MIXED,
        }
        return mapping.get(intent.intent_type, ActionType.MIXED)

    def _extract_npc_responses(self, orchestrator_response: OrchestratorResponse) -> list[NPCResponse]:
        """
        Extract NPC interactions from agent responses metadata.

        Args:
            orchestrator_response: The orchestrator's aggregated response

        Returns:
            List of NPCResponse objects extracted from agent metadata
        """
        npc_responses: list[NPCResponse] = []

        for agent_response in orchestrator_response.agent_responses:
            # Check if agent has NPC interaction data in observations
            if "npc_interactions" in agent_response.observations:
                interactions = agent_response.observations["npc_interactions"]
                if isinstance(interactions, list):
                    for interaction in interactions:
                        if isinstance(interaction, dict):
                            npc_responses.append(NPCResponse(**interaction))

            # Also check metadata for legacy format
            if "npc_responses" in agent_response.metadata:
                responses = agent_response.metadata["npc_responses"]
                if isinstance(responses, list):
                    for response in responses:
                        if isinstance(response, dict):
                            npc_responses.append(NPCResponse(**response))

        return npc_responses

    def _extract_dice_rolls(self, orchestrator_response: OrchestratorResponse) -> list[DiceRoll]:
        """
        Extract dice rolls from agent responses metadata.

        Args:
            orchestrator_response: The orchestrator's aggregated response

        Returns:
            List of DiceRoll objects extracted from agent metadata
        """
        dice_rolls: list[DiceRoll] = []

        for agent_response in orchestrator_response.agent_responses:
            # Check if agent has dice roll data in observations
            if "dice_rolls" in agent_response.observations:
                rolls = agent_response.observations["dice_rolls"]
                if isinstance(rolls, list):
                    for roll in rolls:
                        if isinstance(roll, dict):
                            dice_rolls.append(DiceRoll(**roll))

            # Also check metadata for legacy format
            if "dice_rolls" in agent_response.metadata:
                rolls = agent_response.metadata["dice_rolls"]
                if isinstance(rolls, list):
                    for roll in rolls:
                        if isinstance(roll, dict):
                            dice_rolls.append(DiceRoll(**roll))

        return dice_rolls

    def _extract_state_changes(self, orchestrator_response: OrchestratorResponse) -> list[StateChange]:
        """
        Convert raw state_changes dicts to StateChange models.

        Args:
            orchestrator_response: The orchestrator's aggregated response

        Returns:
            List of StateChange objects
        """
        state_changes: list[StateChange] = []

        for change_dict in orchestrator_response.state_changes:
            if isinstance(change_dict, dict):
                try:
                    state_changes.append(StateChange(**change_dict))
                except Exception as e:
                    logger.warning(f"Failed to parse state change {change_dict}: {e}")

        return state_changes

    async def process_action(
        self,
        session_id: str,
        action: str,
        character_name: Optional[str] = None,
        context: Optional[str] = None
    ) -> ActionResponse:
        """
        Main action processing method.

        This method orchestrates the complete player action workflow:
        1. Validate session is active
        2. Get orchestrator and session
        3. If character_name provided, set context for PC identification
        4. Classify intent via orchestrator
        5. Process through orchestrator pipeline
        6. Build ActionResponse from OrchestratorResponse
        7. Increment turn counter
        8. Return structured response

        Args:
            session_id: The active session ID
            action: The player's action text
            character_name: Optional name of character performing the action
            context: Optional additional context for the action

        Returns:
            ActionResponse with narrative, state changes, dice rolls, etc.
        """
        try:
            # Step 1 & 2: Validate and get session
            orchestrator, session = self._get_active_session(session_id)

            # Step 3: Build context if provided
            if character_name or context:
                # Store in session metadata for PC identification
                if character_name:
                    session.metadata["acting_character"] = character_name
                if context:
                    session.metadata["action_context"] = context

            # Step 4 & 5: Process through orchestrator
            orchestrator_response = await orchestrator.process_player_input(action)

            # Get intent from most recent classification
            # The orchestrator.process_player_input already classified the intent
            intent = orchestrator.classify_intent(action)

            # Step 6: Build ActionResponse
            action_type = self._map_intent_to_action_type(intent)
            state_changes = self._extract_state_changes(orchestrator_response)
            dice_rolls = self._extract_dice_rolls(orchestrator_response)
            npc_responses = self._extract_npc_responses(orchestrator_response)

            # Extract follow-up options from metadata if available
            follow_up_options = orchestrator_response.metadata.get("follow_up_options")

            # Step 7: Turn counter already incremented by process_player_input
            turn_number = session.turn_count

            # Clean up temporary metadata
            session.metadata.pop("acting_character", None)
            session.metadata.pop("action_context", None)

            return ActionResponse(
                narrative=orchestrator_response.narrative,
                action_type=action_type,
                state_changes=state_changes,
                dice_rolls=dice_rolls,
                npc_responses=npc_responses,
                follow_up_options=follow_up_options,
                character_name=character_name,
                turn_number=turn_number,
                warnings=[]
            )

        except ValueError as e:
            # Session not found or validation error
            logger.warning(f"Validation error in process_action: {e}")
            return ActionResponse(
                narrative=f"Session {session_id} not found. Please start a session first.",
                action_type=ActionType.MIXED,
                warnings=[str(e)],
                turn_number=0
            )

        except Exception as e:
            # Orchestrator errors or other unexpected errors
            logger.error(f"Error processing action in session {session_id}: {e}", exc_info=True)
            return ActionResponse(
                narrative=f"I encountered an issue processing that action. {type(e).__name__}: {str(e)}",
                action_type=ActionType.MIXED,
                warnings=[f"{type(e).__name__}: {str(e)}"],
                turn_number=0
            )


# ============================================================================
# MCP Tool Function
# ============================================================================

async def player_action(
    session_id: str,
    action: str,
    character_name: Optional[str] = None,
    context: Optional[str] = None
) -> dict:
    """
    Process a player action in the current Claudmaster session.

    This is the main MCP tool function for player interaction with the AI DM.
    It processes the player's action through the multi-agent orchestrator and
    returns a structured response with narrative, state changes, dice rolls,
    and NPC interactions.

    Args:
        session_id: The active session ID to process the action in
        action: The player's action as natural language text
            Examples: "I attack the goblin with my sword"
                     "I try to persuade the guard to let us through"
                     "I search the room for traps"
        character_name: Optional name of the character performing the action
            Used for multi-PC parties to track which character acted
        context: Optional additional context about the action
            Useful for clarifying ambiguous actions or providing extra details

    Returns:
        Dictionary representation of ActionResponse with the following keys:
            - narrative: The DM's narrative response to the action
            - action_type: Type of action (combat, roleplay, exploration, etc.)
            - state_changes: List of game state changes (HP, location, inventory, etc.)
            - dice_rolls: List of dice rolls made during the action
            - npc_responses: List of NPC reactions or responses
            - follow_up_options: Suggested follow-up actions (if any)
            - warnings: Any warnings or errors encountered
            - character_name: Name of the acting character (if provided)
            - turn_number: Turn number when this action was processed

    Examples:
        Basic action:
        >>> result = await player_action(
        ...     session_id="abc123",
        ...     action="I attack the orc with my longsword"
        ... )

        Action with character name (multi-PC party):
        >>> result = await player_action(
        ...     session_id="abc123",
        ...     action="I cast fireball at the group of goblins",
        ...     character_name="Gandalf"
        ... )

        Action with context:
        >>> result = await player_action(
        ...     session_id="abc123",
        ...     action="I try to sneak past",
        ...     context="Using the shadows for cover"
        ... )
    """
    # Create processor instance
    processor = ActionProcessor(_session_manager)

    # Process the action
    response = await processor.process_action(
        session_id=session_id,
        action=action,
        character_name=character_name,
        context=context
    )

    # Return as dictionary
    return response.model_dump()


__all__ = [
    "DiceRoll",
    "NPCResponse",
    "StateChange",
    "ActionType",
    "ActionResponse",
    "ActionProcessor",
    "player_action",
]
