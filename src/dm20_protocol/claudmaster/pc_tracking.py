"""
Player Character Tracking system for the Claudmaster multi-agent framework.

This module provides multi-PC tracking capabilities for the Orchestrator,
allowing it to manage multiple player characters in a single session.
It handles PC registration, state tracking, and action attribution.

Key components:
- PCState: Tracks individual PC state (location, action, status)
- MultiPlayerConfig: Session-wide configuration for multi-PC games
- PCRegistry: Manages PC registration and state updates
- PCIdentifier: Identifies which PC is acting from player input
"""

from dataclasses import field
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from dm20_protocol.permissions import PlayerRole


class PCState(BaseModel):
    """Tracks the current state of a player character."""

    character_id: str = Field(description="Unique identifier for the character")
    player_name: str = Field(description="Name of the player controlling this character")
    role: PlayerRole = Field(
        default=PlayerRole.PLAYER,
        description="The player's role in the session (DM, PLAYER, or OBSERVER)"
    )
    current_action: Optional[str] = Field(
        default=None,
        description="Description of the character's current/last action"
    )
    location: Optional[str] = Field(
        default=None,
        description="Current location or scene the character is in"
    )
    is_active: bool = Field(
        default=True,
        description="Whether the character is currently active in the session"
    )
    last_action_time: Optional[datetime] = Field(
        default=None,
        description="Timestamp of the character's last recorded action"
    )
    status_effects: list[str] = Field(
        default_factory=list,
        description="List of active status effects on the character"
    )
    private_notes: list[str] = Field(
        default_factory=list,
        description="GM notes about this character (not visible to players)"
    )


class MultiPlayerConfig(BaseModel):
    """Configuration for multi-player sessions."""

    max_players: int = Field(
        default=6,
        ge=1,
        le=12,
        description="Maximum number of player characters allowed in the session"
    )
    allow_dynamic_join: bool = Field(
        default=True,
        description="Whether players can join/leave during the session"
    )
    turn_timeout_seconds: int = Field(
        default=300,
        ge=30,
        description="Maximum seconds to wait for player action before prompting"
    )
    simultaneous_actions: bool = Field(
        default=False,
        description="Whether multiple PCs can act simultaneously (experimental)"
    )
    pc_list: list[str] = Field(
        default_factory=list,
        description="Pre-configured list of character IDs for the session"
    )


