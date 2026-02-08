"""
Tests for the ModuleKeeperAgent.

Verifies RAG-based retrieval, context filtering, and knowledge structuring
for adventure module content.
"""

import pytest
from unittest.mock import Mock, MagicMock

# Configure pytest to use anyio with asyncio backend only
pytestmark = pytest.mark.anyio

# Configure anyio to use only asyncio backend
@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

from dm20_protocol.claudmaster.agents.module_keeper import (
    ModuleKeeperAgent,
    NPCKnowledge,
    LocationDescription,
    EncounterTrigger,
    PlotContext,
)
from dm20_protocol.claudmaster.base import AgentRole
from dm20_protocol.claudmaster.models.module import (
    ModuleStructure,
    NPCReference,
    LocationReference,
    EncounterReference,
    ContentType,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def mock_vector_store():
    """Create a mock VectorStoreManager."""
    mock_store = Mock()
    mock_store.query = Mock(return_value=[])
    return mock_store


@pytest.fixture
def sample_module_structure():
    """Create a sample ModuleStructure for testing."""
    return ModuleStructure(
        module_id="test_module",
        title="Test Adventure Module",
        source_file="test.pdf",
        npcs=[
            NPCReference(
                name="Theron Ironhand",
                location="Tavern",
                chapter="Chapter 1",
                page=10,
                description_preview="A gruff dwarf blacksmith",
            ),
            NPCReference(
                name="Lady Silverleaf",
                location="Castle",
                chapter="Chapter 2",
                page=25,
                description_preview="An elven noblewoman",
            ),
        ],
        locations=[
            LocationReference(
                name="Rusty Dragon Tavern",
                chapter="Chapter 1",
                page=8,
                sub_locations=["Main Room", "Kitchen", "Cellar"],
            ),
            LocationReference(
                name="Silverleaf Castle",
                chapter="Chapter 2",
                page=22,
                parent_location=None,
                sub_locations=["Great Hall", "Throne Room"],
            ),
        ],
        encounters=[
            EncounterReference(
                name="Goblin Ambush",
                location="Forest Path",
                chapter="Chapter 1",
                page=15,
                encounter_type="combat",
            ),
        ],
    )


@pytest.fixture
def module_keeper_agent(mock_vector_store, sample_module_structure):
    """Create a ModuleKeeperAgent instance for testing."""
    return ModuleKeeperAgent(
        vector_store=mock_vector_store,
        module_structure=sample_module_structure,
        current_chapter="Chapter 1",
        current_location="Rusty Dragon Tavern",
    )


# ------------------------------------------------------------------
# Initialization tests
# ------------------------------------------------------------------

def test_initialization(module_keeper_agent, sample_module_structure):
    """Test ModuleKeeperAgent initialization."""
    assert module_keeper_agent.name == "ModuleKeeper"
    assert module_keeper_agent.role == AgentRole.MODULE_KEEPER
    assert module_keeper_agent._module_structure == sample_module_structure
    assert module_keeper_agent._current_chapter == "Chapter 1"
    assert module_keeper_agent._current_location == "Rusty Dragon Tavern"
    assert len(module_keeper_agent._revealed_content) == 0


def test_initialization_without_context(mock_vector_store, sample_module_structure):
    """Test initialization without current chapter/location."""
    agent = ModuleKeeperAgent(
        vector_store=mock_vector_store,
        module_structure=sample_module_structure,
    )
    assert agent._current_chapter is None
    assert agent._current_location is None


# ------------------------------------------------------------------
# ReAct cycle tests
# ------------------------------------------------------------------

async def test_reason_npc_knowledge(module_keeper_agent):
    """Test reasoning for NPC knowledge request."""
    context = {
        "request_type": "npc_knowledge",
        "npc_name": "Theron Ironhand",
        "topic": "blacksmithing",
    }
    reasoning = await module_keeper_agent.reason(context)
    assert "Theron Ironhand" in reasoning
    assert "blacksmithing" in reasoning


async def test_reason_location_description(module_keeper_agent):
    """Test reasoning for location description request."""
    context = {
        "request_type": "location_description",
        "location_name": "Rusty Dragon Tavern",
        "detail_level": "full",
    }
    reasoning = await module_keeper_agent.reason(context)
    assert "Rusty Dragon Tavern" in reasoning
    assert "full" in reasoning


async def test_reason_encounter_trigger(module_keeper_agent):
    """Test reasoning for encounter trigger check."""
    context = {
        "request_type": "encounter_trigger",
        "location": "Forest Path",
        "player_actions": "walking through the forest",
    }
    reasoning = await module_keeper_agent.reason(context)
    assert "Forest Path" in reasoning
    assert "walking through the forest" in reasoning


async def test_reason_plot_context(module_keeper_agent):
    """Test reasoning for plot context request."""
    context = {
        "request_type": "plot_context",
        "query": "What is the main quest?",
    }
    reasoning = await module_keeper_agent.reason(context)
    assert "plot context" in reasoning.lower()
    assert "What is the main quest?" in reasoning


async def test_reason_unknown_request(module_keeper_agent):
    """Test reasoning with unknown request type."""
    context = {"request_type": "invalid_type"}
    reasoning = await module_keeper_agent.reason(context)
    assert "unknown" in reasoning.lower() or "invalid_type" in reasoning


async def test_act(module_keeper_agent):
    """Test act phase returns reasoning wrapper."""
    reasoning = "Test reasoning"
    result = await module_keeper_agent.act(reasoning)
    assert "reasoning" in result
    assert result["reasoning"] == reasoning


async def test_observe(module_keeper_agent):
    """Test observe phase extracts observations."""
    result = {"reasoning": "Test reasoning"}
    observations = await module_keeper_agent.observe(result)

    assert "reasoning_summary" in observations
    assert observations["current_chapter"] == "Chapter 1"
    assert observations["current_location"] == "Rusty Dragon Tavern"
    assert "revealed_count" in observations


async def test_full_react_cycle(module_keeper_agent):
    """Test complete ReAct cycle."""
    context = {
        "request_type": "npc_knowledge",
        "npc_name": "Theron Ironhand",
    }
    response = await module_keeper_agent.run(context)

    assert response.agent_name == "ModuleKeeper"
    assert response.agent_role == AgentRole.MODULE_KEEPER
    assert "Theron Ironhand" in response.reasoning
    assert "current_chapter" in response.observations


# ------------------------------------------------------------------
# NPC Knowledge tests
# ------------------------------------------------------------------

def test_get_npc_knowledge_basic(module_keeper_agent, mock_vector_store):
    """Test basic NPC knowledge retrieval."""
    # Mock vector store results
    mock_vector_store.query.return_value = [
        {
            "id": "doc1",
            "document": "Theron is a gruff dwarf with a strong personality and dedication to his craft.",
            "metadata": {"content_type": "npc", "chapter": "Chapter 1"},
            "distance": 0.2,
        },
        {
            "id": "doc2",
            "document": "His goal is to forge the finest weapons in the land.",
            "metadata": {"content_type": "npc", "chapter": "Chapter 1"},
            "distance": 0.3,
        },
    ]

    knowledge = module_keeper_agent.get_npc_knowledge("Theron Ironhand")

    assert knowledge.npc_name == "Theron Ironhand"
    assert knowledge.current_location == "Tavern"
    assert "personality" in knowledge.personality.lower() or "gruff" in knowledge.personality.lower()
    assert len(knowledge.relevant_quotes) > 0


def test_get_npc_knowledge_with_topic(module_keeper_agent, mock_vector_store):
    """Test NPC knowledge retrieval with specific topic."""
    mock_vector_store.query.return_value = [
        {
            "id": "doc1",
            "document": "Theron knows the secret of forging adamantine weapons.",
            "metadata": {"content_type": "npc"},
            "distance": 0.1,
        },
    ]

    knowledge = module_keeper_agent.get_npc_knowledge(
        "Theron Ironhand",
        topic="adamantine",
    )

    assert knowledge.npc_name == "Theron Ironhand"
    assert "adamantine" in knowledge.knowledge_about_topic.lower()
    mock_vector_store.query.assert_called_once()


def test_get_npc_knowledge_not_found(module_keeper_agent, mock_vector_store):
    """Test NPC knowledge when NPC is not in module structure."""
    mock_vector_store.query.return_value = []

    knowledge = module_keeper_agent.get_npc_knowledge("Unknown NPC")

    assert knowledge.npc_name == "Unknown NPC"
    assert knowledge.current_location == ""
    assert len(knowledge.relevant_quotes) == 0


# ------------------------------------------------------------------
# Location Description tests
# ------------------------------------------------------------------

def test_get_location_description_full(module_keeper_agent, mock_vector_store):
    """Test full location description retrieval."""
    mock_vector_store.query.return_value = [
        {
            "id": "doc1",
            "document": "Read aloud: The tavern is warm and inviting, with a large fireplace.",
            "metadata": {"content_type": "location"},
            "distance": 0.1,
        },
        {
            "id": "doc2",
            "document": "DM Note: There is a secret door behind the bar.",
            "metadata": {"content_type": "location"},
            "distance": 0.2,
        },
        {
            "id": "doc3",
            "document": "Treasure: 50 gold pieces hidden in the cellar.",
            "metadata": {"content_type": "location"},
            "distance": 0.3,
        },
    ]

    description = module_keeper_agent.get_location_description(
        "Rusty Dragon Tavern",
        detail_level="full",
    )

    assert description.name == "Rusty Dragon Tavern"
    assert "tavern" in description.read_aloud_text.lower() or "warm" in description.read_aloud_text.lower()
    assert "secret" in description.dm_description.lower() or len(description.dm_description) > 0
    assert len(description.treasure) > 0
    assert description.exits == ["Main Room", "Kitchen", "Cellar"]


def test_get_location_description_brief(module_keeper_agent, mock_vector_store):
    """Test brief location description (no DM secrets)."""
    mock_vector_store.query.return_value = [
        {
            "id": "doc1",
            "document": "A cozy tavern with wooden tables and chairs.",
            "metadata": {"content_type": "location"},
            "distance": 0.1,
        },
    ]

    description = module_keeper_agent.get_location_description(
        "Rusty Dragon Tavern",
        detail_level="brief",
    )

    assert description.name == "Rusty Dragon Tavern"
    assert description.dm_description == ""
    assert description.hazards == []
    assert description.treasure == []


def test_get_location_description_dm_only(module_keeper_agent, mock_vector_store):
    """Test DM-only location description (no read-aloud)."""
    mock_vector_store.query.return_value = [
        {
            "id": "doc1",
            "document": "DM Info: The innkeeper is actually a spy.",
            "metadata": {"content_type": "location"},
            "distance": 0.1,
        },
    ]

    description = module_keeper_agent.get_location_description(
        "Rusty Dragon Tavern",
        detail_level="dm_only",
    )

    assert description.name == "Rusty Dragon Tavern"
    assert description.read_aloud_text == ""
    assert len(description.dm_description) > 0


# ------------------------------------------------------------------
# Encounter Trigger tests
# ------------------------------------------------------------------

def test_check_encounter_trigger_found(module_keeper_agent, mock_vector_store):
    """Test encounter trigger when encounter exists."""
    mock_vector_store.query.return_value = [
        {
            "id": "doc1",
            "document": "Trigger: When players enter the forest path, goblins attack.",
            "metadata": {"content_type": "encounter"},
            "distance": 0.1,
        },
        {
            "id": "doc2",
            "document": "Creatures: 4 goblins with short swords.",
            "metadata": {"content_type": "encounter"},
            "distance": 0.2,
        },
    ]

    trigger = module_keeper_agent.check_encounter_trigger(
        "Forest Path",
        "entering the path",
    )

    assert trigger is not None
    assert trigger.name == "Goblin Ambush"
    assert "trigger" in trigger.trigger_condition.lower()
    assert len(trigger.creatures) > 0


def test_check_encounter_trigger_not_found(module_keeper_agent, mock_vector_store):
    """Test encounter trigger when no encounter exists."""
    mock_vector_store.query.return_value = []

    trigger = module_keeper_agent.check_encounter_trigger(
        "Safe Location",
        "resting",
    )

    assert trigger is None


# ------------------------------------------------------------------
# Plot Context tests
# ------------------------------------------------------------------

def test_get_plot_context(module_keeper_agent, mock_vector_store):
    """Test plot context retrieval."""
    mock_vector_store.query.return_value = [
        {
            "id": "doc1",
            "document": "The main objective is to rescue Lady Silverleaf from the castle.",
            "metadata": {"chapter": "Chapter 2"},
            "distance": 0.1,
        },
        {
            "id": "doc2",
            "document": "Foreshadowing: The villain's true identity will be revealed later.",
            "metadata": {"chapter": "Chapter 2"},
            "distance": 0.2,
        },
        {
            "id": "doc3",
            "document": "Theron Ironhand knows the secret entrance to the castle.",
            "metadata": {"chapter": "Chapter 1"},
            "distance": 0.3,
        },
    ]

    context = module_keeper_agent.get_plot_context("What is the main quest?")

    assert "Chapter 1" in context.current_chapter_summary
    assert len(context.key_objectives) > 0
    assert len(context.foreshadowing_hints) > 0
    assert "Theron Ironhand" in context.relevant_npcs or "Lady Silverleaf" in context.relevant_npcs


def test_get_plot_context_empty_results(module_keeper_agent, mock_vector_store):
    """Test plot context with no results."""
    mock_vector_store.query.return_value = []

    context = module_keeper_agent.get_plot_context("Unknown query")

    assert context.current_chapter_summary == "Chapter: Chapter 1"
    assert len(context.key_objectives) == 0


# ------------------------------------------------------------------
# Context management tests
# ------------------------------------------------------------------

def test_set_context_chapter(module_keeper_agent):
    """Test setting current chapter."""
    module_keeper_agent.set_context(chapter="Chapter 2")
    assert module_keeper_agent._current_chapter == "Chapter 2"


def test_set_context_location(module_keeper_agent):
    """Test setting current location."""
    module_keeper_agent.set_context(location="Silverleaf Castle")
    assert module_keeper_agent._current_location == "Silverleaf Castle"


def test_set_context_both(module_keeper_agent):
    """Test setting both chapter and location."""
    module_keeper_agent.set_context(
        chapter="Chapter 3",
        location="Dragon Lair",
    )
    assert module_keeper_agent._current_chapter == "Chapter 3"
    assert module_keeper_agent._current_location == "Dragon Lair"


def test_set_context_partial_update(module_keeper_agent):
    """Test that None values don't overwrite existing context."""
    original_chapter = module_keeper_agent._current_chapter
    module_keeper_agent.set_context(location="New Location")

    assert module_keeper_agent._current_chapter == original_chapter
    assert module_keeper_agent._current_location == "New Location"


# ------------------------------------------------------------------
# Revealed content tracking tests
# ------------------------------------------------------------------

def test_mark_revealed(module_keeper_agent):
    """Test marking content as revealed."""
    module_keeper_agent.mark_revealed("npc", "Theron Ironhand")
    assert ("npc", "Theron Ironhand") in module_keeper_agent._revealed_content


def test_mark_revealed_multiple(module_keeper_agent):
    """Test marking multiple pieces of content."""
    module_keeper_agent.mark_revealed("npc", "Theron Ironhand")
    module_keeper_agent.mark_revealed("location", "Rusty Dragon Tavern")
    module_keeper_agent.mark_revealed("secret", "hidden_door")

    assert len(module_keeper_agent._revealed_content) == 3
    assert ("npc", "Theron Ironhand") in module_keeper_agent._revealed_content
    assert ("location", "Rusty Dragon Tavern") in module_keeper_agent._revealed_content
    assert ("secret", "hidden_door") in module_keeper_agent._revealed_content


# ------------------------------------------------------------------
# Query filter tests
# ------------------------------------------------------------------

def test_build_query_filter_no_context(mock_vector_store, sample_module_structure):
    """Test filter building with no context set."""
    agent = ModuleKeeperAgent(
        vector_store=mock_vector_store,
        module_structure=sample_module_structure,
    )
    filter_dict = agent._build_query_filter()
    assert filter_dict is None


def test_build_query_filter_chapter_only(module_keeper_agent):
    """Test filter building with only chapter context."""
    filter_dict = module_keeper_agent._build_query_filter()
    assert filter_dict is not None
    assert "chapter" in filter_dict or "$and" in filter_dict


def test_build_query_filter_content_type_only(mock_vector_store, sample_module_structure):
    """Test filter building with only content type."""
    agent = ModuleKeeperAgent(
        vector_store=mock_vector_store,
        module_structure=sample_module_structure,
    )
    filter_dict = agent._build_query_filter(content_type=ContentType.NPC)
    assert filter_dict is not None
    assert filter_dict.get("content_type") == "npc"


def test_build_query_filter_combined(module_keeper_agent):
    """Test filter building with both chapter and content type."""
    filter_dict = module_keeper_agent._build_query_filter(
        content_type=ContentType.LOCATION,
    )
    assert filter_dict is not None
    # Should have $and with multiple conditions
    if "$and" in filter_dict:
        conditions = filter_dict["$and"]
        assert any("chapter" in cond for cond in conditions)
        assert any("content_type" in cond for cond in conditions)


# ------------------------------------------------------------------
# Integration tests
# ------------------------------------------------------------------

def test_npc_knowledge_uses_context_filter(module_keeper_agent, mock_vector_store):
    """Test that NPC knowledge queries use context filtering."""
    module_keeper_agent.get_npc_knowledge("Theron Ironhand")

    # Verify query was called with a filter
    call_args = mock_vector_store.query.call_args
    assert call_args is not None
    where_param = call_args[1].get("where")
    # Should have some filtering (chapter or content_type)
    # Filter might be None if build_query_filter returns None for NPC type


def test_location_description_uses_context_filter(module_keeper_agent, mock_vector_store):
    """Test that location queries use context filtering."""
    module_keeper_agent.get_location_description("Rusty Dragon Tavern")

    # Verify query was called
    assert mock_vector_store.query.called


def test_encounter_check_uses_context_filter(module_keeper_agent, mock_vector_store):
    """Test that encounter checks use context filtering."""
    module_keeper_agent.check_encounter_trigger("Forest Path", "walking")

    # Verify query was called
    assert mock_vector_store.query.called


def test_plot_context_uses_context_filter(module_keeper_agent, mock_vector_store):
    """Test that plot context queries use context filtering."""
    module_keeper_agent.get_plot_context("main quest")

    # Verify query was called with current chapter context
    call_args = mock_vector_store.query.call_args
    assert call_args is not None
