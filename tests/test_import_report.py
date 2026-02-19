"""Tests for enhanced import report and player name features (Issue #171)."""

import json
from pathlib import Path

import pytest

from dm20_protocol.importers.base import (
    ImportedField,
    ImportReport,
    ImportResult,
    ImportWarning,
    NotImported,
    _categorize_field,
    _generate_suggestions,
    _parse_warning,
    _summarize_field,
)
from dm20_protocol.importers.dndbeyond.mapper import map_ddb_to_character
from dm20_protocol.models import (
    AbilityScore,
    Character,
    CharacterClass,
    Race,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_character():
    """Create a sample character for testing."""
    return Character(
        name="Thorin Ironforge",
        player_name="Alice",
        classes=[CharacterClass(name="Fighter", level=8, hit_dice="d10")],
        race=Race(name="Dwarf", subrace="Hill"),
        background="Soldier",
        alignment="Lawful Good",
        abilities={
            "strength": AbilityScore(score=18),
            "dexterity": AbilityScore(score=14),
            "constitution": AbilityScore(score=16),
            "intelligence": AbilityScore(score=10),
            "wisdom": AbilityScore(score=12),
            "charisma": AbilityScore(score=8),
        },
        hit_points_max=76,
        hit_points_current=70,
        armor_class=18,
        speed=25,
        experience_points=34000,
        skill_proficiencies=["athletics", "intimidation"],
        saving_throw_proficiencies=["strength", "constitution"],
        languages=["Common", "Dwarvish"],
    )


@pytest.fixture
def import_result_success(sample_character):
    """Create a successful import result."""
    return ImportResult(
        character=sample_character,
        mapped_fields=[
            "name", "race", "classes", "background", "alignment",
            "abilities",
            "hit_points_max", "hit_points_current", "armor_class", "speed", "experience_points",
            "skill_proficiencies", "saving_throw_proficiencies", "languages",
            "inventory", "equipment",
            "spells_known", "spell_slots",
            "features", "notes",
        ],
        unmapped_fields=[],
        warnings=[],
        source="url",
        source_id=12345678,
    )


@pytest.fixture
def import_result_with_warnings(sample_character):
    """Create an import result with warnings."""
    return ImportResult(
        character=sample_character,
        mapped_fields=[
            "name", "race", "classes", "background", "alignment",
            "abilities",
            "hit_points_max", "hit_points_current", "armor_class", "speed",
        ],
        unmapped_fields=["spells_known", "spell_slots"],
        warnings=[
            "No classes found, defaulting to Fighter level 1",
            "Could not parse race speed, defaulting to 30",
            "Failed to parse inventory item: missing definition",
        ],
        source="file",
        source_id=None,
    )


@pytest.fixture
def ddb_sample():
    """Load the sample DDB character JSON."""
    path = Path(__file__).parent / "fixtures" / "ddb_character_sample.json"
    with open(path) as f:
        return json.load(f)


# ============================================================================
# ImportReport structure tests
# ============================================================================


class TestImportReportStructure:
    """Test ImportReport model and its sub-models."""

    def test_imported_field_model(self):
        """ImportedField stores name and summary."""
        field = ImportedField(name="abilities", summary="STR 18, DEX 14, CON 16")
        assert field.name == "abilities"
        assert field.summary == "STR 18, DEX 14, CON 16"

    def test_imported_field_default_summary(self):
        """ImportedField defaults to empty summary."""
        field = ImportedField(name="name")
        assert field.summary == ""

    def test_import_warning_model(self):
        """ImportWarning stores field, message, and suggestion."""
        warning = ImportWarning(
            field="classes",
            message="No classes found",
            suggestion="Verify character class on D&D Beyond",
        )
        assert warning.field == "classes"
        assert warning.message == "No classes found"
        assert warning.suggestion == "Verify character class on D&D Beyond"

    def test_import_warning_no_suggestion(self):
        """ImportWarning defaults to empty suggestion."""
        warning = ImportWarning(field="general", message="Something happened")
        assert warning.suggestion == ""

    def test_not_imported_model(self):
        """NotImported stores field and reason."""
        ni = NotImported(field="character_portrait", reason="Not supported")
        assert ni.field == "character_portrait"
        assert ni.reason == "Not supported"

    def test_import_report_status_values(self):
        """ImportReport accepts all valid status values."""
        for status in ["success", "success_with_warnings", "failed"]:
            report = ImportReport(status=status, character_name="Test")
            assert report.status == status

    def test_import_report_all_fields(self):
        """ImportReport stores all structured data."""
        report = ImportReport(
            status="success_with_warnings",
            character_name="Thorin",
            imported_fields=[ImportedField(name="name", summary="Thorin")],
            warnings=[ImportWarning(field="classes", message="Warning")],
            not_imported=[NotImported(field="portrait", reason="Unsupported")],
            suggestions=["Load a rulebook"],
        )
        assert report.character_name == "Thorin"
        assert len(report.imported_fields) == 1
        assert len(report.warnings) == 1
        assert len(report.not_imported) == 1
        assert len(report.suggestions) == 1


# ============================================================================
# ImportReport formatting tests
# ============================================================================


class TestImportReportFormatting:
    """Test ImportReport.format() output."""

    def test_format_header(self):
        """Format includes character name and status in header."""
        report = ImportReport(
            status="success",
            character_name="Thorin Ironforge",
        )
        output = report.format()
        assert "D&D Beyond Import Report - Thorin Ironforge" in output
        assert "Status: SUCCESS" in output

    def test_format_status_with_warnings(self):
        """Format displays 'SUCCESS WITH WARNINGS' for that status."""
        report = ImportReport(
            status="success_with_warnings",
            character_name="Test",
        )
        output = report.format()
        assert "Status: SUCCESS WITH WARNINGS" in output

    def test_format_status_failed(self):
        """Format displays 'FAILED' for that status."""
        report = ImportReport(
            status="failed",
            character_name="Test",
        )
        output = report.format()
        assert "Status: FAILED" in output

    def test_format_imported_fields(self):
        """Format lists imported fields grouped by category."""
        report = ImportReport(
            status="success",
            character_name="Test",
            imported_fields=[
                ImportedField(name="name", summary="Thorin"),
                ImportedField(name="race", summary="Hill Dwarf"),
                ImportedField(name="classes", summary="Fighter 8"),
                ImportedField(name="abilities", summary="STR 18, DEX 14"),
            ],
        )
        output = report.format()
        assert "Imported (4 fields):" in output
        assert "Identity:" in output
        assert "Thorin" in output
        assert "Abilities:" in output

    def test_format_warnings(self):
        """Format lists warnings with suggestions."""
        report = ImportReport(
            status="success_with_warnings",
            character_name="Test",
            warnings=[
                ImportWarning(
                    field="classes",
                    message="No classes found",
                    suggestion="Check D&D Beyond",
                ),
                ImportWarning(
                    field="speed",
                    message="Speed defaulted to 30",
                ),
            ],
        )
        output = report.format()
        assert "Warnings (2):" in output
        assert "No classes found" in output
        assert "Check D&D Beyond" in output
        assert "Speed defaulted to 30" in output

    def test_format_not_imported(self):
        """Format lists not-imported fields with reasons."""
        report = ImportReport(
            status="success_with_warnings",
            character_name="Test",
            not_imported=[
                NotImported(field="character_portrait", reason="Not supported"),
                NotImported(field="abilities", reason="Could not parse"),
            ],
        )
        output = report.format()
        assert "Not Imported (2):" in output
        assert "character_portrait: Not supported" in output
        assert "abilities: Could not parse" in output

    def test_format_suggestions(self):
        """Format lists actionable suggestions."""
        report = ImportReport(
            status="success_with_warnings",
            character_name="Test",
            suggestions=[
                "Load a rulebook for class validation",
                "Set player_name with update_character",
            ],
        )
        output = report.format()
        assert "Suggestions:" in output
        assert "Load a rulebook" in output
        assert "Set player_name" in output

    def test_format_empty_sections_omitted(self):
        """Format omits empty sections."""
        report = ImportReport(
            status="success",
            character_name="Test",
        )
        output = report.format()
        assert "Warnings" not in output
        assert "Not Imported" not in output
        assert "Suggestions" not in output
        # "Imported" should also be omitted when empty
        assert "Imported (0" not in output


# ============================================================================
# ImportResult.build_report() tests
# ============================================================================


class TestBuildReport:
    """Test ImportResult.build_report() conversion."""

    def test_build_report_success(self, import_result_success):
        """Successful import produces status='success'."""
        report = import_result_success.build_report()
        assert report.status == "success"
        assert report.character_name == "Thorin Ironforge"
        assert len(report.imported_fields) == len(import_result_success.mapped_fields)

    def test_build_report_with_warnings(self, import_result_with_warnings):
        """Import with warnings produces status='success_with_warnings'."""
        report = import_result_with_warnings.build_report()
        assert report.status == "success_with_warnings"
        assert len(report.warnings) == 3
        assert len(report.not_imported) > 0  # unmapped + DDB unsupported

    def test_build_report_failed(self, sample_character):
        """Import with no mapped fields produces status='failed'."""
        result = ImportResult(
            character=sample_character,
            mapped_fields=[],
            unmapped_fields=["name", "race", "classes", "abilities"],
            warnings=["Everything failed"],
            source="url",
        )
        report = result.build_report()
        assert report.status == "failed"

    def test_build_report_field_summaries(self, import_result_success):
        """Built report includes value summaries for imported fields."""
        report = import_result_success.build_report()

        # Find the name field
        name_field = next(f for f in report.imported_fields if f.name == "name")
        assert name_field.summary == "Thorin Ironforge"

        # Find abilities
        abilities_field = next(f for f in report.imported_fields if f.name == "abilities")
        assert "STR 18" in abilities_field.summary
        assert "DEX 14" in abilities_field.summary

        # Find classes
        classes_field = next(f for f in report.imported_fields if f.name == "classes")
        assert "Fighter" in classes_field.summary

    def test_build_report_unsupported_fields(self, import_result_success):
        """Built report includes DDB unsupported fields in not_imported."""
        report = import_result_success.build_report()
        not_imported_names = [ni.field for ni in report.not_imported]
        assert "character_portrait" in not_imported_names
        assert "character_theme" in not_imported_names

    def test_build_report_suggestions(self, sample_character):
        """Built report generates appropriate suggestions."""
        # Character with no player name
        char_no_player = sample_character.model_copy(update={"player_name": None})
        result = ImportResult(
            character=char_no_player,
            mapped_fields=["name"],
            unmapped_fields=[],
            warnings=[],
            source="url",
        )
        report = result.build_report()
        player_suggestion = [s for s in report.suggestions if "player_name" in s]
        assert len(player_suggestion) > 0

    def test_build_report_suggestions_class_warning(self, sample_character):
        """Suggestions include rulebook hint when class warnings present."""
        result = ImportResult(
            character=sample_character,
            mapped_fields=["name"],
            unmapped_fields=[],
            warnings=["No classes found, defaulting to Fighter"],
            source="url",
        )
        report = result.build_report()
        rulebook_suggestion = [s for s in report.suggestions if "rulebook" in s.lower()]
        assert len(rulebook_suggestion) > 0


# ============================================================================
# Helper function tests
# ============================================================================


class TestCategorizeField:
    """Test _categorize_field grouping."""

    def test_identity_fields(self):
        assert _categorize_field("name") == "Identity"
        assert _categorize_field("race") == "Identity"
        assert _categorize_field("classes") == "Identity"
        assert _categorize_field("background") == "Identity"
        assert _categorize_field("alignment") == "Identity"

    def test_ability_fields(self):
        assert _categorize_field("abilities") == "Abilities"

    def test_combat_fields(self):
        assert _categorize_field("hit_points_max") == "Combat"
        assert _categorize_field("armor_class") == "Combat"
        assert _categorize_field("speed") == "Combat"

    def test_proficiency_fields(self):
        assert _categorize_field("skill_proficiencies") == "Proficiencies"
        assert _categorize_field("languages") == "Proficiencies"

    def test_spell_fields(self):
        assert _categorize_field("spells_known") == "Spells"
        assert _categorize_field("spell_slots") == "Spells"

    def test_gear_fields(self):
        assert _categorize_field("inventory") == "Gear"
        assert _categorize_field("equipment") == "Gear"

    def test_unknown_fields(self):
        assert _categorize_field("unknown_field") == "Other"


class TestSummarizeField:
    """Test _summarize_field value summaries."""

    def test_summarize_name(self, sample_character):
        assert _summarize_field("name", sample_character) == "Thorin Ironforge"

    def test_summarize_race(self, sample_character):
        result = _summarize_field("race", sample_character)
        assert "Dwarf" in result
        assert "Hill" in result

    def test_summarize_classes(self, sample_character):
        result = _summarize_field("classes", sample_character)
        assert "Fighter" in result

    def test_summarize_abilities(self, sample_character):
        result = _summarize_field("abilities", sample_character)
        assert "STR 18" in result
        assert "DEX 14" in result

    def test_summarize_speed(self, sample_character):
        assert _summarize_field("speed", sample_character) == "25 ft"

    def test_summarize_armor_class(self, sample_character):
        assert _summarize_field("armor_class", sample_character) == "18"

    def test_summarize_unknown_field(self, sample_character):
        """Unknown fields return the field name as-is."""
        assert _summarize_field("totally_unknown", sample_character) == "totally_unknown"


class TestParseWarning:
    """Test _parse_warning structured parsing."""

    def test_parse_class_warning(self):
        w = _parse_warning("No classes found, defaulting to Fighter level 1")
        assert w.field == "classes"
        assert "class" in w.message.lower()
        assert w.suggestion != ""

    def test_parse_speed_warning(self):
        w = _parse_warning("Could not parse race speed, defaulting to 30")
        assert w.field == "speed"
        assert w.suggestion != ""

    def test_parse_inventory_warning(self):
        w = _parse_warning("Failed to parse inventory item: bad data")
        assert w.field == "inventory"

    def test_parse_generic_warning(self):
        w = _parse_warning("Something unexpected happened")
        assert w.field == "general"


class TestGenerateSuggestions:
    """Test _generate_suggestions logic."""

    def test_no_player_name_suggestion(self, sample_character):
        char = sample_character.model_copy(update={"player_name": None})
        suggestions = _generate_suggestions(char, [], [])
        assert any("player_name" in s for s in suggestions)

    def test_no_background_suggestion(self, sample_character):
        char = sample_character.model_copy(update={"background": None})
        suggestions = _generate_suggestions(char, [], [])
        assert any("background" in s.lower() for s in suggestions)

    def test_class_warning_suggests_rulebook(self, sample_character):
        suggestions = _generate_suggestions(
            sample_character, [], ["No classes found"]
        )
        assert any("rulebook" in s.lower() for s in suggestions)

    def test_unmapped_abilities(self, sample_character):
        suggestions = _generate_suggestions(
            sample_character, ["abilities"], []
        )
        assert any("ability" in s.lower() for s in suggestions)


# ============================================================================
# Full integration: DDB mapper -> ImportReport
# ============================================================================


class TestImportReportIntegration:
    """Test the full pipeline: DDB JSON -> ImportResult -> ImportReport -> formatted text."""

    def test_full_report_from_ddb(self, ddb_sample):
        """Full import produces a well-formatted report."""
        result = map_ddb_to_character(ddb_sample, player_name="Alice")
        report = result.build_report()

        assert report.character_name == "Thalion Nightbreeze"
        assert report.status in ("success", "success_with_warnings")
        assert len(report.imported_fields) > 0

        # Format should be valid text
        formatted = report.format()
        assert "D&D Beyond Import Report" in formatted
        assert "Thalion Nightbreeze" in formatted
        assert "Imported" in formatted

    def test_report_with_player_name(self, ddb_sample):
        """Player name flows through to the character."""
        result = map_ddb_to_character(ddb_sample, player_name="Bob")
        assert result.character.player_name == "Bob"

    def test_report_without_player_name(self, ddb_sample):
        """No player name generates a suggestion."""
        result = map_ddb_to_character(ddb_sample)
        report = result.build_report()
        assert any("player_name" in s for s in report.suggestions)

    def test_minimal_character_report(self):
        """Minimal DDB data still produces a valid report."""
        ddb = {
            "id": 999,
            "name": "Minimal",
            "race": {"fullName": "Human"},
            "classes": [{"level": 1, "definition": {"name": "Fighter"}}],
            "stats": [{"id": i, "value": 10} for i in range(1, 7)],
            "bonusStats": [],
            "overrideStats": [],
            "modifiers": {},
            "baseHitPoints": 10,
            "removedHitPoints": 0,
            "temporaryHitPoints": 0,
            "armorClass": 10,
            "currentXp": 0,
        }
        result = map_ddb_to_character(ddb, player_name="TestPlayer")
        report = result.build_report()

        assert report.status in ("success", "success_with_warnings")
        assert report.character_name == "Minimal"

        formatted = report.format()
        assert len(formatted) > 0
        assert "Minimal" in formatted


# ============================================================================
# Player name in list_characters and create_character
# ============================================================================


class TestPlayerNameInCharacter:
    """Test player_name field on Character model."""

    def test_character_with_player_name(self):
        """Character stores player_name."""
        char = Character(
            name="Thorin",
            player_name="Alice",
            classes=[CharacterClass(name="Fighter", level=1, hit_dice="d10")],
            race=Race(name="Dwarf"),
        )
        assert char.player_name == "Alice"

    def test_character_without_player_name(self):
        """Character defaults to None player_name."""
        char = Character(
            name="Thorin",
            classes=[CharacterClass(name="Fighter", level=1, hit_dice="d10")],
            race=Race(name="Dwarf"),
        )
        assert char.player_name is None

    def test_character_model_dump_includes_player_name(self):
        """model_dump() includes player_name."""
        char = Character(
            name="Thorin",
            player_name="Bob",
            classes=[CharacterClass(name="Fighter", level=1, hit_dice="d10")],
            race=Race(name="Dwarf"),
        )
        data = char.model_dump()
        assert "player_name" in data
        assert data["player_name"] == "Bob"

    def test_character_model_dump_null_player_name(self):
        """model_dump() includes null player_name when not set."""
        char = Character(
            name="Thorin",
            classes=[CharacterClass(name="Fighter", level=1, hit_dice="d10")],
            race=Race(name="Dwarf"),
        )
        data = char.model_dump()
        assert "player_name" in data
        assert data["player_name"] is None

    def test_player_name_in_json(self):
        """Player name serializes to JSON properly."""
        char = Character(
            name="Thorin",
            player_name="Alice",
            classes=[CharacterClass(name="Fighter", level=1, hit_dice="d10")],
            race=Race(name="Dwarf"),
        )
        json_data = char.model_dump(mode="json")
        assert json_data["player_name"] == "Alice"

    def test_ddb_import_sets_player_name(self, ddb_sample):
        """DDB import with player_name sets it on the character."""
        result = map_ddb_to_character(ddb_sample, player_name="Charlie")
        assert result.character.player_name == "Charlie"

    def test_ddb_import_no_player_name(self, ddb_sample):
        """DDB import without player_name leaves it None."""
        result = map_ddb_to_character(ddb_sample)
        assert result.character.player_name is None
