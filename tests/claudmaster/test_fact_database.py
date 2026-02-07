"""
Comprehensive tests for the fact tracking system.

Tests cover all functionality of the FactDatabase class, including:
- Initialization and persistence
- Adding and retrieving facts
- Querying with various filters
- Fact relationships and relevance scoring
- Error handling and edge cases
"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path

from gamemaster_mcp.claudmaster.consistency import Fact, FactCategory, FactDatabase


class TestFactModel:
    """Tests for the Fact model."""

    def test_fact_creation_minimal(self):
        """Test creating a fact with minimal required fields."""
        fact = Fact(
            category=FactCategory.EVENT,
            content="The party defeated the dragon",
            session_number=5
        )

        assert fact.category == FactCategory.EVENT
        assert fact.content == "The party defeated the dragon"
        assert fact.session_number == 5
        assert fact.relevance_score == 1.0
        assert fact.related_facts == []
        assert fact.tags == []
        assert fact.source is None

    def test_fact_creation_full(self):
        """Test creating a fact with all fields."""
        fact = Fact(
            id="fact_12345678",
            category=FactCategory.NPC,
            content="Gandalf the Grey is a wizard from the West",
            session_number=1,
            timestamp=datetime(2026, 1, 1, 12, 0, 0),
            relevance_score=2.5,
            related_facts=["fact_87654321"],
            tags=["wizard", "important"],
            source="Narrator"
        )

        assert fact.id == "fact_12345678"
        assert fact.category == FactCategory.NPC
        assert fact.content == "Gandalf the Grey is a wizard from the West"
        assert fact.session_number == 1
        assert fact.timestamp == datetime(2026, 1, 1, 12, 0, 0)
        assert fact.relevance_score == 2.5
        assert fact.related_facts == ["fact_87654321"]
        assert fact.tags == ["wizard", "important"]
        assert fact.source == "Narrator"

    def test_fact_category_enum(self):
        """Test all fact category enum values."""
        categories = [
            FactCategory.EVENT,
            FactCategory.LOCATION,
            FactCategory.NPC,
            FactCategory.ITEM,
            FactCategory.QUEST,
            FactCategory.WORLD,
        ]

        assert len(categories) == 6
        assert FactCategory.EVENT.value == "event"
        assert FactCategory.LOCATION.value == "location"
        assert FactCategory.NPC.value == "npc"
        assert FactCategory.ITEM.value == "item"
        assert FactCategory.QUEST.value == "quest"
        assert FactCategory.WORLD.value == "world"


class TestFactDatabaseInitialization:
    """Tests for FactDatabase initialization."""

    def test_init_creates_empty_database(self, tmp_path):
        """Test that initialization creates an empty database."""
        campaign_path = tmp_path / "test_campaign"
        db = FactDatabase(campaign_path)

        assert db.campaign_path == campaign_path
        assert db.campaign_id == "test_campaign"
        assert len(db.facts) == 0
        assert campaign_path.exists()

    def test_init_creates_directory_if_missing(self, tmp_path):
        """Test that initialization creates the campaign directory if it doesn't exist."""
        campaign_path = tmp_path / "nested" / "campaign"
        assert not campaign_path.exists()

        db = FactDatabase(campaign_path)

        assert campaign_path.exists()
        assert db.campaign_path == campaign_path

    def test_init_loads_existing_database(self, tmp_path):
        """Test that initialization loads an existing database."""
        campaign_path = tmp_path / "test_campaign"
        campaign_path.mkdir()

        # Create a database file
        db_file = campaign_path / "fact_database.json"
        data = {
            "version": "1.0",
            "campaign_id": "test_campaign",
            "facts": [
                {
                    "id": "fact_00000001",
                    "category": "event",
                    "content": "The adventure begins",
                    "session_number": 1,
                    "timestamp": "2026-01-01T12:00:00",
                    "relevance_score": 1.0,
                    "related_facts": [],
                    "tags": [],
                    "source": None
                }
            ],
            "metadata": {
                "total_facts": 1,
                "last_updated": "2026-01-01T12:00:00"
            }
        }
        with open(db_file, "w") as f:
            json.dump(data, f)

        # Load the database
        db = FactDatabase(campaign_path)

        assert len(db.facts) == 1
        assert "fact_00000001" in db.facts
        assert db.facts["fact_00000001"].content == "The adventure begins"


