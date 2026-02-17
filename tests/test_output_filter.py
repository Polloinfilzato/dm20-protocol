"""
Integration tests for output filtering and multi-user session coordination.

Tests that the OutputFilter correctly strips DM-only content from player-visible
responses, that the SessionCoordinator manages participants and turns, and that
the same tool call returns different content for DM vs PLAYER vs OBSERVER.
"""

import time
import pytest
from datetime import datetime, timedelta
from pathlib import Path

from dm20_protocol.output_filter import (
    FilterResult,
    OutputFilter,
    SessionCoordinator,
    SessionParticipant,
    _format_npc_full,
    _format_npc_public,
    _format_location_full,
    _format_location_public,
    _strip_dm_notes_section,
)
from dm20_protocol.permissions import PermissionResolver, PlayerRole
from dm20_protocol.models import NPC, Location
from dm20_protocol.consistency.discovery import (
    DiscoveryLevel,
    DiscoveryTracker,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def resolver():
    """Permission resolver with DM, PLAYER, and OBSERVER roles set up."""
    r = PermissionResolver()
    r.set_player_role("dm_user", PlayerRole.DM)
    r.set_player_role("player_alice", PlayerRole.PLAYER)
    r.set_player_role("player_bob", PlayerRole.PLAYER)
    r.set_player_role("observer_carol", PlayerRole.OBSERVER)
    return r


@pytest.fixture
def coordinator():
    """Session coordinator with participants joined."""
    c = SessionCoordinator()
    c.join_session("dm_user", role=PlayerRole.DM)
    c.join_session("player_alice", role=PlayerRole.PLAYER, character_id="Aldric")
    c.join_session("player_bob", role=PlayerRole.PLAYER, character_id="Brynn")
    c.join_session("observer_carol", role=PlayerRole.OBSERVER)
    return c


@pytest.fixture
def output_filter(resolver, coordinator):
    """OutputFilter wired with resolver and coordinator."""
    return OutputFilter(resolver, coordinator)


@pytest.fixture
def sample_npc():
    """Sample NPC with both public and DM-only fields."""
    return NPC(
        name="Elara Nightwhisper",
        description="A mysterious elven woman with silver hair and piercing green eyes.",
        bio="Elara is secretly a spy for the Shadow Council. She feeds information to the cult of Vecna.",
        race="Elf",
        occupation="Herbalist",
        location="Greenhollow Village",
        attitude="friendly",
        notes="DM: She will betray the party in session 5.",
        stats={"HP": 32, "AC": 14},
        relationships={"Aldric": "trusted ally", "Mayor Bramble": "secret enemy"},
    )


@pytest.fixture
def sample_location():
    """Sample location with notable features and notes."""
    return Location(
        name="Shadowfen Ruins",
        location_type="dungeon",
        description="Ancient ruins half-swallowed by a misty swamp.",
        population=None,
        government=None,
        notable_features=[
            "Crumbling Stone Archway",
            "Hidden Underground Passage",
            "Glowing Rune Circle",
        ],
        notes="DM: The hidden passage leads to the BBEG's lair.",
    )


@pytest.fixture
def discovery_tracker(tmp_path):
    """Discovery tracker with specific discovery states set up."""
    tracker = DiscoveryTracker(tmp_path)
    # Shadowfen Ruins: location is GLIMPSED, only first feature discovered
    tracker.discover_location("Shadowfen Ruins", DiscoveryLevel.GLIMPSED)
    tracker.discover_feature(
        "Shadowfen Ruins",
        "Crumbling Stone Archway",
        DiscoveryLevel.EXPLORED,
    )
    # "Hidden Underground Passage" and "Glowing Rune Circle" remain UNDISCOVERED
    return tracker


# ---------------------------------------------------------------------------
# FilterResult model tests
# ---------------------------------------------------------------------------

class TestFilterResult:
    """Tests for the FilterResult model."""

    def test_default_values(self):
        """Test default FilterResult."""
        result = FilterResult()
        assert result.content == ""
        assert result.private_addenda == {}
        assert result.was_filtered is False

    def test_with_content(self):
        """Test FilterResult with content."""
        result = FilterResult(content="hello", was_filtered=True)
        assert result.content == "hello"
        assert result.was_filtered is True


# ---------------------------------------------------------------------------
# SessionCoordinator tests
# ---------------------------------------------------------------------------

class TestSessionCoordinator:
    """Tests for the SessionCoordinator."""

    def test_join_session_new(self):
        """Test joining a new session."""
        coord = SessionCoordinator()
        p = coord.join_session("alice", PlayerRole.PLAYER, "Aldric")
        assert p.player_id == "alice"
        assert p.role == PlayerRole.PLAYER
        assert p.character_id == "Aldric"
        assert p.is_connected is True
        assert coord.participant_count == 1
        assert coord.connected_count == 1

    def test_join_session_rejoin(self):
        """Test rejoining after disconnect."""
        coord = SessionCoordinator()
        coord.join_session("alice", PlayerRole.PLAYER, "Aldric")
        coord.leave_session("alice")
        assert coord.connected_count == 0

        p = coord.join_session("alice", PlayerRole.PLAYER)
        assert p.is_connected is True
        assert coord.connected_count == 1
        # participant_count should still be 1 (same entry reused)
        assert coord.participant_count == 1

    def test_leave_session(self):
        """Test leaving a session."""
        coord = SessionCoordinator()
        coord.join_session("alice", PlayerRole.PLAYER)
        result = coord.leave_session("alice")
        assert result is True
        assert coord.connected_count == 0
        # Still in participants list
        assert coord.participant_count == 1

    def test_leave_session_unknown(self):
        """Test leaving with unknown player_id returns False."""
        coord = SessionCoordinator()
        assert coord.leave_session("nobody") is False

    def test_heartbeat(self):
        """Test heartbeat updates last_active."""
        coord = SessionCoordinator()
        p = coord.join_session("alice", PlayerRole.PLAYER)
        old_time = p.last_active

        # Small delay to ensure time difference
        time.sleep(0.01)
        result = coord.heartbeat("alice")
        assert result is True
        assert coord.get_participant("alice").last_active > old_time

    def test_heartbeat_disconnected(self):
        """Test heartbeat fails for disconnected participant."""
        coord = SessionCoordinator()
        coord.join_session("alice", PlayerRole.PLAYER)
        coord.leave_session("alice")
        assert coord.heartbeat("alice") is False

    def test_heartbeat_unknown(self):
        """Test heartbeat returns False for unknown player."""
        coord = SessionCoordinator()
        assert coord.heartbeat("nobody") is False

    def test_get_connected_players(self):
        """Test getting connected PLAYER participants."""
        coord = SessionCoordinator()
        coord.join_session("dm", PlayerRole.DM)
        coord.join_session("alice", PlayerRole.PLAYER)
        coord.join_session("bob", PlayerRole.PLAYER)
        coord.join_session("carol", PlayerRole.OBSERVER)

        players = coord.get_connected_players()
        assert len(players) == 2
        assert all(p.role == PlayerRole.PLAYER for p in players)

    def test_get_connected_participants(self):
        """Test getting all connected participants."""
        coord = SessionCoordinator()
        coord.join_session("dm", PlayerRole.DM)
        coord.join_session("alice", PlayerRole.PLAYER)
        coord.leave_session("alice")

        connected = coord.get_connected_participants()
        assert len(connected) == 1
        assert connected[0].player_id == "dm"

    def test_turn_tracking(self):
        """Test turn tracking lifecycle."""
        coord = SessionCoordinator()
        coord.join_session("alice", PlayerRole.PLAYER, "Aldric")

        # No active turn initially
        assert coord.is_turn_active is False
        assert coord.get_turn_context() is None

        # Set turn
        coord.set_current_turn("alice")
        assert coord.is_turn_active is True
        assert coord.current_turn_player == "alice"
        context = coord.get_turn_context()
        assert context is not None
        assert "Aldric" in context

        # Clear turn
        coord.set_current_turn(None)
        assert coord.is_turn_active is False
        assert coord.get_turn_context() is None

    def test_turn_context_unknown_player(self):
        """Test turn context for non-participant player."""
        coord = SessionCoordinator()
        coord.set_current_turn("unknown_player")
        context = coord.get_turn_context()
        assert "unknown_player" in context

    def test_private_messaging(self):
        """Test sending and retrieving private messages."""
        coord = SessionCoordinator()
        coord.join_session("dm", PlayerRole.DM)
        coord.join_session("alice", PlayerRole.PLAYER)

        msg = coord.send_private_message("dm", "alice", "You notice a hidden door.")
        assert msg["sender_id"] == "dm"
        assert msg["recipient_id"] == "alice"
        assert msg["content"] == "You notice a hidden door."

        pending = coord.get_pending_messages("alice")
        assert len(pending) == 1
        assert pending[0]["content"] == "You notice a hidden door."

        # DM should not see alice's messages
        dm_pending = coord.get_pending_messages("dm")
        assert len(dm_pending) == 0

    def test_private_message_invalid_recipient(self):
        """Test private message to unknown participant raises ValueError."""
        coord = SessionCoordinator()
        coord.join_session("dm", PlayerRole.DM)

        with pytest.raises(ValueError, match="not a session participant"):
            coord.send_private_message("dm", "nobody", "Hello")


# ---------------------------------------------------------------------------
# OutputFilter: NPC filtering tests
# ---------------------------------------------------------------------------

class TestOutputFilterNPC:
    """Tests for NPC response filtering by role."""

    def test_dm_sees_full_npc(self, output_filter, sample_npc):
        """DM sees all NPC fields including bio, notes, stats, relationships."""
        result = output_filter.filter_npc_response(sample_npc, player_id="dm_user")
        assert result.was_filtered is False
        assert "Bio:" in result.content
        assert "spy for the Shadow Council" in result.content
        assert "Notes:" in result.content
        assert "betray the party" in result.content
        assert "Stats:" in result.content
        assert "Relationships:" in result.content

    def test_player_sees_public_npc(self, output_filter, sample_npc):
        """PLAYER sees only public NPC fields, bio/notes/stats/relationships stripped."""
        result = output_filter.filter_npc_response(sample_npc, player_id="player_alice")
        assert result.was_filtered is True
        # Public fields present
        assert "Elara Nightwhisper" in result.content
        assert "Elf" in result.content
        assert "Herbalist" in result.content
        assert "Greenhollow Village" in result.content
        assert "friendly" in result.content
        assert "mysterious elven woman" in result.content
        # DM-only fields absent
        assert "spy for the Shadow Council" not in result.content
        assert "betray the party" not in result.content
        assert "HP" not in result.content
        assert "trusted ally" not in result.content

    def test_observer_sees_public_npc(self, output_filter, sample_npc):
        """OBSERVER sees the same as PLAYER: public fields only."""
        result = output_filter.filter_npc_response(sample_npc, player_id="observer_carol")
        assert result.was_filtered is True
        assert "Elara Nightwhisper" in result.content
        assert "spy for the Shadow Council" not in result.content

    def test_none_player_id_bypasses_filter(self, output_filter, sample_npc):
        """None player_id (single-player mode) returns full NPC."""
        result = output_filter.filter_npc_response(sample_npc, player_id=None)
        assert result.was_filtered is False
        assert "Bio:" in result.content
        assert "spy for the Shadow Council" in result.content

    def test_same_npc_different_roles(self, output_filter, sample_npc):
        """Same tool call returns different content for DM vs PLAYER."""
        dm_result = output_filter.filter_npc_response(sample_npc, player_id="dm_user")
        player_result = output_filter.filter_npc_response(sample_npc, player_id="player_alice")
        observer_result = output_filter.filter_npc_response(sample_npc, player_id="observer_carol")

        # DM content is longer (has bio, notes, stats, relationships)
        assert len(dm_result.content) > len(player_result.content)
        # PLAYER and OBSERVER see the same content
        assert player_result.content == observer_result.content
        # DM was not filtered, others were
        assert dm_result.was_filtered is False
        assert player_result.was_filtered is True
        assert observer_result.was_filtered is True


# ---------------------------------------------------------------------------
# OutputFilter: Location filtering tests
# ---------------------------------------------------------------------------

class TestOutputFilterLocation:
    """Tests for location response filtering by role and discovery."""

    def test_dm_sees_full_location(self, output_filter, sample_location):
        """DM sees all location fields including notes."""
        result = output_filter.filter_location_response(
            sample_location, player_id="dm_user"
        )
        assert result.was_filtered is False
        assert "Shadowfen Ruins" in result.content
        assert "Hidden Underground Passage" in result.content
        assert "Glowing Rune Circle" in result.content
        assert "BBEG's lair" in result.content

    def test_player_sees_public_location(self, output_filter, sample_location):
        """PLAYER sees location without DM notes (no discovery tracker)."""
        result = output_filter.filter_location_response(
            sample_location, player_id="player_alice"
        )
        assert result.was_filtered is True
        assert "Shadowfen Ruins" in result.content
        # All features visible (no discovery filter applied)
        assert "Crumbling Stone Archway" in result.content
        assert "Hidden Underground Passage" in result.content
        # Notes stripped
        assert "BBEG's lair" not in result.content

    def test_player_with_discovery_filter(self, output_filter, sample_location, discovery_tracker):
        """PLAYER with discovery tracker sees only discovered features."""
        result = output_filter.filter_location_response(
            sample_location,
            player_id="player_alice",
            discovery_tracker=discovery_tracker,
        )
        assert result.was_filtered is True
        # Discovered feature visible
        assert "Crumbling Stone Archway" in result.content
        # Undiscovered features hidden
        assert "Hidden Underground Passage" not in result.content
        assert "Glowing Rune Circle" not in result.content
        # Discovery info shown
        assert "Discovery Level" in result.content
        # Hidden count shown
        assert "undiscovered" in result.content.lower()

    def test_dm_with_discovery_tracker(self, output_filter, sample_location, discovery_tracker):
        """DM sees full location even when discovery tracker is provided."""
        result = output_filter.filter_location_response(
            sample_location,
            player_id="dm_user",
            discovery_tracker=discovery_tracker,
        )
        assert result.was_filtered is False
        # DM sees all features
        assert "Hidden Underground Passage" in result.content
        assert "Glowing Rune Circle" in result.content
        assert "BBEG's lair" in result.content

    def test_none_player_id_bypasses_location_filter(self, output_filter, sample_location, discovery_tracker):
        """None player_id returns full location regardless of discovery tracker."""
        result = output_filter.filter_location_response(
            sample_location,
            player_id=None,
            discovery_tracker=discovery_tracker,
        )
        assert result.was_filtered is False
        assert "Hidden Underground Passage" in result.content

    def test_same_location_different_roles(self, output_filter, sample_location, discovery_tracker):
        """Same location returns different content for DM, PLAYER, and OBSERVER."""
        dm_result = output_filter.filter_location_response(
            sample_location, player_id="dm_user", discovery_tracker=discovery_tracker
        )
        player_result = output_filter.filter_location_response(
            sample_location, player_id="player_alice", discovery_tracker=discovery_tracker
        )
        observer_result = output_filter.filter_location_response(
            sample_location, player_id="observer_carol", discovery_tracker=discovery_tracker
        )

        # DM sees everything (longer)
        assert len(dm_result.content) > len(player_result.content)
        # Both player and observer are filtered
        assert player_result.was_filtered is True
        assert observer_result.was_filtered is True


# ---------------------------------------------------------------------------
# OutputFilter: Generic response filtering
# ---------------------------------------------------------------------------

class TestOutputFilterGeneric:
    """Tests for generic response filtering and turn context."""

    def test_generic_no_player_id(self, output_filter):
        """No player_id returns raw response unchanged."""
        result = output_filter.filter_response("Hello world", player_id=None)
        assert result.content == "Hello world"
        assert result.was_filtered is False

    def test_generic_with_player_id(self, output_filter):
        """Player_id present but no active turn returns raw content."""
        result = output_filter.filter_response("Hello world", player_id="player_alice")
        assert result.content == "Hello world"
        assert result.was_filtered is False

    def test_generic_with_turn_context(self, output_filter, coordinator):
        """Turn context prepended when player is the current turn holder."""
        coordinator.set_current_turn("player_alice")
        result = output_filter.filter_response("You see a goblin.", player_id="player_alice")
        assert "Aldric" in result.content  # Character name from turn context
        assert "You see a goblin." in result.content
        assert result.was_filtered is True

    def test_turn_context_not_for_other_player(self, output_filter, coordinator):
        """Turn context NOT prepended for a player who is NOT the current turn holder."""
        coordinator.set_current_turn("player_alice")
        result = output_filter.filter_response("General info", player_id="player_bob")
        # Bob should not see turn notification (it's Alice's turn)
        assert "Aldric" not in result.content
        assert result.content == "General info"

    def test_game_state_dm_notes_stripped(self, output_filter):
        """Game state response has DM notes stripped for players."""
        raw = """**Campaign:** Test
**Session:** 5
**Notes:** The BBEG is planning an ambush at session 6.
"""
        result = output_filter.filter_game_state_response(raw, player_id="player_alice")
        assert result.was_filtered is True
        assert "BBEG" not in result.content
        assert "Campaign" in result.content

    def test_game_state_dm_sees_notes(self, output_filter):
        """DM sees full game state including notes."""
        raw = """**Campaign:** Test
**Notes:** The BBEG is planning an ambush.
"""
        result = output_filter.filter_game_state_response(raw, player_id="dm_user")
        assert result.was_filtered is False
        assert "BBEG" in result.content


# ---------------------------------------------------------------------------
# OutputFilter: get_role convenience
# ---------------------------------------------------------------------------

class TestOutputFilterGetRole:
    """Tests for the get_role convenience method."""

    def test_none_returns_dm(self, output_filter):
        """None player_id returns DM role."""
        assert output_filter.get_role(None) == PlayerRole.DM

    def test_known_player(self, output_filter):
        """Known player_id returns their assigned role."""
        assert output_filter.get_role("player_alice") == PlayerRole.PLAYER
        assert output_filter.get_role("dm_user") == PlayerRole.DM
        assert output_filter.get_role("observer_carol") == PlayerRole.OBSERVER

    def test_unknown_player_defaults_to_player(self, output_filter):
        """Unknown player_id defaults to PLAYER role."""
        assert output_filter.get_role("stranger") == PlayerRole.PLAYER


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    """Tests for NPC/location formatting helpers."""

    def test_format_npc_full(self, sample_npc):
        """Full NPC format includes all fields."""
        text = _format_npc_full(sample_npc)
        assert "Elara Nightwhisper" in text
        assert "Bio:" in text
        assert "spy for the Shadow Council" in text
        assert "Notes:" in text
        assert "betray" in text
        assert "Stats:" in text
        assert "Relationships:" in text

    def test_format_npc_public(self, sample_npc):
        """Public NPC format excludes DM fields."""
        text = _format_npc_public(sample_npc)
        assert "Elara Nightwhisper" in text
        assert "Description:" in text
        # No DM fields
        assert "Bio:" not in text
        assert "Notes:" not in text
        assert "Stats:" not in text
        assert "Relationships:" not in text
        assert "spy" not in text

    def test_format_location_full(self, sample_location):
        """Full location format includes all fields."""
        text = _format_location_full(sample_location)
        assert "Shadowfen Ruins" in text
        assert "Notes:" in text
        assert "BBEG" in text
        assert "Crumbling Stone Archway" in text

    def test_format_location_public(self, sample_location):
        """Public location format excludes DM notes."""
        text = _format_location_public(sample_location)
        assert "Shadowfen Ruins" in text
        assert "Crumbling Stone Archway" in text
        # No notes section
        assert "BBEG" not in text

    def test_strip_dm_notes_section(self):
        """Test DM notes stripping."""
        text = "**Name:** Test\n**Notes:** Secret stuff.\n"
        stripped = _strip_dm_notes_section(text)
        assert "Secret stuff" not in stripped
        assert "Name" in stripped

    def test_strip_dm_notes_preserves_other_sections(self):
        """Test that stripping notes preserves other content."""
        text = """**Name:** Test
**Description:** Public info
**Notes:** Secret DM info
**Population:** 500
"""
        stripped = _strip_dm_notes_section(text)
        assert "Public info" in stripped
        assert "Secret DM info" not in stripped
        assert "500" in stripped


# ---------------------------------------------------------------------------
# PCRegistry participant tracking tests
# ---------------------------------------------------------------------------

class TestPCRegistryParticipantTracking:
    """Tests for participant tracking methods added to PCRegistry."""

    def test_join_session_new(self):
        """Test joining a session creates a new PCState."""
        from dm20_protocol.claudmaster.pc_tracking import PCRegistry, MultiPlayerConfig
        registry = PCRegistry(MultiPlayerConfig())
        state = registry.join_session("char1", "Alice", PlayerRole.PLAYER)
        assert state.character_id == "char1"
        assert state.player_name == "Alice"
        assert state.is_active is True
        assert state.role == PlayerRole.PLAYER
        assert state.last_action_time is not None

    def test_join_session_rejoin(self):
        """Test rejoining reactivates an existing PC."""
        from dm20_protocol.claudmaster.pc_tracking import PCRegistry, MultiPlayerConfig
        registry = PCRegistry(MultiPlayerConfig())
        registry.join_session("char1", "Alice")
        registry.leave_session("char1")
        assert registry.active_count == 0

        state = registry.join_session("char1", "Alice")
        assert state.is_active is True
        assert registry.active_count == 1
        assert registry.count == 1  # Same entry, not duplicated

    def test_leave_session(self):
        """Test leaving a session deactivates the PC."""
        from dm20_protocol.claudmaster.pc_tracking import PCRegistry, MultiPlayerConfig
        registry = PCRegistry(MultiPlayerConfig())
        registry.join_session("char1", "Alice")
        result = registry.leave_session("char1")
        assert result is True
        assert registry.active_count == 0
        assert registry.count == 1  # PC still in registry

    def test_leave_session_unknown(self):
        """Test leaving with unknown character returns False."""
        from dm20_protocol.claudmaster.pc_tracking import PCRegistry, MultiPlayerConfig
        registry = PCRegistry(MultiPlayerConfig())
        assert registry.leave_session("unknown") is False

    def test_leave_session_clears_active_pc(self):
        """Test that leaving clears active_pc if it was the leaving PC."""
        from dm20_protocol.claudmaster.pc_tracking import PCRegistry, MultiPlayerConfig
        registry = PCRegistry(MultiPlayerConfig())
        registry.join_session("char1", "Alice")
        registry.active_pc = "char1"
        registry.leave_session("char1")
        assert registry.active_pc is None

    def test_heartbeat(self):
        """Test heartbeat updates last_action_time."""
        from dm20_protocol.claudmaster.pc_tracking import PCRegistry, MultiPlayerConfig
        registry = PCRegistry(MultiPlayerConfig())
        state = registry.join_session("char1", "Alice")
        old_time = state.last_action_time

        time.sleep(0.01)
        result = registry.heartbeat("char1")
        assert result is True
        assert registry.get_pc_state("char1").last_action_time > old_time

    def test_heartbeat_inactive(self):
        """Test heartbeat fails for inactive PC."""
        from dm20_protocol.claudmaster.pc_tracking import PCRegistry, MultiPlayerConfig
        registry = PCRegistry(MultiPlayerConfig())
        registry.join_session("char1", "Alice")
        registry.leave_session("char1")
        assert registry.heartbeat("char1") is False

    def test_heartbeat_unknown(self):
        """Test heartbeat returns False for unknown character."""
        from dm20_protocol.claudmaster.pc_tracking import PCRegistry, MultiPlayerConfig
        registry = PCRegistry(MultiPlayerConfig())
        assert registry.heartbeat("unknown") is False


# ---------------------------------------------------------------------------
# Integration: PrivateInfoManager visibility levels
# ---------------------------------------------------------------------------

class TestPrivateInfoVisibility:
    """Tests for InfoVisibility enforcement through the filtering pipeline."""

    def test_info_visibility_levels_exist(self):
        """Verify all InfoVisibility levels are defined."""
        from dm20_protocol.claudmaster.private_info import InfoVisibility
        assert InfoVisibility.PUBLIC == "public"
        assert InfoVisibility.PARTY == "party"
        assert InfoVisibility.PRIVATE == "private"
        assert InfoVisibility.DM_ONLY == "dm_only"
        assert InfoVisibility.SUBSET == "subset"

    def test_private_info_manager_get_visible_info(self):
        """Test PrivateInfoManager.get_visible_info filters by visibility."""
        from dm20_protocol.claudmaster.pc_tracking import PCRegistry, MultiPlayerConfig
        from dm20_protocol.claudmaster.private_info import (
            InfoVisibility,
            PrivateInfoManager,
        )

        config = MultiPlayerConfig()
        registry = PCRegistry(config)
        registry.register_pc("alice_char", "Alice")
        registry.register_pc("bob_char", "Bob")

        manager = PrivateInfoManager(registry)

        # Add info at different visibility levels
        manager.add_private_info("alice_char", "Public fact", InfoVisibility.PUBLIC)
        manager.add_private_info("alice_char", "Party secret", InfoVisibility.PARTY)
        manager.add_private_info(
            "alice_char", "Alice only", InfoVisibility.PRIVATE
        )
        manager.add_private_info(
            "alice_char", "DM eyes only", InfoVisibility.DM_ONLY
        )
        manager.add_private_info(
            "alice_char", "Subset info", InfoVisibility.SUBSET,
            visible_to=["alice_char"],
        )

        # Alice sees: PUBLIC, PARTY, PRIVATE, SUBSET (but not DM_ONLY)
        alice_info = manager.get_visible_info("alice_char")
        alice_contents = {i.content for i in alice_info}
        assert "Public fact" in alice_contents
        assert "Party secret" in alice_contents
        assert "Alice only" in alice_contents
        assert "Subset info" in alice_contents
        assert "DM eyes only" not in alice_contents

        # Bob sees: PUBLIC, PARTY (but not Alice's PRIVATE or SUBSET)
        bob_info = manager.get_visible_info("bob_char")
        bob_contents = {i.content for i in bob_info}
        assert "Public fact" in bob_contents
        assert "Party secret" in bob_contents
        assert "Alice only" not in bob_contents
        assert "Subset info" not in bob_contents
        assert "DM eyes only" not in bob_contents


# ---------------------------------------------------------------------------
# Integration: End-to-end role-based filtering
# ---------------------------------------------------------------------------

class TestEndToEndRoleFiltering:
    """End-to-end integration tests proving same data returns differently per role."""

    def test_npc_all_three_roles(self, output_filter, sample_npc):
        """Same NPC, three roles, three views."""
        dm = output_filter.filter_npc_response(sample_npc, "dm_user")
        player = output_filter.filter_npc_response(sample_npc, "player_alice")
        observer = output_filter.filter_npc_response(sample_npc, "observer_carol")

        # DM: all content
        assert "Bio:" in dm.content
        assert "Notes:" in dm.content
        assert "Stats:" in dm.content
        assert "Relationships:" in dm.content

        # Player: no DM content
        assert "Bio:" not in player.content
        assert "spy" not in player.content

        # Observer: same as player
        assert player.content == observer.content

    def test_location_all_three_roles_with_discovery(
        self, output_filter, sample_location, discovery_tracker
    ):
        """Same location, three roles, discovery filter applied for non-DM."""
        dm = output_filter.filter_location_response(
            sample_location, "dm_user", discovery_tracker
        )
        player = output_filter.filter_location_response(
            sample_location, "player_alice", discovery_tracker
        )
        observer = output_filter.filter_location_response(
            sample_location, "observer_carol", discovery_tracker
        )

        # DM sees all features
        assert "Hidden Underground Passage" in dm.content
        assert "Glowing Rune Circle" in dm.content

        # Player sees only discovered features
        assert "Crumbling Stone Archway" in player.content
        assert "Hidden Underground Passage" not in player.content

        # Observer sees same as player
        assert "Crumbling Stone Archway" in observer.content
        assert "Hidden Underground Passage" not in observer.content
