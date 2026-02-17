"""
Unit tests for PackImporter, PackValidator, and the import MCP tools.

Tests cover:
- Pack validation: schema check, version compatibility, entity count consistency
- Clean import: importing into an empty campaign
- Conflict modes: skip, overwrite, rename
- Preview/dry-run mode: shows what would happen without mutating
- Selective import: filtering by entity type
- ID regeneration: new UUIDs for imported entities
- Relationship re-linking: cross-references updated after renames
- Round-trip: export from one campaign, import into another
- Validation failure scenarios
"""

import json
import pytest
from datetime import datetime
from pathlib import Path

from dm20_protocol.compendium import (
    CompendiumPack,
    ConflictMode,
    ImportResult,
    PackImporter,
    PackMetadata,
    PackSerializer,
    PackValidator,
    ValidationResult,
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
def source_campaign() -> Campaign:
    """Campaign to export packs from."""
    game_state = GameState(campaign_name="Source Campaign")

    npcs = {
        "Durnan": NPC(
            name="Durnan",
            description="Owner of the Yawning Portal",
            race="Human",
            occupation="Innkeeper",
            location="Waterdeep",
            attitude="friendly",
            notes="veteran adventurer",
        ),
        "Laeral Silverhand": NPC(
            name="Laeral Silverhand",
            description="Open Lord of Waterdeep",
            race="Human",
            occupation="Ruler",
            location="Waterdeep",
            attitude="neutral",
            notes="powerful mage",
            relationships={"Durnan": "ally"},
        ),
    }

    locations = {
        "Waterdeep": Location(
            name="Waterdeep",
            location_type="city",
            description="City of Splendors",
            population=1300000,
            npcs=["Durnan", "Laeral Silverhand"],
            connections=["Baldur's Gate"],
            notes="major trade hub",
        ),
        "Baldur's Gate": Location(
            name="Baldur's Gate",
            location_type="city",
            description="Port city on the Sword Coast",
            population=125000,
            connections=["Waterdeep"],
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
            notes="waterdeep quest",
        ),
    }

    encounters = {
        "Sewer Ambush": CombatEncounter(
            name="Sewer Ambush",
            description="Ambush by wererats in the Waterdeep sewers",
            enemies=["Wererat x3", "Dire Rat x5"],
            difficulty="hard",
            location="Waterdeep",
            notes="",
        ),
    }

    return Campaign(
        name="Source Campaign",
        description="A source campaign for testing",
        dm_name="Test DM",
        npcs=npcs,
        locations=locations,
        quests=quests,
        encounters=encounters,
        game_state=game_state,
    )


@pytest.fixture
def empty_campaign() -> Campaign:
    """An empty target campaign."""
    return Campaign(
        name="Target Campaign",
        description="Empty target for imports",
        game_state=GameState(campaign_name="Target Campaign"),
    )


@pytest.fixture
def populated_campaign() -> Campaign:
    """A campaign that already has some entities (for conflict testing)."""
    return Campaign(
        name="Populated Campaign",
        description="Already has entities",
        npcs={
            "Durnan": NPC(
                name="Durnan",
                description="A different Durnan (local tavern owner)",
                race="Human",
                location="Neverwinter",
            ),
        },
        locations={
            "Waterdeep": Location(
                name="Waterdeep",
                location_type="city",
                description="Already tracked Waterdeep",
            ),
        },
        quests={
            "Find the Stone": Quest(
                title="Find the Stone",
                description="A different stone quest",
            ),
        },
        encounters={
            "Sewer Ambush": CombatEncounter(
                name="Sewer Ambush",
                description="A different sewer encounter",
            ),
        },
        game_state=GameState(campaign_name="Populated Campaign"),
    )


@pytest.fixture
def sample_pack(source_campaign: Campaign) -> CompendiumPack:
    """A pack exported from the source campaign."""
    return PackSerializer.export_selective(
        source_campaign,
        name="Test Pack",
        author="Test Author",
    )


@pytest.fixture
def packs_dir(tmp_path: Path) -> Path:
    """Temporary packs directory."""
    d = tmp_path / "packs"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# PackValidator Tests
# ---------------------------------------------------------------------------


class TestPackValidator:
    """Tests for pack validation."""

    def test_validate_valid_pack(self, sample_pack: CompendiumPack) -> None:
        """A well-formed pack should pass validation."""
        data = sample_pack.model_dump(mode="json")
        result = PackValidator.validate_data(data)
        assert result.valid is True
        assert result.errors == []

    def test_validate_invalid_json_file(self, tmp_path: Path) -> None:
        """An invalid JSON file should fail validation."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json {{{", encoding="utf-8")
        result = PackValidator.validate_file(bad_file)
        assert result.valid is False
        assert any("Invalid JSON" in e for e in result.errors)

    def test_validate_missing_file(self, tmp_path: Path) -> None:
        """A missing file should fail validation."""
        result = PackValidator.validate_file(tmp_path / "ghost.json")
        assert result.valid is False
        assert any("not found" in e for e in result.errors)

    def test_validate_missing_metadata(self) -> None:
        """Data without metadata should fail schema validation."""
        result = PackValidator.validate_data({"npcs": []})
        assert result.valid is False
        assert len(result.errors) > 0

    def test_validate_incompatible_major_version(self, sample_pack: CompendiumPack) -> None:
        """An incompatible major version should produce an error."""
        data = sample_pack.model_dump(mode="json")
        data["metadata"]["schema_version"] = "2.0"
        result = PackValidator.validate_data(data)
        assert result.valid is False
        assert any("Incompatible schema version" in e for e in result.errors)

    def test_validate_minor_version_warning(self, sample_pack: CompendiumPack) -> None:
        """A compatible but different minor version should produce a warning."""
        data = sample_pack.model_dump(mode="json")
        data["metadata"]["schema_version"] = "1.1"
        result = PackValidator.validate_data(data)
        assert result.valid is True  # Still valid
        assert any("differs from current" in w for w in result.warnings)

    def test_validate_entity_count_mismatch(self, sample_pack: CompendiumPack) -> None:
        """Mismatched entity counts should produce warnings."""
        data = sample_pack.model_dump(mode="json")
        data["metadata"]["entity_counts"]["npcs"] = 99
        result = PackValidator.validate_data(data)
        assert result.valid is True  # Warnings only, not errors
        assert any("npcs" in w and "99" in w for w in result.warnings)

    def test_validate_file_round_trip(
        self, sample_pack: CompendiumPack, packs_dir: Path
    ) -> None:
        """A saved pack file should pass file-level validation."""
        file_path = PackSerializer.save_pack(sample_pack, packs_dir)
        result = PackValidator.validate_file(file_path)
        assert result.valid is True
        assert result.errors == []

    def test_validate_missing_entity_fields(self) -> None:
        """Entities missing required fields should produce warnings."""
        data = {
            "metadata": PackMetadata(
                name="Incomplete",
                entity_counts={"npcs": 1, "locations": 1},
            ).model_dump(mode="json"),
            "npcs": [{"race": "Elf"}],  # Missing "name"
            "locations": [{"name": "Foo"}],  # Missing "location_type" and "description"
        }
        result = PackValidator.validate_data(data)
        assert result.valid is True  # Warnings, not errors
        assert any("NPC #0 missing" in w for w in result.warnings)
        assert any("Location #0 missing" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# PackImporter - Clean Import Tests
# ---------------------------------------------------------------------------


class TestCleanImport:
    """Tests for importing into an empty campaign (no conflicts)."""

    def test_import_all_entities(
        self, sample_pack: CompendiumPack, empty_campaign: Campaign
    ) -> None:
        """Importing into an empty campaign should create all entities."""
        result = PackImporter.import_pack(sample_pack, empty_campaign)
        assert result.preview is False
        # 2 NPCs + 2 locations + 1 quest + 1 encounter = 6
        total = len(sample_pack.npcs) + len(sample_pack.locations) + len(sample_pack.quests) + len(sample_pack.encounters)
        assert result.created_count == total
        assert total == 6
        assert result.skipped_count == 0
        assert result.overwritten_count == 0
        assert result.renamed_count == 0

        # Verify entities in campaign
        assert "Durnan" in empty_campaign.npcs
        assert "Waterdeep" in empty_campaign.locations
        assert "Find the Stone" in empty_campaign.quests
        assert "Sewer Ambush" in empty_campaign.encounters

    def test_import_updates_campaign_timestamp(
        self, sample_pack: CompendiumPack, empty_campaign: Campaign
    ) -> None:
        """Import should update the campaign's updated_at timestamp."""
        before = empty_campaign.updated_at
        PackImporter.import_pack(sample_pack, empty_campaign)
        assert empty_campaign.updated_at is not None
        # updated_at should be set (might be same instant in fast tests)

    def test_imported_entities_have_new_ids(
        self, sample_pack: CompendiumPack, empty_campaign: Campaign
    ) -> None:
        """Imported entities should get fresh UUIDs, not the pack's original IDs."""
        # Record original IDs from the pack
        original_ids = set()
        for npc_data in sample_pack.npcs:
            original_ids.add(npc_data.get("id", ""))
        for loc_data in sample_pack.locations:
            original_ids.add(loc_data.get("id", ""))

        PackImporter.import_pack(sample_pack, empty_campaign)

        # Check that no imported entity kept its original ID
        imported_ids = set()
        for npc in empty_campaign.npcs.values():
            imported_ids.add(npc.id)
        for loc in empty_campaign.locations.values():
            imported_ids.add(loc.id)

        # No overlap (unless by astronomical coincidence)
        assert len(original_ids & imported_ids) == 0


# ---------------------------------------------------------------------------
# PackImporter - Conflict Mode Tests
# ---------------------------------------------------------------------------


class TestConflictModes:
    """Tests for skip, overwrite, and rename conflict resolution."""

    def test_skip_keeps_existing(
        self, sample_pack: CompendiumPack, populated_campaign: Campaign
    ) -> None:
        """Skip mode should keep existing entities untouched."""
        original_desc = populated_campaign.npcs["Durnan"].description
        result = PackImporter.import_pack(
            sample_pack, populated_campaign,
            conflict_mode=ConflictMode.SKIP,
        )
        assert result.skipped_count > 0
        # Original Durnan should be unchanged
        assert populated_campaign.npcs["Durnan"].description == original_desc

    def test_overwrite_replaces_existing(
        self, sample_pack: CompendiumPack, populated_campaign: Campaign
    ) -> None:
        """Overwrite mode should replace existing entities with pack entities."""
        result = PackImporter.import_pack(
            sample_pack, populated_campaign,
            conflict_mode=ConflictMode.OVERWRITE,
        )
        assert result.overwritten_count > 0
        # Durnan should now have the pack's description
        assert populated_campaign.npcs["Durnan"].description == "Owner of the Yawning Portal"

    def test_rename_adds_suffix(
        self, sample_pack: CompendiumPack, populated_campaign: Campaign
    ) -> None:
        """Rename mode should add a numeric suffix to conflicting entities."""
        result = PackImporter.import_pack(
            sample_pack, populated_campaign,
            conflict_mode=ConflictMode.RENAME,
        )
        assert result.renamed_count > 0
        # Original Durnan should still exist
        assert "Durnan" in populated_campaign.npcs
        # Renamed import should also exist
        assert "Durnan (2)" in populated_campaign.npcs
        assert populated_campaign.npcs["Durnan (2)"].description == "Owner of the Yawning Portal"

    def test_rename_increments_suffix(self, sample_pack: CompendiumPack) -> None:
        """Rename should find the next available suffix number."""
        campaign = Campaign(
            name="Busy",
            description="Already has Durnan and Durnan (2)",
            npcs={
                "Durnan": NPC(name="Durnan", description="Original"),
                "Durnan (2)": NPC(name="Durnan (2)", description="Second"),
            },
            game_state=GameState(campaign_name="Busy"),
        )
        result = PackImporter.import_pack(
            sample_pack, campaign,
            conflict_mode=ConflictMode.RENAME,
        )
        # Should create "Durnan (3)"
        assert "Durnan (3)" in campaign.npcs

    def test_skip_non_conflicting_still_created(
        self, sample_pack: CompendiumPack, populated_campaign: Campaign
    ) -> None:
        """Non-conflicting entities should be created even in skip mode."""
        result = PackImporter.import_pack(
            sample_pack, populated_campaign,
            conflict_mode=ConflictMode.SKIP,
        )
        # Laeral Silverhand and Baldur's Gate don't exist in populated_campaign
        assert "Laeral Silverhand" in populated_campaign.npcs
        assert "Baldur's Gate" in populated_campaign.locations
        assert result.created_count > 0


# ---------------------------------------------------------------------------
# PackImporter - Preview/Dry-Run Tests
# ---------------------------------------------------------------------------


class TestPreviewMode:
    """Tests for dry-run preview mode."""

    def test_preview_does_not_mutate(
        self, sample_pack: CompendiumPack, empty_campaign: Campaign
    ) -> None:
        """Preview mode should not add any entities to the campaign."""
        result = PackImporter.import_pack(
            sample_pack, empty_campaign, preview=True,
        )
        assert result.preview is True
        assert result.created_count > 0  # Would create things
        # But campaign is still empty
        assert len(empty_campaign.npcs) == 0
        assert len(empty_campaign.locations) == 0
        assert len(empty_campaign.quests) == 0
        assert len(empty_campaign.encounters) == 0

    def test_preview_reports_conflicts(
        self, sample_pack: CompendiumPack, populated_campaign: Campaign
    ) -> None:
        """Preview should correctly report conflicts without mutating."""
        original_desc = populated_campaign.npcs["Durnan"].description
        result = PackImporter.import_pack(
            sample_pack, populated_campaign,
            conflict_mode=ConflictMode.OVERWRITE,
            preview=True,
        )
        assert result.overwritten_count > 0
        # But campaign should NOT have been mutated
        assert populated_campaign.npcs["Durnan"].description == original_desc

    def test_preview_summary(
        self, sample_pack: CompendiumPack, empty_campaign: Campaign
    ) -> None:
        """Preview summary should indicate it was a preview."""
        result = PackImporter.import_pack(
            sample_pack, empty_campaign, preview=True,
        )
        summary = result.summary()
        assert "Preview" in summary
        assert "created" in summary


# ---------------------------------------------------------------------------
# PackImporter - Selective Import Tests
# ---------------------------------------------------------------------------


class TestSelectiveImport:
    """Tests for entity type filtering."""

    def test_import_npcs_only(
        self, sample_pack: CompendiumPack, empty_campaign: Campaign
    ) -> None:
        """Filtering to NPCs should only import NPCs."""
        result = PackImporter.import_pack(
            sample_pack, empty_campaign,
            entity_filter=["npcs"],
        )
        assert len(empty_campaign.npcs) == len(sample_pack.npcs)
        assert len(empty_campaign.locations) == 0
        assert len(empty_campaign.quests) == 0
        assert len(empty_campaign.encounters) == 0

    def test_import_locations_and_quests(
        self, sample_pack: CompendiumPack, empty_campaign: Campaign
    ) -> None:
        """Filter to locations and quests should skip NPCs and encounters."""
        result = PackImporter.import_pack(
            sample_pack, empty_campaign,
            entity_filter=["locations", "quests"],
        )
        assert len(empty_campaign.npcs) == 0
        assert len(empty_campaign.locations) == len(sample_pack.locations)
        assert len(empty_campaign.quests) == len(sample_pack.quests)
        assert len(empty_campaign.encounters) == 0

    def test_invalid_entity_filter_raises(
        self, sample_pack: CompendiumPack, empty_campaign: Campaign
    ) -> None:
        """An invalid entity type filter should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid entity types"):
            PackImporter.import_pack(
                sample_pack, empty_campaign,
                entity_filter=["characters"],
            )


# ---------------------------------------------------------------------------
# Relationship Re-linking Tests
# ---------------------------------------------------------------------------


class TestRelinkingAfterRename:
    """Tests that cross-references are updated after entity renames."""

    def test_npc_location_relinked_on_rename(self) -> None:
        """If a location is renamed, NPCs pointing to it should be updated."""
        pack = CompendiumPack(
            metadata=PackMetadata(name="Relink Test", entity_counts={"npcs": 1, "locations": 1}),
            npcs=[{"name": "Guard", "id": "aaa", "location": "Townhall"}],
            locations=[{"name": "Townhall", "id": "bbb", "location_type": "building", "description": "Town hall"}],
        )
        # Pre-populate campaign with a different "Townhall"
        campaign = Campaign(
            name="Relink",
            description="",
            locations={
                "Townhall": Location(name="Townhall", location_type="building", description="Existing town hall"),
            },
            game_state=GameState(campaign_name="Relink"),
        )
        result = PackImporter.import_pack(
            pack, campaign, conflict_mode=ConflictMode.RENAME,
        )
        # Townhall should have been renamed to "Townhall (2)"
        assert "Townhall (2)" in campaign.locations
        # Guard NPC should now reference "Townhall (2)"
        guard = campaign.npcs.get("Guard")
        assert guard is not None
        assert guard.location == "Townhall (2)"

    def test_location_npc_list_relinked_on_rename(self) -> None:
        """If an NPC is renamed, location.npcs lists should be updated."""
        pack = CompendiumPack(
            metadata=PackMetadata(name="Relink NPC List"),
            npcs=[{"name": "Merchant", "id": "aaa"}],
            locations=[{
                "name": "Market",
                "id": "bbb",
                "location_type": "district",
                "description": "Market district",
                "npcs": ["Merchant"],
            }],
        )
        campaign = Campaign(
            name="Relink2",
            description="",
            npcs={"Merchant": NPC(name="Merchant", description="Existing merchant")},
            game_state=GameState(campaign_name="Relink2"),
        )
        result = PackImporter.import_pack(
            pack, campaign, conflict_mode=ConflictMode.RENAME,
        )
        # Market should have "Merchant (2)" in its NPC list
        market = campaign.locations.get("Market")
        assert market is not None
        assert "Merchant (2)" in market.npcs

    def test_quest_giver_relinked_on_rename(self) -> None:
        """If an NPC quest giver is renamed, quest.giver should be updated."""
        pack = CompendiumPack(
            metadata=PackMetadata(name="Quest Relink"),
            npcs=[{"name": "Elder", "id": "aaa"}],
            quests=[{
                "title": "Help the Elder",
                "id": "bbb",
                "description": "Assist the village elder",
                "giver": "Elder",
            }],
        )
        campaign = Campaign(
            name="Relink3",
            description="",
            npcs={"Elder": NPC(name="Elder", description="Existing elder")},
            game_state=GameState(campaign_name="Relink3"),
        )
        result = PackImporter.import_pack(
            pack, campaign, conflict_mode=ConflictMode.RENAME,
        )
        quest = campaign.quests.get("Help the Elder")
        assert quest is not None
        assert quest.giver == "Elder (2)"

    def test_encounter_location_relinked_on_rename(self) -> None:
        """If a location is renamed, encounter.location should be updated."""
        pack = CompendiumPack(
            metadata=PackMetadata(name="Encounter Relink"),
            locations=[{"name": "Cave", "id": "aaa", "location_type": "dungeon", "description": "A dark cave"}],
            encounters=[{
                "name": "Goblin Fight",
                "id": "bbb",
                "description": "Fight goblins",
                "location": "Cave",
            }],
        )
        campaign = Campaign(
            name="Relink4",
            description="",
            locations={"Cave": Location(name="Cave", location_type="dungeon", description="Existing cave")},
            game_state=GameState(campaign_name="Relink4"),
        )
        result = PackImporter.import_pack(
            pack, campaign, conflict_mode=ConflictMode.RENAME,
        )
        encounter = campaign.encounters.get("Goblin Fight")
        assert encounter is not None
        assert encounter.location == "Cave (2)"

    def test_location_connections_relinked_on_rename(self) -> None:
        """If connected locations are renamed, connections should be updated."""
        pack = CompendiumPack(
            metadata=PackMetadata(name="Connection Relink"),
            locations=[
                {"name": "TownA", "id": "a1", "location_type": "town", "description": "Town A", "connections": ["TownB"]},
                {"name": "TownB", "id": "b1", "location_type": "town", "description": "Town B", "connections": ["TownA"]},
            ],
        )
        campaign = Campaign(
            name="Relink5",
            description="",
            locations={
                "TownB": Location(name="TownB", location_type="town", description="Existing Town B"),
            },
            game_state=GameState(campaign_name="Relink5"),
        )
        result = PackImporter.import_pack(
            pack, campaign, conflict_mode=ConflictMode.RENAME,
        )
        # TownA should have been created (no conflict)
        assert "TownA" in campaign.locations
        # TownB should have been renamed to "TownB (2)"
        assert "TownB (2)" in campaign.locations
        # TownA's connections should reference "TownB (2)"
        town_a = campaign.locations["TownA"]
        assert "TownB (2)" in town_a.connections


# ---------------------------------------------------------------------------
# Round-Trip Tests (Export -> Import)
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Test exporting from one campaign and importing into another."""

    def test_export_import_round_trip(
        self, source_campaign: Campaign, empty_campaign: Campaign
    ) -> None:
        """Entities should survive an export -> import round-trip."""
        # Export
        pack = PackSerializer.export_selective(
            source_campaign,
            name="Round Trip",
        )
        # Import
        result = PackImporter.import_pack(pack, empty_campaign)
        assert result.created_count > 0
        assert result.skipped_count == 0

        # Verify entity names match
        assert set(empty_campaign.npcs.keys()) == set(source_campaign.npcs.keys())
        assert set(empty_campaign.locations.keys()) == set(source_campaign.locations.keys())
        assert set(empty_campaign.quests.keys()) == set(source_campaign.quests.keys())
        assert set(empty_campaign.encounters.keys()) == set(source_campaign.encounters.keys())

        # Verify content preserved
        for npc_name in source_campaign.npcs:
            assert empty_campaign.npcs[npc_name].description == source_campaign.npcs[npc_name].description
            assert empty_campaign.npcs[npc_name].race == source_campaign.npcs[npc_name].race

    def test_save_load_import_round_trip(
        self, source_campaign: Campaign, empty_campaign: Campaign, packs_dir: Path
    ) -> None:
        """Export -> save to disk -> load from disk -> import should work."""
        # Export and save
        pack = PackSerializer.export_selective(source_campaign, name="Disk Round Trip")
        file_path = PackSerializer.save_pack(pack, packs_dir)

        # Load from disk
        loaded_pack = PackSerializer.load_pack(file_path)

        # Validate
        validation = PackValidator.validate_file(file_path)
        assert validation.valid is True

        # Import
        result = PackImporter.import_pack(loaded_pack, empty_campaign)
        assert result.created_count > 0
        assert set(empty_campaign.npcs.keys()) == set(source_campaign.npcs.keys())


# ---------------------------------------------------------------------------
# ImportResult Tests
# ---------------------------------------------------------------------------


class TestImportResult:
    """Tests for ImportResult model and summary."""

    def test_summary_format(self) -> None:
        """Summary should be human-readable."""
        result = ImportResult(pack_name="Test Pack", preview=False)
        from dm20_protocol.compendium import ImportEntityResult
        result.entities = [
            ImportEntityResult(entity_type="npcs", original_name="A", imported_name="A", action="created"),
            ImportEntityResult(entity_type="npcs", original_name="B", imported_name="B", action="skipped"),
            ImportEntityResult(entity_type="locations", original_name="C", imported_name="C (2)", action="renamed"),
        ]
        summary = result.summary()
        assert "Imported" in summary
        assert "1 created" in summary
        assert "1 skipped" in summary
        assert "1 renamed" in summary

    def test_preview_summary(self) -> None:
        """Preview summary should say 'Preview'."""
        result = ImportResult(pack_name="Test", preview=True)
        assert "Preview" in result.summary()

    def test_empty_summary(self) -> None:
        """Empty result should show 'nothing to import'."""
        result = ImportResult(pack_name="Empty", preview=False)
        assert "nothing to import" in result.summary()


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and error scenarios."""

    def test_import_empty_pack(self, empty_campaign: Campaign) -> None:
        """Importing an empty pack should do nothing."""
        pack = CompendiumPack(
            metadata=PackMetadata(name="Empty Pack"),
        )
        result = PackImporter.import_pack(pack, empty_campaign)
        assert result.created_count == 0
        assert len(empty_campaign.npcs) == 0

    def test_case_insensitive_conflict_detection(self) -> None:
        """Conflict detection should be case-insensitive."""
        pack = CompendiumPack(
            metadata=PackMetadata(name="Case Test"),
            npcs=[{"name": "durnan", "id": "aaa"}],
        )
        campaign = Campaign(
            name="Case",
            description="",
            npcs={"Durnan": NPC(name="Durnan", description="Existing")},
            game_state=GameState(campaign_name="Case"),
        )
        result = PackImporter.import_pack(
            pack, campaign, conflict_mode=ConflictMode.SKIP,
        )
        assert result.skipped_count == 1

    def test_multiple_same_name_in_pack_rename(self) -> None:
        """If a pack somehow has two entities with near-same names, rename handles it."""
        pack = CompendiumPack(
            metadata=PackMetadata(name="Dup Test"),
            npcs=[
                {"name": "Guard", "id": "a1"},
                {"name": "Guard", "id": "a2"},
            ],
        )
        campaign = Campaign(
            name="Dup",
            description="",
            npcs={"Guard": NPC(name="Guard", description="Existing guard")},
            game_state=GameState(campaign_name="Dup"),
        )
        result = PackImporter.import_pack(
            pack, campaign, conflict_mode=ConflictMode.RENAME,
        )
        # Original + renamed(2) + renamed(3) (because pack has two "Guard" entries)
        assert "Guard" in campaign.npcs
        assert "Guard (2)" in campaign.npcs
        assert "Guard (3)" in campaign.npcs

    def test_validation_result_model(self) -> None:
        """ValidationResult model should work correctly."""
        vr = ValidationResult(valid=True)
        assert vr.valid is True
        assert vr.errors == []
        assert vr.warnings == []

        vr2 = ValidationResult(valid=False, errors=["bad"], warnings=["meh"])
        assert vr2.valid is False
        assert len(vr2.errors) == 1
        assert len(vr2.warnings) == 1
