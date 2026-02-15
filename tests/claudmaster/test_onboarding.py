"""
Tests for Guided Onboarding Flow (#119).

Verifies that new users with no existing campaigns are automatically
guided through campaign creation, character suggestions, and first scene.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


from dm20_protocol.claudmaster.onboarding import (
    OnboardingState,
    OnboardingResult,
    detect_new_user,
    run_onboarding,
    generate_first_scene,
    _fallback_character_suggestions,
    _fallback_first_scene,
    DEFAULT_CAMPAIGN_NAME,
)
from dm20_protocol.claudmaster.tools.session_tools import (
    start_claudmaster_session,
    SessionState,
    _session_manager,
)


# ============================================================================
# OnboardingState Tests
# ============================================================================

class TestOnboardingState:
    """Tests for OnboardingState data model."""

    def test_default_values(self):
        """Default state starts at character_creation."""
        state = OnboardingState()
        assert state.step == "character_creation"
        assert state.campaign_created is False
        assert state.character_created is False
        assert state.first_scene_delivered is False

    def test_to_dict(self):
        """State serializes to a JSON-safe dict."""
        state = OnboardingState(
            step="first_scene",
            campaign_created=True,
            campaign_name="My Campaign",
        )
        d = state.to_dict()
        assert d["step"] == "first_scene"
        assert d["campaign_created"] is True
        assert d["campaign_name"] == "My Campaign"

    def test_from_dict_roundtrip(self):
        """from_dict restores state from to_dict output."""
        original = OnboardingState(
            step="complete",
            campaign_created=True,
            character_created=True,
            first_scene_delivered=True,
            campaign_name="Test",
        )
        restored = OnboardingState.from_dict(original.to_dict())
        assert restored.step == original.step
        assert restored.campaign_created == original.campaign_created
        assert restored.campaign_name == original.campaign_name

    def test_from_dict_handles_missing_keys(self):
        """from_dict uses defaults for missing keys."""
        state = OnboardingState.from_dict({})
        assert state.step == "character_creation"
        assert state.campaign_created is False


# ============================================================================
# detect_new_user Tests
# ============================================================================

class TestDetectNewUser:
    """Tests for detect_new_user()."""

    def test_returns_true_when_no_campaigns(self):
        """New user detected when list_campaigns() returns empty."""
        mock_storage = MagicMock()
        mock_storage.list_campaigns.return_value = []
        assert detect_new_user(mock_storage) is True

    def test_returns_false_when_campaigns_exist(self):
        """Not a new user when campaigns exist."""
        mock_storage = MagicMock()
        mock_storage.list_campaigns.return_value = ["Campaign A"]
        assert detect_new_user(mock_storage) is False

    def test_returns_false_when_storage_is_none(self):
        """Not a new user when storage is unavailable."""
        assert detect_new_user(None) is False


# ============================================================================
# run_onboarding Tests
# ============================================================================

class TestRunOnboarding:
    """Tests for run_onboarding()."""

    async def test_creates_campaign_with_provided_name(self):
        """Onboarding creates a campaign with the user's name."""
        mock_storage = MagicMock()
        mock_storage.create_campaign.return_value = MagicMock(name="Dragon Heist")

        result = await run_onboarding(
            storage=mock_storage,
            campaign_name="Dragon Heist",
        )

        mock_storage.create_campaign.assert_called_once()
        call_kwargs = mock_storage.create_campaign.call_args
        assert call_kwargs.kwargs["name"] == "Dragon Heist"
        assert result.campaign_name == "Dragon Heist"

    async def test_uses_default_name_when_empty(self):
        """Uses DEFAULT_CAMPAIGN_NAME when user provides empty string."""
        mock_storage = MagicMock()
        mock_storage.create_campaign.return_value = MagicMock()

        result = await run_onboarding(
            storage=mock_storage,
            campaign_name="  ",
        )

        call_kwargs = mock_storage.create_campaign.call_args
        assert call_kwargs.kwargs["name"] == DEFAULT_CAMPAIGN_NAME

    async def test_generates_character_suggestions_with_narrator(self):
        """Character suggestions are generated via Narrator when available."""
        mock_storage = MagicMock()
        mock_storage.create_campaign.return_value = MagicMock()

        mock_narrator = AsyncMock()
        mock_narrator.generate = AsyncMock(
            return_value="*Welcome, adventurer!* Choose your hero..."
        )

        result = await run_onboarding(
            storage=mock_storage,
            campaign_name="Test",
            narrator=mock_narrator,
        )

        assert "Welcome" in result.character_suggestions
        mock_narrator.generate.assert_called_once()

    async def test_falls_back_when_narrator_unavailable(self):
        """Uses fallback suggestions when no Narrator is provided."""
        mock_storage = MagicMock()
        mock_storage.create_campaign.return_value = MagicMock()

        result = await run_onboarding(
            storage=mock_storage,
            campaign_name="Test",
            narrator=None,
        )

        assert "Torvin Ironforge" in result.character_suggestions
        assert "Dwarf Fighter" in result.character_suggestions

    async def test_falls_back_when_narrator_fails(self):
        """Uses fallback when Narrator raises an exception."""
        mock_storage = MagicMock()
        mock_storage.create_campaign.return_value = MagicMock()

        mock_narrator = AsyncMock()
        mock_narrator.generate = AsyncMock(side_effect=Exception("LLM error"))

        result = await run_onboarding(
            storage=mock_storage,
            campaign_name="Test",
            narrator=mock_narrator,
        )

        assert "Torvin Ironforge" in result.character_suggestions

    async def test_onboarding_state_is_set(self):
        """Onboarding state reflects completed steps."""
        mock_storage = MagicMock()
        mock_storage.create_campaign.return_value = MagicMock()

        result = await run_onboarding(
            storage=mock_storage,
            campaign_name="Test",
        )

        assert result.onboarding_state.campaign_created is True
        assert result.onboarding_state.step == "character_creation"

    async def test_raises_on_campaign_creation_failure(self):
        """Propagates exception if campaign creation fails."""
        mock_storage = MagicMock()
        mock_storage.create_campaign.side_effect = IOError("Disk full")

        with pytest.raises(IOError, match="Disk full"):
            await run_onboarding(storage=mock_storage, campaign_name="Test")