class TestAddAndGetFact:
    """Tests for adding and retrieving facts."""

    def test_add_fact_with_id(self, tmp_path):
        """Test adding a fact with a pre-assigned ID."""
        db = FactDatabase(tmp_path / "campaign")
        fact = Fact(
            id="fact_custom",
            category=FactCategory.EVENT,
            content="Test event",
            session_number=1
        )

        fact_id = db.add_fact(fact)

        assert fact_id == "fact_custom"
        assert "fact_custom" in db.facts
        assert db.facts["fact_custom"].content == "Test event"

    def test_add_fact_auto_generates_id(self, tmp_path):
        """Test that adding a fact without an ID auto-generates one."""
        db = FactDatabase(tmp_path / "campaign")
        fact = Fact(
            category=FactCategory.NPC,
            content="Mysterious stranger",
            session_number=2
        )

        fact_id = db.add_fact(fact)

        assert fact_id.startswith("fact_")
        assert len(fact_id) == len("fact_") + 8  # "fact_" + 8 hex chars
        assert fact_id in db.facts
        assert db.facts[fact_id].content == "Mysterious stranger"

    def test_get_fact_existing(self, tmp_path):
        """Test retrieving an existing fact."""
        db = FactDatabase(tmp_path / "campaign")
        fact = Fact(
            id="fact_test",
            category=FactCategory.LOCATION,
            content="The Prancing Pony Inn",
            session_number=1
        )
        db.add_fact(fact)

        retrieved = db.get_fact("fact_test")

        assert retrieved is not None
        assert retrieved.id == "fact_test"
        assert retrieved.content == "The Prancing Pony Inn"

    def test_get_fact_nonexistent(self, tmp_path):
        """Test retrieving a non-existent fact returns None."""
        db = FactDatabase(tmp_path / "campaign")

        retrieved = db.get_fact("fact_nonexistent")

        assert retrieved is None


class TestQueryFacts:
    """Tests for querying facts with filters."""

    @pytest.fixture
    def populated_db(self, tmp_path):
        """Create a database populated with test facts."""
        db = FactDatabase(tmp_path / "campaign")

        facts = [
            Fact(
                id="fact_001",
                category=FactCategory.EVENT,
                content="Dragon attack on village",
                session_number=1,
                relevance_score=3.0,
                tags=["combat", "dragon"]
            ),
            Fact(
                id="fact_002",
                category=FactCategory.EVENT,
                content="Party meets at tavern",
                session_number=1,
                relevance_score=1.5,
                tags=["social"]
            ),
            Fact(
                id="fact_003",
                category=FactCategory.NPC,
                content="Innkeeper named Bob",
                session_number=1,
                relevance_score=1.0,
                tags=["social", "npc"]
            ),
            Fact(
                id="fact_004",
                category=FactCategory.LOCATION,
                content="Ancient ruins discovered",
                session_number=2,
                relevance_score=2.5,
                tags=["exploration"]
            ),
            Fact(
                id="fact_005",
                category=FactCategory.EVENT,
                content="Party finds treasure",
                session_number=2,
                relevance_score=2.0,
                tags=["treasure", "exploration"]
            ),
        ]

        for fact in facts:
            db.add_fact(fact)

        return db

    def test_query_all_facts(self, populated_db):
        """Test querying without filters returns all facts."""
        results = populated_db.query_facts()

        assert len(results) == 5

    def test_query_by_category(self, populated_db):
        """Test filtering by category."""
        results = populated_db.query_facts(category=FactCategory.EVENT)

        assert len(results) == 3
        assert all(f.category == FactCategory.EVENT for f in results)

    def test_query_by_session(self, populated_db):
        """Test filtering by session number."""
        results = populated_db.query_facts(session=1)

        assert len(results) == 3
        assert all(f.session_number == 1 for f in results)

    def test_query_by_min_relevance(self, populated_db):
        """Test filtering by minimum relevance score."""
        results = populated_db.query_facts(min_relevance=2.0)

        assert len(results) == 3
        assert all(f.relevance_score >= 2.0 for f in results)

    def test_query_by_single_tag(self, populated_db):
        """Test filtering by a single tag."""
        results = populated_db.query_facts(tags=["exploration"])

        assert len(results) == 2
        assert all("exploration" in f.tags for f in results)

    def test_query_by_multiple_tags(self, populated_db):
        """Test filtering by multiple tags (AND logic)."""
        results = populated_db.query_facts(tags=["social", "npc"])

        assert len(results) == 1
        assert results[0].id == "fact_003"

    def test_query_combined_filters(self, populated_db):
        """Test combining multiple filters."""
        results = populated_db.query_facts(
            category=FactCategory.EVENT,
            session=2,
            min_relevance=1.5
        )

        assert len(results) == 1
        assert results[0].id == "fact_005"

    def test_query_with_limit(self, populated_db):
        """Test limiting query results."""
        results = populated_db.query_facts(limit=2)

        assert len(results) == 2
        # Should return highest relevance first
        assert results[0].id == "fact_001"  # relevance 3.0
        assert results[1].id == "fact_004"  # relevance 2.5

    def test_query_sorts_by_relevance(self, populated_db):
        """Test that results are sorted by relevance (descending)."""
        results = populated_db.query_facts()

        # Check that results are sorted by relevance (highest first)
        relevance_scores = [f.relevance_score for f in results]
        assert relevance_scores == sorted(relevance_scores, reverse=True)

    def test_query_no_matches(self, populated_db):
        """Test query with no matches returns empty list."""
        results = populated_db.query_facts(
            category=FactCategory.ITEM,
            session=99
        )

        assert len(results) == 0


