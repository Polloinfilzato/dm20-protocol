"""
Integration bridge between Party Mode queues and existing dm20 systems.

Thin adapter that delegates to PermissionResolver, OutputFilter, and
PrivateInfoManager. No business logic lives here — the bridge just
translates between queue data formats and the existing API surfaces.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from dm20_protocol.permissions import PermissionResolver, PlayerRole
from dm20_protocol.storage import DnDStorage

if TYPE_CHECKING:
    from dm20_protocol.claudmaster.turn_manager import TurnManager

logger = logging.getLogger("dm20-protocol.party.bridge")


def format_response(
    raw_response: dict[str, Any],
    player_id: str,
    permission_resolver: PermissionResolver,
) -> dict[str, Any]:
    """
    Filter a response for a specific player based on their role.

    Strips dm_only content for non-DM players. Includes private messages
    only for the matching player_id. OBSERVERs get only public narrative.

    Args:
        raw_response: Full response dict with narrative, private, dm_only
        player_id: The player to filter for
        permission_resolver: Used to determine player role

    Returns:
        Filtered response dict safe for the given player
    """
    role = permission_resolver.get_player_role(player_id)

    filtered: dict[str, Any] = {
        "id": raw_response.get("id"),
        "timestamp": raw_response.get("timestamp"),
        "action_id": raw_response.get("action_id"),
        "narrative": raw_response.get("narrative", ""),
    }

    # Observers only get public narrative
    if role == PlayerRole.OBSERVER:
        return filtered

    # Players get their own private messages
    private = raw_response.get("private", {})
    if player_id in private:
        filtered["private"] = private[player_id]

    # DM gets everything
    if role == PlayerRole.DM:
        if "dm_only" in raw_response:
            filtered["dm_only"] = raw_response["dm_only"]
        # DM also sees all private messages
        if private:
            filtered["all_private"] = private

    return filtered


def get_character_view(
    player_id: str,
    storage: DnDStorage,
    permission_resolver: PermissionResolver,
) -> Optional[dict[str, Any]]:
    """
    Get character data for a player with permission check.

    Args:
        player_id: The player whose character to retrieve
        storage: Campaign storage manager
        permission_resolver: Permission validation

    Returns:
        Character data dict, or None if not found or not permitted
    """
    allowed = permission_resolver.check_permission(
        player_id, "get_character", player_id
    )
    if not allowed:
        logger.warning(f"Permission denied: {player_id} -> get_character")
        return None

    try:
        character = storage.get_character(player_id)
        if character is None:
            return None
        return character.model_dump(mode="json")
    except Exception as e:
        logger.error(f"Failed to get character {player_id}: {e}")
        return None


def get_combat_state(
    player_id: str,
    turn_manager: TurnManager,
    storage: DnDStorage,
) -> Optional[dict[str, Any]]:
    """
    Get current combat state personalized for a specific player.

    Reads TurnManager state and builds a combat state dict including
    initiative order, current turn, round number, and a ``your_turn``
    boolean that is personalized per player.

    For simultaneous mode, returns the prompt, timeout, and submission
    status instead of turn-based fields.

    Args:
        player_id: The player requesting combat state
        turn_manager: Active TurnManager instance
        storage: Campaign storage for character lookups

    Returns:
        Combat state dict, or None if no active combat round
    """
    from dm20_protocol.claudmaster.turn_manager import TurnPhase

    state = turn_manager.state
    if state is None:
        return {
            "type": "combat_state",
            "data": {"active": False},
        }

    if state.phase != TurnPhase.COMBAT:
        return {
            "type": "combat_state",
            "data": {"active": False},
        }

    # Determine mode from distribution_mode
    from dm20_protocol.claudmaster.turn_manager import TurnDistribution

    is_simultaneous = (
        state.distribution_mode == TurnDistribution.FREE_FORM
        and turn_manager._simultaneous_queue
    )

    if is_simultaneous:
        # Simultaneous mode state
        submitted = [a.pc_id for a in turn_manager._simultaneous_queue]
        waiting_for = [
            pc_id for pc_id in state.turn_order if pc_id not in submitted
        ]
        return {
            "type": "combat_state",
            "data": {
                "active": True,
                "mode": "simultaneous",
                "prompt": "Everyone act simultaneously!",
                "timeout_seconds": 300,
                "submitted": submitted,
                "waiting_for": waiting_for,
            },
        }

    # Turn-based mode
    current_turn = turn_manager.get_current_turn()
    initiative_list = _build_initiative_list(
        state.turn_order, turn_manager._combat_initiatives, storage
    )

    return {
        "type": "combat_state",
        "data": {
            "active": True,
            "mode": "turn_based",
            "current_turn": current_turn,
            "round": state.current_round,
            "initiative": initiative_list,
            "your_turn": current_turn == player_id,
        },
    }


def is_players_turn(player_id: str, turn_manager: TurnManager) -> bool:
    """
    Check whether it is the given player's turn.

    A simple convenience wrapper around TurnManager.can_act() that
    also returns False when no round is active.

    Args:
        player_id: The player to check
        turn_manager: Active TurnManager instance

    Returns:
        True if the player can act right now, False otherwise
    """
    return turn_manager.can_act(player_id)


def _build_initiative_list(
    turn_order: list[str],
    combat_initiatives: dict[str, int],
    storage: DnDStorage,
) -> list[dict[str, Any]]:
    """
    Build a detailed initiative list with character stats.

    For each character in the turn order, looks up HP, max HP, AC,
    and active conditions from the storage layer.

    Args:
        turn_order: Ordered list of character IDs
        combat_initiatives: Map of character_id -> initiative roll
        storage: Campaign storage for character data

    Returns:
        List of initiative entry dicts with id, name, initiative,
        hp, max_hp, ac, and conditions
    """
    entries: list[dict[str, Any]] = []
    for char_id in turn_order:
        entry: dict[str, Any] = {
            "id": char_id,
            "name": char_id,
            "initiative": combat_initiatives.get(char_id, 0),
            "hp": 0,
            "max_hp": 0,
            "ac": 10,
            "conditions": [],
        }

        try:
            character = storage.get_character(char_id)
            if character is not None:
                entry["name"] = character.name
                entry["hp"] = character.hit_points_current
                entry["max_hp"] = character.hit_points_max
                entry["ac"] = character.armor_class
                entry["conditions"] = list(character.conditions)
        except Exception as e:
            logger.debug(f"Could not load character data for {char_id}: {e}")

        entries.append(entry)

    return entries


__all__ = [
    "format_response",
    "get_character_view",
    "get_combat_state",
    "is_players_turn",
]
