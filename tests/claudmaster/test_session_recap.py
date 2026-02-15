"""
Tests for Session Recap Generator integration (#120).

Verifies that resuming a session generates an atmospheric "Previously on..."
recap from persisted session data, delivered through the Narrator agent.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


# Import models
try:
    from dm20_protocol.models import (
        Campaign, GameState, Character, CharacterClass, Race, AbilityScore, Quest,
    )
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False

from dm20_protocol.claudmaster.tools.session_tools import (
    SessionManager,
    SessionState,
    _session_manager,
)
from dm20_protocol.claudmaster.config import ClaudmasterConfig
from dm20_protocol.claudmaster.session import ClaudmasterSession


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_campaign():
    """Create a campaign with quests and characters for recap testing."""
    if MODELS_AVAILABLE:
        game_state = GameState(
            campaign_name="Recap Test Campaign",
            current_location="The Silver Tankard Tavern",
            in_combat=False,
            party_level=3,
        )

        character = Character(
            id="char1",
            name="Torvin Ironforge",
            character_class=CharacterClass(name="Fighter", level=3, hit_dice="1d10"),
            race=Race(name="Dwarf"),
            abilities={
                "strength": AbilityScore(score=16),
                "dexterity": AbilityScore(score=12),
                "constitution": AbilityScore(score=15),
                "intelligence": AbilityScore(score=10),
                "wisdom": AbilityScore(score=13),
                "charisma": AbilityScore(score=8),
            },
            hit_points_max=28,
            hit_points_current=22,
        )

        quest = Quest(
            id="quest1",
            title="The Missing Merchant",
            description="Find the merchant who disappeared on the road to Neverwinter",
            giver="Mayor Harbin",
            status="active",
        )

        campaign = Campaign(
            id="test-campaign-recap",
            name="Recap Test Campaign",
            description="A campaign for testing recap generation",
            game_state=game_state,
            characters={"char1": character},
            quests={"quest1": quest},
        )
        return campaign
    else:
        # Fallback mock
        class MockQuest:
            title = "The Missing Merchant"
            giver = "Mayor Harbin"
            status = "active"

        class MockGameState:
            campaign_name = "Recap Test Campaign"
            current_location = "The Silver Tankard Tavern"
            in_combat = False
            party_level = 3

        class MockCharacterClass:
            name = "Fighter"
            level = 3

        class MockCharacter:
            id = "char1"
            name = "Torvin Ironforge"
            character_class = MockCharacterClass()
            hit_points_current = 22
            hit_points_max = 28

        class MockCampaign:
            id = "test-campaign-recap"
            name = "Recap Test Campaign"
            description = "A campaign for testing recap generation"
            game_state = MockGameState()
            characters = {"char1": MockCharacter()}
            npcs = {}
            quests = {"quest1": MockQuest()}

        return MockCampaign()


@pytest.fixture
def mock_session_with_history():
    """Create a ClaudmasterSession with conversation history."""
    config = ClaudmasterConfig()
    session = ClaudmasterSession(
        session_id="recap-test-session",
        campaign_id="test-campaign-recap",
        config=config,
        started_at=datetime.now(),
        turn_count=5,
        conversation_history=[
            {"role": "user", "content": "I look around the tavern"},
            {"role": "assistant", "content": "The Silver Tankard is bustling with evening patrons. A bard plays softly in the corner."},
            {"role": "user", "content": "I approach the barkeep and ask about the missing merchant"},
            {"role": "assistant", "content": "The barkeep leans in close. 'Aye, old Sildar was last seen heading north on the Triboar Trail. Hasn't been back in three days.'"},
            {"role": "user", "content": "I gather my equipment and prepare to leave at dawn"},
            {"role": "assistant", "content": "You check your pack: rations, rope, and your trusty battleaxe. The night passes uneventfully at the inn."},
        ],
        metadata={},
    )
    return session


@pytest.fixture
def empty_session():
    """Create a ClaudmasterSession with no history."""
    config = ClaudmasterConfig()
    return ClaudmasterSession(
        session_id="empty-session",
        campaign_id="test-campaign-recap",
        config=config,
        started_at=datetime.now(),
        turn_count=0,
        conversation_history=[],
        metadata={},
    )


@pytest.fixture
def session_manager():
    """Create a fresh SessionManager for each test."""
    return SessionManager()


# ============================================================================
# _extract_recap_data Tests
# ============================================================================

class TestExtractRecapData:
    """Tests for SessionManager._extract_recap_data()."""

    def test_extracts_location(self, mock_campaign, mock_session_with_history):
        """Location is extracted from campaign game state."""
        data = SessionManager._extract_recap_data(mock_campaign, mock_session_with_history)
        assert data["location"] == "The Silver Tankard Tavern"

    def test_extracts_active_quests(self, mock_campaign, mock_session_with_history):
        """Active quests are listed with title and giver."""
        data = SessionManager._extract_recap_data(mock_campaign, mock_session_with_history)
        assert "The Missing Merchant" in data["active_quests"]
        assert "Mayor Harbin" in data["active_quests"]

    def test_extracts_recent_events(self, mock_campaign, mock_session_with_history):
        """Recent assistant messages are extracted as events."""
        data = SessionManager._extract_recap_data(mock_campaign, mock_session_with_history)
        assert "Silver Tankard" in data["recent_events"]
        assert "battleaxe" in data["recent_events"]

    def test_extracts_party_status(self, mock_campaign, mock_session_with_history):
        """Party status includes character name, class, level, and HP."""
        data = SessionManager._extract_recap_data(mock_campaign, mock_session_with_history)
        assert "Torvin Ironforge" in data["party_status"]
        assert "Fighter" in data["party_status"]
        assert "L3" in data["party_status"]
        assert "22/28" in data["party_status"]

    def test_handles_no_quests(self, mock_campaign, mock_session_with_history):
        """Returns 'None active' when campaign has no active quests."""
        mock_campaign.quests = {}
        data = SessionManager._extract_recap_data(mock_campaign, mock_session_with_history)
        assert data["active_quests"] == "None active"

    def test_handles_empty_history(self, mock_campaign, empty_session):
        """Returns fallback text when no conversation history."""
        data = SessionManager._extract_recap_data(mock_campaign, empty_session)
        assert "No recent events" in data["recent_events"]

    def test_handles_missing_location(self, mock_campaign, mock_session_with_history):
        """Returns fallback when location is None."""
        mock_campaign.game_state.current_location = None
        data = SessionManager._extract_recap_data(mock_campaign, mock_session_with_history)
        assert data["location"] == "an unknown location"

    def test_truncates_long_events(self, mock_campaign, mock_session_with_history):
        """Long assistant messages are truncated to 150 chars."""
        long_msg = "A" * 200
        mock_session_with_history.conversation_history.append(
            {"role": "assistant", "content": long_msg}
        )
        data = SessionManager._extract_recap_data(mock_campaign, mock_session_with_history)
        # Each event line starts with "- " so check for truncation marker
        assert "..." in data["recent_events"]

    def test_limits_to_5_events(self, mock_campaign, mock_session_with_history):
        """Only the last 5 assistant messages are included."""
        for i in range(10):
            mock_session_with_history.conversation_history.append(
                {"role": "assistant", "content": f"Event {i}"}
            )
        data = SessionManager._extract_recap_data(mock_campaign, mock_session_with_history)
        # Count bullet points
        event_count = data["recent_events"].count("\n- ") + 1
        assert event_count <= 5


# ============================================================================
# _generate_session_recap Tests
# ============================================================================

class TestGenerateSessionRecap:
    """Tests for SessionManager._generate_session_recap()."""

    async def test_generates_recap_with_narrator(
        self, session_manager, mock_campaign, mock_session_with_history
    ):
        """Recap is generated via Narrator agent when available."""
        mock_narrator = MagicMock()
        mock_narrator.generate_recap = AsyncMock(
            return_value="*Previously on your adventure...* You found yourself at the Silver Tankard."
        )

        mock_orchestrator = MagicMock()
        mock_orchestrator.agents = {"narrator": mock_narrator}
        mock_orchestrator.campaign = mock_campaign

        recap = await session_manager._generate_session_recap(
            orchestrator=mock_orchestrator,
            session=mock_session_with_history,
            campaign=mock_campaign,
        )

        assert recap is not None
        assert "Silver Tankard" in recap
        mock_narrator.generate_recap.assert_called_once()

        # Verify the correct data was passed
        call_kwargs = mock_narrator.generate_recap.call_args.kwargs
        assert "The Silver Tankard Tavern" in call_kwargs["location"]
        assert "The Missing Merchant" in call_kwargs["active_quests"]

    async def test_skips_recap_when_no_history(
        self, session_manager, mock_campaign, empty_session
    ):
        """Recap is skipped when session has no conversation history."""
        mock_orchestrator = MagicMock()
        mock_orchestrator.campaign = mock_campaign

        recap = await session_manager._generate_session_recap(
            orchestrator=mock_orchestrator,
            session=empty_session,
            campaign=mock_campaign,
        )

        assert recap is None

    async def test_skips_recap_when_narrator_missing(
        self, session_manager, mock_campaign, mock_session_with_history
    ):
        """Recap is None when Narrator agent is not registered."""
        mock_orchestrator = MagicMock()
        mock_orchestrator.agents = {}  # No narrator
        mock_orchestrator.campaign = mock_campaign

        recap = await session_manager._generate_session_recap(
            orchestrator=mock_orchestrator,
            session=mock_session_with_history,
            campaign=mock_campaign,
        )

        assert recap is None

    async def test_handles_narrator_error_gracefully(
        self, session_manager, mock_campaign, mock_session_with_history
    ):
        """Recap returns None if Narrator raises an exception."""
        mock_narrator = MagicMock()
        mock_narrator.generate_recap = AsyncMock(side_effect=Exception("LLM timeout"))

        mock_orchestrator = MagicMock()
        mock_orchestrator.agents = {"narrator": mock_narrator}
        mock_orchestrator.campaign = mock_campaign

        recap = await session_manager._generate_session_recap(
            orchestrator=mock_orchestrator,
            session=mock_session_with_history,
            campaign=mock_campaign,
        )

        assert recap is None


# ============================================================================
# SessionState.recap Field Tests
# ============================================================================

class TestSessionStateRecapField:
    """Tests for the recap field on SessionState model."""

    def test_recap_defaults_to_none(self):
        """SessionState.recap is None by default."""
        from dm20_protocol.claudmaster.tools.session_tools import (
            CampaignSummary, ModuleSummary, GameStateSummary,
        )
        state = SessionState(
            session_id="test",
            status="active",
            campaign_info=CampaignSummary(
                campaign_id="c1", campaign_name="Test", character_count=0, npc_count=0
            ),
            module_info=ModuleSummary(is_loaded=False),
            game_state=GameStateSummary(
                current_location="Town", in_combat=False, turn_count=0
            ),
            party_info=[],
            last_events=[],
            context_budget=4096,
        )
        assert state.recap is None

    def test_recap_included_in_model_dump(self):
        """Recap appears in model_dump() output when set."""
        from dm20_protocol.claudmaster.tools.session_tools import (
            CampaignSummary, ModuleSummary, GameStateSummary,
        )
        state = SessionState(
            session_id="test",
            status="active",
            campaign_info=CampaignSummary(
                campaign_id="c1", campaign_name="Test", character_count=0, npc_count=0
            ),
            module_info=ModuleSummary(is_loaded=False),
            game_state=GameStateSummary(
                current_location="Town", in_combat=False, turn_count=0
            ),
            party_info=[],
            last_events=[],
            context_budget=4096,
            recap="Previously on your adventure...",
        )
        dump = state.model_dump()
        assert dump["recap"] == "Previously on your adventure..."


# ============================================================================
# NarratorAgent.generate_recap Tests
# ============================================================================

class TestNarratorGenerateRecap:
    """Tests for NarratorAgent.generate_recap()."""

    async def test_narrator_generate_recap_calls_llm(self):
        """generate_recap() formats the prompt and calls the LLM."""
        from dm20_protocol.claudmaster.agents.narrator import NarratorAgent

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value="Previously on your adventure...")

        narrator = NarratorAgent(llm=mock_llm)

        result = await narrator.generate_recap(
            location="The Silver Tankard",
            active_quests="- The Missing Merchant",
            recent_events="- You asked the barkeep about the merchant",
            party_status="Torvin Ironforge (L3 Fighter, HP 22/28)",
        )

        assert result == "Previously on your adventure..."
        mock_llm.generate.assert_called_once()

        # Verify the prompt contains the facts
        prompt = mock_llm.generate.call_args.args[0]
        assert "The Silver Tankard" in prompt
        assert "The Missing Merchant" in prompt
        assert "barkeep" in prompt
        assert "Torvin Ironforge" in prompt

    async def test_narrator_generate_recap_handles_empty_data(self):
        """generate_recap() uses fallback text for missing data."""
        from dm20_protocol.claudmaster.agents.narrator import NarratorAgent

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value="The adventure continues...")

        narrator = NarratorAgent(llm=mock_llm)

        result = await narrator.generate_recap(
            location="",
            active_quests="",
            recent_events="",
            party_status="",
        )

        prompt = mock_llm.generate.call_args.args[0]
        assert "Unknown" in prompt
        assert "None active" in prompt