class TestRelatedFacts:
    """Tests for fact relationships."""

    def test_get_related_facts_empty(self, tmp_path):
        """Test getting related facts when there are none."""
        db = FactDatabase(tmp_path / "campaign")
        fact = Fact(
            id="fact_001",
            category=FactCategory.EVENT,
            content="Event with no relations",
            session_number=1
        )
        db.add_fact(fact)

        related = db.get_related_facts("fact_001")

        assert len(related) == 0

    def test_get_related_facts_with_relations(self, tmp_path):
        """Test getting related facts when they exist."""
        db = FactDatabase(tmp_path / "campaign")

        fact1 = Fact(
            id="fact_001",
            category=FactCategory.EVENT,
            content="Dragon appears",
            session_number=1,
            related_facts=["fact_002", "fact_003"]
        )
        fact2 = Fact(
            id="fact_002",
            category=FactCategory.NPC,
            content="Dragon named Smaug",
            session_number=1
        )
        fact3 = Fact(
            id="fact_003",
            category=FactCategory.LOCATION,
            content="Dragon's lair in mountains",
            session_number=1
        )

        db.add_fact(fact1)
        db.add_fact(fact2)
        db.add_fact(fact3)

        related = db.get_related_facts("fact_001")

        assert len(related) == 2
        assert any(f.id == "fact_002" for f in related)
        assert any(f.id == "fact_003" for f in related)

    def test_get_related_facts_nonexistent(self, tmp_path):
        """Test getting related facts for a non-existent fact."""
        db = FactDatabase(tmp_path / "campaign")

        related = db.get_related_facts("fact_nonexistent")

        assert len(related) == 0

    def test_get_related_facts_ignores_missing_relations(self, tmp_path):
        """Test that missing related fact IDs are skipped gracefully."""
        db = FactDatabase(tmp_path / "campaign")

        fact = Fact(
            id="fact_001",
            category=FactCategory.EVENT,
            content="Event with broken relations",
            session_number=1,
            related_facts=["fact_002", "fact_999"]  # fact_999 doesn't exist
        )
        fact2 = Fact(
            id="fact_002",
            category=FactCategory.NPC,
            content="Valid relation",
            session_number=1
        )

        db.add_fact(fact)
        db.add_fact(fact2)

        related = db.get_related_facts("fact_001")

        assert len(related) == 1
        assert related[0].id == "fact_002"


class TestLinkFacts:
    """Tests for bidirectional fact linking."""

    def test_link_facts_bidirectional(self, tmp_path):
        """Test that linking creates bidirectional relationships."""
        db = FactDatabase(tmp_path / "campaign")

        fact1 = Fact(
            id="fact_001",
            category=FactCategory.EVENT,
            content="First fact",
            session_number=1
        )
        fact2 = Fact(
            id="fact_002",
            category=FactCategory.EVENT,
            content="Second fact",
            session_number=1
        )

        db.add_fact(fact1)
        db.add_fact(fact2)
        db.link_facts("fact_001", "fact_002")

        # Check bidirectional links
        assert "fact_002" in db.facts["fact_001"].related_facts
        assert "fact_001" in db.facts["fact_002"].related_facts

    def test_link_facts_no_duplicates(self, tmp_path):
        """Test that linking the same facts twice doesn't create duplicates."""
        db = FactDatabase(tmp_path / "campaign")

        fact1 = Fact(
            id="fact_001",
            category=FactCategory.EVENT,
            content="First fact",
            session_number=1
        )
        fact2 = Fact(
            id="fact_002",
            category=FactCategory.EVENT,
            content="Second fact",
            session_number=1
        )

        db.add_fact(fact1)
        db.add_fact(fact2)
        db.link_facts("fact_001", "fact_002")
        db.link_facts("fact_001", "fact_002")  # Link again

        # Check no duplicates
        assert db.facts["fact_001"].related_facts.count("fact_002") == 1
        assert db.facts["fact_002"].related_facts.count("fact_001") == 1

    def test_link_facts_first_not_found(self, tmp_path):
        """Test linking with non-existent first fact raises KeyError."""
        db = FactDatabase(tmp_path / "campaign")

        fact2 = Fact(
            id="fact_002",
            category=FactCategory.EVENT,
            content="Second fact",
            session_number=1
        )
        db.add_fact(fact2)

        with pytest.raises(KeyError, match="fact_001"):
            db.link_facts("fact_001", "fact_002")

    def test_link_facts_second_not_found(self, tmp_path):
        """Test linking with non-existent second fact raises KeyError."""
        db = FactDatabase(tmp_path / "campaign")

        fact1 = Fact(
            id="fact_001",
            category=FactCategory.EVENT,
            content="First fact",
            session_number=1
        )
        db.add_fact(fact1)

        with pytest.raises(KeyError, match="fact_002"):
            db.link_facts("fact_001", "fact_002")