# ============================================================================
# generate_first_scene Tests
# ============================================================================

class TestGenerateFirstScene:
    """Tests for generate_first_scene()."""

    async def test_generates_scene_with_character_info(self):
        """First scene includes character name and details."""
        mock_narrator = AsyncMock()
        mock_narrator.generate = AsyncMock(
            return_value="You, Torvin, sit at the bar of the Yawning Portal..."
        )

        scene = await generate_first_scene(
            narrator=mock_narrator,
            character_name="Torvin",
            character_class="Fighter",
            character_race="Dwarf",
        )

        assert "Torvin" in scene
        # Verify the prompt contains character info
        prompt = mock_narrator.generate.call_args.args[0]
        assert "Torvin" in prompt
        assert "Fighter" in prompt
        assert "Dwarf" in prompt

    async def test_uses_fallback_on_narrator_failure(self):
        """Returns static fallback scene on Narrator error."""
        mock_narrator = AsyncMock()
        mock_narrator.generate = AsyncMock(side_effect=Exception("Timeout"))

        scene = await generate_first_scene(
            narrator=mock_narrator,
            character_name="Lyra",
            character_class="Rogue",
            character_race="Elf",
        )

        assert "Lyra" in scene
        assert "Yawning Portal" in scene


# ============================================================================
# Fallback Tests
# ============================================================================

