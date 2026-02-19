"""
Game State Context Observer for the prefetch engine.

This module monitors game state changes and classifies the current context
(combat, exploration, dialogue, etc.) to determine when and what to prefetch.
Combat context triggers the most aggressive prefetching since it benefits
most from reduced latency.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("dm20-protocol")


class GameContext(str, Enum):
    """Classification of the current game context.

    Different contexts trigger different prefetch strategies:
    - COMBAT: Highest value — pre-generate hit/miss/crit narrative variants
    - EXPLORATION: Medium value — pre-generate location descriptions
    - DIALOGUE: Low value — too unpredictable for useful prefetching
    - IDLE: No prefetching needed
    """
    COMBAT = "combat"
    EXPLORATION = "exploration"
    DIALOGUE = "dialogue"
    IDLE = "idle"


@dataclass
class PlayerTurn:
    """Represents a player's upcoming turn in combat.

    Attributes:
        turn_id: Unique identifier for this turn.
        character_name: Name of the character whose turn it is.
        character_class: Character's class (e.g., "fighter", "wizard").
        target_name: Name of the most likely target.
        target_ac: Target's armor class.
        weapon: Primary weapon or spell being used.
        action_type: Expected action type (attack, spell, ability).
        context: Additional context about the combat state.
    """
    turn_id: str
    character_name: str
    character_class: str = "fighter"
    target_name: str = "enemy"
    target_ac: int = 15
    weapon: str = "longsword"
    action_type: str = "attack"
    context: dict[str, Any] = field(default_factory=dict)


class ContextObserver:
    """Monitors game state changes and triggers prefetch operations.

    The observer classifies the current game context based on signals in the
    game state (active combat, exploration markers, dialogue indicators) and
    invokes registered callbacks when the context changes or when a new
    player turn is about to start.

    The observer respects a configurable intensity level that controls how
    aggressively it triggers prefetch operations:
    - "off": No prefetching, observer is passive
    - "conservative": Only prefetch in combat (highest value)
    - "aggressive": Prefetch in combat and exploration

    Usage:
        observer = ContextObserver(intensity="conservative")

        # Register callback for combat prefetch
        observer.on_combat_turn(my_prefetch_callback)

        # Feed game state updates
        observer.on_state_change(game_state)
    """

    # Game state keys that signal combat context
    COMBAT_INDICATORS = {
        "combat_active",
        "in_combat",
        "initiative_order",
        "current_round",
    }

    # Game state keys that signal exploration context
    EXPLORATION_INDICATORS = {
        "exploring",
        "current_location",
        "travel_mode",
        "dungeon_room",
    }

    # Game state keys that signal dialogue context
    DIALOGUE_INDICATORS = {
        "dialogue_active",
        "speaking_npc",
        "conversation",
    }

    def __init__(self, intensity: str = "conservative") -> None:
        """Initialize the context observer.

        Args:
            intensity: Prefetch intensity level. One of: "off", "conservative",
                "aggressive". Default is "conservative".

        Raises:
            ValueError: If intensity is not a valid level.
        """
        valid_intensities = {"off", "conservative", "aggressive"}
        if intensity not in valid_intensities:
            raise ValueError(
                f"Invalid prefetch intensity '{intensity}'. "
                f"Must be one of: {', '.join(sorted(valid_intensities))}"
            )

        self._intensity = intensity
        self._current_context = GameContext.IDLE
        self._combat_turn_callbacks: list[Callable] = []
        self._context_change_callbacks: list[Callable] = []
        self._last_game_state: dict[str, Any] = {}

        logger.info(f"ContextObserver initialized with intensity={intensity}")

    @property
    def intensity(self) -> str:
        """Return the current prefetch intensity level."""
        return self._intensity

    @intensity.setter
    def intensity(self, value: str) -> None:
        """Set the prefetch intensity level.

        Args:
            value: New intensity level.

        Raises:
            ValueError: If value is not a valid level.
        """
        valid = {"off", "conservative", "aggressive"}
        if value not in valid:
            raise ValueError(
                f"Invalid prefetch intensity '{value}'. "
                f"Must be one of: {', '.join(sorted(valid))}"
            )
        old = self._intensity
        self._intensity = value
        if old != value:
            logger.info(f"Prefetch intensity changed: {old} -> {value}")

    @property
    def current_context(self) -> GameContext:
        """Return the currently classified game context."""
        return self._current_context

    def on_combat_turn(self, callback: Callable) -> None:
        """Register a callback for when a combat turn is about to start.

        The callback receives (game_state: dict, player_turn: PlayerTurn).

        Args:
            callback: Function to call when a combat turn is detected.
        """
        self._combat_turn_callbacks.append(callback)

    def on_context_change(self, callback: Callable) -> None:
        """Register a callback for when the game context changes.

        The callback receives (old_context: GameContext, new_context: GameContext).

        Args:
            callback: Function to call when context changes.
        """
        self._context_change_callbacks.append(callback)

    def on_state_change(self, game_state: dict[str, Any]) -> GameContext:
        """Process a game state update and trigger appropriate prefetch.

        Classifies the current context, detects changes, and invokes
        registered callbacks. This is the main entry point for the observer.

        Args:
            game_state: Current game state dictionary.

        Returns:
            The classified GameContext.
        """
        if self._intensity == "off":
            self._last_game_state = dict(game_state)
            return GameContext.IDLE

        # Classify the current context
        new_context = self._classify_context(game_state)

        # Detect context change
        if new_context != self._current_context:
            old_context = self._current_context
            self._current_context = new_context
            logger.info(
                f"Game context changed: {old_context.value} -> {new_context.value}"
            )
            self._notify_context_change(old_context, new_context)

        # Trigger combat prefetch if applicable
        if new_context == GameContext.COMBAT:
            self._check_combat_turn(game_state)

        self._last_game_state = dict(game_state)
        return new_context

    def should_prefetch(self, context: GameContext | None = None) -> bool:
        """Determine if prefetching should occur for the given context.

        Takes into account the current intensity setting.

        Args:
            context: Context to check. Uses current context if not provided.

        Returns:
            True if prefetching should be active for this context.
        """
        if self._intensity == "off":
            return False

        ctx = context or self._current_context

        if self._intensity == "conservative":
            return ctx == GameContext.COMBAT

        if self._intensity == "aggressive":
            return ctx in (GameContext.COMBAT, GameContext.EXPLORATION)

        return False

    def extract_player_turn(self, game_state: dict[str, Any]) -> PlayerTurn | None:
        """Extract player turn information from the game state.

        Attempts to build a PlayerTurn from the game state's combat data.
        Returns None if insufficient information is available.

        Args:
            game_state: Current game state dictionary.

        Returns:
            PlayerTurn if turn information can be extracted, None otherwise.
        """
        # Look for combat turn data
        current_turn = game_state.get("current_turn", {})
        if not current_turn:
            # Try alternative key names
            current_turn = game_state.get("active_turn", {})

        if not isinstance(current_turn, dict) or not current_turn:
            return None

        character_name = current_turn.get("character_name", "")
        if not character_name:
            character_name = current_turn.get("name", "")

        if not character_name:
            return None

        # Build turn ID from round and character
        round_num = game_state.get("current_round", 1)
        turn_id = f"round_{round_num}_{character_name.lower().replace(' ', '_')}"

        # Extract target info
        target = current_turn.get("target", {})
        target_name = target.get("name", "enemy") if isinstance(target, dict) else str(target) if target else "enemy"
        target_ac = target.get("ac", 15) if isinstance(target, dict) else 15

        return PlayerTurn(
            turn_id=turn_id,
            character_name=character_name,
            character_class=current_turn.get("class", "fighter"),
            target_name=target_name,
            target_ac=target_ac,
            weapon=current_turn.get("weapon", "weapon"),
            action_type=current_turn.get("action_type", "attack"),
            context={
                "round": round_num,
                "initiative_order": game_state.get("initiative_order", []),
                "combatants": game_state.get("combatants", []),
            },
        )

    def _classify_context(self, game_state: dict[str, Any]) -> GameContext:
        """Classify the current game context from state signals.

        Uses indicator keys to determine the most likely context.
        Priority: combat > exploration > dialogue > idle.

        Args:
            game_state: Current game state dictionary.

        Returns:
            Classified GameContext.
        """
        state_keys = set(game_state.keys())

        # Check combat indicators (highest priority)
        if state_keys & self.COMBAT_INDICATORS:
            # Verify combat is actually active (not just has the key)
            for key in self.COMBAT_INDICATORS:
                value = game_state.get(key)
                if value and value is not False:
                    return GameContext.COMBAT

        # Check exploration indicators
        if state_keys & self.EXPLORATION_INDICATORS:
            for key in self.EXPLORATION_INDICATORS:
                value = game_state.get(key)
                if value and value is not False:
                    return GameContext.EXPLORATION

        # Check dialogue indicators
        if state_keys & self.DIALOGUE_INDICATORS:
            for key in self.DIALOGUE_INDICATORS:
                value = game_state.get(key)
                if value and value is not False:
                    return GameContext.DIALOGUE

        return GameContext.IDLE

    def _check_combat_turn(self, game_state: dict[str, Any]) -> None:
        """Check for a new combat turn and trigger callbacks.

        Compares the current turn with the last known turn to detect
        changes. Only fires callbacks when a new turn is detected.

        Args:
            game_state: Current game state with combat data.
        """
        if not self._combat_turn_callbacks:
            return

        player_turn = self.extract_player_turn(game_state)
        if player_turn is None:
            return

        # Check if this is a new turn (different from last known)
        last_turn = self._last_game_state.get("current_turn", {})
        current_turn = game_state.get("current_turn", {})

        if current_turn != last_turn:
            logger.debug(
                f"New combat turn detected: {player_turn.character_name} "
                f"(turn_id={player_turn.turn_id})"
            )
            self._notify_combat_turn(game_state, player_turn)

    def _notify_combat_turn(
        self,
        game_state: dict[str, Any],
        player_turn: PlayerTurn,
    ) -> None:
        """Notify all registered combat turn callbacks.

        Args:
            game_state: Current game state.
            player_turn: Extracted player turn data.
        """
        for callback in self._combat_turn_callbacks:
            try:
                callback(game_state, player_turn)
            except Exception as e:
                logger.error(
                    f"Error in combat turn callback: {e}",
                    exc_info=True,
                )

    def _notify_context_change(
        self,
        old_context: GameContext,
        new_context: GameContext,
    ) -> None:
        """Notify all registered context change callbacks.

        Args:
            old_context: Previous game context.
            new_context: New game context.
        """
        for callback in self._context_change_callbacks:
            try:
                callback(old_context, new_context)
            except Exception as e:
                logger.error(
                    f"Error in context change callback: {e}",
                    exc_info=True,
                )


__all__ = [
    "ContextObserver",
    "GameContext",
    "PlayerTurn",
]