class TestUpdateRelevance:
    """Tests for updating fact relevance scores."""

    def test_update_relevance_success(self, tmp_path):
        """Test successfully updating a fact's relevance score."""
        db = FactDatabase(tmp_path / "campaign")

        fact = Fact(
            id="fact_001",
            category=FactCategory.EVENT,
            content="Important event",
            session_number=1,
            relevance_score=1.0
        )
        db.add_fact(fact)

        db.update_relevance("fact_001", 5.0)

        assert db.facts["fact_001"].relevance_score == 5.0

    def test_update_relevance_not_found(self, tmp_path):
        """Test updating non-existent fact raises KeyError."""
        db = FactDatabase(tmp_path / "campaign")

        with pytest.raises(KeyError, match="fact_999"):
            db.update_relevance("fact_999", 3.0)


class TestSaveAndLoad:
    """Tests for persistence (save/load)."""

    def test_save_creates_file(self, tmp_path):
        """Test that save creates the database file."""
        db = FactDatabase(tmp_path / "campaign")
        db_file = tmp_path / "campaign" / "fact_database.json"

        assert not db_file.exists()

        db.save()

        assert db_file.exists()

    def test_save_and_load_roundtrip(self, tmp_path):
        """Test that facts can be saved and loaded correctly."""
        campaign_path = tmp_path / "campaign"
        db1 = FactDatabase(campaign_path)

        # Add facts
        fact1 = Fact(
            id="fact_001",
            category=FactCategory.EVENT,
            content="Dragon attack",
            session_number=1,
            relevance_score=3.0,
            tags=["combat", "dragon"],
            source="Narrator"
        )
        fact2 = Fact(
            id="fact_002",
            category=FactCategory.NPC,
            content="Innkeeper Bob",
            session_number=1,
            relevance_score=1.5,
            tags=["social"],
            related_facts=["fact_001"]
        )

        db1.add_fact(fact1)
        db1.add_fact(fact2)
        db1.save()

        # Load into new database
        db2 = FactDatabase(campaign_path)

        assert len(db2.facts) == 2
        assert "fact_001" in db2.facts
        assert "fact_002" in db2.facts

        # Verify fact 1
        loaded_fact1 = db2.facts["fact_001"]
        assert loaded_fact1.category == FactCategory.EVENT
        assert loaded_fact1.content == "Dragon attack"
        assert loaded_fact1.session_number == 1
        assert loaded_fact1.relevance_score == 3.0
        assert loaded_fact1.tags == ["combat", "dragon"]
        assert loaded_fact1.source == "Narrator"

        # Verify fact 2
        loaded_fact2 = db2.facts["fact_002"]
        assert loaded_fact2.category == FactCategory.NPC
        assert loaded_fact2.content == "Innkeeper Bob"
        assert loaded_fact2.related_facts == ["fact_001"]

    def test_load_with_missing_file(self, tmp_path):
        """Test that load handles missing file gracefully."""
        campaign_path = tmp_path / "campaign"
        db = FactDatabase(campaign_path)

        # Should not raise, should create empty database
        assert len(db.facts) == 0

    def test_load_with_corrupt_json(self, tmp_path):
        """Test that load handles corrupt JSON gracefully."""
        campaign_path = tmp_path / "campaign"
        campaign_path.mkdir()
        db_file = campaign_path / "fact_database.json"

        # Write corrupt JSON
        with open(db_file, "w") as f:
            f.write("{ this is not valid json }")

        # Should not raise, should start with empty database
        db = FactDatabase(campaign_path)
        assert len(db.facts) == 0

    def test_load_with_invalid_structure(self, tmp_path):
        """Test that load handles invalid database structure gracefully."""
        campaign_path = tmp_path / "campaign"
        campaign_path.mkdir()
        db_file = campaign_path / "fact_database.json"

        # Write valid JSON but invalid structure
        with open(db_file, "w") as f:
            json.dump({"wrong": "structure"}, f)

        # Should not raise, should start with empty database
        db = FactDatabase(campaign_path)
        assert len(db.facts) == 0

    def test_save_preserves_metadata(self, tmp_path):
        """Test that save includes correct metadata."""
        db = FactDatabase(tmp_path / "campaign")

        fact = Fact(
            id="fact_001",
            category=FactCategory.EVENT,
            content="Test",
            session_number=1
        )
        db.add_fact(fact)
        db.save()

        # Read the file directly
        db_file = tmp_path / "campaign" / "fact_database.json"
        with open(db_file, "r") as f:
            data = json.load(f)

        assert data["version"] == "1.0"
        assert data["campaign_id"] == "campaign"
        assert data["metadata"]["total_facts"] == 1
        assert "last_updated" in data["metadata"]


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_empty_database_queries(self, tmp_path):
        """Test querying an empty database."""
        db = FactDatabase(tmp_path / "campaign")

        results = db.query_facts()
        assert len(results) == 0

        results = db.query_facts(category=FactCategory.EVENT)
        assert len(results) == 0

    def test_fact_with_unicode_content(self, tmp_path):
        """Test facts with unicode characters."""
        db = FactDatabase(tmp_path / "campaign")

        fact = Fact(
            id="fact_001",
            category=FactCategory.NPC,
            content="Elf named Ëlrønd with rûnes",
            session_number=1
        )
        db.add_fact(fact)
        db.save()

        # Reload and verify
        db2 = FactDatabase(tmp_path / "campaign")
        loaded = db2.get_fact("fact_001")
        assert loaded.content == "Elf named Ëlrønd with rûnes"

    def test_very_large_relevance_score(self, tmp_path):
        """Test facts with very large relevance scores."""
        db = FactDatabase(tmp_path / "campaign")

        fact = Fact(
            id="fact_001",
            category=FactCategory.EVENT,
            content="Campaign-defining event",
            session_number=1,
            relevance_score=1000000.0
        )
        db.add_fact(fact)

        assert db.facts["fact_001"].relevance_score == 1000000.0

    def test_zero_relevance_score(self, tmp_path):
        """Test facts with zero relevance score."""
        db = FactDatabase(tmp_path / "campaign")

        fact = Fact(
            id="fact_001",
            category=FactCategory.EVENT,
            content="Irrelevant event",
            session_number=1,
            relevance_score=0.0
        )
        db.add_fact(fact)

        # Should still be retrievable
        results = db.query_facts(min_relevance=0.0)
        assert len(results) == 1

    def test_many_related_facts(self, tmp_path):
        """Test fact with many related facts."""
        db = FactDatabase(tmp_path / "campaign")

        # Create 100 related facts
        related_ids = []
        for i in range(100):
            fact = Fact(
                id=f"fact_{i:03d}",
                category=FactCategory.EVENT,
                content=f"Related event {i}",
                session_number=1
            )
            db.add_fact(fact)
            related_ids.append(fact.id)

        # Create main fact with all relations
        main_fact = Fact(
            id="fact_main",
            category=FactCategory.EVENT,
            content="Main event with many relations",
            session_number=1,
            related_facts=related_ids
        )
        db.add_fact(main_fact)

        related = db.get_related_facts("fact_main")
        assert len(related) == 100

    def test_timestamp_preservation(self, tmp_path):
        """Test that timestamps are preserved through save/load."""
        db1 = FactDatabase(tmp_path / "campaign")

        timestamp = datetime(2026, 1, 15, 10, 30, 45)
        fact = Fact(
            id="fact_001",
            category=FactCategory.EVENT,
            content="Event with specific timestamp",
            session_number=1,
            timestamp=timestamp
        )
        db1.add_fact(fact)
        db1.save()

        # Reload
        db2 = FactDatabase(tmp_path / "campaign")
        loaded = db2.get_fact("fact_001")

        # Compare timestamps (might have slight differences due to serialization)
        assert loaded.timestamp.year == 2026
        assert loaded.timestamp.month == 1
        assert loaded.timestamp.day == 15
        assert loaded.timestamp.hour == 10
        assert loaded.timestamp.minute == 30
        assert loaded.timestamp.second == 45
