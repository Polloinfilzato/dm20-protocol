"""
Tests for Starter Adventure Content (#123).

Verifies the built-in tutorial adventure: The Yawning Portal location,
Durnan and Viari NPCs, starter quest, and goblin encounter.
"""

import pytest

from dm20_protocol.models import Campaign, GameState
from dm20_protocol.claudmaster.starter_adventure import (
    STARTER_LOCATION,
    STARTER_NPC_DURNAN,
    STARTER_NPC_VIARI,
    STARTER_QUEST,
    STARTER_ENCOUNTER,
    populate_campaign_with_starter_content,
)


# ============================================================================
# Content Quality Tests
# ============================================================================

class TestStarterLocation:
    """Tests for The Yawning Portal location."""

    def test_location_has_atmospheric_description(self):
        """Location description is vivid with sensory details."""
        assert len(STARTER_LOCATION.description) > 100
        # Sensory details
        assert "lantern" in STARTER_LOCATION.description.lower()
        assert "hearth" in STARTER_LOCATION.description.lower()
        assert "well" in STARTER_LOCATION.description.lower()

    def test_location_has_notable_features(self):
        """Location has interactive elements for exploration."""
        assert len(STARTER_LOCATION.notable_features) >= 2
        features_text = " ".join(STARTER_LOCATION.notable_features).lower()
        assert "well" in features_text or "undermountain" in features_text
        assert "notice board" in features_text or "map" in features_text

    def test_location_references_npcs(self):
        """Location lists its NPCs."""
        assert "Durnan" in STARTER_LOCATION.npcs
        assert "Viari" in STARTER_LOCATION.npcs

    def test_location_has_connections(self):
        """Location connects to other areas."""
        assert len(STARTER_LOCATION.connections) >= 1


class TestStarterNPCs:
    """Tests for Durnan and Viari NPCs."""

    def test_durnan_is_quest_giver(self):
        """Durnan is friendly and gives the starter quest."""
        assert STARTER_NPC_DURNAN.attitude == "friendly"
        assert "quest" in STARTER_NPC_DURNAN.notes.lower() or "goblin" in STARTER_NPC_DURNAN.bio.lower()

    def test_durnan_has_distinct_personality(self):
        """Durnan has description, bio, occupation."""
        assert STARTER_NPC_DURNAN.description
        assert STARTER_NPC_DURNAN.bio
        assert STARTER_NPC_DURNAN.occupation
        assert len(STARTER_NPC_DURNAN.description) > 50

    def test_viari_is_combat_trigger(self):
        """Viari provides the map / combat trigger."""
        assert "map" in STARTER_NPC_VIARI.bio.lower()
        assert STARTER_NPC_VIARI.attitude == "neutral"

    def test_viari_has_distinct_personality(self):
        """Viari has description, bio, occupation different from Durnan."""
        assert STARTER_NPC_VIARI.description
        assert STARTER_NPC_VIARI.bio
        assert STARTER_NPC_VIARI.race != STARTER_NPC_DURNAN.race

    def test_npcs_know_each_other(self):
        """Both NPCs have relationship entries."""
        assert "Viari" in STARTER_NPC_DURNAN.relationships
        assert "Durnan" in STARTER_NPC_VIARI.relationships


class TestStarterQuest:
    """Tests for the starter quest."""

    def test_quest_is_active(self):
        """Quest starts in active status."""
        assert STARTER_QUEST.status == "active"

    def test_quest_has_objectives(self):
        """Quest has clear objectives."""
        assert len(STARTER_QUEST.objectives) >= 3

    def test_quest_has_giver(self):
        """Quest is given by Durnan."""
        assert STARTER_QUEST.giver == "Durnan"

    def test_quest_has_reward(self):
        """Quest offers a reward."""
        assert STARTER_QUEST.reward


class TestStarterEncounter:
    """Tests for the goblin ambush encounter."""

    def test_encounter_is_easy(self):
        """Tutorial encounter is easy difficulty."""
        assert STARTER_ENCOUNTER.difficulty == "easy"

    def test_encounter_has_enemies(self):
        """Encounter has defined enemies."""
        assert len(STARTER_ENCOUNTER.enemies) >= 1
        assert any("goblin" in e.lower() for e in STARTER_ENCOUNTER.enemies)

    def test_encounter_allows_non_combat_resolution(self):
        """Encounter notes mention alternative resolutions."""
        notes = STARTER_ENCOUNTER.notes.lower()
        assert "stealth" in notes or "diplomacy" in notes or "intimidation" in notes


# ============================================================================
# populate_campaign_with_starter_content Tests
# ============================================================================

class TestPopulateCampaign:
    """Tests for populate_campaign_with_starter_content()."""

    @pytest.fixture
    def empty_campaign(self):
        """Create an empty campaign to populate."""
        game_state = GameState(
            campaign_name="Test",
            current_location=None,
            in_combat=False,
            party_level=1,
        )
        return Campaign(
            id="test-populate",
            name="Test Campaign",
            description="Empty campaign for testing",
            game_state=game_state,
        )

    def test_adds_location(self, empty_campaign):
        """Populating adds the Yawning Portal location."""
        populate_campaign_with_starter_content(empty_campaign)
        assert STARTER_LOCATION.id in empty_campaign.locations
        assert empty_campaign.locations[STARTER_LOCATION.id].name == "The Yawning Portal"

    def test_adds_npcs(self, empty_campaign):
        """Populating adds both NPCs."""
        populate_campaign_with_starter_content(empty_campaign)
        assert STARTER_NPC_DURNAN.id in empty_campaign.npcs
        assert STARTER_NPC_VIARI.id in empty_campaign.npcs

    def test_adds_quest(self, empty_campaign):
        """Populating adds the starter quest."""
        populate_campaign_with_starter_content(empty_campaign)
        assert STARTER_QUEST.id in empty_campaign.quests
        assert empty_campaign.quests[STARTER_QUEST.id].title == "Trouble on the Triboar Trail"

    def test_adds_encounter(self, empty_campaign):
        """Populating adds the goblin encounter."""
        populate_campaign_with_starter_content(empty_campaign)
        assert STARTER_ENCOUNTER.id in empty_campaign.encounters

    def test_sets_starting_location(self, empty_campaign):
        """Populating sets the game state location to The Yawning Portal."""
        assert empty_campaign.game_state.current_location is None
        populate_campaign_with_starter_content(empty_campaign)
        assert empty_campaign.game_state.current_location == "The Yawning Portal"

    def test_is_idempotent(self, empty_campaign):
        """Calling populate twice doesn't create duplicates."""
        populate_campaign_with_starter_content(empty_campaign)
        populate_campaign_with_starter_content(empty_campaign)
        assert len(empty_campaign.locations) == 1
        assert len(empty_campaign.npcs) == 2

    def test_gameplay_flow_elements(self, empty_campaign):
        """All three gameplay elements are present: exploration, dialogue, combat."""
        populate_campaign_with_starter_content(empty_campaign)

        # Exploration: location with notable features
        loc = empty_campaign.locations[STARTER_LOCATION.id]
        assert len(loc.notable_features) >= 2

        # Dialogue: NPCs with bios for dialogue generation
        durnan = empty_campaign.npcs[STARTER_NPC_DURNAN.id]
        assert durnan.bio is not None

        # Combat: encounter with enemies
        encounter = empty_campaign.encounters[STARTER_ENCOUNTER.id]
        assert len(encounter.enemies) >= 1
