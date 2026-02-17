"""
Shared fixtures for Party Mode E2E and integration tests.

Provides a fully wired PartyServer with 4 PCs (thorin, elara, vex, gorm),
an OBSERVER, mock storage with character data, and token generation.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dm20_protocol.claudmaster.pc_tracking import MultiPlayerConfig, PCRegistry
from dm20_protocol.models import AbilityScore, Character, CharacterClass, Race
from dm20_protocol.permissions import PermissionResolver, PlayerRole
from dm20_protocol.party.server import PartyServer


# ---------------------------------------------------------------------------
# Character fixtures
# ---------------------------------------------------------------------------

PLAYER_IDS = ["thorin", "elara", "vex", "gorm"]
ALL_IDS = [*PLAYER_IDS, "OBSERVER"]


def _make_character(name: str, cls: str, level: int, ac: int, hp: int) -> Character:
    return Character(
        name=name,
        race=Race(name="Human"),
        character_class=CharacterClass(name=cls, level=level),
        armor_class=ac,
        hit_points_max=hp,
        hit_points_current=hp,
        abilities={
            "strength": AbilityScore(score=14),
            "dexterity": AbilityScore(score=12),
            "constitution": AbilityScore(score=13),
            "intelligence": AbilityScore(score=10),
            "wisdom": AbilityScore(score=11),
            "charisma": AbilityScore(score=10),
        },
    )


CHARACTERS = {
    "thorin": _make_character("Thorin", "Fighter", 5, 18, 52),
    "elara": _make_character("Elara", "Wizard", 5, 12, 28),
    "vex": _make_character("Vex", "Rogue", 5, 15, 38),
    "gorm": _make_character("Gorm", "Cleric", 5, 16, 42),
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def e2e_campaign_dir() -> Path:
    """Temporary campaign directory for E2E tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        (path / "party").mkdir(parents=True, exist_ok=True)
        yield path


@pytest.fixture
def e2e_pc_registry() -> PCRegistry:
    """PCRegistry with 4 players + 1 observer."""
    config = MultiPlayerConfig(max_players=6)
    registry = PCRegistry(config)
    for pid in PLAYER_IDS:
        registry.join_session(pid, f"Player-{pid}", PlayerRole.PLAYER)
    registry.join_session("OBSERVER", "Spectator", PlayerRole.OBSERVER)
    return registry


@pytest.fixture
def e2e_permission_resolver() -> PermissionResolver:
    """PermissionResolver with roles and character ownership."""
    resolver = PermissionResolver()
    for pid in PLAYER_IDS:
        resolver.set_player_role(pid, PlayerRole.PLAYER)
        resolver.register_character_ownership(pid, pid)
    resolver.set_player_role("OBSERVER", PlayerRole.OBSERVER)
    return resolver


@pytest.fixture
def e2e_mock_storage() -> MagicMock:
    """Mock DnDStorage returning test characters."""
    storage = MagicMock(spec=["get_character"])

    def _get(char_id: str) -> Character:
        if char_id in CHARACTERS:
            return CHARACTERS[char_id]
        raise ValueError(f"Character {char_id} not found")

    storage.get_character.side_effect = _get
    return storage


@pytest.fixture
def e2e_server(
    e2e_pc_registry: PCRegistry,
    e2e_permission_resolver: PermissionResolver,
    e2e_mock_storage: MagicMock,
    e2e_campaign_dir: Path,
) -> PartyServer:
    """Fully wired PartyServer with tokens for all players."""
    server = PartyServer(
        pc_registry=e2e_pc_registry,
        permission_resolver=e2e_permission_resolver,
        storage=e2e_mock_storage,
        campaign_dir=e2e_campaign_dir,
        host="127.0.0.1",
        port=9999,
    )
    for pid in ALL_IDS:
        server.token_manager.generate_token(pid)
    return server


@pytest.fixture
def e2e_tokens(e2e_server: PartyServer) -> dict[str, str]:
    """Map player_id -> token for all players."""
    return e2e_server.token_manager.get_all_tokens()