class TestFallbacks:
    """Tests for static fallback content."""

    def test_fallback_character_suggestions(self):
        """Fallback includes three distinct characters."""
        text = _fallback_character_suggestions()
        assert "Torvin Ironforge" in text
        assert "Lyra Nightwhisper" in text
        assert "Brother Marcus" in text
        assert "Fighter" in text
        assert "Rogue" in text
        assert "Cleric" in text

    def test_fallback_first_scene(self):
        """Fallback scene personalizes with character name."""
        scene = _fallback_first_scene("Grog")
        assert "Grog" in scene
        assert "Yawning Portal" in scene


# ============================================================================
# Integration: start_claudmaster_session + onboarding
# ============================================================================

class TestStartSessionOnboarding:
    """Tests for onboarding integration in start_claudmaster_session()."""

    async def test_triggers_onboarding_when_no_campaigns(self):
        """Onboarding is triggered when campaign not found and no campaigns exist."""
        import dm20_protocol.claudmaster.tools.session_tools as st

        mock_storage = MagicMock()
        mock_storage.list_campaigns.return_value = []  # No campaigns

        # After onboarding creates the campaign, load_campaign should work
        from dm20_protocol.models import Campaign, GameState, Character, CharacterClass, Race, AbilityScore
        game_state = GameState(
            campaign_name="My Adventure",
            current_location="Starting Town",
            in_combat=False,
            party_level=1,
        )
        mock_campaign = Campaign(
            id="test-id",
            name="My Adventure",
            description="A test onboarding campaign",
            game_state=game_state,
        )

        # First call raises (campaign not found), second call works (after creation)
        mock_storage.load_campaign.side_effect = [
            FileNotFoundError("Not found"),
            mock_campaign,
        ]
        mock_storage.create_campaign.return_value = mock_campaign
        mock_storage.get_claudmaster_config.side_effect = ValueError("No config")

        original_storage = st._storage
        st._storage = mock_storage

        try:
            result = await start_claudmaster_session(campaign_name="My Adventure")

            assert result.get("is_onboarding") is True
            assert result.get("onboarding") is not None
            assert result["onboarding"]["step"] == "character_creation"
            assert result["onboarding"]["character_suggestions"]  # Not empty
        finally:
            st._storage = original_storage
            # Clean up active sessions
            for sid in list(_session_manager._active_sessions.keys()):
                _session_manager.end_session(sid)

    async def test_returns_error_when_campaign_missing_but_others_exist(self):
        """Returns normal error when campaign not found but other campaigns exist."""
        import dm20_protocol.claudmaster.tools.session_tools as st

        mock_storage = MagicMock()
        mock_storage.list_campaigns.return_value = ["Other Campaign"]
        mock_storage.load_campaign.side_effect = FileNotFoundError("Not found")

        original_storage = st._storage
        st._storage = mock_storage

        try:
            result = await start_claudmaster_session(campaign_name="Nonexistent")

            assert result["status"] == "error"
            assert result.get("is_onboarding") is not True
        finally:
            st._storage = original_storage

    async def test_returning_users_skip_onboarding(self):
        """Users with existing campaigns skip onboarding entirely."""
        import dm20_protocol.claudmaster.tools.session_tools as st

        from dm20_protocol.models import Campaign
        mock_campaign = MagicMock(spec=Campaign)
        mock_campaign.id = "existing-id"
        mock_campaign.name = "Existing Campaign"
        mock_campaign.characters = {}
        mock_campaign.npcs = {}
        mock_campaign.quests = {}
        mock_campaign.game_state = MagicMock()
        mock_campaign.game_state.current_location = "Town"
        mock_campaign.game_state.in_combat = False

        mock_storage = MagicMock()
        mock_storage.list_campaigns.return_value = ["Existing Campaign"]
        mock_storage.load_campaign.return_value = mock_campaign
        mock_storage.get_claudmaster_config.side_effect = ValueError("No config")

        original_storage = st._storage
        st._storage = mock_storage

        try:
            result = await start_claudmaster_session(campaign_name="Existing Campaign")

            assert result["status"] == "active"
            assert result.get("is_onboarding", False) is False
        finally:
            st._storage = original_storage
            for sid in list(_session_manager._active_sessions.keys()):
                _session_manager.end_session(sid)