class PCRegistry:
    """Manages player character registration and state tracking."""

    def __init__(self, config: MultiPlayerConfig):
        """
        Initialize the PC registry with configuration.

        Args:
            config: Multi-player session configuration
        """
        self.config = config
        self._registry: dict[str, PCState] = {}
        self._active_pc: Optional[str] = None

    @property
    def active_pc(self) -> Optional[str]:
        """Get the currently active PC character ID."""
        return self._active_pc

    @active_pc.setter
    def active_pc(self, character_id: Optional[str]) -> None:
        """
        Set the currently active PC.

        Args:
            character_id: Character ID to set as active, or None to clear

        Raises:
            ValueError: If character_id is not None and not registered
        """
        if character_id is not None and character_id not in self._registry:
            raise ValueError(f"Character {character_id} not registered")
        self._active_pc = character_id

    def register_pc(self, character_id: str, player_name: str) -> PCState:
        """
        Register a player character for the session.

        Args:
            character_id: Unique identifier for the character
            player_name: Name of the player controlling this character

        Returns:
            The created PCState

        Raises:
            ValueError: If max_players exceeded or character_id already registered
        """
        if len(self._registry) >= self.config.max_players:
            raise ValueError(f"Maximum {self.config.max_players} players reached")
        if character_id in self._registry:
            raise ValueError(f"Character {character_id} already registered")

        state = PCState(character_id=character_id, player_name=player_name)
        self._registry[character_id] = state
        return state

    def unregister_pc(self, character_id: str) -> None:
        """
        Remove a PC from the session.

        Args:
            character_id: Character ID to unregister

        Raises:
            KeyError: If character not registered
            RuntimeError: If dynamic join/leave is disabled
        """
        if character_id not in self._registry:
            raise KeyError(f"Character {character_id} not registered")
        if not self.config.allow_dynamic_join:
            raise RuntimeError("Dynamic join/leave is disabled")
        del self._registry[character_id]
        if self._active_pc == character_id:
            self._active_pc = None

    def get_pc_state(self, character_id: str) -> PCState:
        """
        Get current state for a specific PC.

        Args:
            character_id: Character ID to look up

        Returns:
            The PCState for the character

        Raises:
            KeyError: If character not registered
        """
        if character_id not in self._registry:
            raise KeyError(f"Character {character_id} not registered")
        return self._registry[character_id]

    def update_pc_state(self, character_id: str, **updates) -> PCState:
        """
        Update state for a specific PC.

        Args:
            character_id: Character ID to update
            **updates: Field updates to apply to the PCState

        Returns:
            The updated PCState

        Raises:
            KeyError: If character not registered
            AttributeError: If invalid field name in updates
        """
        state = self.get_pc_state(character_id)
        for key, value in updates.items():
            if not hasattr(state, key):
                raise AttributeError(f"PCState has no attribute '{key}'")
            setattr(state, key, value)
        state.last_action_time = datetime.now()
        return state

    def get_all_active(self) -> list[PCState]:
        """
        Get all active PCs.

        Returns:
            List of PCState objects for all active characters
        """
        return [s for s in self._registry.values() if s.is_active]

    def get_all_pcs(self) -> list[PCState]:
        """
        Get all registered PCs.

        Returns:
            List of all PCState objects in the registry
        """
        return list(self._registry.values())

    # ------------------------------------------------------------------
    # Session Participant Tracking
    # ------------------------------------------------------------------

    def join_session(
        self,
        character_id: str,
        player_name: str,
        role: PlayerRole = PlayerRole.PLAYER,
    ) -> PCState:
        """Register a PC joining the session with participant tracking.

        If the character is already registered but inactive, reactivates them.
        If not registered at all, registers and activates them.

        Args:
            character_id: Unique identifier for the character.
            player_name: Name of the player controlling this character.
            role: The player's role (DM, PLAYER, OBSERVER).

        Returns:
            The PCState for the joined character.
        """
        if character_id in self._registry:
            state = self._registry[character_id]
            state.is_active = True
            state.last_action_time = datetime.now()
            state.role = role
            return state

        # New registration (bypasses max_players for rejoining)
        state = PCState(
            character_id=character_id,
            player_name=player_name,
            role=role,
            is_active=True,
            last_action_time=datetime.now(),
        )
        self._registry[character_id] = state
        return state

    def leave_session(self, character_id: str) -> bool:
        """Mark a PC as leaving the session (deactivated, not removed).

        Args:
            character_id: Character ID to deactivate.

        Returns:
            True if the character was found and deactivated, False otherwise.
        """
        if character_id not in self._registry:
            return False

        self._registry[character_id].is_active = False
        if self._active_pc == character_id:
            self._active_pc = None
        return True

    def heartbeat(self, character_id: str) -> bool:
        """Update a PC's last_action_time timestamp.

        Used to track activity and detect idle/disconnected participants.

        Args:
            character_id: Character ID sending the heartbeat.

        Returns:
            True if the character was found and updated, False otherwise.
        """
        if character_id not in self._registry:
            return False

        state = self._registry[character_id]
        if not state.is_active:
            return False

        state.last_action_time = datetime.now()
        return True

    @property
    def count(self) -> int:
        """Get total number of registered PCs."""
        return len(self._registry)

    @property
    def active_count(self) -> int:
        """Get number of active PCs."""
        return len([s for s in self._registry.values() if s.is_active])


class PCIdentifier:
    """Identifies which PC is acting from player input."""

    def __init__(self, registry: PCRegistry):
        """
        Initialize the PC identifier.

        Args:
            registry: The PCRegistry to use for lookups
        """
        self._registry = registry
        self._last_speaker: Optional[str] = None

    def identify_acting_pc(self, input_text: str) -> Optional[str]:
        """
        Identify which PC is taking an action from input text.

        Strategies (in order):
        1. Explicit naming: "Gandalf attacks the orc"
        2. Player name mapping: "John: I cast fireball"
        3. Pronoun resolution: Track who spoke last
        4. Context inference: Return active PC

        Args:
            input_text: Player input text to analyze

        Returns:
            Character ID of the acting PC, or None if cannot determine
        """
        # Strategy 1: Check for character name in input
        for state in self._registry.get_all_pcs():
            # Check character name (case-insensitive)
            name_lower = state.character_id.lower()
            input_lower = input_text.lower()
            if name_lower in input_lower:
                self._last_speaker = state.character_id
                return state.character_id

        # Strategy 2: Player name mapping ("PlayerName: action")
        if ":" in input_text:
            prefix = input_text.split(":", 1)[0].strip().lower()
            for state in self._registry.get_all_pcs():
                if state.player_name.lower() == prefix:
                    self._last_speaker = state.character_id
                    return state.character_id

        # Strategy 3: Return last speaker if available
        if self._last_speaker and self._last_speaker in [
            s.character_id for s in self._registry.get_all_active()
        ]:
            return self._last_speaker

        # Strategy 4: Return active PC from registry
        active = self._registry.active_pc
        if active:
            return active

        # Fallback: return first active PC
        active_pcs = self._registry.get_all_active()
        if active_pcs:
            return active_pcs[0].character_id

        return None

    def set_last_speaker(self, character_id: str) -> None:
        """
        Explicitly set who spoke last.

        Args:
            character_id: Character ID to mark as last speaker
        """
        self._last_speaker = character_id

    def clear_last_speaker(self) -> None:
        """Clear last speaker tracking."""
        self._last_speaker = None


__all__ = [
    "PCState",
    "MultiPlayerConfig",
    "PCRegistry",
    "PCIdentifier",
]
