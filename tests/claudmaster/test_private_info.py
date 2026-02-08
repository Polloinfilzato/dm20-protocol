"""
Tests for the private information management system.

Tests cover:
- PrivateInfo creation and visibility filtering
- Info sharing (allowed and disallowed)
- Private messaging (send, read, pending)
- Hidden rolls (create, messages, reveal)
- Secret knowledge (add, relevance check, prompt)
- Response formatting with mixed visibility
- DM whisper formatting
- Info expiration cleanup
- Knowledge topic search
"""

from datetime import datetime, timedelta

import pytest

from dm20_protocol.claudmaster.private_info import (
    InfoVisibility,
    PrivateInfo,
    PrivateMessage,
    HiddenRoll,
    SecretKnowledge,
    PrivateInfoManager,
)
from dm20_protocol.claudmaster.pc_tracking import (
    PCRegistry,
    PCState,
    MultiPlayerConfig,
)


@pytest.fixture
def config():
    """Create a test MultiPlayerConfig."""
    return MultiPlayerConfig(max_players=4, allow_dynamic_join=True)


@pytest.fixture
def registry(config):
    """Create a test PCRegistry with some registered PCs."""
    reg = PCRegistry(config)
    reg.register_pc("aragorn", "John")
    reg.register_pc("legolas", "Sarah")
    reg.register_pc("gimli", "Mike")
    reg.register_pc("gandalf", "Emma")
    return reg


@pytest.fixture
def manager(registry):
    """Create a test PrivateInfoManager."""
    return PrivateInfoManager(registry)


class TestPrivateInfoCreation:
    """Test PrivateInfo creation and basic properties."""

    def test_create_private_info(self, manager):
        """Test creating a private info piece."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="You notice a hidden door",
            visibility=InfoVisibility.PRIVATE,
            source="perception_check"
        )

        assert info.info_id is not None
        assert info.content == "You notice a hidden door"
        assert info.visibility == InfoVisibility.PRIVATE
        assert "aragorn" in info.visible_to
        assert info.source == "perception_check"
        assert info.can_share is True
        assert info.expires is None

    def test_create_public_info(self, manager):
        """Test creating public info."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="The door is locked",
            visibility=InfoVisibility.PUBLIC
        )

        assert info.visibility == InfoVisibility.PUBLIC
        assert info.content == "The door is locked"

    def test_create_party_info(self, manager):
        """Test creating party-wide info."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="You hear footsteps approaching",
            visibility=InfoVisibility.PARTY
        )

        assert info.visibility == InfoVisibility.PARTY

    def test_create_subset_info(self, manager):
        """Test creating subset visibility info."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="You both see the trap",
            visibility=InfoVisibility.SUBSET,
            visible_to=["aragorn", "legolas"]
        )

        assert info.visibility == InfoVisibility.SUBSET
        assert "aragorn" in info.visible_to
        assert "legolas" in info.visible_to
        assert "gimli" not in info.visible_to

    def test_create_dm_only_info(self, manager):
        """Test creating DM-only info."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="This PC is about to trigger a trap",
            visibility=InfoVisibility.DM_ONLY
        )

        assert info.visibility == InfoVisibility.DM_ONLY

    def test_create_info_with_expiration(self, manager):
        """Test creating info with expiration."""
        future = datetime.now() + timedelta(hours=1)
        info = manager.add_private_info(
            pc_id="aragorn",
            content="You feel a temporary boost",
            visibility=InfoVisibility.PRIVATE,
            expires=future
        )

        assert info.expires == future

    def test_create_info_no_sharing(self, manager):
        """Test creating info that cannot be shared."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="You have a vision (cannot tell others)",
            visibility=InfoVisibility.PRIVATE,
            can_share=False
        )

        assert info.can_share is False

    def test_create_info_invalid_pc(self, manager):
        """Test creating info for non-existent PC raises error."""
        with pytest.raises(KeyError):
            manager.add_private_info(
                pc_id="frodo",
                content="Test",
                visibility=InfoVisibility.PRIVATE
            )


