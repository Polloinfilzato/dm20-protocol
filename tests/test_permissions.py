"""
Tests for the role-based permission system.

Tests PlayerRole enum, PermissionLevel, PERMISSION_MATRIX, and
PermissionResolver for every (role, tool) combination and edge cases.
"""

import time
import pytest
from datetime import datetime, timedelta

from dm20_protocol.permissions import (
    PlayerRole,
    PermissionLevel,
    PermissionResolver,
    TemporaryPermission,
    PlayerRoleAssignment,
    PERMISSION_MATRIX,
    _READ_TOOLS,
    _CHARACTER_TOOLS,
    _DM_ONLY_TOOLS,
)


# ---------------------------------------------------------------------------
# PlayerRole enum tests
# ---------------------------------------------------------------------------

class TestPlayerRole:
    """Tests for the PlayerRole enum."""

    def test_values(self):
        """Test that enum values are correct strings."""
        assert PlayerRole.DM == "dm"
        assert PlayerRole.PLAYER == "player"
        assert PlayerRole.OBSERVER == "observer"

    def test_string_enum(self):
        """Test that PlayerRole is a string enum."""
        assert isinstance(PlayerRole.DM, str)
        assert isinstance(PlayerRole.PLAYER, str)
        assert isinstance(PlayerRole.OBSERVER, str)

    def test_from_string(self):
        """Test constructing PlayerRole from string."""
        assert PlayerRole("dm") == PlayerRole.DM
        assert PlayerRole("player") == PlayerRole.PLAYER
        assert PlayerRole("observer") == PlayerRole.OBSERVER

    def test_invalid_role(self):
        """Test that invalid role string raises ValueError."""
        with pytest.raises(ValueError):
            PlayerRole("admin")


# ---------------------------------------------------------------------------
# PermissionLevel enum tests
# ---------------------------------------------------------------------------

class TestPermissionLevel:
    """Tests for the PermissionLevel enum."""

    def test_values(self):
        """Test that enum values are correct strings."""
        assert PermissionLevel.ALLOWED == "allowed"
        assert PermissionLevel.DENIED == "denied"
        assert PermissionLevel.CONDITIONAL == "conditional"

    def test_string_enum(self):
        """Test that PermissionLevel is a string enum."""
        assert isinstance(PermissionLevel.ALLOWED, str)


# ---------------------------------------------------------------------------
# TemporaryPermission model tests
# ---------------------------------------------------------------------------

class TestTemporaryPermission:
    """Tests for the TemporaryPermission Pydantic model."""

    def test_create_default(self):
        """Test creating with minimal fields."""
        tp = TemporaryPermission(player_id="p1", tool_name="update_character")
        assert tp.player_id == "p1"
        assert tp.tool_name == "update_character"
        assert tp.expires_at is None
        assert tp.granted_by == "DM"
        assert isinstance(tp.granted_at, datetime)

    def test_create_with_expiry(self):
        """Test creating with explicit expiry."""
        future = datetime.now() + timedelta(hours=1)
        tp = TemporaryPermission(
            player_id="p1",
            tool_name="create_npc",
            expires_at=future,
        )
        assert tp.expires_at == future

    def test_serialization_roundtrip(self):
        """Test model_dump and model_validate roundtrip."""
        tp = TemporaryPermission(player_id="p1", tool_name="update_quest")
        data = tp.model_dump(mode="json")
        tp2 = TemporaryPermission.model_validate(data)
        assert tp2.player_id == tp.player_id
        assert tp2.tool_name == tp.tool_name


# ---------------------------------------------------------------------------
# PlayerRoleAssignment model tests
# ---------------------------------------------------------------------------

class TestPlayerRoleAssignment:
    """Tests for the PlayerRoleAssignment Pydantic model."""

    def test_default_role(self):
        """Test that default role is PLAYER."""
        pra = PlayerRoleAssignment(player_id="p1")
        assert pra.role == PlayerRole.PLAYER

    def test_dm_role(self):
        """Test explicit DM role assignment."""
        pra = PlayerRoleAssignment(player_id="dm1", role=PlayerRole.DM)
        assert pra.role == PlayerRole.DM

    def test_serialization_roundtrip(self):
        """Test model_dump and model_validate roundtrip."""
        pra = PlayerRoleAssignment(player_id="p1", role=PlayerRole.OBSERVER)
        data = pra.model_dump(mode="json")
        pra2 = PlayerRoleAssignment.model_validate(data)
        assert pra2.player_id == "p1"
        assert pra2.role == PlayerRole.OBSERVER


