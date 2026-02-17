"""
Tests for the party knowledge tracking module.

Tests PartyKnowledge, AcquisitionMethod, KnowledgeRecord, and the
bidirectional NPC knowledge integration for tracking what the adventuring
party collectively knows about the game world.
"""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path

from dm20_protocol.claudmaster.consistency.fact_database import FactDatabase
from dm20_protocol.claudmaster.consistency.models import (
    Fact,
    FactCategory,
    KnowledgeSource,
)
from dm20_protocol.claudmaster.consistency.npc_knowledge import NPCKnowledgeTracker
from dm20_protocol.consistency.party_knowledge import (
    PARTY_KNOWN_TAG,
    AcquisitionMethod,
    KnowledgeRecord,
    PartyKnowledge,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fact_db(tmp_path):
    """Create a FactDatabase with some pre-loaded facts."""
    db = FactDatabase(tmp_path)

    db.add_fact(Fact(
        id="fact_dragon",
        category=FactCategory.WORLD,
        content="A red dragon named Infernus lairs beneath Mount Doom",
        session_number=1,
        relevance_score=1.0,
        tags=["dragon", "mount_doom"],
    ))
    db.add_fact(Fact(
        id="fact_curse",
        category=FactCategory.QUEST,
        content="The village of Barovia is cursed by the vampire lord Strahd",
        session_number=1,
        relevance_score=0.9,
        tags=["curse", "strahd", "barovia"],
    ))
    db.add_fact(Fact(
        id="fact_potion",
        category=FactCategory.ITEM,
        content="The Moonwell produces a healing potion every full moon",
        session_number=2,
        relevance_score=0.7,
        tags=["potion", "moonwell"],
    ))
    db.add_fact(Fact(
        id="fact_npc_secret",
        category=FactCategory.NPC,
        content="The innkeeper is secretly a spy for the thieves' guild",
        session_number=1,
        relevance_score=0.8,
        tags=["npc", "spy", "thieves_guild"],
    ))
    db.add_fact(Fact(
        id="fact_ancient_lore",
        category=FactCategory.WORLD,
        content="The ancient elven empire fell due to a magical cataclysm",
        session_number=1,
        relevance_score=0.6,
        tags=["history", "elven", "cataclysm"],
    ))

    return db


@pytest.fixture
def party_knowledge(tmp_path, fact_db):
    """Create a PartyKnowledge instance."""
    return PartyKnowledge(fact_db, tmp_path)


@pytest.fixture
def npc_tracker(tmp_path, fact_db):
    """Create an NPCKnowledgeTracker instance."""
    return NPCKnowledgeTracker(fact_db, tmp_path)


# ---------------------------------------------------------------------------
# AcquisitionMethod Tests
# ---------------------------------------------------------------------------

class TestAcquisitionMethod:
    """Tests for AcquisitionMethod enum."""

    def test_all_methods_exist(self):
        """Test that all expected methods are defined."""
        expected = [
            "told_by_npc", "observed", "investigated", "read",
            "overheard", "deduced", "magical", "common_knowledge",
        ]
        for method_str in expected:
            assert AcquisitionMethod(method_str) is not None

    def test_string_value(self):
        """Test that enum values are strings."""
        assert AcquisitionMethod.TOLD_BY_NPC == "told_by_npc"
        assert AcquisitionMethod.OBSERVED == "observed"


# ---------------------------------------------------------------------------
# KnowledgeRecord Tests
# ---------------------------------------------------------------------------

class TestKnowledgeRecord:
    """Tests for KnowledgeRecord model."""

    def test_create_minimal(self):
        """Test creating a KnowledgeRecord with required fields only."""
        record = KnowledgeRecord(
            fact_id="fact_1",
            source="Bartender",
            method=AcquisitionMethod.TOLD_BY_NPC,
            learned_session=1,
        )
        assert record.fact_id == "fact_1"
        assert record.source == "Bartender"
        assert record.method == AcquisitionMethod.TOLD_BY_NPC
        assert record.learned_session == 1
        assert record.location is None
        assert record.notes is None
        assert record.learned_at is not None

    def test_create_full(self):
        """Test creating a KnowledgeRecord with all fields."""
        record = KnowledgeRecord(
            fact_id="fact_2",
            source="Ancient Tome",
            method=AcquisitionMethod.READ,
            learned_session=3,
            location="Library of Alexandria",
            notes="Found in the restricted section",
        )
        assert record.location == "Library of Alexandria"
        assert record.notes == "Found in the restricted section"

    def test_serialization_roundtrip(self):
        """Test model_dump and model_validate roundtrip."""
        record = KnowledgeRecord(
            fact_id="fact_3",
            source="Elara the Ranger",
            method=AcquisitionMethod.OBSERVED,
            learned_session=2,
            location="Dark Forest",
        )
        data = record.model_dump(mode="json")
        record2 = KnowledgeRecord.model_validate(data)
        assert record2.fact_id == record.fact_id
        assert record2.source == record.source
        assert record2.method == record.method
        assert record2.learned_session == record.learned_session
        assert record2.location == record.location


# ---------------------------------------------------------------------------
# PartyKnowledge Tests
# ---------------------------------------------------------------------------

class TestPartyKnowledge:
    """Tests for PartyKnowledge manager class."""

    def test_init_creates_directory(self, tmp_path, fact_db):
        """Test that initialization creates the campaign directory."""
        campaign_dir = tmp_path / "new_campaign"
        pk = PartyKnowledge(fact_db, campaign_dir)
        assert campaign_dir.exists()
        assert pk.known_fact_count == 0

    def test_init_type_validation(self, tmp_path):
        """Test that initialization rejects non-FactDatabase objects."""
        with pytest.raises(TypeError, match="must be a FactDatabase instance"):
            PartyKnowledge("not_a_fact_db", tmp_path)

    # -- learn_fact --

    def test_learn_fact_basic(self, party_knowledge, fact_db):
        """Test basic fact learning."""
        result = party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        assert result is True
        assert party_knowledge.known_fact_count == 1
        assert party_knowledge.party_knows("fact_dragon")

    def test_learn_fact_adds_tag(self, party_knowledge, fact_db):
        """Test that learn_fact adds the party_known tag to the fact."""
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        fact = fact_db.get_fact("fact_dragon")
        assert PARTY_KNOWN_TAG in fact.tags

    def test_learn_fact_with_all_fields(self, party_knowledge):
        """Test learning a fact with all optional fields."""
        party_knowledge.learn_fact(
            fact_id="fact_curse",
            source="Ismark",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=2,
            location="Village of Barovia",
            notes="Ismark was desperate for help",
        )
        record = party_knowledge.get_record("fact_curse")
        assert record is not None
        assert record.source == "Ismark"
        assert record.location == "Village of Barovia"
        assert record.notes == "Ismark was desperate for help"

    def test_learn_fact_string_method(self, party_knowledge):
        """Test learning a fact with method as string."""
        result = party_knowledge.learn_fact(
            fact_id="fact_potion",
            source="Herbalist",
            method="investigated",
            session=2,
        )
        assert result is True
        record = party_knowledge.get_record("fact_potion")
        assert record.method == AcquisitionMethod.INVESTIGATED

    def test_learn_fact_duplicate(self, party_knowledge):
        """Test that learning the same fact twice is a no-op."""
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        result = party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Different Source",
            method=AcquisitionMethod.OBSERVED,
            session=3,
        )
        assert result is False
        assert party_knowledge.known_fact_count == 1
        # Original record should be preserved
        record = party_knowledge.get_record("fact_dragon")
        assert record.source == "Old Sage"

    def test_learn_fact_nonexistent(self, party_knowledge):
        """Test that learning a nonexistent fact raises KeyError."""
        with pytest.raises(KeyError, match="not found in FactDatabase"):
            party_knowledge.learn_fact(
                fact_id="fact_nonexistent",
                source="Nobody",
                method=AcquisitionMethod.OBSERVED,
                session=1,
            )

    def test_learn_fact_tag_idempotent(self, party_knowledge, fact_db):
        """Test that the party_known tag is not duplicated if already present."""
        # Manually add the tag first
        fact = fact_db.get_fact("fact_dragon")
        fact.tags.append(PARTY_KNOWN_TAG)

        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        # Should not have duplicate tags
        count = fact.tags.count(PARTY_KNOWN_TAG)
        assert count == 1

    # -- party_knows --

    def test_party_knows_true(self, party_knowledge):
        """Test party_knows returns True for known facts."""
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        assert party_knowledge.party_knows("fact_dragon") is True

    def test_party_knows_false(self, party_knowledge):
        """Test party_knows returns False for unknown facts."""
        assert party_knowledge.party_knows("fact_dragon") is False

    # -- get_record --

    def test_get_record_exists(self, party_knowledge):
        """Test getting an existing record."""
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        record = party_knowledge.get_record("fact_dragon")
        assert record is not None
        assert record.fact_id == "fact_dragon"

    def test_get_record_not_found(self, party_knowledge):
        """Test getting a non-existent record returns None."""
        assert party_knowledge.get_record("fact_nonexistent") is None

    # -- knows_about --

    def test_knows_about_content_match(self, party_knowledge):
        """Test querying knowledge by content."""
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        party_knowledge.learn_fact(
            fact_id="fact_curse",
            source="Ismark",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=2,
        )

        results = party_knowledge.knows_about("dragon")
        assert len(results) == 1
        assert results[0]["fact"].id == "fact_dragon"

    def test_knows_about_case_insensitive(self, party_knowledge):
        """Test that knows_about is case insensitive."""
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        results = party_knowledge.knows_about("DRAGON")
        assert len(results) == 1

    def test_knows_about_tag_match(self, party_knowledge):
        """Test that knows_about matches against tags."""
        party_knowledge.learn_fact(
            fact_id="fact_curse",
            source="Ismark",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=2,
        )
        results = party_knowledge.knows_about("strahd")
        assert len(results) == 1
        assert results[0]["fact"].id == "fact_curse"

    def test_knows_about_category_match(self, party_knowledge):
        """Test that knows_about matches against category."""
        party_knowledge.learn_fact(
            fact_id="fact_potion",
            source="Herbalist",
            method=AcquisitionMethod.INVESTIGATED,
            session=2,
        )
        results = party_knowledge.knows_about("item")
        assert len(results) == 1
        assert results[0]["fact"].id == "fact_potion"

    def test_knows_about_no_results(self, party_knowledge):
        """Test knows_about with no matches."""
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        results = party_knowledge.knows_about("unicorn")
        assert len(results) == 0

    def test_knows_about_sorted_by_relevance(self, party_knowledge):
        """Test that knows_about results are sorted by relevance."""
        # Both facts mention "world" category but have different relevance
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        party_knowledge.learn_fact(
            fact_id="fact_ancient_lore",
            source="Library",
            method=AcquisitionMethod.READ,
            session=2,
        )
        results = party_knowledge.knows_about("world")
        assert len(results) == 2
        # fact_dragon has relevance 1.0, fact_ancient_lore has 0.6
        assert results[0]["fact"].id == "fact_dragon"
        assert results[1]["fact"].id == "fact_ancient_lore"

    # -- get_all_known_facts --

    def test_get_all_known_facts(self, party_knowledge):
        """Test getting all known facts."""
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        party_knowledge.learn_fact(
            fact_id="fact_curse",
            source="Ismark",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=2,
        )
        results = party_knowledge.get_all_known_facts()
        assert len(results) == 2
        # Should be sorted by session (most recent first)
        assert results[0]["record"].learned_session == 2
        assert results[1]["record"].learned_session == 1

    def test_get_all_known_facts_empty(self, party_knowledge):
        """Test getting all known facts when none exist."""
        assert party_knowledge.get_all_known_facts() == []

    # -- get_knowledge_by_source --

    def test_get_knowledge_by_source(self, party_knowledge):
        """Test filtering knowledge by source."""
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        party_knowledge.learn_fact(
            fact_id="fact_curse",
            source="Ismark",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=2,
        )
        party_knowledge.learn_fact(
            fact_id="fact_ancient_lore",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=3,
        )

        results = party_knowledge.get_knowledge_by_source("Old Sage")
        assert len(results) == 2
        fact_ids = {r["fact"].id for r in results}
        assert fact_ids == {"fact_dragon", "fact_ancient_lore"}

    def test_get_knowledge_by_source_case_insensitive(self, party_knowledge):
        """Test that source filtering is case insensitive."""
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        results = party_knowledge.get_knowledge_by_source("old sage")
        assert len(results) == 1

    # -- get_knowledge_by_method --

    def test_get_knowledge_by_method(self, party_knowledge):
        """Test filtering knowledge by method."""
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        party_knowledge.learn_fact(
            fact_id="fact_potion",
            source="Herbalist",
            method=AcquisitionMethod.INVESTIGATED,
            session=2,
        )

        results = party_knowledge.get_knowledge_by_method(AcquisitionMethod.TOLD_BY_NPC)
        assert len(results) == 1
        assert results[0]["fact"].id == "fact_dragon"

    def test_get_knowledge_by_method_string(self, party_knowledge):
        """Test filtering by method using string value."""
        party_knowledge.learn_fact(
            fact_id="fact_potion",
            source="Herbalist",
            method=AcquisitionMethod.INVESTIGATED,
            session=2,
        )
        results = party_knowledge.get_knowledge_by_method("investigated")
        assert len(results) == 1

    # -- Persistence --

    def test_save_and_load_roundtrip(self, tmp_path, fact_db):
        """Test persistence round-trip."""
        pk1 = PartyKnowledge(fact_db, tmp_path)
        pk1.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
            location="Tavern",
            notes="Said in hushed tones",
        )
        pk1.learn_fact(
            fact_id="fact_curse",
            source="Ismark",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=2,
        )
        pk1.save()

        # Verify file exists
        assert (tmp_path / "party_knowledge.json").exists()

        # Load into new instance
        pk2 = PartyKnowledge(fact_db, tmp_path)
        assert pk2.known_fact_count == 2
        assert pk2.party_knows("fact_dragon")
        assert pk2.party_knows("fact_curse")

        record = pk2.get_record("fact_dragon")
        assert record.source == "Old Sage"
        assert record.method == AcquisitionMethod.TOLD_BY_NPC
        assert record.learned_session == 1
        assert record.location == "Tavern"
        assert record.notes == "Said in hushed tones"

    def test_save_file_structure(self, tmp_path, fact_db):
        """Test the structure of the saved JSON file."""
        pk = PartyKnowledge(fact_db, tmp_path)
        pk.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        pk.save()

        data = json.loads((tmp_path / "party_knowledge.json").read_text())
        assert "version" in data
        assert data["version"] == "1.0"
        assert "records" in data
        assert len(data["records"]) == 1
        assert "metadata" in data
        assert data["metadata"]["total_known_facts"] == 1

    def test_load_nonexistent_file(self, tmp_path, fact_db):
        """Test that loading from a missing file starts empty."""
        pk = PartyKnowledge(fact_db, tmp_path)
        assert pk.known_fact_count == 0

    def test_load_corrupt_file(self, tmp_path, fact_db):
        """Test that loading from a corrupt file starts empty."""
        (tmp_path / "party_knowledge.json").write_text("not valid json!!!")
        pk = PartyKnowledge(fact_db, tmp_path)
        assert pk.known_fact_count == 0

    def test_load_invalid_structure(self, tmp_path, fact_db):
        """Test that loading from invalid structure starts empty."""
        (tmp_path / "party_knowledge.json").write_text(json.dumps({"no_records": []}))
        pk = PartyKnowledge(fact_db, tmp_path)
        assert pk.known_fact_count == 0


