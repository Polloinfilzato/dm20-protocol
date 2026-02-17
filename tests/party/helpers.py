"""
Helper utilities for Party Mode E2E tests.

Provides SimulatedPlayer wrapper and assertion helpers for permission
boundary testing.
"""

from __future__ import annotations

from typing import Any

from starlette.testclient import TestClient

from dm20_protocol.party.server import PartyServer


class SimulatedPlayer:
    """
    Wraps a Starlette TestClient to simulate a player in E2E tests.

    Provides convenience methods for HTTP and WebSocket interactions
    using the player's token.
    """

    def __init__(self, player_id: str, token: str, client: TestClient) -> None:
        self.player_id = player_id
        self.token = token
        self.client = client
        self.received_messages: list[dict[str, Any]] = []

    # -- HTTP helpers -------------------------------------------------------

    def submit_action(self, action_text: str) -> dict[str, Any]:
        """POST /action with this player's token."""
        resp = self.client.post(
            "/action",
            json={"action": action_text},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        return resp.json()

    def get_action_status(self, action_id: str) -> dict[str, Any]:
        """GET /action/{id}/status."""
        resp = self.client.get(f"/action/{action_id}/status")
        return resp.json()

    def get_character(self, target_id: str) -> tuple[int, dict[str, Any]]:
        """GET /character/{target_id} with this player's token."""
        resp = self.client.get(f"/character/{target_id}?token={self.token}")
        return resp.status_code, resp.json()

    def get_play_page(self) -> tuple[int, str]:
        """GET /play with this player's token."""
        resp = self.client.get(f"/play?token={self.token}")
        return resp.status_code, resp.text


def make_players(server: PartyServer, player_ids: list[str]) -> dict[str, SimulatedPlayer]:
    """Create SimulatedPlayer instances for the given player IDs."""
    client = TestClient(server.app)
    tokens = server.token_manager.get_all_tokens()
    return {
        pid: SimulatedPlayer(pid, tokens[pid], client)
        for pid in player_ids
    }


def assert_no_private_leak(
    messages: list[dict[str, Any]],
    owner_id: str,
    all_player_ids: list[str],
) -> list[str]:
    """
    Check that a player's messages contain no private content
    belonging to other players.

    Returns a list of violation descriptions (empty = no violations).
    """
    violations: list[str] = []
    for msg in messages:
        # Check direct private field
        private = msg.get("private")
        if private is not None:
            # 'private' should be a string (this player's private msg)
            # not a dict with other players' keys
            if isinstance(private, dict):
                for other_id in all_player_ids:
                    if other_id != owner_id and other_id in private:
                        violations.append(
                            f"{owner_id} received private content for {other_id} "
                            f"in msg {msg.get('id')}"
                        )

        # Check all_private field (should only appear for DM)
        if "all_private" in msg:
            violations.append(
                f"{owner_id} received 'all_private' field in msg {msg.get('id')}"
            )

        # Check dm_only field
        if "dm_only" in msg:
            violations.append(
                f"{owner_id} received 'dm_only' field in msg {msg.get('id')}"
            )

    return violations