class TestInfoVisibility:
    """Test info visibility filtering."""

    def test_get_private_info(self, manager):
        """Test getting private info visible only to one PC."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="Private to Aragorn",
            visibility=InfoVisibility.PRIVATE
        )

        aragorn_info = manager.get_visible_info("aragorn")
        legolas_info = manager.get_visible_info("legolas")

        assert info in aragorn_info
        assert info not in legolas_info

    def test_get_public_info(self, manager):
        """Test getting public info visible to all."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="Public announcement",
            visibility=InfoVisibility.PUBLIC
        )

        aragorn_info = manager.get_visible_info("aragorn")
        legolas_info = manager.get_visible_info("legolas")
        gimli_info = manager.get_visible_info("gimli")

        assert info in aragorn_info
        assert info in legolas_info
        assert info in gimli_info

    def test_get_party_info(self, manager):
        """Test getting party info visible to active PCs."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="Party-wide info",
            visibility=InfoVisibility.PARTY
        )

        # All active PCs should see it
        aragorn_info = manager.get_visible_info("aragorn")
        legolas_info = manager.get_visible_info("legolas")

        assert info in aragorn_info
        assert info in legolas_info

        # Mark one PC inactive
        manager.pc_registry.update_pc_state("gimli", is_active=False)
        gimli_info = manager.get_visible_info("gimli")

        # Inactive PC should not see party info
        assert info not in gimli_info

    def test_get_subset_info(self, manager):
        """Test getting subset visibility info."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="Shared secret",
            visibility=InfoVisibility.SUBSET,
            visible_to=["aragorn", "legolas"]
        )

        aragorn_info = manager.get_visible_info("aragorn")
        legolas_info = manager.get_visible_info("legolas")
        gimli_info = manager.get_visible_info("gimli")

        assert info in aragorn_info
        assert info in legolas_info
        assert info not in gimli_info

    def test_dm_only_never_visible(self, manager):
        """Test DM-only info is never visible to PCs."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="DM secret",
            visibility=InfoVisibility.DM_ONLY
        )

        aragorn_info = manager.get_visible_info("aragorn")
        legolas_info = manager.get_visible_info("legolas")

        assert info not in aragorn_info
        assert info not in legolas_info

    def test_get_visible_info_invalid_pc(self, manager):
        """Test getting info for non-existent PC raises error."""
        with pytest.raises(KeyError):
            manager.get_visible_info("frodo")

    def test_expired_info_not_visible(self, manager):
        """Test expired info is filtered out."""
        past = datetime.now() - timedelta(hours=1)
        info = manager.add_private_info(
            pc_id="aragorn",
            content="Expired info",
            visibility=InfoVisibility.PRIVATE,
            expires=past
        )

        aragorn_info = manager.get_visible_info("aragorn")
        assert info not in aragorn_info


class TestInfoSharing:
    """Test info sharing between PCs."""

    def test_share_info_success(self, manager):
        """Test successfully sharing info."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="Secret info",
            visibility=InfoVisibility.PRIVATE
        )

        # Aragorn shares with Legolas
        result = manager.share_info("aragorn", "legolas", info.info_id)

        assert result is True
        assert "legolas" in info.visible_to

        # Legolas can now see it
        legolas_info = manager.get_visible_info("legolas")
        assert info in legolas_info

    def test_share_info_not_allowed(self, manager):
        """Test sharing info that cannot be shared."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="Unshareable secret",
            visibility=InfoVisibility.PRIVATE,
            can_share=False
        )

        result = manager.share_info("aragorn", "legolas", info.info_id)

        assert result is False
        assert "legolas" not in info.visible_to

    def test_share_info_no_access(self, manager):
        """Test sharing info PC doesn't have access to."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="Private to Aragorn",
            visibility=InfoVisibility.PRIVATE
        )

        # Legolas tries to share it but doesn't have access
        with pytest.raises(ValueError, match="does not have access"):
            manager.share_info("legolas", "gimli", info.info_id)

    def test_share_info_not_found(self, manager):
        """Test sharing non-existent info."""
        with pytest.raises(ValueError, match="not found"):
            manager.share_info("aragorn", "legolas", "fake-id")

    def test_share_info_invalid_pcs(self, manager):
        """Test sharing with invalid PC IDs."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="Test",
            visibility=InfoVisibility.PRIVATE
        )

        with pytest.raises(KeyError):
            manager.share_info("frodo", "legolas", info.info_id)

        with pytest.raises(KeyError):
            manager.share_info("aragorn", "frodo", info.info_id)


class TestKnowledgeCheck:
    """Test knowledge topic search."""

    def test_check_knowledge_found(self, manager):
        """Test finding knowledge by topic."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="The password is 'mellon'",
            visibility=InfoVisibility.PRIVATE
        )

        result = manager.check_knowledge("aragorn", "password")
        assert result == info

    def test_check_knowledge_not_found(self, manager):
        """Test not finding knowledge."""
        manager.add_private_info(
            pc_id="aragorn",
            content="The door is locked",
            visibility=InfoVisibility.PRIVATE
        )

        result = manager.check_knowledge("aragorn", "password")
        assert result is None

    def test_check_knowledge_case_insensitive(self, manager):
        """Test knowledge search is case-insensitive."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="The PASSWORD is 'mellon'",
            visibility=InfoVisibility.PRIVATE
        )

        result = manager.check_knowledge("aragorn", "password")
        assert result == info

    def test_check_knowledge_no_access(self, manager):
        """Test checking knowledge PC doesn't have access to."""
        manager.add_private_info(
            pc_id="aragorn",
            content="The password is 'mellon'",
            visibility=InfoVisibility.PRIVATE
        )

        result = manager.check_knowledge("legolas", "password")
        assert result is None

    def test_check_knowledge_invalid_pc(self, manager):
        """Test checking knowledge for non-existent PC."""
        with pytest.raises(KeyError):
            manager.check_knowledge("frodo", "password")


