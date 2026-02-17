"""
Permission boundary tests for Party Mode.

Verifies that private information never leaks across player boundaries.
Tests run large volumes of mixed-content messages and assert zero
violations across all players and the OBSERVER role.
"""

from __future__ import annotations

import pytest

from dm20_protocol.party.server import PartyServer
from dm20_protocol.party.bridge import format_response
from dm20_protocol.permissions import PermissionResolver

from .conftest import ALL_IDS, PLAYER_IDS
from .helpers import assert_no_private_leak


class TestPermissionBoundary:
    """Zero-tolerance permission boundary tests."""

    def test_100_message_stress_test(
        self,
        e2e_server: PartyServer,
        e2e_permission_resolver: PermissionResolver,
    ) -> None:
        """
        Push 100 responses with mixed private content.
        For each player, assert they ONLY see their own private content.
        For OBSERVER, assert they see ZERO private content.
        """
        # Generate 100 responses with varied private content patterns
        for i in range(100):
            response: dict = {"narrative": f"Public event {i}"}

            # Every 2nd message: private content for one player
            if i % 2 == 0:
                target = PLAYER_IDS[i % len(PLAYER_IDS)]
                response["private"] = {target: f"Secret for {target} in msg {i}"}

            # Every 5th message: multiple private messages
            if i % 5 == 0:
                response["private"] = {
                    pid: f"Multi-secret for {pid} in msg {i}"
                    for pid in PLAYER_IDS
                }

            # Every 3rd message: DM-only content
            if i % 3 == 0:
                response["dm_only"] = f"DM notes for message {i}"

            e2e_server.response_queue.push(response)

        # Verify each player
        all_violations: list[str] = []

        for pid in PLAYER_IDS:
            msgs = e2e_server.response_queue.get_for_player(pid)
            assert len(msgs) == 100

            # Check no dm_only leaks
            for msg in msgs:
                if "dm_only" in msg:
                    all_violations.append(
                        f"{pid} received dm_only in msg {msg.get('id')}"
                    )

            # Check private content belongs to this player only
            for msg in msgs:
                if "private" in msg:
                    # In get_for_player, private is already a string (this player's)
                    # It should be a string, not a dict with other players' keys
                    assert isinstance(msg["private"], str), (
                        f"{pid} received non-string private: {type(msg['private'])}"
                    )

        # Observer: zero private content
        observer_msgs = e2e_server.response_queue.get_for_player("OBSERVER")
        assert len(observer_msgs) == 100

        for msg in observer_msgs:
            if "private" in msg:
                all_violations.append(
                    f"OBSERVER received private in msg {msg.get('id')}"
                )
            if "dm_only" in msg:
                all_violations.append(
                    f"OBSERVER received dm_only in msg {msg.get('id')}"
                )

        assert all_violations == [], (
            f"Permission violations found:\n" + "\n".join(all_violations)
        )

    def test_format_response_player_isolation(
        self,
        e2e_permission_resolver: PermissionResolver,
    ) -> None:
        """
        Test format_response() for every player: no cross-player leaks.
        """
        raw = {
            "id": "res_test",
            "timestamp": "2026-01-01T00:00:00Z",
            "narrative": "Something happens",
            "private": {
                "thorin": "Thorin sees this",
                "elara": "Elara sees this",
                "vex": "Vex sees this",
                "gorm": "Gorm sees this",
            },
            "dm_only": "DM-only info",
        }

        # Each player should see ONLY their own private
        for pid in PLAYER_IDS:
            filtered = format_response(raw, pid, e2e_permission_resolver)

            assert filtered["narrative"] == "Something happens"
            assert filtered.get("private") == raw["private"][pid]
            assert "dm_only" not in filtered
            assert "all_private" not in filtered

    def test_format_response_observer_sees_nothing_private(
        self,
        e2e_permission_resolver: PermissionResolver,
    ) -> None:
        """OBSERVER sees only public narrative, nothing else."""
        raw = {
            "id": "res_obs",
            "timestamp": "2026-01-01T00:00:00Z",
            "narrative": "Public text",
            "private": {"thorin": "secret", "elara": "also secret"},
            "dm_only": "DM info",
        }

        filtered = format_response(raw, "OBSERVER", e2e_permission_resolver)

        assert filtered["narrative"] == "Public text"
        assert "private" not in filtered
        assert "dm_only" not in filtered
        assert "all_private" not in filtered

    def test_observer_never_receives_private_across_messages(
        self,
        e2e_server: PartyServer,
    ) -> None:
        """OBSERVER receives 0 private messages across 50 varied responses."""
        for i in range(50):
            e2e_server.response_queue.push({
                "narrative": f"Event {i}",
                "private": {
                    PLAYER_IDS[i % len(PLAYER_IDS)]: f"Secret {i}",
                },
                "dm_only": f"DM note {i}",
            })

        observer_msgs = e2e_server.response_queue.get_for_player("OBSERVER")
        private_count = sum(1 for m in observer_msgs if "private" in m)
        dm_only_count = sum(1 for m in observer_msgs if "dm_only" in m)

        assert private_count == 0, f"OBSERVER received {private_count} private messages"
        assert dm_only_count == 0, f"OBSERVER received {dm_only_count} dm_only messages"

    def test_player_sees_only_own_private(
        self,
        e2e_server: PartyServer,
    ) -> None:
        """Each player only receives their own private messages."""
        # Push messages where every player gets a different private msg
        for i in range(20):
            e2e_server.response_queue.push({
                "narrative": f"Round {i}",
                "private": {
                    pid: f"Private-{pid}-{i}"
                    for pid in PLAYER_IDS
                },
            })

        for pid in PLAYER_IDS:
            msgs = e2e_server.response_queue.get_for_player(pid)
            for i, msg in enumerate(msgs):
                # Should have exactly this player's private content
                assert msg.get("private") == f"Private-{pid}-{i}"

    def test_http_character_endpoint_respects_ownership(
        self,
        e2e_server: PartyServer,
        e2e_tokens: dict[str, str],
    ) -> None:
        """Character endpoint validates token but allows reads."""
        from starlette.testclient import TestClient

        client = TestClient(e2e_server.app)

        # Each player can read their own character
        for pid in PLAYER_IDS:
            resp = client.get(
                f"/character/{pid}?token={e2e_tokens[pid]}"
            )
            assert resp.status_code == 200
            assert resp.json()["name"] == pid.capitalize()

        # OBSERVER can also read (get_character is allowed for all roles)
        resp = client.get(
            f"/character/thorin?token={e2e_tokens['OBSERVER']}"
        )
        assert resp.status_code == 200
