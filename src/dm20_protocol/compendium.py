"""
CompendiumPack model, serializer, validator, and importer for portable campaign content.

Provides the ability to export campaign entities (NPCs, locations, quests,
encounters) as self-contained pack files that can be shared, backed up,
or imported into other campaigns.

Key classes:
- PackMetadata: Creation timestamp, entity counts, source campaign info.
- CompendiumPack: Portable pack containing metadata and entity collections.
- PackSerializer: Extracts entities from a Campaign and produces pack JSON.
- PackValidator: Schema and version checks for pack integrity.
- PackImporter: Loads pack content into campaigns with conflict resolution.
"""

import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from shortuuid import random as shortuuid_random

from .models import (
    Campaign,
    CombatEncounter,
    GameState,
    Location,
    NPC,
    Quest,
    SessionNote,
)

logger = logging.getLogger("dm20-protocol")

# Current pack schema version for forward-compatibility
PACK_SCHEMA_VERSION = "1.0"


class PackMetadata(BaseModel):
    """Metadata about a compendium pack.

    Tracks creation time, entity counts, source campaign, and
    authorship information for provenance and compatibility.
    """

    pack_id: str = Field(default_factory=lambda: shortuuid_random(length=12))
    name: str = Field(description="Human-readable pack name")
    description: str = Field(default="", description="Pack description")
    author: str = Field(default="", description="Pack author")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    system_version: str = Field(
        default="5e",
        description="Game system version (e.g., '5e', '5e-2024')",
    )
    schema_version: str = Field(
        default=PACK_SCHEMA_VERSION,
        description="Pack schema version for forward-compatibility",
    )
    source_campaign: str = Field(
        default="",
        description="Name of the campaign this pack was exported from",
    )
    created_at: datetime = Field(default_factory=datetime.now)
    entity_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Count of each entity type included in the pack",
    )


class CompendiumPack(BaseModel):
    """Portable collection of campaign entities.

    A CompendiumPack is a self-contained JSON-serializable bundle that
    holds NPCs, locations, quests, encounters, and optionally game state
    and session notes.  It is designed for sharing content between
    campaigns and for full campaign backups.
    """

    metadata: PackMetadata
    npcs: list[dict[str, Any]] = Field(default_factory=list)
    locations: list[dict[str, Any]] = Field(default_factory=list)
    quests: list[dict[str, Any]] = Field(default_factory=list)
    encounters: list[dict[str, Any]] = Field(default_factory=list)

    # Full-backup-only fields
    game_state: dict[str, Any] | None = Field(
        default=None,
        description="Game state snapshot (only included in full backups)",
    )
    sessions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Session notes (only included in full backups)",
    )