class TestPrivateMessaging:
    """Test private message system."""

    def test_send_private_message(self, manager):
        """Test sending a private message."""
        msg = manager.send_private_message(
            content="Roll a stealth check",
            recipients=["aragorn"]
        )

        assert msg.message_id is not None
        assert msg.content == "Roll a stealth check"
        assert msg.recipients == ["aragorn"]
        assert msg.message_type == "dm_note"
        assert len(msg.read_by) == 0

    def test_send_message_multiple_recipients(self, manager):
        """Test sending message to multiple PCs."""
        msg = manager.send_private_message(
            content="You both hear a noise",
            recipients=["aragorn", "legolas"],
            message_type="secret"
        )

        assert "aragorn" in msg.recipients
        assert "legolas" in msg.recipients
        assert msg.message_type == "secret"

    def test_get_pending_messages(self, manager):
        """Test getting unread messages."""
        msg1 = manager.send_private_message(
            content="Message 1",
            recipients=["aragorn"]
        )
        msg2 = manager.send_private_message(
            content="Message 2",
            recipients=["aragorn", "legolas"]
        )
        manager.send_private_message(
            content="Message 3",
            recipients=["gimli"]
        )

        aragorn_pending = manager.get_pending_messages("aragorn")
        legolas_pending = manager.get_pending_messages("legolas")
        gimli_pending = manager.get_pending_messages("gimli")

        assert len(aragorn_pending) == 2
        assert msg1 in aragorn_pending
        assert msg2 in aragorn_pending

        assert len(legolas_pending) == 1
        assert msg2 in legolas_pending

        assert len(gimli_pending) == 1

    def test_mark_message_read(self, manager):
        """Test marking messages as read."""
        msg = manager.send_private_message(
            content="Test message",
            recipients=["aragorn", "legolas"]
        )

        # Mark read by Aragorn
        manager.mark_message_read(msg.message_id, "aragorn")

        assert "aragorn" in msg.read_by
        assert "legolas" not in msg.read_by

        # Aragorn shouldn't see it in pending
        aragorn_pending = manager.get_pending_messages("aragorn")
        assert msg not in aragorn_pending

        # Legolas should still see it
        legolas_pending = manager.get_pending_messages("legolas")
        assert msg in legolas_pending

    def test_mark_message_read_not_recipient(self, manager):
        """Test marking message read by non-recipient."""
        msg = manager.send_private_message(
            content="Test",
            recipients=["aragorn"]
        )

        with pytest.raises(ValueError, match="not a recipient"):
            manager.mark_message_read(msg.message_id, "legolas")

    def test_mark_message_read_not_found(self, manager):
        """Test marking non-existent message as read."""
        with pytest.raises(ValueError, match="not found"):
            manager.mark_message_read("fake-id", "aragorn")

    def test_mark_message_read_invalid_pc(self, manager):
        """Test marking message read with invalid PC."""
        msg = manager.send_private_message(
            content="Test",
            recipients=["aragorn"]
        )

        with pytest.raises(KeyError):
            manager.mark_message_read(msg.message_id, "frodo")

    def test_send_message_invalid_recipient(self, manager):
        """Test sending message to non-existent PC."""
        with pytest.raises(KeyError):
            manager.send_private_message(
                content="Test",
                recipients=["frodo"]
            )

    def test_get_pending_messages_invalid_pc(self, manager):
        """Test getting messages for non-existent PC."""
        with pytest.raises(KeyError):
            manager.get_pending_messages("frodo")


