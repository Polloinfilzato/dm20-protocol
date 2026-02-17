"""
Action and Response queues for Party Mode.

Thread-safe queues with JSONL persistence for crash recovery and debugging.
Actions flow from player browsers into the ActionQueue; the host processes
them via /dm:party-next; responses flow back through the ResponseQueue.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("dm20-protocol.party.queue")


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string with microsecond precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ActionQueue:
    """
    Thread-safe action queue with JSONL persistence.

    Player actions are pushed by the web server and popped by the host's
    game loop (/dm:party-next). Each action transitions through statuses:
    pending -> processing -> resolved.

    Attributes:
        _actions: Ordered dict of action_id -> action dict
        _pending: Deque of action_ids with status 'pending'
        _lock: Threading lock for safe concurrent access
        _jsonl_path: Path to the JSONL persistence file
    """

    def __init__(self, campaign_dir: Path) -> None:
        """
        Initialize the ActionQueue.

        Args:
            campaign_dir: Campaign directory; JSONL stored at
                          {campaign_dir}/party/actions.jsonl
        """
        self._actions: dict[str, dict[str, Any]] = {}
        self._pending: deque[str] = deque()
        self._lock = threading.Lock()
        self._counter = 0

        # Set up persistence
        party_dir = campaign_dir / "party"
        party_dir.mkdir(parents=True, exist_ok=True)
        self._jsonl_path = party_dir / "actions.jsonl"

        # Restore from JSONL if exists
        self._restore_from_jsonl()

    def _restore_from_jsonl(self) -> None:
        """Rebuild in-memory state from existing JSONL file.

        JSONL is append-only, so the same action_id may appear multiple
        times with different statuses. We read all lines first, keeping
        only the latest state for each action, then build the pending
        queue from the final states.
        """
        if not self._jsonl_path.exists():
            return

        try:
            with open(self._jsonl_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    action = json.loads(line)
                    action_id = action["id"]
                    # Overwrite with latest state for this action
                    self._actions[action_id] = action
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Error restoring actions from JSONL: {e}")

        if self._actions:
            # Build pending queue from final states
            for action_id, action in self._actions.items():
                if action["status"] in ("pending", "processing"):
                    action["status"] = "pending"
                    self._pending.append(action_id)

            # Update counter to continue from last ID
            max_num = 0
            for aid in self._actions:
                try:
                    num = int(aid.split("_")[1])
                    max_num = max(max_num, num)
                except (IndexError, ValueError):
                    pass
            self._counter = max_num
            logger.info(f"Restored {len(self._actions)} actions, "
                       f"{len(self._pending)} pending")

    def _append_jsonl(self, action: dict[str, Any]) -> None:
        """Append an action record to the JSONL file."""
        try:
            with open(self._jsonl_path, "a") as f:
                f.write(json.dumps(action) + "\n")
        except OSError as e:
            logger.error(f"Failed to write action to JSONL: {e}")

    def push(self, player_id: str, text: str) -> str:
        """
        Add a new action to the queue.

        Args:
            player_id: The player submitting the action
            text: The action text

        Returns:
            The generated action_id
        """
        with self._lock:
            self._counter += 1
            action_id = f"act_{self._counter:04d}"

            action = {
                "id": action_id,
                "player_id": player_id,
                "text": text,
                "timestamp": _now_iso(),
                "status": "pending",
            }

            self._actions[action_id] = action
            self._pending.append(action_id)
            self._append_jsonl(action)

        logger.info(f"Action queued: {action_id} from {player_id}")
        return action_id

    def pop(self) -> Optional[dict[str, Any]]:
        """
        Get the next pending action and mark it as processing.

        Returns:
            The action dict, or None if no pending actions
        """
        with self._lock:
            while self._pending:
                action_id = self._pending.popleft()
                action = self._actions.get(action_id)
                if action and action["status"] == "pending":
                    action["status"] = "processing"
                    self._append_jsonl(action)
                    logger.info(f"Action popped: {action_id}")
                    return dict(action)  # Return a copy
            return None

    def resolve(self, action_id: str, response: dict[str, Any]) -> None:
        """
        Mark an action as resolved.

        Args:
            action_id: The action to resolve
            response: The response data (stored for reference)

        Raises:
            KeyError: If action_id not found
        """
        with self._lock:
            if action_id not in self._actions:
                raise KeyError(f"Action {action_id} not found")

            action = self._actions[action_id]
            action["status"] = "resolved"
            action["resolved_at"] = _now_iso()
            self._append_jsonl(action)

        logger.info(f"Action resolved: {action_id}")

    def get_status(self, action_id: str) -> Optional[str]:
        """
        Get the current status of an action.

        Args:
            action_id: The action to check

        Returns:
            Status string ('pending', 'processing', 'resolved') or None
        """
        with self._lock:
            action = self._actions.get(action_id)
            return action["status"] if action else None

    def get_pending_count(self) -> int:
        """Return the number of pending actions."""
        with self._lock:
            return len(self._pending)

    def clear(self) -> None:
        """Clear all actions (for testing or session reset)."""
        with self._lock:
            self._actions.clear()
            self._pending.clear()
            self._counter = 0


class ResponseQueue:
    """
    Append-only response queue with per-player filtering.

    Responses are pushed by the host after processing actions. Each
    response contains public narrative, optional private messages per
    player, and optional DM-only content.

    Attributes:
        _responses: List of response dicts
        _lock: Threading lock for safe concurrent access
        _jsonl_path: Path to the JSONL persistence file
        _on_push: Optional callback invoked when a response is pushed
    """

    def __init__(
        self,
        campaign_dir: Path,
        on_push: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> None:
        """
        Initialize the ResponseQueue.

        Args:
            campaign_dir: Campaign directory; JSONL stored at
                          {campaign_dir}/party/responses.jsonl
            on_push: Optional callback called with each new response
        """
        self._responses: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._counter = 0
        self._on_push = on_push

        # Set up persistence
        party_dir = campaign_dir / "party"
        party_dir.mkdir(parents=True, exist_ok=True)
        self._jsonl_path = party_dir / "responses.jsonl"

        # Restore from JSONL
        self._restore_from_jsonl()

    def _restore_from_jsonl(self) -> None:
        """Rebuild in-memory state from existing JSONL file."""
        if not self._jsonl_path.exists():
            return

        try:
            with open(self._jsonl_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    response = json.loads(line)
                    self._responses.append(response)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Error restoring responses from JSONL: {e}")

        if self._responses:
            # Update counter
            max_num = 0
            for resp in self._responses:
                try:
                    num = int(resp["id"].split("_")[1])
                    max_num = max(max_num, num)
                except (IndexError, ValueError, KeyError):
                    pass
            self._counter = max_num
            logger.info(f"Restored {len(self._responses)} responses")

    def _append_jsonl(self, response: dict[str, Any]) -> None:
        """Append a response record to the JSONL file."""
        try:
            with open(self._jsonl_path, "a") as f:
                f.write(json.dumps(response) + "\n")
        except OSError as e:
            logger.error(f"Failed to write response to JSONL: {e}")

    def push(self, response: dict[str, Any]) -> str:
        """
        Add a response to the queue.

        The response dict should have:
        - narrative: str (public text visible to all)
        - private: dict[str, str] (player_id -> private text, optional)
        - dm_only: str (DM-only notes, optional)
        - action_id: str (the action this responds to, optional)

        Args:
            response: The response data

        Returns:
            The generated response_id
        """
        with self._lock:
            self._counter += 1
            response_id = f"res_{self._counter:04d}"

            record = {
                "id": response_id,
                "timestamp": _now_iso(),
                **response,
            }

            self._responses.append(record)
            self._append_jsonl(record)

        logger.info(f"Response pushed: {response_id}")

        # Fire callback (outside lock to avoid deadlocks)
        if self._on_push:
            try:
                self._on_push(record)
            except Exception as e:
                logger.error(f"on_push callback error: {e}")

        return response_id

    def get_for_player(
        self,
        player_id: str,
        since_timestamp: Optional[str] = None,
        is_dm: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get filtered responses for a specific player.

        Strips dm_only content for non-DM players. Includes private
        messages only for the matching player_id.

        Args:
            player_id: The player requesting responses
            since_timestamp: Only return responses after this ISO timestamp
            is_dm: Whether this player has the DM role

        Returns:
            List of filtered response dicts
        """
        with self._lock:
            responses = list(self._responses)

        result = []
        for resp in responses:
            # Filter by timestamp: exclude responses at or before since_timestamp
            if since_timestamp and resp.get("timestamp", "") <= since_timestamp:
                continue

            filtered = {
                "id": resp.get("id"),
                "timestamp": resp.get("timestamp"),
                "action_id": resp.get("action_id"),
                "narrative": resp.get("narrative", ""),
            }

            # Include private message only for this player
            private = resp.get("private", {})
            if player_id in private:
                filtered["private"] = private[player_id]

            # Include dm_only content only for DM
            if is_dm and "dm_only" in resp:
                filtered["dm_only"] = resp["dm_only"]

            result.append(filtered)

        return result

    def get_all(self) -> list[dict[str, Any]]:
        """Return all responses (unfiltered, for DM/debug use)."""
        with self._lock:
            return list(self._responses)

    def clear(self) -> None:
        """Clear all responses (for testing or session reset)."""
        with self._lock:
            self._responses.clear()
            self._counter = 0


__all__ = [
    "ActionQueue",
    "ResponseQueue",
]
