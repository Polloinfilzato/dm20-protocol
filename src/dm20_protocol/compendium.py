"""
CompendiumPack model and serializer for portable campaign content export.

Provides the ability to export campaign entities (NPCs, locations, quests,
encounters) as self-contained pack files that can be shared, backed up,
or imported into other campaigns.

Key classes:
- PackMetadata: Creation timestamp, entity counts, source campaign info.
- CompendiumPack: Portable pack containing metadata and entity collections.
- PackSerializer: Extracts entities from a Campaign and produces pack JSON.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
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
