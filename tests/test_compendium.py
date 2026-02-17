"""
Unit tests for the CompendiumPack model and PackSerializer.

Tests cover:
- PackMetadata and CompendiumPack model validation
- Serialization round-trip (model_dump -> model_validate)
- Selective export by entity type
- Location-based filtering
- Tag-based filtering
- Full campaign backup
- Inter-entity relationships preserved
- Pack save/load to disk
"""

import json
import pytest
from datetime import datetime
from pathlib import Path

from dm20_protocol.compendium import (
    CompendiumPack,
    PackMetadata,
    PackSerializer,
    PACK_SCHEMA_VERSION,
)
from dm20_protocol.models import (
    Campaign,
    CombatEncounter,
    GameState,
    Location,
    NPC,
    Quest,
    SessionNote,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_campaign() -> Campaign:
    """Create a campaign with multiple entity types for testing."""
    game_state = GameState(campaign_name="Waterdeep Adventures")

    npcs = {
        "Durnan": NPC(
            name="Durnan",
            description="Owner of the Yawning Portal",
            race="Human",
            occupation="Innkeeper",
            location="Waterdeep",
            attitude="friendly",
            notes="veteran adventurer, tag:important",
        ),
        "Laeral Silverhand": NPC(
            name="Laeral Silverhand",
            description="Open Lord of Waterdeep",
            race="Human",
            occupation="Ruler",
            location="Waterdeep",
            attitude="neutral",
            notes="powerful mage, tag:important",
        ),
        "Strahd von Zarovich": NPC(
            name="Strahd von Zarovich",
            description="Vampire lord of Barovia",
            race="Undead",
            occupation="Ruler",
            location="Castle Ravenloft",
            attitude="hostile",
            notes="vampire, tag:villain",
        ),
    }

    locations = {
        "Waterdeep": Location(
            name="Waterdeep",
            location_type="city",
            description="City of Splendors",
            population=1300000,
            notable_features=["Yawning Portal", "Castle Waterdeep"],
            notes="major trade hub, tag:important",
        ),
        "Castle Ravenloft": Location(
            name="Castle Ravenloft",
            location_type="castle",
            description="Dark fortress in Barovia",
            notes="haunted, tag:villain",
        ),
        "Baldur's Gate": Location(
            name="Baldur's Gate",
            location_type="city",
            description="Port city on the Sword Coast",
            population=125000,
            notes="",
        ),
    }

    quests = {
        "Find the Stone": Quest(
            title="Find the Stone",
            description="Locate the Stone of Golorr",
            giver="Durnan",
            status="active",
            objectives=["Talk to contacts", "Search the sewers"],
            notes="waterdeep, tag:important",
        ),
        "Defeat Strahd": Quest(
            title="Defeat Strahd",
            description="Destroy the vampire lord",
            giver="Strahd von Zarovich",
            status="active",
            objectives=["Find the Sun Sword", "Confront Strahd"],
            notes="barovia, tag:villain",
        ),
    }

    encounters = {
        "Sewer Ambush": CombatEncounter(
            name="Sewer Ambush",
            description="Ambush by wererats in the Waterdeep sewers",
            enemies=["Wererat x3", "Dire Rat x5"],
            difficulty="hard",
            location="Waterdeep",
            notes="tag:important",
        ),
        "Castle Courtyard": CombatEncounter(
            name="Castle Courtyard",
            description="Wolves in the courtyard of Castle Ravenloft",
            enemies=["Dire Wolf x4"],
            difficulty="medium",
            location="Castle Ravenloft",
            notes="tag:villain",
        ),
    }

    sessions = [
        SessionNote(
            session_number=1,
            summary="The party arrived in Waterdeep and met Durnan.",
            events=["Arrived in Waterdeep", "Met Durnan at the Yawning Portal"],
        ),
        SessionNote(
            session_number=2,
            summary="The party explored the sewers.",
            events=["Fought wererats", "Found a clue"],
        ),
    ]

    return Campaign(
        name="Waterdeep Adventures",
        description="A campaign set in Waterdeep and beyond",
        dm_name="Test DM",
        npcs=npcs,
        locations=locations,
        quests=quests,
        encounters=encounters,
        sessions=sessions,
        game_state=game_state,
    )


@pytest.fixture
def empty_campaign() -> Campaign:
    """Create an empty campaign for edge case testing."""
    return Campaign(
        name="Empty Campaign",
        description="No entities",
        game_state=GameState(campaign_name="Empty Campaign"),
    )


@pytest.fixture
def packs_dir(tmp_path: Path) -> Path:
    """Create a temporary packs directory."""
    d = tmp_path / "packs"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# PackMetadata Tests
# ---------------------------------------------------------------------------


class TestPackMetadata:
    """Tests for PackMetadata model."""

    def test_default_values(self) -> None:
        """PackMetadata should have sensible defaults."""
        meta = PackMetadata(name="Test Pack")
        assert meta.name == "Test Pack"
        assert meta.description == ""
        assert meta.author == ""
        assert meta.tags == []
        assert meta.system_version == "5e"
        assert meta.schema_version == PACK_SCHEMA_VERSION
        assert meta.source_campaign == ""
        assert isinstance(meta.created_at, datetime)
        assert meta.entity_counts == {}
        assert len(meta.pack_id) == 12

    def test_custom_values(self) -> None:
        """PackMetadata should accept custom values."""
        meta = PackMetadata(
            name="Custom Pack",
            description="A custom pack",
            author="Test Author",
            tags=["horror", "undead"],
            system_version="5e-2024",
            source_campaign="Ravenloft",
            entity_counts={"npcs": 5, "locations": 3},
        )
        assert meta.description == "A custom pack"
        assert meta.author == "Test Author"
        assert meta.tags == ["horror", "undead"]
        assert meta.system_version == "5e-2024"
        assert meta.source_campaign == "Ravenloft"
        assert meta.entity_counts["npcs"] == 5

    def test_serialization_round_trip(self) -> None:
        """PackMetadata should survive JSON round-trip."""
        meta = PackMetadata(
            name="Round Trip Pack",
            tags=["test"],
            entity_counts={"npcs": 2},
        )
        data = meta.model_dump(mode="json")
        restored = PackMetadata.model_validate(data)
        assert restored.name == meta.name
        assert restored.tags == meta.tags
        assert restored.entity_counts == meta.entity_counts
        assert restored.pack_id == meta.pack_id


# ---------------------------------------------------------------------------
# CompendiumPack Tests
# ---------------------------------------------------------------------------


class TestCompendiumPack:
    """Tests for CompendiumPack model."""

    def test_empty_pack(self) -> None:
        """An empty pack should be valid."""
        pack = CompendiumPack(metadata=PackMetadata(name="Empty"))
        assert pack.npcs == []
        assert pack.locations == []
        assert pack.quests == []
        assert pack.encounters == []
        assert pack.game_state is None
        assert pack.sessions == []

    def test_pack_with_entities(self) -> None:
        """A pack with entities should store them correctly."""
        npc_data = {"name": "Gandalf", "race": "Maiar"}
        pack = CompendiumPack(
            metadata=PackMetadata(name="Test"),
            npcs=[npc_data],
        )
        assert len(pack.npcs) == 1
        assert pack.npcs[0]["name"] == "Gandalf"

    def test_serialization_round_trip(self) -> None:
        """CompendiumPack should survive JSON round-trip."""
        meta = PackMetadata(name="Round Trip", entity_counts={"npcs": 1})
        pack = CompendiumPack(
            metadata=meta,
            npcs=[{"name": "Test NPC", "id": "abc123"}],
            locations=[{"name": "Test Location", "location_type": "city", "description": "A city"}],
        )
        data = pack.model_dump(mode="json")
        restored = CompendiumPack.model_validate(data)
        assert restored.metadata.name == pack.metadata.name
        assert len(restored.npcs) == 1
        assert len(restored.locations) == 1
        assert restored.npcs[0]["name"] == "Test NPC"


# ---------------------------------------------------------------------------
# PackSerializer - Selective Export Tests
# ---------------------------------------------------------------------------


class TestPackSerializerSelective:
    """Tests for selective entity export."""

    def test_export_all_types(self, sample_campaign: Campaign) -> None:
        """Exporting without entity_types should include everything."""
        pack = PackSerializer.export_selective(
            sample_campaign,
            name="All Entities",
        )
        assert len(pack.npcs) == 3
        assert len(pack.locations) == 3
        assert len(pack.quests) == 2
        assert len(pack.encounters) == 2
        assert pack.metadata.source_campaign == "Waterdeep Adventures"
        assert pack.metadata.entity_counts["npcs"] == 3

    def test_export_npcs_only(self, sample_campaign: Campaign) -> None:
        """Export only NPCs."""
        pack = PackSerializer.export_selective(
            sample_campaign,
            name="NPCs Only",
            entity_types=["npcs"],
        )
        assert len(pack.npcs) == 3
        assert len(pack.locations) == 0
        assert len(pack.quests) == 0
        assert len(pack.encounters) == 0

    def test_export_locations_only(self, sample_campaign: Campaign) -> None:
        """Export only locations."""
        pack = PackSerializer.export_selective(
            sample_campaign,
            name="Locations Only",
            entity_types=["locations"],
        )
        assert len(pack.npcs) == 0
        assert len(pack.locations) == 3

    def test_export_multiple_types(self, sample_campaign: Campaign) -> None:
        """Export a subset of entity types."""
        pack = PackSerializer.export_selective(
            sample_campaign,
            name="NPCs and Quests",
            entity_types=["npcs", "quests"],
        )
        assert len(pack.npcs) == 3
        assert len(pack.quests) == 2
        assert len(pack.locations) == 0
        assert len(pack.encounters) == 0

    def test_export_invalid_type_raises(self, sample_campaign: Campaign) -> None:
        """Requesting an invalid entity type should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid entity types"):
            PackSerializer.export_selective(
                sample_campaign,
                name="Bad",
                entity_types=["characters"],  # Not a valid pack entity type
            )

    def test_export_empty_campaign(self, empty_campaign: Campaign) -> None:
        """Exporting an empty campaign should produce an empty pack."""
        pack = PackSerializer.export_selective(
            empty_campaign,
            name="Empty Export",
        )
        assert len(pack.npcs) == 0
        assert len(pack.locations) == 0
        assert len(pack.quests) == 0
        assert len(pack.encounters) == 0
        assert all(v == 0 for v in pack.metadata.entity_counts.values())


# ---------------------------------------------------------------------------
# PackSerializer - Location Filter Tests
# ---------------------------------------------------------------------------


class TestPackSerializerLocationFilter:
    """Tests for location-based filtering."""

    def test_filter_npcs_by_location(self, sample_campaign: Campaign) -> None:
        """NPCs should be filtered by their location field."""
        pack = PackSerializer.export_selective(
            sample_campaign,
            name="Waterdeep NPCs",
            entity_types=["npcs"],
            location_filter="Waterdeep",
        )
        assert len(pack.npcs) == 2
        names = {npc["name"] for npc in pack.npcs}
        assert "Durnan" in names
        assert "Laeral Silverhand" in names
        assert "Strahd von Zarovich" not in names

    def test_filter_locations_by_name(self, sample_campaign: Campaign) -> None:
        """Locations should be filtered by name match."""
        pack = PackSerializer.export_selective(
            sample_campaign,
            name="Ravenloft",
            entity_types=["locations"],
            location_filter="Ravenloft",
        )
        assert len(pack.locations) == 1
        assert pack.locations[0]["name"] == "Castle Ravenloft"

    def test_filter_encounters_by_location(self, sample_campaign: Campaign) -> None:
        """Encounters should be filtered by their location field."""
        pack = PackSerializer.export_selective(
            sample_campaign,
            name="Waterdeep Encounters",
            entity_types=["encounters"],
            location_filter="Waterdeep",
        )
        assert len(pack.encounters) == 1
        assert pack.encounters[0]["name"] == "Sewer Ambush"

    def test_filter_quests_by_giver_location(self, sample_campaign: Campaign) -> None:
        """Quests should be filterable by their giver's location."""
        pack = PackSerializer.export_selective(
            sample_campaign,
            name="Waterdeep Quests",
            entity_types=["quests"],
            location_filter="Waterdeep",
        )
        # "Find the Stone" has giver Durnan who is in Waterdeep
        # and its notes contain "waterdeep"
        assert len(pack.quests) >= 1
        titles = {q["title"] for q in pack.quests}
        assert "Find the Stone" in titles

    def test_filter_case_insensitive(self, sample_campaign: Campaign) -> None:
        """Location filter should be case-insensitive."""
        pack = PackSerializer.export_selective(
            sample_campaign,
            name="Case Test",
            entity_types=["npcs"],
            location_filter="waterdeep",
        )
        assert len(pack.npcs) == 2

    def test_filter_no_match(self, sample_campaign: Campaign) -> None:
        """A filter with no matches should produce empty collections."""
        pack = PackSerializer.export_selective(
            sample_campaign,
            name="No Match",
            location_filter="Neverwinter",
        )
        assert len(pack.npcs) == 0
        assert len(pack.locations) == 0


# ---------------------------------------------------------------------------
# PackSerializer - Tag Filter Tests
# ---------------------------------------------------------------------------


class TestPackSerializerTagFilter:
    """Tests for tag-based filtering."""

    def test_filter_by_single_tag(self, sample_campaign: Campaign) -> None:
        """Should find entities whose notes contain the tag."""
        pack = PackSerializer.export_by_tags(
            sample_campaign,
            name="Important Entities",
            filter_tags=["tag:important"],
        )
        # NPCs: Durnan, Laeral (both have tag:important)
        assert len(pack.npcs) == 2
        # Locations: Waterdeep
        assert len(pack.locations) == 1
        # Quests: Find the Stone
        assert len(pack.quests) == 1
        # Encounters: Sewer Ambush
        assert len(pack.encounters) == 1

    def test_filter_by_multiple_tags(self, sample_campaign: Campaign) -> None:
        """Multiple tags should match entities with any tag (OR logic)."""
        pack = PackSerializer.export_by_tags(
            sample_campaign,
            name="Important or Villain",
            filter_tags=["tag:important", "tag:villain"],
        )
        assert len(pack.npcs) == 3  # All three have one of the tags
        assert len(pack.locations) == 2  # Waterdeep + Castle Ravenloft

    def test_filter_no_tag_match(self, sample_campaign: Campaign) -> None:
        """No matching tags should produce empty collections."""
        pack = PackSerializer.export_by_tags(
            sample_campaign,
            name="No Match",
            filter_tags=["tag:nonexistent"],
        )
        assert len(pack.npcs) == 0
        assert len(pack.locations) == 0


# ---------------------------------------------------------------------------
# PackSerializer - Full Backup Tests
# ---------------------------------------------------------------------------


class TestPackSerializerFullBackup:
    """Tests for full campaign backup."""

    def test_full_backup_includes_all(self, sample_campaign: Campaign) -> None:
        """Full backup should include all entities, game state, and sessions."""
        pack = PackSerializer.export_full_backup(sample_campaign)
        assert len(pack.npcs) == 3
        assert len(pack.locations) == 3
        assert len(pack.quests) == 2
        assert len(pack.encounters) == 2
        assert pack.game_state is not None
        assert pack.game_state["campaign_name"] == "Waterdeep Adventures"
        assert len(pack.sessions) == 2
        assert "backup" in pack.metadata.tags
        assert "full" in pack.metadata.tags
        assert pack.metadata.entity_counts["sessions"] == 2

    def test_full_backup_default_name(self, sample_campaign: Campaign) -> None:
        """Full backup should use default name if not specified."""
        pack = PackSerializer.export_full_backup(sample_campaign)
        assert "Waterdeep Adventures" in pack.metadata.name
        assert "Full Backup" in pack.metadata.name

    def test_full_backup_custom_name(self, sample_campaign: Campaign) -> None:
        """Full backup should accept custom name."""
        pack = PackSerializer.export_full_backup(
            sample_campaign,
            name="My Custom Backup",
        )
        assert pack.metadata.name == "My Custom Backup"

    def test_full_backup_empty_campaign(self, empty_campaign: Campaign) -> None:
        """Full backup of empty campaign should still work."""
        pack = PackSerializer.export_full_backup(empty_campaign)
        assert len(pack.npcs) == 0
        assert pack.game_state is not None
        assert len(pack.sessions) == 0


# ---------------------------------------------------------------------------
# PackSerializer - Persistence Tests
# ---------------------------------------------------------------------------


class TestPackPersistence:
    """Tests for save and load of pack files."""

    def test_save_and_load_round_trip(
        self, sample_campaign: Campaign, packs_dir: Path
    ) -> None:
        """Saving and loading a pack should preserve all data."""
        original = PackSerializer.export_selective(
            sample_campaign,
            name="Round Trip Test",
            author="Test Author",
            tags=["test"],
        )
        file_path = PackSerializer.save_pack(original, packs_dir)
        assert file_path.exists()
        assert file_path.suffix == ".json"

        loaded = PackSerializer.load_pack(file_path)
        assert loaded.metadata.name == original.metadata.name
        assert loaded.metadata.author == original.metadata.author
        assert loaded.metadata.tags == original.metadata.tags
        assert loaded.metadata.source_campaign == original.metadata.source_campaign
        assert len(loaded.npcs) == len(original.npcs)
        assert len(loaded.locations) == len(original.locations)
        assert len(loaded.quests) == len(original.quests)
        assert len(loaded.encounters) == len(original.encounters)

    def test_save_creates_directory(self, tmp_path: Path, sample_campaign: Campaign) -> None:
        """save_pack should create the packs directory if needed."""
        packs_dir = tmp_path / "nonexistent" / "packs"
        pack = PackSerializer.export_selective(
            sample_campaign,
            name="Directory Test",
        )
        file_path = PackSerializer.save_pack(pack, packs_dir)
        assert file_path.exists()
        assert packs_dir.exists()

    def test_load_nonexistent_file_raises(self, tmp_path: Path) -> None:
        """Loading a nonexistent file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            PackSerializer.load_pack(tmp_path / "nonexistent.json")

    def test_saved_file_is_valid_json(
        self, sample_campaign: Campaign, packs_dir: Path
    ) -> None:
        """The saved file should be valid JSON."""
        pack = PackSerializer.export_selective(
            sample_campaign,
            name="JSON Validation Test",
        )
        file_path = PackSerializer.save_pack(pack, packs_dir)

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "metadata" in data
        assert data["metadata"]["name"] == "JSON Validation Test"

    def test_full_backup_round_trip(
        self, sample_campaign: Campaign, packs_dir: Path
    ) -> None:
        """Full backup should survive save/load round-trip with game_state and sessions."""
        original = PackSerializer.export_full_backup(sample_campaign)
        file_path = PackSerializer.save_pack(original, packs_dir)

        loaded = PackSerializer.load_pack(file_path)
        assert loaded.game_state is not None
        assert loaded.game_state["campaign_name"] == "Waterdeep Adventures"
        assert len(loaded.sessions) == 2


# ---------------------------------------------------------------------------
# Inter-entity Relationship Tests
# ---------------------------------------------------------------------------


class TestRelationshipPreservation:
    """Tests that inter-entity references are preserved in exports."""

    def test_npc_location_reference_preserved(self, sample_campaign: Campaign) -> None:
        """NPC location references should be preserved in the exported pack."""
        pack = PackSerializer.export_selective(
            sample_campaign,
            name="Relationship Test",
        )
        durnan = next(npc for npc in pack.npcs if npc["name"] == "Durnan")
        assert durnan["location"] == "Waterdeep"

        # Verify the referenced location also exists in the pack
        location_names = {loc["name"] for loc in pack.locations}
        assert durnan["location"] in location_names

    def test_quest_giver_reference_preserved(self, sample_campaign: Campaign) -> None:
        """Quest giver references should point to NPCs in the pack."""
        pack = PackSerializer.export_selective(
            sample_campaign,
            name="Quest Reference Test",
        )
        quest = next(q for q in pack.quests if q["title"] == "Find the Stone")
        assert quest["giver"] == "Durnan"

        npc_names = {npc["name"] for npc in pack.npcs}
        assert quest["giver"] in npc_names

    def test_location_npc_list_preserved(self, sample_campaign: Campaign) -> None:
        """Location NPC references should survive export."""
        # Add NPC reference to a location
        sample_campaign.locations["Waterdeep"].npcs = ["Durnan", "Laeral Silverhand"]

        pack = PackSerializer.export_selective(
            sample_campaign,
            name="Location NPCs Test",
        )
        waterdeep = next(loc for loc in pack.locations if loc["name"] == "Waterdeep")
        assert "Durnan" in waterdeep["npcs"]
        assert "Laeral Silverhand" in waterdeep["npcs"]