class TestDMWhisper:
    """Test DM whisper formatting."""

    def test_format_dm_whisper(self, manager):
        """Test formatting a DM whisper."""
        whisper = manager.format_dm_whisper("aragorn", "You notice something")

        assert whisper == "[Private to John]: You notice something"

    def test_format_dm_whisper_different_player(self, manager):
        """Test whisper formatting for different players."""
        whisper1 = manager.format_dm_whisper("aragorn", "Test")
        whisper2 = manager.format_dm_whisper("legolas", "Test")

        assert "John" in whisper1
        assert "Sarah" in whisper2

    def test_format_dm_whisper_invalid_pc(self, manager):
        """Test whisper for non-existent PC."""
        with pytest.raises(KeyError):
            manager.format_dm_whisper("frodo", "Test")


class TestHiddenRolls:
    """Test hidden roll system."""

    def test_create_hidden_roll(self, manager):
        """Test creating a hidden roll."""
        roll = manager.create_hidden_roll(
            pc_id="aragorn",
            roll_type="perception",
            result=18,
            dc=15
        )

        assert roll.roll_id is not None
        assert roll.pc_id == "aragorn"
        assert roll.roll_type == "perception"
        assert roll.result == 18
        assert roll.dc == 15
        assert roll.success is True
        assert len(roll.revealed_to) == 0

    def test_create_hidden_roll_failure(self, manager):
        """Test creating a failed hidden roll."""
        roll = manager.create_hidden_roll(
            pc_id="gimli",
            roll_type="stealth",
            result=8,
            dc=12
        )

        assert roll.success is False

    def test_create_hidden_roll_no_dc(self, manager):
        """Test creating roll without DC."""
        roll = manager.create_hidden_roll(
            pc_id="legolas",
            roll_type="insight",
            result=15
        )

        assert roll.dc is None
        assert roll.success is None

    def test_get_hidden_roll_message_success(self, manager):
        """Test getting messages for successful roll."""
        roll = manager.create_hidden_roll(
            pc_id="aragorn",
            roll_type="perception",
            result=20,
            dc=15
        )

        private_msg, public_msg = manager.get_hidden_roll_message(roll)

        assert "20" in private_msg
        assert "DC 15" in private_msg
        assert "succeeded" in private_msg
        assert "John" in public_msg
        assert "perception" in public_msg
        # Private details not in public message
        assert "20" not in public_msg

    def test_get_hidden_roll_message_failure(self, manager):
        """Test getting messages for failed roll."""
        roll = manager.create_hidden_roll(
            pc_id="gimli",
            roll_type="stealth",
            result=8,
            dc=12
        )

        private_msg, public_msg = manager.get_hidden_roll_message(roll)

        assert "failed" in private_msg
        assert "8" in private_msg

    def test_get_hidden_roll_message_no_dc(self, manager):
        """Test getting messages for roll without DC."""
        roll = manager.create_hidden_roll(
            pc_id="legolas",
            roll_type="insight",
            result=15
        )

        private_msg, public_msg = manager.get_hidden_roll_message(roll)

        assert "15" in private_msg
        assert "succeeded" not in private_msg
        assert "failed" not in private_msg

    def test_reveal_roll(self, manager):
        """Test revealing a hidden roll."""
        roll = manager.create_hidden_roll(
            pc_id="aragorn",
            roll_type="perception",
            result=18
        )

        manager.reveal_roll(roll.roll_id, ["legolas", "gimli"])

        assert "legolas" in roll.revealed_to
        assert "gimli" in roll.revealed_to
        assert "aragorn" not in roll.revealed_to

    def test_reveal_roll_not_found(self, manager):
        """Test revealing non-existent roll."""
        with pytest.raises(ValueError, match="not found"):
            manager.reveal_roll("fake-id", ["legolas"])

    def test_reveal_roll_invalid_pc(self, manager):
        """Test revealing roll to non-existent PC."""
        roll = manager.create_hidden_roll(
            pc_id="aragorn",
            roll_type="perception",
            result=18
        )

        with pytest.raises(KeyError):
            manager.reveal_roll(roll.roll_id, ["frodo"])

    def test_create_hidden_roll_invalid_pc(self, manager):
        """Test creating roll for non-existent PC."""
        with pytest.raises(KeyError):
            manager.create_hidden_roll(
                pc_id="frodo",
                roll_type="perception",
                result=10
            )