# ---------------------------------------------------------------------------
# PERMISSION_MATRIX tests
# ---------------------------------------------------------------------------

class TestPermissionMatrix:
    """Tests for the permission matrix structure and completeness."""

    def test_all_read_tools_present(self):
        """Test that all read tools are in the matrix."""
        for tool in _READ_TOOLS:
            assert tool in PERMISSION_MATRIX, f"Read tool '{tool}' missing from matrix"

    def test_all_character_tools_present(self):
        """Test that all character tools are in the matrix."""
        for tool in _CHARACTER_TOOLS:
            assert tool in PERMISSION_MATRIX, f"Character tool '{tool}' missing from matrix"

    def test_all_dm_only_tools_present(self):
        """Test that all DM-only tools are in the matrix."""
        for tool in _DM_ONLY_TOOLS:
            assert tool in PERMISSION_MATRIX, f"DM-only tool '{tool}' missing from matrix"

    def test_no_overlap_between_categories(self):
        """Test that tool categories don't overlap."""
        assert len(_READ_TOOLS & _CHARACTER_TOOLS) == 0, "Overlap between READ and CHARACTER"
        assert len(_READ_TOOLS & _DM_ONLY_TOOLS) == 0, "Overlap between READ and DM_ONLY"
        assert len(_CHARACTER_TOOLS & _DM_ONLY_TOOLS) == 0, "Overlap between CHARACTER and DM_ONLY"

    def test_read_tools_all_roles_allowed(self):
        """Test that read tools are ALLOWED for all roles."""
        for tool in _READ_TOOLS:
            perms = PERMISSION_MATRIX[tool]
            assert perms[PlayerRole.DM] == PermissionLevel.ALLOWED
            assert perms[PlayerRole.PLAYER] == PermissionLevel.ALLOWED
            assert perms[PlayerRole.OBSERVER] == PermissionLevel.ALLOWED

    def test_character_tools_dm_allowed(self):
        """Test that character tools are ALLOWED for DM."""
        for tool in _CHARACTER_TOOLS:
            assert PERMISSION_MATRIX[tool][PlayerRole.DM] == PermissionLevel.ALLOWED

    def test_character_tools_player_conditional(self):
        """Test that character tools are CONDITIONAL for PLAYER."""
        for tool in _CHARACTER_TOOLS:
            assert PERMISSION_MATRIX[tool][PlayerRole.PLAYER] == PermissionLevel.CONDITIONAL

    def test_character_tools_observer_denied(self):
        """Test that character tools are DENIED for OBSERVER."""
        for tool in _CHARACTER_TOOLS:
            assert PERMISSION_MATRIX[tool][PlayerRole.OBSERVER] == PermissionLevel.DENIED

    def test_dm_only_tools_dm_allowed(self):
        """Test that DM-only tools are ALLOWED for DM."""
        for tool in _DM_ONLY_TOOLS:
            assert PERMISSION_MATRIX[tool][PlayerRole.DM] == PermissionLevel.ALLOWED

    def test_dm_only_tools_player_denied(self):
        """Test that DM-only tools are DENIED for PLAYER."""
        for tool in _DM_ONLY_TOOLS:
            assert PERMISSION_MATRIX[tool][PlayerRole.PLAYER] == PermissionLevel.DENIED

    def test_dm_only_tools_observer_denied(self):
        """Test that DM-only tools are DENIED for OBSERVER."""
        for tool in _DM_ONLY_TOOLS:
            assert PERMISSION_MATRIX[tool][PlayerRole.OBSERVER] == PermissionLevel.DENIED

    def test_every_entry_has_all_three_roles(self):
        """Test that every matrix entry has DM, PLAYER, and OBSERVER keys."""
        for tool, perms in PERMISSION_MATRIX.items():
            assert PlayerRole.DM in perms, f"DM missing from {tool}"
            assert PlayerRole.PLAYER in perms, f"PLAYER missing from {tool}"
            assert PlayerRole.OBSERVER in perms, f"OBSERVER missing from {tool}"

    def test_dm_always_allowed(self):
        """Test that DM role is ALLOWED for every tool in the matrix."""
        for tool, perms in PERMISSION_MATRIX.items():
            assert perms[PlayerRole.DM] == PermissionLevel.ALLOWED, (
                f"DM should be ALLOWED for '{tool}', got {perms[PlayerRole.DM]}"
            )


