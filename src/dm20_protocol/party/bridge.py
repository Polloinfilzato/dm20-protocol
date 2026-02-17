"""
Integration bridge between Party Mode queues and existing dm20 systems.

Thin adapter that delegates to PermissionResolver, OutputFilter, and
PrivateInfoManager. No business logic lives here — the bridge just
translates between queue data formats and the existing API surfaces.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from dm20_protocol.permissions import PermissionResolver, PlayerRole
from dm20_protocol.storage import DnDStorage

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


def get_combat_state(player_id: str) -> Optional[dict[str, Any]]:
    """
    Get current combat state for a player.

    Placeholder for Task 154 (Combat Turn Coordination).

    Args:
        player_id: The player requesting combat state

    Returns:
        Combat state dict, or None if not in combat
    """
    # TODO: Will be implemented in Task 154
    return None


__all__ = [
    "format_response",
    "get_character_view",
    "get_combat_state",
]