class TestSecretKnowledge:
    """Test secret knowledge system."""

    def test_add_character_secret(self, manager):
        """Test adding a character secret."""
        secret = manager.add_character_secret(
            pc_id="aragorn",
            subject="Royal heritage",
            content="Aragorn is the heir of Isildur",
            source="background",
            category="background",
            relevance_tags=["king", "gondor", "lineage"]
        )

        assert secret.knowledge_id is not None
        assert secret.pc_id == "aragorn"
        assert secret.subject == "Royal heritage"
        assert secret.content == "Aragorn is the heir of Isildur"
        assert secret.category == "background"
        assert "king" in secret.relevance_tags
        assert len(secret.shared_with) == 0

    def test_check_secret_relevance(self, manager):
        """Test checking if secrets are relevant."""
        secret1 = manager.add_character_secret(
            pc_id="aragorn",
            subject="Royal heritage",
            content="Heir of Isildur",
            relevance_tags=["king", "gondor", "crown"]
        )
        manager.add_character_secret(
            pc_id="legolas",
            subject="Elf knowledge",
            content="Ancient lore",
            relevance_tags=["elves", "rivendell"]
        )

        # Context mentions "king"
        relevant = manager.check_secret_relevance(
            "The king of Gondor is needed"
        )

        assert len(relevant) == 1
        assert secret1 in relevant

    def test_check_secret_relevance_multiple(self, manager):
        """Test finding multiple relevant secrets."""
        secret1 = manager.add_character_secret(
            pc_id="aragorn",
            subject="Sword",
            content="Reforged Narsil",
            relevance_tags=["sword", "weapon"]
        )
        secret2 = manager.add_character_secret(
            pc_id="gimli",
            subject="Axe mastery",
            content="Expert with axes",
            relevance_tags=["weapon", "combat"]
        )

        relevant = manager.check_secret_relevance("Choose your weapon")

        assert len(relevant) == 2
        assert secret1 in relevant
        assert secret2 in relevant

    def test_check_secret_relevance_case_insensitive(self, manager):
        """Test relevance check is case-insensitive."""
        secret = manager.add_character_secret(
            pc_id="aragorn",
            subject="Test",
            content="Test",
            relevance_tags=["KING"]
        )

        relevant = manager.check_secret_relevance("The king approaches")

        assert len(relevant) == 1
        assert secret in relevant

    def test_check_secret_relevance_none(self, manager):
        """Test no relevant secrets found."""
        manager.add_character_secret(
            pc_id="aragorn",
            subject="Test",
            content="Test",
            relevance_tags=["sword"]
        )

        relevant = manager.check_secret_relevance("You see a dragon")

        assert len(relevant) == 0

    def test_prompt_secret_share(self, manager):
        """Test generating secret share prompt."""
        secret = manager.add_character_secret(
            pc_id="aragorn",
            subject="Hidden passage",
            content="There's a secret tunnel",
            relevance_tags=["tunnel", "escape"]
        )

        prompt = manager.prompt_secret_share("aragorn", secret.knowledge_id)

        assert "John" in prompt  # Player name
        assert "Hidden passage" in prompt  # Subject
        assert "relevant" in prompt
        assert "share" in prompt

    def test_prompt_secret_share_not_found(self, manager):
        """Test prompting for non-existent secret."""
        with pytest.raises(ValueError, match="not found"):
            manager.prompt_secret_share("aragorn", "fake-id")

    def test_prompt_secret_share_wrong_pc(self, manager):
        """Test prompting for secret that doesn't belong to PC."""
        secret = manager.add_character_secret(
            pc_id="aragorn",
            subject="Test",
            content="Test",
            relevance_tags=[]
        )

        with pytest.raises(ValueError, match="not found"):
            manager.prompt_secret_share("legolas", secret.knowledge_id)

    def test_add_secret_invalid_pc(self, manager):
        """Test adding secret for non-existent PC."""
        with pytest.raises(KeyError):
            manager.add_character_secret(
                pc_id="frodo",
                subject="Test",
                content="Test"
            )

    def test_add_secret_default_values(self, manager):
        """Test adding secret with default values."""
        secret = manager.add_character_secret(
            pc_id="aragorn",
            subject="Test",
            content="Test content"
        )

        assert secret.source == "background"
        assert secret.category == "background"
        assert len(secret.relevance_tags) == 0