# ---------------------------------------------------------------------------
# PermissionResolver tests
# ---------------------------------------------------------------------------

class TestPermissionResolverInit:
    """Tests for PermissionResolver initialization."""

    def test_empty_init(self):
        """Test that a new resolver has no assignments or permissions."""
        resolver = PermissionResolver()
        assert resolver.role_count == 0
        assert resolver.temp_permission_count == 0

    def test_get_all_assignments_empty(self):
        """Test get_all_role_assignments returns empty dict initially."""
        resolver = PermissionResolver()
        assert resolver.get_all_role_assignments() == {}


class TestPermissionResolverRoles:
    """Tests for role assignment operations."""

    def test_set_and_get_role(self):
        """Test setting and getting a player role."""
        resolver = PermissionResolver()
        resolver.set_player_role("p1", PlayerRole.DM)
        assert resolver.get_player_role("p1") == PlayerRole.DM

    def test_default_role_is_player(self):
        """Test that unassigned players default to PLAYER."""
        resolver = PermissionResolver()
        assert resolver.get_player_role("unknown") == PlayerRole.PLAYER

    def test_change_role(self):
        """Test that role can be changed."""
        resolver = PermissionResolver()
        resolver.set_player_role("p1", PlayerRole.PLAYER)
        resolver.set_player_role("p1", PlayerRole.DM)
        assert resolver.get_player_role("p1") == PlayerRole.DM

    def test_remove_role(self):
        """Test removing a role assignment."""
        resolver = PermissionResolver()
        resolver.set_player_role("p1", PlayerRole.DM)
        assert resolver.remove_player_role("p1") is True
        # Falls back to default PLAYER
        assert resolver.get_player_role("p1") == PlayerRole.PLAYER

    def test_remove_nonexistent_role(self):
        """Test removing a role that doesn't exist returns False."""
        resolver = PermissionResolver()
        assert resolver.remove_player_role("nobody") is False

    def test_role_count(self):
        """Test that role_count tracks assignments."""
        resolver = PermissionResolver()
        resolver.set_player_role("p1", PlayerRole.DM)
        resolver.set_player_role("p2", PlayerRole.PLAYER)
        assert resolver.role_count == 2

    def test_get_all_role_assignments(self):
        """Test getting all role assignments as a dict copy."""
        resolver = PermissionResolver()
        resolver.set_player_role("dm1", PlayerRole.DM)
        resolver.set_player_role("p1", PlayerRole.PLAYER)
        assignments = resolver.get_all_role_assignments()
        assert assignments == {"dm1": PlayerRole.DM, "p1": PlayerRole.PLAYER}
        # Verify it's a copy
        assignments["p2"] = PlayerRole.OBSERVER
        assert resolver.role_count == 2


class TestPermissionResolverOwnership:
    """Tests for character ownership management."""

    def test_register_ownership(self):
        """Test registering character ownership."""
        resolver = PermissionResolver()
        resolver.register_character_ownership("char-001", "player-1")
        assert resolver.is_owner("player-1", "char-001") is True

    def test_is_owner_false(self):
        """Test that non-owner returns False."""
        resolver = PermissionResolver()
        resolver.register_character_ownership("char-001", "player-1")
        assert resolver.is_owner("player-2", "char-001") is False

    def test_is_owner_unregistered(self):
        """Test that unregistered character returns False."""
        resolver = PermissionResolver()
        assert resolver.is_owner("player-1", "char-unknown") is False

    def test_unregister_ownership(self):
        """Test removing character ownership."""
        resolver = PermissionResolver()
        resolver.register_character_ownership("char-001", "player-1")
        resolver.unregister_character_ownership("char-001")
        assert resolver.is_owner("player-1", "char-001") is False

    def test_unregister_nonexistent(self):
        """Test unregistering a non-existent character doesn't raise."""
        resolver = PermissionResolver()
        resolver.unregister_character_ownership("does-not-exist")  # Should not raise

    def test_ownership_override(self):
        """Test that re-registering changes ownership."""
        resolver = PermissionResolver()
        resolver.register_character_ownership("char-001", "player-1")
        resolver.register_character_ownership("char-001", "player-2")
        assert resolver.is_owner("player-2", "char-001") is True
        assert resolver.is_owner("player-1", "char-001") is False


