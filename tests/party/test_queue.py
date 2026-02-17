"""
Tests for Party Mode action and response queues.

Tests ActionQueue (push/pop/resolve, JSONL persistence, thread safety)
and ResponseQueue (push, per-player filtering, JSONL persistence).
"""

import json
import tempfile
import threading
from pathlib import Path

import pytest

from dm20_protocol.party.queue import ActionQueue, ResponseQueue


class TestActionQueue:
    """Tests for ActionQueue."""

    def _make_queue(self, tmp_path: Path) -> ActionQueue:
        """Create an ActionQueue with a temp campaign dir."""
        return ActionQueue(tmp_path)

    def test_push_creates_action(self, tmp_path: Path) -> None:
        """Test that push creates an action with correct fields."""
        q = self._make_queue(tmp_path)
        action_id = q.push("thorin", "I attack the orc")

        assert action_id.startswith("act_")
        assert q.get_status(action_id) == "pending"
        assert q.get_pending_count() == 1

    def test_push_multiple_actions(self, tmp_path: Path) -> None:
        """Test pushing multiple actions generates unique IDs."""
        q = self._make_queue(tmp_path)
        id1 = q.push("thorin", "action 1")
        id2 = q.push("legolas", "action 2")
        id3 = q.push("thorin", "action 3")

        assert id1 != id2 != id3
        assert q.get_pending_count() == 3

    def test_pop_returns_oldest_first(self, tmp_path: Path) -> None:
        """Test that pop returns actions in FIFO order."""
        q = self._make_queue(tmp_path)
        q.push("thorin", "first")
        q.push("legolas", "second")

        action = q.pop()
        assert action is not None
        assert action["text"] == "first"
        assert action["player_id"] == "thorin"
        assert action["status"] == "processing"

    def test_pop_empty_queue(self, tmp_path: Path) -> None:
        """Test that pop returns None on empty queue."""
        q = self._make_queue(tmp_path)
        assert q.pop() is None

    def test_pop_marks_as_processing(self, tmp_path: Path) -> None:
        """Test that pop changes status to processing."""
        q = self._make_queue(tmp_path)
        action_id = q.push("thorin", "attack")
        q.pop()

        assert q.get_status(action_id) == "processing"
        assert q.get_pending_count() == 0

    def test_resolve_action(self, tmp_path: Path) -> None:
        """Test resolving an action."""
        q = self._make_queue(tmp_path)
        action_id = q.push("thorin", "attack")
        q.pop()
        q.resolve(action_id, {"narrative": "You swing your axe!"})

        assert q.get_status(action_id) == "resolved"

    def test_resolve_unknown_action_raises(self, tmp_path: Path) -> None:
        """Test that resolving an unknown action raises KeyError."""
        q = self._make_queue(tmp_path)
        with pytest.raises(KeyError):
            q.resolve("act_9999", {})

    def test_get_status_unknown(self, tmp_path: Path) -> None:
        """Test that get_status returns None for unknown actions."""
        q = self._make_queue(tmp_path)
        assert q.get_status("act_nonexistent") is None

    def test_jsonl_persistence(self, tmp_path: Path) -> None:
        """Test that actions are persisted to JSONL and restored."""
        q1 = self._make_queue(tmp_path)
        id1 = q1.push("thorin", "first action")
        id2 = q1.push("legolas", "second action")
        q1.pop()  # Mark first as processing

        # Verify JSONL file exists
        jsonl_path = tmp_path / "party" / "actions.jsonl"
        assert jsonl_path.exists()

        # Create new queue from same directory — should restore state
        q2 = self._make_queue(tmp_path)

        # Processing action should be re-queued as pending
        assert q2.get_pending_count() == 2
        action = q2.pop()
        assert action is not None
        assert action["text"] == "first action"

    def test_jsonl_resolved_not_requeued(self, tmp_path: Path) -> None:
        """Test that resolved actions are not re-queued on restore."""
        q1 = self._make_queue(tmp_path)
        action_id = q1.push("thorin", "done action")
        q1.pop()
        q1.resolve(action_id, {"narrative": "done"})

        q2 = self._make_queue(tmp_path)
        assert q2.get_pending_count() == 0

    def test_thread_safety_concurrent_pushes(self, tmp_path: Path) -> None:
        """Test that concurrent pushes don't corrupt the queue."""
        q = self._make_queue(tmp_path)
        errors: list[Exception] = []

        def push_actions(player_id: str, count: int) -> None:
            try:
                for i in range(count):
                    q.push(player_id, f"action {i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=push_actions, args=(f"player_{i}", 50))
            for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert q.get_pending_count() == 200  # 4 threads * 50 actions

    def test_clear(self, tmp_path: Path) -> None:
        """Test clearing the queue."""
        q = self._make_queue(tmp_path)
        q.push("thorin", "action 1")
        q.push("legolas", "action 2")
        q.clear()

        assert q.get_pending_count() == 0
        assert q.pop() is None


class TestResponseQueue:
    """Tests for ResponseQueue."""

    def _make_queue(self, tmp_path: Path) -> ResponseQueue:
        """Create a ResponseQueue with a temp campaign dir."""
        return ResponseQueue(tmp_path)

    def test_push_response(self, tmp_path: Path) -> None:
        """Test pushing a response."""
        q = self._make_queue(tmp_path)
        resp_id = q.push({
            "action_id": "act_0001",
            "narrative": "The orc falls!",
        })

        assert resp_id.startswith("res_")
        responses = q.get_all()
        assert len(responses) == 1
        assert responses[0]["narrative"] == "The orc falls!"

    def test_get_for_player_public_only(self, tmp_path: Path) -> None:
        """Test that players get public narrative."""
        q = self._make_queue(tmp_path)
        q.push({
            "narrative": "A door opens.",
            "action_id": "act_0001",
        })

        results = q.get_for_player("thorin")
        assert len(results) == 1
        assert results[0]["narrative"] == "A door opens."

    def test_get_for_player_private_filtering(self, tmp_path: Path) -> None:
        """Test that private messages are filtered per player."""
        q = self._make_queue(tmp_path)
        q.push({
            "narrative": "You approach the chest.",
            "private": {
                "thorin": "You notice a trap mechanism",
                "legolas": "Your elven eyes spot movement in shadows",
            },
            "action_id": "act_0001",
        })

        thorin_view = q.get_for_player("thorin")
        assert thorin_view[0]["private"] == "You notice a trap mechanism"
        assert "all_private" not in thorin_view[0]

        legolas_view = q.get_for_player("legolas")
        assert legolas_view[0]["private"] == "Your elven eyes spot movement in shadows"

        # Gimli gets no private info
        gimli_view = q.get_for_player("gimli")
        assert "private" not in gimli_view[0]

    def test_get_for_player_dm_only_stripped(self, tmp_path: Path) -> None:
        """Test that dm_only content is stripped for non-DM players."""
        q = self._make_queue(tmp_path)
        q.push({
            "narrative": "The merchant greets you.",
            "dm_only": "The merchant is secretly a spy for the BBEG",
            "action_id": "act_0001",
        })

        # Non-DM player should not see dm_only
        player_view = q.get_for_player("thorin", is_dm=False)
        assert "dm_only" not in player_view[0]

        # DM should see dm_only
        dm_view = q.get_for_player("dm_user", is_dm=True)
        assert dm_view[0]["dm_only"] == "The merchant is secretly a spy for the BBEG"

    def test_get_for_player_since_timestamp(self, tmp_path: Path) -> None:
        """Test filtering by timestamp."""
        q = self._make_queue(tmp_path)
        q.push({"narrative": "Old message", "action_id": "act_0001"})

        # Get all responses
        all_resp = q.get_for_player("thorin")
        assert len(all_resp) == 1
        ts = all_resp[0]["timestamp"]

        # Push a newer message
        q.push({"narrative": "New message", "action_id": "act_0002"})

        # Filter since the first message's timestamp
        new_resp = q.get_for_player("thorin", since_timestamp=ts)
        assert len(new_resp) == 1
        assert new_resp[0]["narrative"] == "New message"

    def test_on_push_callback(self, tmp_path: Path) -> None:
        """Test that on_push callback fires."""
        received: list[dict] = []
        q = ResponseQueue(tmp_path, on_push=lambda r: received.append(r))

        q.push({"narrative": "Test", "action_id": "act_0001"})

        assert len(received) == 1
        assert received[0]["narrative"] == "Test"

    def test_jsonl_persistence(self, tmp_path: Path) -> None:
        """Test that responses are persisted to JSONL."""
        q1 = self._make_queue(tmp_path)
        q1.push({"narrative": "First", "action_id": "act_0001"})
        q1.push({"narrative": "Second", "action_id": "act_0002"})

        jsonl_path = tmp_path / "party" / "responses.jsonl"
        assert jsonl_path.exists()

        # Restore from file
        q2 = self._make_queue(tmp_path)
        all_resp = q2.get_all()
        assert len(all_resp) == 2
        assert all_resp[0]["narrative"] == "First"
        assert all_resp[1]["narrative"] == "Second"

    def test_clear(self, tmp_path: Path) -> None:
        """Test clearing responses."""
        q = self._make_queue(tmp_path)
        q.push({"narrative": "msg", "action_id": "act_0001"})
        q.clear()

        assert len(q.get_all()) == 0