class TestResponseFormatting:
    """Test response formatting with mixed visibility."""

    def test_format_response_public_only(self, manager):
        """Test formatting response with only public content."""
        result = manager.format_response_with_private(
            public_content="Everyone sees this",
            private_additions={}
        )

        assert len(result) == 4  # All 4 active PCs
        assert result["aragorn"] == "Everyone sees this"
        assert result["legolas"] == "Everyone sees this"
        assert result["gimli"] == "Everyone sees this"
        assert result["gandalf"] == "Everyone sees this"

    def test_format_response_with_private(self, manager):
        """Test formatting response with private additions."""
        result = manager.format_response_with_private(
            public_content="Everyone sees this",
            private_additions={
                "aragorn": "You notice a trap",
                "legolas": "You hear footsteps"
            }
        )

        # Aragorn sees public + private
        assert "Everyone sees this" in result["aragorn"]
        assert "You notice a trap" in result["aragorn"]
        assert "Private to John" in result["aragorn"]

        # Legolas sees public + private
        assert "Everyone sees this" in result["legolas"]
        assert "You hear footsteps" in result["legolas"]
        assert "Private to Sarah" in result["legolas"]

        # Gimli sees only public
        assert result["gimli"] == "Everyone sees this"
        assert "trap" not in result["gimli"]

    def test_format_response_inactive_pc(self, manager):
        """Test formatting doesn't include inactive PCs."""
        # Mark one PC inactive
        manager.pc_registry.update_pc_state("gimli", is_active=False)

        result = manager.format_response_with_private(
            public_content="Test",
            private_additions={}
        )

        # Only active PCs in result
        assert len(result) == 3
        assert "aragorn" in result
        assert "legolas" in result
        assert "gandalf" in result
        assert "gimli" not in result

    def test_format_response_invalid_pc(self, manager):
        """Test formatting with invalid PC in private additions."""
        with pytest.raises(KeyError):
            manager.format_response_with_private(
                public_content="Test",
                private_additions={"frodo": "Private"}
            )