class PackSerializer:
    """Extracts entities from a Campaign and produces CompendiumPack objects.

    Supports:
    - Selective export by entity type (e.g., only NPCs).
    - Location-based filtering (e.g., NPCs whose location matches a filter).
    - Tag-based filtering (e.g., quests whose notes contain a tag).
    - Full campaign backup (all entities + game state + sessions).
    """

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @staticmethod
    def export_selective(
        campaign: Campaign,
        *,
        name: str,
        description: str = "",
        author: str = "",
        tags: list[str] | None = None,
        entity_types: list[str] | None = None,
        location_filter: str | None = None,
    ) -> CompendiumPack:
        """Export selected entities from a campaign.

        Args:
            campaign: Source campaign to export from.
            name: Name for the resulting pack.
            description: Pack description.
            author: Pack author.
            tags: Categorization tags.
            entity_types: Entity types to include.
                Accepted values: "npcs", "locations", "quests", "encounters".
                If None or empty, all types are included.
            location_filter: If provided, only include entities associated
                with this location (case-insensitive substring match).

        Returns:
            A CompendiumPack with the requested entities.
        """
        all_types = {"npcs", "locations", "quests", "encounters"}
        requested = set(entity_types) if entity_types else all_types

        # Validate requested types
        invalid = requested - all_types
        if invalid:
            raise ValueError(
                f"Invalid entity types: {invalid}. "
                f"Valid types: {sorted(all_types)}"
            )

        npcs: list[dict[str, Any]] = []
        locations: list[dict[str, Any]] = []
        quests: list[dict[str, Any]] = []
        encounters: list[dict[str, Any]] = []

        loc_lower = location_filter.lower() if location_filter else None

        if "npcs" in requested:
            for npc in campaign.npcs.values():
                npc_data = npc.model_dump(mode="json")
                if loc_lower:
                    npc_location = (npc.location or "").lower()
                    if loc_lower not in npc_location:
                        continue
                npcs.append(npc_data)

        if "locations" in requested:
            for loc in campaign.locations.values():
                loc_data = loc.model_dump(mode="json")
                if loc_lower:
                    loc_name = loc.name.lower()
                    if loc_lower not in loc_name:
                        continue
                locations.append(loc_data)

        if "quests" in requested:
            for quest in campaign.quests.values():
                quest_data = quest.model_dump(mode="json")
                if loc_lower:
                    # Filter quests by giver's location or quest notes
                    giver_name = quest.giver or ""
                    giver_npc = campaign.npcs.get(giver_name)
                    giver_location = (giver_npc.location or "").lower() if giver_npc else ""
                    quest_notes = quest.notes.lower()
                    if loc_lower not in giver_location and loc_lower not in quest_notes:
                        continue
                quests.append(quest_data)

        if "encounters" in requested:
            for enc in campaign.encounters.values():
                enc_data = enc.model_dump(mode="json")
                if loc_lower:
                    enc_location = (enc.location or "").lower()
                    if loc_lower not in enc_location:
                        continue
                encounters.append(enc_data)

        entity_counts = {
            "npcs": len(npcs),
            "locations": len(locations),
            "quests": len(quests),
            "encounters": len(encounters),
        }

        metadata = PackMetadata(
            name=name,
            description=description,
            author=author,
            tags=tags or [],
            source_campaign=campaign.name,
            entity_counts=entity_counts,
        )

        return CompendiumPack(
            metadata=metadata,
            npcs=npcs,
            locations=locations,
            quests=quests,
            encounters=encounters,
        )

    @staticmethod
    def export_full_backup(
        campaign: Campaign,
        *,
        name: str | None = None,
        author: str = "",
    ) -> CompendiumPack:
        """Export a full campaign backup including game state and sessions.

        This preserves all entities plus game state and session notes for
        complete campaign restoration.

        Args:
            campaign: Source campaign to export.
            name: Pack name (defaults to "{campaign.name} - Full Backup").
            author: Pack author.

        Returns:
            A CompendiumPack with all entities, game state, and sessions.
        """
        pack_name = name or f"{campaign.name} - Full Backup"

        npcs = [npc.model_dump(mode="json") for npc in campaign.npcs.values()]
        locations = [loc.model_dump(mode="json") for loc in campaign.locations.values()]
        quests = [q.model_dump(mode="json") for q in campaign.quests.values()]
        encounters = [enc.model_dump(mode="json") for enc in campaign.encounters.values()]
        game_state = campaign.game_state.model_dump(mode="json")
        sessions = [s.model_dump(mode="json") for s in campaign.sessions]

        entity_counts = {
            "npcs": len(npcs),
            "locations": len(locations),
            "quests": len(quests),
            "encounters": len(encounters),
            "sessions": len(sessions),
        }

        metadata = PackMetadata(
            name=pack_name,
            description=f"Full backup of campaign '{campaign.name}'",
            author=author,
            tags=["backup", "full"],
            source_campaign=campaign.name,
            entity_counts=entity_counts,
        )

        return CompendiumPack(
            metadata=metadata,
            npcs=npcs,
            locations=locations,
            quests=quests,
            encounters=encounters,
            game_state=game_state,
            sessions=sessions,
        )

    @staticmethod
    def export_by_tags(
        campaign: Campaign,
        *,
        name: str,
        filter_tags: list[str],
        description: str = "",
        author: str = "",
    ) -> CompendiumPack:
        """Export entities whose notes or tags contain any of the filter tags.

        Performs a case-insensitive substring match against NPC notes,
        location notes, quest notes, and encounter notes.

        Args:
            campaign: Source campaign.
            name: Pack name.
            filter_tags: Tags to match (case-insensitive).
            description: Pack description.
            author: Pack author.

        Returns:
            A CompendiumPack with matching entities.
        """
        tags_lower = [t.lower() for t in filter_tags]

        def _matches(text: str) -> bool:
            text_lower = text.lower()
            return any(tag in text_lower for tag in tags_lower)

        npcs = [
            npc.model_dump(mode="json")
            for npc in campaign.npcs.values()
            if _matches(npc.notes)
        ]
        locations = [
            loc.model_dump(mode="json")
            for loc in campaign.locations.values()
            if _matches(loc.notes)
        ]
        quests = [
            q.model_dump(mode="json")
            for q in campaign.quests.values()
            if _matches(q.notes)
        ]
        encounters = [
            enc.model_dump(mode="json")
            for enc in campaign.encounters.values()
            if _matches(enc.notes)
        ]

        entity_counts = {
            "npcs": len(npcs),
            "locations": len(locations),
            "quests": len(quests),
            "encounters": len(encounters),
        }

        metadata = PackMetadata(
            name=name,
            description=description,
            author=author,
            tags=filter_tags,
            source_campaign=campaign.name,
            entity_counts=entity_counts,
        )

        return CompendiumPack(
            metadata=metadata,
            npcs=npcs,
            locations=locations,
            quests=quests,
            encounters=encounters,
        )

    # ------------------------------------------------------------------ #
    # Persistence helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def save_pack(pack: CompendiumPack, packs_dir: Path) -> Path:
        """Serialize a CompendiumPack to a JSON file.

        The file is saved as ``{packs_dir}/{pack_id}.json``.

        Args:
            pack: The pack to save.
            packs_dir: Directory to write the pack file into.

        Returns:
            Path to the written JSON file.
        """
        packs_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize the pack name for use as a filename
        safe_name = "".join(
            c for c in pack.metadata.name if c.isalnum() or c in (" ", "-", "_")
        ).strip().replace(" ", "-").lower()
        filename = f"{safe_name}_{pack.metadata.pack_id}.json"
        file_path = packs_dir / filename

        pack_data = pack.model_dump(mode="json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(pack_data, f, indent=2, default=str)

        logger.info(f"Saved compendium pack to {file_path}")
        return file_path

    @staticmethod
    def load_pack(file_path: Path) -> CompendiumPack:
        """Load a CompendiumPack from a JSON file.

        Args:
            file_path: Path to the pack JSON file.

        Returns:
            Deserialized CompendiumPack.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Pack file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return CompendiumPack.model_validate(data)


# ====================================================================== #
# Validation
# ====================================================================== #


class ValidationResult(BaseModel):
    """Result of a pack validation check."""

    valid: bool = Field(description="Whether the pack is valid")
    errors: list[str] = Field(default_factory=list, description="Validation error messages")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings")


class PackValidator:
    """Validates a CompendiumPack for schema conformance and version compatibility.

    Checks:
    - JSON structure can be parsed into a CompendiumPack (schema validation).
    - schema_version is compatible with the current PACK_SCHEMA_VERSION.
    - Entity counts in metadata match the actual entity lists.
    - Required fields are present in entity dicts.
    """

    # Compatible schema versions (major version must match)
    COMPATIBLE_MAJOR = "1"

    @classmethod
    def validate_file(cls, file_path: Path) -> ValidationResult:
        """Validate a pack JSON file.

        Args:
            file_path: Path to the pack JSON file.

        Returns:
            ValidationResult with errors/warnings.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not file_path.exists():
            return ValidationResult(valid=False, errors=[f"File not found: {file_path}"])

        # Step 1: JSON parse
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except json.JSONDecodeError as e:
            return ValidationResult(valid=False, errors=[f"Invalid JSON: {e}"])

        return cls.validate_data(raw_data)

    @classmethod
    def validate_data(cls, raw_data: dict[str, Any]) -> ValidationResult:
        """Validate pack data (already parsed from JSON).

        Args:
            raw_data: Dictionary parsed from pack JSON.

        Returns:
            ValidationResult with errors/warnings.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Step 1: Pydantic schema validation
        try:
            pack = CompendiumPack.model_validate(raw_data)
        except ValidationError as e:
            error_messages = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
            return ValidationResult(valid=False, errors=error_messages)

        # Step 2: Version compatibility check
        schema_version = pack.metadata.schema_version
        try:
            major = schema_version.split(".")[0]
            if major != cls.COMPATIBLE_MAJOR:
                errors.append(
                    f"Incompatible schema version '{schema_version}'. "
                    f"Expected major version {cls.COMPATIBLE_MAJOR}.x "
                    f"(current: {PACK_SCHEMA_VERSION})"
                )
        except (IndexError, AttributeError):
            errors.append(f"Invalid schema version format: '{schema_version}'")

        if schema_version != PACK_SCHEMA_VERSION:
            warnings.append(
                f"Schema version '{schema_version}' differs from current "
                f"'{PACK_SCHEMA_VERSION}'. Minor differences are tolerated."
            )

        # Step 3: Entity count consistency
        expected_counts = pack.metadata.entity_counts
        actual_counts = {
            "npcs": len(pack.npcs),
            "locations": len(pack.locations),
            "quests": len(pack.quests),
            "encounters": len(pack.encounters),
        }
        if pack.sessions:
            actual_counts["sessions"] = len(pack.sessions)

        for entity_type, actual in actual_counts.items():
            expected = expected_counts.get(entity_type)
            if expected is not None and expected != actual:
                warnings.append(
                    f"Metadata declares {expected} {entity_type} but pack "
                    f"contains {actual}"
                )

        # Step 4: Required fields in entities
        _npc_required = {"name"}
        _loc_required = {"name", "location_type", "description"}
        _quest_required = {"title", "description"}
        _enc_required = {"name", "description"}

        for i, npc_data in enumerate(pack.npcs):
            missing = _npc_required - set(npc_data.keys())
            if missing:
                warnings.append(f"NPC #{i} missing fields: {missing}")

        for i, loc_data in enumerate(pack.locations):
            missing = _loc_required - set(loc_data.keys())
            if missing:
                warnings.append(f"Location #{i} missing fields: {missing}")

        for i, quest_data in enumerate(pack.quests):
            missing = _quest_required - set(quest_data.keys())
            if missing:
                warnings.append(f"Quest #{i} missing fields: {missing}")

        for i, enc_data in enumerate(pack.encounters):
            missing = _enc_required - set(enc_data.keys())
            if missing:
                warnings.append(f"Encounter #{i} missing fields: {missing}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )


# ====================================================================== #
# Import
# ====================================================================== #


class ConflictMode(str, Enum):
    """Strategy for handling name collisions during import."""

    SKIP = "skip"        # Keep existing entity, discard imported one
    OVERWRITE = "overwrite"  # Replace existing entity with imported one
    RENAME = "rename"    # Add numeric suffix to imported entity name


class ImportEntityResult(BaseModel):
    """Outcome of importing a single entity."""

    entity_type: str
    original_name: str
    imported_name: str
    action: str = Field(description="'created', 'skipped', 'overwritten', or 'renamed'")


class ImportResult(BaseModel):
    """Aggregate outcome of a pack import operation."""

    pack_name: str
    preview: bool = Field(description="True if this was a dry-run preview")
    entities: list[ImportEntityResult] = Field(default_factory=list)

    @property
    def created_count(self) -> int:
        return sum(1 for e in self.entities if e.action == "created")

    @property
    def skipped_count(self) -> int:
        return sum(1 for e in self.entities if e.action == "skipped")

    @property
    def overwritten_count(self) -> int:
        return sum(1 for e in self.entities if e.action == "overwritten")

    @property
    def renamed_count(self) -> int:
        return sum(1 for e in self.entities if e.action == "renamed")

    def summary(self) -> str:
        """Human-readable import summary."""
        mode = "Preview" if self.preview else "Imported"
        parts = []
        if self.created_count:
            parts.append(f"{self.created_count} created")
        if self.skipped_count:
            parts.append(f"{self.skipped_count} skipped")
        if self.overwritten_count:
            parts.append(f"{self.overwritten_count} overwritten")
        if self.renamed_count:
            parts.append(f"{self.renamed_count} renamed")
        detail = ", ".join(parts) if parts else "nothing to import"
        return f"{mode} pack '{self.pack_name}': {detail}"


class PackImporter:
    """Imports a CompendiumPack into a Campaign with conflict resolution.

    Supports:
    - Three conflict modes: skip, overwrite, rename.
    - Preview/dry-run mode (no mutations).
    - Selective import by entity type or specific entity names.
    - ID regeneration to avoid collisions across campaigns.
    - Relationship re-linking after ID regeneration.
    """

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @classmethod
    def import_pack(
        cls,
        pack: CompendiumPack,
        campaign: Campaign,
        *,
        conflict_mode: ConflictMode = ConflictMode.SKIP,
        preview: bool = False,
        entity_filter: list[str] | None = None,
    ) -> ImportResult:
        """Import pack entities into a campaign.

        Args:
            pack: The CompendiumPack to import.
            campaign: Target campaign to import into.
            conflict_mode: How to handle name collisions.
            preview: If True, compute what would happen without mutating campaign.
            entity_filter: Restrict to these entity types
                (e.g. ``["npcs", "locations"]``). None = all types.

        Returns:
            ImportResult describing every entity action.
        """
        all_types = {"npcs", "locations", "quests", "encounters"}
        requested = set(entity_filter) if entity_filter else all_types

        invalid = requested - all_types
        if invalid:
            raise ValueError(
                f"Invalid entity types: {invalid}. "
                f"Valid types: {sorted(all_types)}"
            )

        result = ImportResult(pack_name=pack.metadata.name, preview=preview)

        # Phase 1: Regenerate IDs and build old->new mapping
        id_map: dict[str, str] = {}
        name_map: dict[str, str] = {}  # old_name -> new_name (for renames)

        # Collect entities to import, regenerating IDs
        import_npcs: list[dict[str, Any]] = []
        import_locations: list[dict[str, Any]] = []
        import_quests: list[dict[str, Any]] = []
        import_encounters: list[dict[str, Any]] = []

        if "npcs" in requested:
            for npc_data in pack.npcs:
                new_data = cls._regenerate_id(npc_data, id_map)
                import_npcs.append(new_data)

        if "locations" in requested:
            for loc_data in pack.locations:
                new_data = cls._regenerate_id(loc_data, id_map)
                import_locations.append(new_data)

        if "quests" in requested:
            for quest_data in pack.quests:
                new_data = cls._regenerate_id(quest_data, id_map)
                import_quests.append(new_data)

        if "encounters" in requested:
            for enc_data in pack.encounters:
                new_data = cls._regenerate_id(enc_data, id_map)
                import_encounters.append(new_data)

        # Phase 2: Resolve conflicts and determine final names
        cls._resolve_entities(
            import_npcs, campaign.npcs, "npcs", "name",
            conflict_mode, result, name_map,
        )
        cls._resolve_entities(
            import_locations, campaign.locations, "locations", "name",
            conflict_mode, result, name_map,
        )
        cls._resolve_entities(
            import_quests, campaign.quests, "quests", "title",
            conflict_mode, result, name_map,
        )
        cls._resolve_entities(
            import_encounters, campaign.encounters, "encounters", "name",
            conflict_mode, result, name_map,
        )

        # Phase 3: Re-link cross-references using name_map
        cls._relink_npcs(import_npcs, name_map)
        cls._relink_locations(import_locations, name_map)
        cls._relink_quests(import_quests, name_map)
        cls._relink_encounters(import_encounters, name_map)

        # Phase 4: Apply to campaign (skip if preview)
        if not preview:
            cls._apply_npcs(import_npcs, campaign, result)
            cls._apply_locations(import_locations, campaign, result)
            cls._apply_quests(import_quests, campaign, result)
            cls._apply_encounters(import_encounters, campaign, result)
            campaign.updated_at = datetime.now()

        return result

    # ------------------------------------------------------------------ #
    # ID Regeneration
    # ------------------------------------------------------------------ #

    @staticmethod
    def _regenerate_id(
        entity_data: dict[str, Any],
        id_map: dict[str, str],
    ) -> dict[str, Any]:
        """Create a copy of entity data with a new UUID, recording the mapping.

        Args:
            entity_data: Original entity dict.
            id_map: Mutable mapping of old_id -> new_id (updated in-place).

        Returns:
            Shallow copy of entity_data with a fresh ``id`` field.
        """
        new_data = dict(entity_data)
        old_id = new_data.get("id", "")
        new_id = shortuuid_random(length=8)
        new_data["id"] = new_id
        if old_id:
            id_map[old_id] = new_id
        return new_data

    # ------------------------------------------------------------------ #
    # Conflict Resolution
    # ------------------------------------------------------------------ #

    @classmethod
    def _resolve_entities(
        cls,
        entities: list[dict[str, Any]],
        existing: dict[str, Any],
        entity_type: str,
        name_field: str,
        conflict_mode: ConflictMode,
        result: ImportResult,
        name_map: dict[str, str],
    ) -> None:
        """Determine the action (create/skip/overwrite/rename) for each entity.

        Modifies ``entities`` in-place to update names for renames, and
        populates ``result.entities`` with the action taken for each entity.

        Conflict detection is case-insensitive by name/title.

        Args:
            entities: List of entity dicts to import.
            existing: Current campaign entities dict (keyed by name/title).
            entity_type: Type label (e.g., "npcs").
            name_field: Key used for the entity name ("name" or "title").
            conflict_mode: Conflict resolution strategy.
            result: ImportResult to populate.
            name_map: Mutable old_name -> new_name mapping (for renames).
        """
        # Build case-insensitive index of existing names
        existing_lower = {k.lower(): k for k in existing.keys()}

        for entity_data in entities:
            original_name = entity_data.get(name_field, "Unknown")
            name_lower = original_name.lower()

            if name_lower in existing_lower:
                # Conflict detected
                if conflict_mode == ConflictMode.SKIP:
                    result.entities.append(ImportEntityResult(
                        entity_type=entity_type,
                        original_name=original_name,
                        imported_name=original_name,
                        action="skipped",
                    ))
                elif conflict_mode == ConflictMode.OVERWRITE:
                    result.entities.append(ImportEntityResult(
                        entity_type=entity_type,
                        original_name=original_name,
                        imported_name=original_name,
                        action="overwritten",
                    ))
                elif conflict_mode == ConflictMode.RENAME:
                    new_name = cls._unique_name(original_name, existing_lower)
                    entity_data[name_field] = new_name
                    name_map[original_name] = new_name
                    # Track the new name in existing_lower to avoid double-rename
                    existing_lower[new_name.lower()] = new_name
                    result.entities.append(ImportEntityResult(
                        entity_type=entity_type,
                        original_name=original_name,
                        imported_name=new_name,
                        action="renamed",
                    ))
            else:
                # No conflict
                # Track this name so subsequent pack entities don't collide
                existing_lower[name_lower] = original_name
                result.entities.append(ImportEntityResult(
                    entity_type=entity_type,
                    original_name=original_name,
                    imported_name=original_name,
                    action="created",
                ))

    @staticmethod
    def _unique_name(base_name: str, existing_lower: dict[str, str]) -> str:
        """Generate a unique name by appending a numeric suffix.

        Args:
            base_name: Original entity name.
            existing_lower: Lowercase mapping of already-used names.

        Returns:
            A name like "Durnan (2)" that doesn't collide.
        """
        counter = 2
        while True:
            candidate = f"{base_name} ({counter})"
            if candidate.lower() not in existing_lower:
                return candidate
            counter += 1

    # ------------------------------------------------------------------ #
    # Relationship Re-linking
    # ------------------------------------------------------------------ #

    @staticmethod
    def _relink_npcs(
        npcs: list[dict[str, Any]],
        name_map: dict[str, str],
    ) -> None:
        """Update NPC cross-references after renames.

        Fields updated:
        - ``location``: name of a Location.
        - ``relationships``: dict mapping character/NPC names to descriptions.
        """
        for npc_data in npcs:
            # Location reference
            loc = npc_data.get("location")
            if loc and loc in name_map:
                npc_data["location"] = name_map[loc]

            # Relationships dict: keys are character/NPC names
            rels = npc_data.get("relationships")
            if rels and isinstance(rels, dict):
                new_rels = {}
                for rel_name, rel_desc in rels.items():
                    new_key = name_map.get(rel_name, rel_name)
                    new_rels[new_key] = rel_desc
                npc_data["relationships"] = new_rels

    @staticmethod
    def _relink_locations(
        locations: list[dict[str, Any]],
        name_map: dict[str, str],
    ) -> None:
        """Update Location cross-references after renames.

        Fields updated:
        - ``npcs``: list of NPC names.
        - ``connections``: list of connected Location names.
        """
        for loc_data in locations:
            # NPC name list
            npc_names = loc_data.get("npcs")
            if npc_names and isinstance(npc_names, list):
                loc_data["npcs"] = [name_map.get(n, n) for n in npc_names]

            # Connected location names
            connections = loc_data.get("connections")
            if connections and isinstance(connections, list):
                loc_data["connections"] = [name_map.get(c, c) for c in connections]

    @staticmethod
    def _relink_quests(
        quests: list[dict[str, Any]],
        name_map: dict[str, str],
    ) -> None:
        """Update Quest cross-references after renames.

        Fields updated:
        - ``giver``: NPC name who gave the quest.
        """
        for quest_data in quests:
            giver = quest_data.get("giver")
            if giver and giver in name_map:
                quest_data["giver"] = name_map[giver]

    @staticmethod
    def _relink_encounters(
        encounters: list[dict[str, Any]],
        name_map: dict[str, str],
    ) -> None:
        """Update CombatEncounter cross-references after renames.

        Fields updated:
        - ``location``: Location name.
        """
        for enc_data in encounters:
            loc = enc_data.get("location")
            if loc and loc in name_map:
                enc_data["location"] = name_map[loc]

    # ------------------------------------------------------------------ #
    # Apply to Campaign
    # ------------------------------------------------------------------ #

    @staticmethod
    def _apply_npcs(
        npcs: list[dict[str, Any]],
        campaign: Campaign,
        result: ImportResult,
    ) -> None:
        """Materialize NPC dicts into the campaign."""
        # Build a quick lookup of result actions by (entity_type, original_name)
        action_map: dict[str, str] = {}
        for er in result.entities:
            if er.entity_type == "npcs":
                action_map[er.imported_name] = er.action

        for npc_data in npcs:
            name = npc_data.get("name", "")
            action = action_map.get(name, "")
            if action == "skipped":
                continue
            npc = NPC.model_validate(npc_data)
            campaign.npcs[npc.name] = npc

    @staticmethod
    def _apply_locations(
        locations: list[dict[str, Any]],
        campaign: Campaign,
        result: ImportResult,
    ) -> None:
        """Materialize Location dicts into the campaign."""
        action_map: dict[str, str] = {}
        for er in result.entities:
            if er.entity_type == "locations":
                action_map[er.imported_name] = er.action

        for loc_data in locations:
            name = loc_data.get("name", "")
            action = action_map.get(name, "")
            if action == "skipped":
                continue
            loc = Location.model_validate(loc_data)
            campaign.locations[loc.name] = loc

    @staticmethod
    def _apply_quests(
        quests: list[dict[str, Any]],
        campaign: Campaign,
        result: ImportResult,
    ) -> None:
        """Materialize Quest dicts into the campaign."""
        action_map: dict[str, str] = {}
        for er in result.entities:
            if er.entity_type == "quests":
                action_map[er.imported_name] = er.action

        for quest_data in quests:
            title = quest_data.get("title", "")
            action = action_map.get(title, "")
            if action == "skipped":
                continue
            quest = Quest.model_validate(quest_data)
            campaign.quests[quest.title] = quest

    @staticmethod
    def _apply_encounters(
        encounters: list[dict[str, Any]],
        campaign: Campaign,
        result: ImportResult,
    ) -> None:
        """Materialize CombatEncounter dicts into the campaign."""
        action_map: dict[str, str] = {}
        for er in result.entities:
            if er.entity_type == "encounters":
                action_map[er.imported_name] = er.action

        for enc_data in encounters:
            name = enc_data.get("name", "")
            action = action_map.get(name, "")
            if action == "skipped":
                continue
            enc = CombatEncounter.model_validate(enc_data)
            campaign.encounters[enc.name] = enc