class TestPermissionResolverSinglePlayer:
    """Tests for single-player bypass (player_id=None)."""

    def test_none_player_id_always_true(self):
        """Test that None player_id bypasses all checks."""
        resolver = PermissionResolver()
        # DM-only tool with no roles set
        assert resolver.check_permission(None, "create_campaign") is True

    def test_none_player_id_on_every_tool(self):
        """Test that None player_id returns True for ALL tools in matrix."""
        resolver = PermissionResolver()
        for tool_name in PERMISSION_MATRIX:
            assert resolver.check_permission(None, tool_name) is True, (
                f"Single-player bypass failed for '{tool_name}'"
            )

    def test_none_player_id_unknown_tool(self):
        """Test that None player_id returns True even for unknown tools."""
        resolver = PermissionResolver()
        assert resolver.check_permission(None, "totally_fake_tool") is True

    def test_none_player_id_zero_overhead(self):
        """Test that None path is fast (no dict lookups needed)."""
        resolver = PermissionResolver()
        # Add lots of data to make non-bypass path slow
        for i in range(1000):
            resolver.set_player_role(f"player-{i}", PlayerRole.PLAYER)

        # None path should be near-instant regardless
        start = time.perf_counter()
        for _ in range(10000):
            resolver.check_permission(None, "update_character")
        elapsed = time.perf_counter() - start
        # Should complete in well under 1 second
        assert elapsed < 1.0, f"None bypass took {elapsed:.3f}s for 10k calls"


class TestPermissionResolverDM:
    """Tests for DM role permissions."""

    def test_dm_access_to_read_tools(self):
        """Test DM has access to all read tools."""
        resolver = PermissionResolver()
        resolver.set_player_role("dm1", PlayerRole.DM)
        for tool in _READ_TOOLS:
            assert resolver.check_permission("dm1", tool) is True, (
                f"DM denied for read tool '{tool}'"
            )

    def test_dm_access_to_character_tools(self):
        """Test DM has access to all character tools (no ownership needed)."""
        resolver = PermissionResolver()
        resolver.set_player_role("dm1", PlayerRole.DM)
        for tool in _CHARACTER_TOOLS:
            assert resolver.check_permission("dm1", tool) is True, (
                f"DM denied for character tool '{tool}'"
            )

    def test_dm_access_to_dm_only_tools(self):
        """Test DM has access to all DM-only tools."""
        resolver = PermissionResolver()
        resolver.set_player_role("dm1", PlayerRole.DM)
        for tool in _DM_ONLY_TOOLS:
            assert resolver.check_permission("dm1", tool) is True, (
                f"DM denied for DM-only tool '{tool}'"
            )

    def test_dm_access_to_unknown_tool(self):
        """Test DM has access even to tools not in the matrix."""
        resolver = PermissionResolver()
        resolver.set_player_role("dm1", PlayerRole.DM)
        assert resolver.check_permission("dm1", "some_unknown_tool") is True