class TestInfoExpiration:
    """Test info expiration cleanup."""

    def test_remove_expired_info(self, manager):
        """Test removing expired information."""
        past = datetime.now() - timedelta(hours=1)
        future = datetime.now() + timedelta(hours=1)

        # Add expired info
        manager.add_private_info(
            pc_id="aragorn",
            content="Expired 1",
            visibility=InfoVisibility.PRIVATE,
            expires=past
        )
        manager.add_private_info(
            pc_id="legolas",
            content="Expired 2",
            visibility=InfoVisibility.PRIVATE,
            expires=past
        )

        # Add non-expired info
        manager.add_private_info(
            pc_id="aragorn",
            content="Valid 1",
            visibility=InfoVisibility.PRIVATE,
            expires=future
        )
        manager.add_private_info(
            pc_id="gimli",
            content="Valid 2",
            visibility=InfoVisibility.PRIVATE
        )

        count = manager.remove_expired_info()

        assert count == 2

        # Check expired info is gone
        aragorn_info = manager.get_visible_info("aragorn")
        assert len(aragorn_info) == 1
        assert aragorn_info[0].content == "Valid 1"

    def test_remove_expired_no_expiration(self, manager):
        """Test cleanup with no expired info."""
        manager.add_private_info(
            pc_id="aragorn",
            content="No expiration",
            visibility=InfoVisibility.PRIVATE
        )

        count = manager.remove_expired_info()

        assert count == 0

    def test_remove_expired_cleans_empty_lists(self, manager):
        """Test cleanup removes empty PC info lists."""
        past = datetime.now() - timedelta(hours=1)

        manager.add_private_info(
            pc_id="aragorn",
            content="Expired",
            visibility=InfoVisibility.PRIVATE,
            expires=past
        )

        manager.remove_expired_info()

        # Info store should be empty for aragorn
        assert "aragorn" not in manager._info_store


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_manager(self, manager):
        """Test operations on empty manager."""
        assert manager.get_visible_info("aragorn") == []
        assert manager.get_pending_messages("aragorn") == []
        assert manager.check_knowledge("aragorn", "test") is None
        assert manager.check_secret_relevance("test") == []
        assert manager.remove_expired_info() == 0

    def test_multiple_info_same_pc(self, manager):
        """Test adding multiple info pieces to same PC."""
        info1 = manager.add_private_info(
            pc_id="aragorn",
            content="Info 1",
            visibility=InfoVisibility.PRIVATE
        )
        info2 = manager.add_private_info(
            pc_id="aragorn",
            content="Info 2",
            visibility=InfoVisibility.PRIVATE
        )

        visible = manager.get_visible_info("aragorn")
        assert len(visible) == 2
        assert info1 in visible
        assert info2 in visible

    def test_share_already_visible(self, manager):
        """Test sharing info to PC who already has access."""
        info = manager.add_private_info(
            pc_id="aragorn",
            content="Test",
            visibility=InfoVisibility.SUBSET,
            visible_to=["aragorn", "legolas"]
        )

        # Share to Legolas who already has access
        result = manager.share_info("aragorn", "legolas", info.info_id)

        assert result is True
        # Legolas should only appear once in visible_to
        assert info.visible_to.count("legolas") == 1

    def test_mark_message_read_twice(self, manager):
        """Test marking same message read multiple times."""
        msg = manager.send_private_message(
            content="Test",
            recipients=["aragorn"]
        )

        manager.mark_message_read(msg.message_id, "aragorn")
        manager.mark_message_read(msg.message_id, "aragorn")

        # Should only appear once in read_by
        assert msg.read_by.count("aragorn") == 1

    def test_reveal_roll_twice(self, manager):
        """Test revealing roll to same PC multiple times."""
        roll = manager.create_hidden_roll(
            pc_id="aragorn",
            roll_type="perception",
            result=15
        )

        manager.reveal_roll(roll.roll_id, ["legolas"])
        manager.reveal_roll(roll.roll_id, ["legolas"])

        # Should only appear once
        assert roll.revealed_to.count("legolas") == 1
