"""
Concurrency tests for Party Mode.

Verifies thread safety of action queues under simultaneous access
from multiple simulated players.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from dm20_protocol.party.server import PartyServer
from dm20_protocol.party.queue import ActionQueue, ResponseQueue

from .conftest import PLAYER_IDS


class TestConcurrentActionSubmission:
    """Test simultaneous action submission from multiple players."""

    def test_4_players_submit_simultaneously(
        self, e2e_server: PartyServer
    ) -> None:
        """4 players submit actions within threads — all queue correctly."""
        results: dict[str, dict[str, Any]] = {}
        errors: list[str] = []

        def submit(pid: str) -> None:
            try:
                from starlette.testclient import TestClient

                client = TestClient(e2e_server.app)
                token = e2e_server.token_manager.get_all_tokens()[pid]
                resp = client.post(
                    "/action",
                    json={"action": f"{pid} acts simultaneously"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                results[pid] = resp.json()
            except Exception as e:
                errors.append(f"{pid}: {e}")

        threads = [threading.Thread(target=submit, args=(pid,)) for pid in PLAYER_IDS]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Errors during submission: {errors}"

        # All 4 should succeed
        for pid in PLAYER_IDS:
            assert pid in results, f"No result for {pid}"
            assert results[pid].get("success") is True, f"{pid} failed: {results[pid]}"
            assert results[pid]["player_id"] == pid

        # All action IDs should be unique
        action_ids = [r["action_id"] for r in results.values()]
        assert len(set(action_ids)) == 4, f"Duplicate action IDs: {action_ids}"

        # All 4 should be in queue
        assert e2e_server.action_queue.get_pending_count() == 4

    def test_concurrent_push_pop_no_corruption(
        self, e2e_campaign_dir
    ) -> None:
        """Push and pop from ActionQueue concurrently — no data corruption."""
        queue = ActionQueue(e2e_campaign_dir)
        pushed_ids: list[str] = []
        popped_actions: list[dict] = []
        push_lock = threading.Lock()
        pop_lock = threading.Lock()

        def push_many(player_id: str, count: int) -> None:
            for i in range(count):
                aid = queue.push(player_id, f"Action {i}")
                with push_lock:
                    pushed_ids.append(aid)

        def pop_many(count: int) -> None:
            for _ in range(count):
                action = queue.pop()
                if action:
                    with pop_lock:
                        popped_actions.append(action)

        # 4 threads pushing 25 actions each
        push_threads = [
            threading.Thread(target=push_many, args=(pid, 25))
            for pid in PLAYER_IDS
        ]
        for t in push_threads:
            t.start()
        for t in push_threads:
            t.join(timeout=10)

        assert len(pushed_ids) == 100

        # 4 threads popping concurrently
        pop_threads = [
            threading.Thread(target=pop_many, args=(25,))
            for _ in range(4)
        ]
        for t in pop_threads:
            t.start()
        for t in pop_threads:
            t.join(timeout=10)

        # All 100 should be popped (no duplicates, no missing)
        assert len(popped_actions) == 100
        popped_ids = [a["id"] for a in popped_actions]
        assert len(set(popped_ids)) == 100, "Duplicate pops detected"

        # Each player should have exactly 25 actions
        for pid in PLAYER_IDS:
            player_actions = [a for a in popped_actions if a["player_id"] == pid]
            assert len(player_actions) == 25, (
                f"{pid} has {len(player_actions)} actions, expected 25"
            )

    def test_concurrent_response_push(
        self, e2e_campaign_dir
    ) -> None:
        """ResponseQueue handles concurrent pushes without corruption."""
        queue = ResponseQueue(e2e_campaign_dir)
        pushed_ids: list[str] = []
        lock = threading.Lock()

        def push_responses(prefix: str, count: int) -> None:
            for i in range(count):
                rid = queue.push({"narrative": f"{prefix}-{i}"})
                with lock:
                    pushed_ids.append(rid)

        threads = [
            threading.Thread(target=push_responses, args=(pid, 25))
            for pid in PLAYER_IDS
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(pushed_ids) == 100
        assert len(set(pushed_ids)) == 100, "Duplicate response IDs"

        all_responses = queue.get_all()
        assert len(all_responses) == 100

    def test_concurrent_get_for_player(
        self, e2e_campaign_dir
    ) -> None:
        """Reading filtered responses while pushing is safe."""
        queue = ResponseQueue(e2e_campaign_dir)
        read_results: dict[str, int] = {}
        errors: list[str] = []

        # Pre-load some responses
        for i in range(50):
            queue.push({
                "narrative": f"Event {i}",
                "private": {PLAYER_IDS[i % 4]: f"Private {i}"},
            })

        def push_more() -> None:
            for i in range(50):
                queue.push({"narrative": f"Extra {i}"})

        def read_for_player(pid: str) -> None:
            try:
                msgs = queue.get_for_player(pid)
                read_results[pid] = len(msgs)
            except Exception as e:
                errors.append(f"{pid}: {e}")

        # Push more while reading
        push_thread = threading.Thread(target=push_more)
        read_threads = [
            threading.Thread(target=read_for_player, args=(pid,))
            for pid in PLAYER_IDS
        ]

        push_thread.start()
        for t in read_threads:
            t.start()

        push_thread.join(timeout=10)
        for t in read_threads:
            t.join(timeout=10)

        assert not errors, f"Errors during concurrent read: {errors}"
        # Each player should have read at least the pre-loaded 50
        for pid in PLAYER_IDS:
            assert read_results.get(pid, 0) >= 50


class TestConcurrentTokenOperations:
    """Test thread safety of token operations."""

    def test_concurrent_token_refresh(
        self, e2e_server: PartyServer
    ) -> None:
        """Refreshing tokens concurrently doesn't corrupt state."""
        results: dict[str, str] = {}
        errors: list[str] = []

        def refresh(pid: str) -> None:
            try:
                new_token = e2e_server.token_manager.refresh_token(pid)
                results[pid] = new_token
            except Exception as e:
                errors.append(f"{pid}: {e}")

        threads = [
            threading.Thread(target=refresh, args=(pid,))
            for pid in PLAYER_IDS
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Errors: {errors}"

        # Each player should have a valid new token
        for pid in PLAYER_IDS:
            assert pid in results
            validated = e2e_server.token_manager.validate_token(results[pid])
            assert validated == pid, f"Token for {pid} validates as {validated}"

    def test_concurrent_validate(
        self, e2e_server: PartyServer
    ) -> None:
        """Concurrent token validations return correct results."""
        tokens = e2e_server.token_manager.get_all_tokens()
        results: dict[str, str | None] = {}

        def validate(pid: str) -> None:
            token = tokens[pid]
            result = e2e_server.token_manager.validate_token(token)
            results[pid] = result

        threads = [
            threading.Thread(target=validate, args=(pid,))
            for pid in PLAYER_IDS
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        for pid in PLAYER_IDS:
            assert results[pid] == pid