# ---------------------------------------------------------------------------
# Bidirectional NPC Integration Tests
# ---------------------------------------------------------------------------

class TestNPCBidirectionalIntegration:
    """Tests for bidirectional knowledge flow between party and NPCs."""

    def test_share_with_npc(self, party_knowledge, npc_tracker):
        """Test sharing a party-known fact with an NPC."""
        # Party learns a fact
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )

        # Share it with an NPC
        result = party_knowledge.share_with_npc(
            npc_tracker=npc_tracker,
            npc_id="guard_captain",
            fact_id="fact_dragon",
            shared_by="Aldric",
            session=2,
        )
        assert result is True
        assert npc_tracker.npc_knows_fact("guard_captain", "fact_dragon")

    def test_share_with_npc_unknown_fact(self, party_knowledge, npc_tracker):
        """Test that the party cannot share facts they don't know."""
        result = party_knowledge.share_with_npc(
            npc_tracker=npc_tracker,
            npc_id="guard_captain",
            fact_id="fact_dragon",
            shared_by="Aldric",
            session=1,
        )
        assert result is False
        assert not npc_tracker.npc_knows_fact("guard_captain", "fact_dragon")

    def test_share_with_npc_already_knows(self, party_knowledge, npc_tracker):
        """Test sharing a fact the NPC already knows."""
        # NPC already knows the fact
        npc_tracker.add_knowledge(
            npc_id="guard_captain",
            fact_id="fact_dragon",
            source=KnowledgeSource.COMMON_KNOWLEDGE,
            session=1,
        )

        # Party also knows it
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )

        # Sharing should return False (NPC already knows)
        result = party_knowledge.share_with_npc(
            npc_tracker=npc_tracker,
            npc_id="guard_captain",
            fact_id="fact_dragon",
            shared_by="Aldric",
            session=2,
        )
        assert result is False

    def test_npc_shares_with_party(self, party_knowledge, npc_tracker):
        """Test NPC sharing knowledge with the party via share_with_party."""
        # NPC knows facts
        npc_tracker.add_knowledge(
            npc_id="tavern_keeper",
            fact_id="fact_npc_secret",
            source=KnowledgeSource.WITNESSED,
            session=1,
        )
        npc_tracker.add_knowledge(
            npc_id="tavern_keeper",
            fact_id="fact_curse",
            source=KnowledgeSource.RUMOR,
            session=1,
        )

        # NPC shares with party
        shared = npc_tracker.share_with_party(
            npc_id="tavern_keeper",
            fact_ids=["fact_npc_secret", "fact_curse"],
            party_knowledge=party_knowledge,
            session=2,
            location="The Rusty Flagon",
        )

        assert len(shared) == 2
        assert "fact_npc_secret" in shared
        assert "fact_curse" in shared
        assert party_knowledge.party_knows("fact_npc_secret")
        assert party_knowledge.party_knows("fact_curse")

        # Check acquisition metadata
        record = party_knowledge.get_record("fact_npc_secret")
        assert record.source == "tavern_keeper"
        assert record.method == AcquisitionMethod.TOLD_BY_NPC
        assert record.learned_session == 2
        assert record.location == "The Rusty Flagon"

    def test_npc_shares_unknown_fact(self, party_knowledge, npc_tracker):
        """Test that NPC cannot share facts they don't know."""
        shared = npc_tracker.share_with_party(
            npc_id="tavern_keeper",
            fact_ids=["fact_dragon"],
            party_knowledge=party_knowledge,
            session=1,
        )
        assert len(shared) == 0
        assert not party_knowledge.party_knows("fact_dragon")

    def test_npc_shares_partially_known(self, party_knowledge, npc_tracker):
        """Test NPC sharing mix of known and unknown facts."""
        # NPC only knows one of the facts
        npc_tracker.add_knowledge(
            npc_id="merchant",
            fact_id="fact_potion",
            source=KnowledgeSource.PROFESSION,
            session=1,
        )

        shared = npc_tracker.share_with_party(
            npc_id="merchant",
            fact_ids=["fact_potion", "fact_dragon"],
            party_knowledge=party_knowledge,
            session=2,
        )

        assert len(shared) == 1
        assert "fact_potion" in shared
        assert party_knowledge.party_knows("fact_potion")
        assert not party_knowledge.party_knows("fact_dragon")

    def test_npc_shares_already_known_by_party(self, party_knowledge, npc_tracker):
        """Test NPC sharing a fact the party already knows."""
        # Party already knows the fact
        party_knowledge.learn_fact(
            fact_id="fact_curse",
            source="Ismark",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )

        # NPC also knows it
        npc_tracker.add_knowledge(
            npc_id="priest",
            fact_id="fact_curse",
            source=KnowledgeSource.COMMON_KNOWLEDGE,
            session=1,
        )

        # NPC tries to share - should not be in shared list
        shared = npc_tracker.share_with_party(
            npc_id="priest",
            fact_ids=["fact_curse"],
            party_knowledge=party_knowledge,
            session=2,
        )

        assert len(shared) == 0
        # Original record preserved
        record = party_knowledge.get_record("fact_curse")
        assert record.source == "Ismark"

    def test_full_bidirectional_workflow(self, tmp_path, fact_db):
        """Test a complete bidirectional knowledge flow."""
        pk = PartyKnowledge(fact_db, tmp_path)
        npc = NPCKnowledgeTracker(fact_db, tmp_path)

        # 1. NPC shares info with party
        npc.add_knowledge(
            npc_id="sage",
            fact_id="fact_dragon",
            source=KnowledgeSource.WITNESSED,
            session=1,
        )
        npc.add_knowledge(
            npc_id="sage",
            fact_id="fact_ancient_lore",
            source=KnowledgeSource.PROFESSION,
            session=1,
        )

        shared_to_party = npc.share_with_party(
            npc_id="sage",
            fact_ids=["fact_dragon", "fact_ancient_lore"],
            party_knowledge=pk,
            session=2,
        )
        assert len(shared_to_party) == 2

        # 2. Party investigates and learns more
        pk.learn_fact(
            fact_id="fact_potion",
            source="Investigation",
            method=AcquisitionMethod.INVESTIGATED,
            session=3,
        )

        # 3. Party shares the investigation results with a different NPC
        result = pk.share_with_npc(
            npc_tracker=npc,
            npc_id="guard_captain",
            fact_id="fact_potion",
            shared_by="Elara",
            session=4,
        )
        assert result is True
        assert npc.npc_knows_fact("guard_captain", "fact_potion")

        # 4. Verify party knows 3 facts total
        assert pk.known_fact_count == 3
        all_known = pk.get_all_known_facts()
        assert len(all_known) == 3

        # 5. Save and reload
        pk.save()
        npc.save()

        pk2 = PartyKnowledge(fact_db, tmp_path)
        assert pk2.known_fact_count == 3