class TestPermissionResolverPlayer:
    """Tests for PLAYER role permissions."""

    def test_player_read_tools_allowed(self):
        """Test PLAYER has access to all read tools."""
        resolver = PermissionResolver()
        resolver.set_player_role("p1", PlayerRole.PLAYER)
        for tool in _READ_TOOLS:
            assert resolver.check_permission("p1", tool) is True, (
                f"PLAYER denied for read tool '{tool}'"
            )

    def test_player_character_tools_denied_without_ownership(self):
        """Test PLAYER denied for character tools without ownership."""
        resolver = PermissionResolver()
        resolver.set_player_role("p1", PlayerRole.PLAYER)
        for tool in _CHARACTER_TOOLS:
            # No target entity ID
            assert resolver.check_permission("p1", tool) is False, (
                f"PLAYER allowed for '{tool}' without target_entity_id"
            )
            # With entity ID but no ownership
            assert resolver.check_permission("p1", tool, "char-other") is False, (
                f"PLAYER allowed for '{tool}' on non-owned character"
            )

    def test_player_character_tools_allowed_with_ownership(self):
        """Test PLAYER allowed for character tools on owned characters."""
        resolver = PermissionResolver()
        resolver.set_player_role("p1", PlayerRole.PLAYER)
        resolver.register_character_ownership("char-001", "p1")
        for tool in _CHARACTER_TOOLS:
            assert resolver.check_permission("p1", tool, "char-001") is True, (
                f"PLAYER denied for '{tool}' on owned character"
            )

    def test_player_dm_only_tools_denied(self):
        """Test PLAYER denied for all DM-only tools."""
        resolver = PermissionResolver()
        resolver.set_player_role("p1", PlayerRole.PLAYER)
        for tool in _DM_ONLY_TOOLS:
            assert resolver.check_permission("p1", tool) is False, (
                f"PLAYER allowed for DM-only tool '{tool}'"
            )

    def test_player_unknown_tool_denied(self):
        """Test PLAYER denied for tools not in the matrix."""
        resolver = PermissionResolver()
        resolver.set_player_role("p1", PlayerRole.PLAYER)
        assert resolver.check_permission("p1", "nonexistent_tool") is False

    def test_player_cannot_modify_other_player_character(self):
        """Test that PLAYER cannot modify another player's character."""
        resolver = PermissionResolver()
        resolver.set_player_role("p1", PlayerRole.PLAYER)
        resolver.set_player_role("p2", PlayerRole.PLAYER)
        resolver.register_character_ownership("char-001", "p1")
        resolver.register_character_ownership("char-002", "p2")

        # p1 can modify char-001 but not char-002
        assert resolver.check_permission("p1", "update_character", "char-001") is True
        assert resolver.check_permission("p1", "update_character", "char-002") is False

        # p2 can modify char-002 but not char-001
        assert resolver.check_permission("p2", "update_character", "char-002") is True
        assert resolver.check_permission("p2", "update_character", "char-001") is False


class TestPermissionResolverObserver:
    """Tests for OBSERVER role permissions."""

    def test_observer_read_tools_allowed(self):
        """Test OBSERVER has access to all read tools."""
        resolver = PermissionResolver()
        resolver.set_player_role("obs1", PlayerRole.OBSERVER)
        for tool in _READ_TOOLS:
            assert resolver.check_permission("obs1", tool) is True, (
                f"OBSERVER denied for read tool '{tool}'"
            )

    def test_observer_character_tools_denied(self):
        """Test OBSERVER denied for all character tools."""
        resolver = PermissionResolver()
        resolver.set_player_role("obs1", PlayerRole.OBSERVER)
        for tool in _CHARACTER_TOOLS:
            assert resolver.check_permission("obs1", tool) is False, (
                f"OBSERVER allowed for character tool '{tool}'"
            )

    def test_observer_dm_only_tools_denied(self):
        """Test OBSERVER denied for all DM-only tools."""
        resolver = PermissionResolver()
        resolver.set_player_role("obs1", PlayerRole.OBSERVER)
        for tool in _DM_ONLY_TOOLS:
            assert resolver.check_permission("obs1", tool) is False, (
                f"OBSERVER allowed for DM-only tool '{tool}'"
            )

    def test_observer_denied_even_with_ownership(self):
        """Test OBSERVER denied even if they own a character."""
        resolver = PermissionResolver()
        resolver.set_player_role("obs1", PlayerRole.OBSERVER)
        resolver.register_character_ownership("char-001", "obs1")
        # OBSERVER is DENIED (not CONDITIONAL) for character tools
        assert resolver.check_permission("obs1", "update_character", "char-001") is False

    def test_observer_unknown_tool_denied(self):
        """Test OBSERVER denied for unknown tools."""
        resolver = PermissionResolver()
        resolver.set_player_role("obs1", PlayerRole.OBSERVER)
        assert resolver.check_permission("obs1", "fake_tool") is False


# ---------------------------------------------------------------------------
# Temporary permission tests
# ---------------------------------------------------------------------------

