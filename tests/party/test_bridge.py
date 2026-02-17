"""
Tests for Party Mode integration bridge.

Tests response filtering by player role (DM, PLAYER, OBSERVER).
"""

from unittest.mock import MagicMock

import pytest

from dm20_protocol.party.bridge import format_response
from dm20_protocol.permissions import PlayerRole


class TestFormatResponse:
    """Tests for format_response."""

    def _mock_resolver(self, role: PlayerRole) -> MagicMock:
        """Create a mock PermissionResolver that returns the given role."""
        resolver = MagicMock()
        resolver.get_player_role.return_value = role
        return resolver

    def test_player_gets_public_narrative(self) -> None:
        """Test that players receive public narrative."""
        resolver = self._mock_resolver(PlayerRole.PLAYER)
        raw = {
            "id": "res_0001",
            "timestamp": "2026-02-17T20:00:00Z",
            "action_id": "act_0001",
            "narrative": "The dragon roars!",
        }

        result = format_response(raw, "thorin", resolver)
        assert result["narrative"] == "The dragon roars!"

    def test_player_gets_own_private(self) -> None:
        """Test that players get their own private messages only."""
        resolver = self._mock_resolver(PlayerRole.PLAYER)
        raw = {
            "id": "res_0001",
            "timestamp": "2026-02-17T20:00:00Z",
            "narrative": "You see a chest.",
            "private": {
                "thorin": "You notice it's trapped",
                "legolas": "You hear footsteps behind",
            },
        }

        result = format_response(raw, "thorin", resolver)
        assert result["private"] == "You notice it's trapped"
        assert "all_private" not in result

    def test_player_no_dm_only(self) -> None:
        """Test that dm_only content is stripped for players."""
        resolver = self._mock_resolver(PlayerRole.PLAYER)
        raw = {
            "id": "res_0001",
            "timestamp": "2026-02-17T20:00:00Z",
            "narrative": "The NPC smiles.",
            "dm_only": "NPC is planning betrayal",
        }

        result = format_response(raw, "thorin", resolver)
        assert "dm_only" not in result

    def test_dm_gets_everything(self) -> None:
        """Test that DM gets all content including dm_only and all private."""
        resolver = self._mock_resolver(PlayerRole.DM)
        raw = {
            "id": "res_0001",
            "timestamp": "2026-02-17T20:00:00Z",
            "narrative": "The party enters the cave.",
            "private": {
                "thorin": "Trap ahead",
                "legolas": "Shadows moving",
            },
            "dm_only": "BBEG is watching from above",
        }

        result = format_response(raw, "dm_user", resolver)
        assert result["narrative"] == "The party enters the cave."
        assert result["dm_only"] == "BBEG is watching from above"
        assert result["all_private"]["thorin"] == "Trap ahead"
        assert result["all_private"]["legolas"] == "Shadows moving"

    def test_observer_gets_only_narrative(self) -> None:
        """Test that observers get only public narrative."""
        resolver = self._mock_resolver(PlayerRole.OBSERVER)
        raw = {
            "id": "res_0001",
            "timestamp": "2026-02-17T20:00:00Z",
            "narrative": "Combat begins!",
            "private": {"thorin": "secret"},
            "dm_only": "hidden info",
        }

        result = format_response(raw, "observer_1", resolver)
        assert result["narrative"] == "Combat begins!"
        assert "private" not in result
        assert "dm_only" not in result
        assert "all_private" not in result

    def test_player_without_private_message(self) -> None:
        """Test player who has no private messages in response."""
        resolver = self._mock_resolver(PlayerRole.PLAYER)
        raw = {
            "id": "res_0001",
            "timestamp": "2026-02-17T20:00:00Z",
            "narrative": "Nothing special happens.",
            "private": {"legolas": "only for legolas"},
        }

        result = format_response(raw, "thorin", resolver)
        assert "private" not in result