# ---------------------------------------------------------------------------
# FactDatabase Tag Integration Tests
# ---------------------------------------------------------------------------

class TestFactDatabaseTagIntegration:
    """Tests for the party_known tag in FactDatabase."""

    def test_query_party_known_facts_via_tags(self, party_knowledge, fact_db):
        """Test querying party-known facts via FactDatabase tags."""
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        party_knowledge.learn_fact(
            fact_id="fact_curse",
            source="Ismark",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=2,
        )

        # Query via FactDatabase tags
        results = fact_db.query_facts(tags=[PARTY_KNOWN_TAG])
        assert len(results) == 2
        fact_ids = {f.id for f in results}
        assert fact_ids == {"fact_dragon", "fact_curse"}

    def test_unlearned_facts_not_tagged(self, party_knowledge, fact_db):
        """Test that unlearned facts don't have the party_known tag."""
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )

        # fact_curse should NOT have the tag
        fact = fact_db.get_fact("fact_curse")
        assert PARTY_KNOWN_TAG not in fact.tags

    def test_combined_tag_query(self, party_knowledge, fact_db):
        """Test querying with party_known tag combined with other tags."""
        party_knowledge.learn_fact(
            fact_id="fact_dragon",
            source="Old Sage",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=1,
        )
        party_knowledge.learn_fact(
            fact_id="fact_curse",
            source="Ismark",
            method=AcquisitionMethod.TOLD_BY_NPC,
            session=2,
        )

        # Query for party-known facts about dragons specifically
        results = fact_db.query_facts(tags=[PARTY_KNOWN_TAG, "dragon"])
        assert len(results) == 1
        assert results[0].id == "fact_dragon"