class TestTemporaryPermissions:
    """Tests for temporary permission grants and revocations."""

    def test_grant_allows_denied_tool(self):
        """Test that granting permission allows a normally denied tool."""
        resolver = PermissionResolver()
        resolver.set_player_role("p1", PlayerRole.PLAYER)
        # Normally denied
        assert resolver.check_permission("p1", "create_npc") is False
        # Grant
        perm = resolver.grant_permission("p1", "create_npc")
        assert isinstance(perm, TemporaryPermission)
        # Now allowed
        assert resolver.check_permission("p1", "create_npc") is True

    def test_grant_with_duration(self):
        """Test that grant with duration sets expires_at."""
        resolver = PermissionResolver()
        perm = resolver.grant_permission("p1", "create_npc", duration_minutes=60)
        assert perm.expires_at is not None
        assert perm.expires_at > datetime.now()

    def test_session_scoped_grant(self):
        """Test that grant without duration is session-scoped (no expiry)."""
        resolver = PermissionResolver()
        perm = resolver.grant_permission("p1", "create_npc")
        assert perm.expires_at is None

    def test_revoke_permission(self):
        """Test revoking a temporary permission."""
        resolver = PermissionResolver()
        resolver.set_player_role("p1", PlayerRole.PLAYER)
        resolver.grant_permission("p1", "create_npc")
        assert resolver.check_permission("p1", "create_npc") is True

        revoked = resolver.revoke_permission("p1", "create_npc")
        assert revoked == 1
        assert resolver.check_permission("p1", "create_npc") is False

    def test_revoke_nonexistent(self):
        """Test revoking a permission that doesn't exist."""
        resolver = PermissionResolver()
        assert resolver.revoke_permission("p1", "create_npc") == 0

    def test_expired_permission_auto_cleanup(self):
        """Test that expired permissions are cleaned up on check."""
        resolver = PermissionResolver()
        resolver.set_player_role("p1", PlayerRole.PLAYER)

        # Create an already-expired permission
        expired_perm = TemporaryPermission(
            player_id="p1",
            tool_name="create_npc",
            expires_at=datetime.now() - timedelta(seconds=1),
        )
        resolver._temp_permissions.append(expired_perm)
        assert resolver.temp_permission_count == 1

        # Check should not grant access (expired) and should clean up
        assert resolver.check_permission("p1", "create_npc") is False
        assert resolver.temp_permission_count == 0

    def test_cleanup_expired(self):
        """Test explicit cleanup of expired permissions."""
        resolver = PermissionResolver()
        expired = TemporaryPermission(
            player_id="p1",
            tool_name="create_npc",
            expires_at=datetime.now() - timedelta(seconds=1),
        )
        valid = TemporaryPermission(
            player_id="p2",
            tool_name="create_location",
            expires_at=datetime.now() + timedelta(hours=1),
        )
        session_scoped = TemporaryPermission(
            player_id="p3",
            tool_name="update_quest",
            expires_at=None,
        )
        resolver._temp_permissions = [expired, valid, session_scoped]

        removed = resolver.cleanup_expired()
        assert removed == 1
        assert resolver.temp_permission_count == 2

    def test_multiple_grants_same_tool(self):
        """Test that multiple grants for the same tool stack."""
        resolver = PermissionResolver()
        resolver.grant_permission("p1", "create_npc")
        resolver.grant_permission("p1", "create_npc")
        assert resolver.temp_permission_count == 2

        # Revoking removes all
        revoked = resolver.revoke_permission("p1", "create_npc")
        assert revoked == 2
        assert resolver.temp_permission_count == 0

    def test_grant_for_observer(self):
        """Test that temporary grants work for observers too."""
        resolver = PermissionResolver()
        resolver.set_player_role("obs1", PlayerRole.OBSERVER)
        assert resolver.check_permission("obs1", "update_character") is False

        resolver.grant_permission("obs1", "update_character")
        assert resolver.check_permission("obs1", "update_character") is True

    def test_temp_permission_count(self):
        """Test the temp_permission_count property."""
        resolver = PermissionResolver()
        assert resolver.temp_permission_count == 0
        resolver.grant_permission("p1", "create_npc")
        assert resolver.temp_permission_count == 1
        resolver.grant_permission("p2", "create_location")
        assert resolver.temp_permission_count == 2


# ---------------------------------------------------------------------------
# Default role behavior tests
# ---------------------------------------------------------------------------

class TestDefaultRoleBehavior:
    """Tests for players without explicit role assignments."""

    def test_unassigned_player_defaults_to_player(self):
        """Test that unassigned player_id is treated as PLAYER."""
        resolver = PermissionResolver()
        # "unknown" has no explicit role, should default to PLAYER
        assert resolver.check_permission("unknown", "get_campaign_info") is True
        assert resolver.check_permission("unknown", "create_npc") is False

    def test_unassigned_conditional_requires_ownership(self):
        """Test that unassigned player still needs ownership for character tools."""
        resolver = PermissionResolver()
        resolver.register_character_ownership("char-001", "unknown")

        assert resolver.check_permission("unknown", "update_character", "char-001") is True
        assert resolver.check_permission("unknown", "update_character", "char-other") is False


# ---------------------------------------------------------------------------
# Edge cases and integration tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests for edge cases and unusual scenarios."""

    def test_empty_player_id_string(self):
        """Test that empty string player_id is NOT treated as None."""
        resolver = PermissionResolver()
        # Empty string is not None, so it goes through permission checks
        # Defaults to PLAYER role
        assert resolver.check_permission("", "create_npc") is False
        assert resolver.check_permission("", "get_campaign_info") is True

    def test_whitespace_player_id(self):
        """Test that whitespace player_id is treated as a real player."""
        resolver = PermissionResolver()
        resolver.set_player_role(" ", PlayerRole.DM)
        assert resolver.check_permission(" ", "create_campaign") is True

    def test_case_sensitive_player_id(self):
        """Test that player IDs are case-sensitive."""
        resolver = PermissionResolver()
        resolver.set_player_role("Player1", PlayerRole.DM)
        assert resolver.get_player_role("Player1") == PlayerRole.DM
        assert resolver.get_player_role("player1") == PlayerRole.PLAYER  # default

    def test_multiple_characters_one_player(self):
        """Test a player owning multiple characters."""
        resolver = PermissionResolver()
        resolver.set_player_role("p1", PlayerRole.PLAYER)
        resolver.register_character_ownership("char-001", "p1")
        resolver.register_character_ownership("char-002", "p1")

        assert resolver.check_permission("p1", "update_character", "char-001") is True
        assert resolver.check_permission("p1", "update_character", "char-002") is True
        assert resolver.check_permission("p1", "update_character", "char-003") is False


class TestCompleteMatrix:
    """Integration tests covering every (role, tool_category) combination."""

    @pytest.fixture
    def resolver(self):
        """Create a resolver with DM, PLAYER, and OBSERVER configured."""
        r = PermissionResolver()
        r.set_player_role("dm", PlayerRole.DM)
        r.set_player_role("player", PlayerRole.PLAYER)
        r.set_player_role("observer", PlayerRole.OBSERVER)
        r.register_character_ownership("my-char", "player")
        return r

    def test_dm_full_matrix(self, resolver):
        """Test DM access across all tools in the matrix."""
        for tool_name in PERMISSION_MATRIX:
            assert resolver.check_permission("dm", tool_name) is True, (
                f"DM should have access to '{tool_name}'"
            )

    def test_player_read_matrix(self, resolver):
        """Test PLAYER read access across all read tools."""
        for tool in _READ_TOOLS:
            assert resolver.check_permission("player", tool) is True

    def test_player_character_matrix_owned(self, resolver):
        """Test PLAYER access to character tools for owned character."""
        for tool in _CHARACTER_TOOLS:
            assert resolver.check_permission("player", tool, "my-char") is True

    def test_player_character_matrix_not_owned(self, resolver):
        """Test PLAYER denied for character tools on non-owned character."""
        for tool in _CHARACTER_TOOLS:
            assert resolver.check_permission("player", tool, "other-char") is False

    def test_player_dm_only_matrix(self, resolver):
        """Test PLAYER denied for all DM-only tools."""
        for tool in _DM_ONLY_TOOLS:
            assert resolver.check_permission("player", tool) is False

    def test_observer_read_matrix(self, resolver):
        """Test OBSERVER read access across all read tools."""
        for tool in _READ_TOOLS:
            assert resolver.check_permission("observer", tool) is True

    def test_observer_write_matrix(self, resolver):
        """Test OBSERVER denied for all write tools."""
        for tool in _CHARACTER_TOOLS | _DM_ONLY_TOOLS:
            assert resolver.check_permission("observer", tool) is False

    def test_single_player_bypass_matrix(self, resolver):
        """Test None player_id bypasses for all tools."""
        for tool_name in PERMISSION_MATRIX:
            assert resolver.check_permission(None, tool_name) is True
