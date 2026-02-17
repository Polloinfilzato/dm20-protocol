"""Bidirectional mapping between Character model and YAML frontmatter.

Defines which fields appear in the frontmatter, their editability tiers,
and conversion functions between the nested Pydantic model and a semi-flat dict.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel

from dm20_protocol.models import Character


class EditTier(str, Enum):
    """Who can edit a field in the character sheet.

    - player_free: auto-applied without DM review (hp_current, notes, etc.)
    - player_approval: queued for DM to approve/reject
    - dm_only: silently rejected if changed by player
    """
    PLAYER_FREE = "player_free"
    PLAYER_APPROVAL = "player_approval"
    DM_ONLY = "dm_only"


class FieldMapping(BaseModel):
    """Maps a frontmatter key to a Character model path."""
    frontmatter_key: str
    model_path: str  # dot-notation path into Character (e.g. "character_class.name")
    tier: EditTier
    section: str = ""  # grouping label for YAML comments


# --- Ordered field definitions ---
# Order here determines YAML output order.

FIELD_MAPPINGS: list[FieldMapping] = [
    # System (dm_only) - these are sheet-internal, not from Character model
    FieldMapping(frontmatter_key="dm20_id", model_path="id", tier=EditTier.DM_ONLY, section="System"),
    FieldMapping(frontmatter_key="dm20_version", model_path="_sync.dm20_version", tier=EditTier.DM_ONLY, section="System"),
    FieldMapping(frontmatter_key="dm20_last_sync", model_path="_sync.last_sync", tier=EditTier.DM_ONLY, section="System"),

    # Identity (player_approval)
    FieldMapping(frontmatter_key="name", model_path="name", tier=EditTier.PLAYER_APPROVAL, section="Identity"),
    FieldMapping(frontmatter_key="player", model_path="player_name", tier=EditTier.PLAYER_APPROVAL, section="Identity"),
    FieldMapping(frontmatter_key="class", model_path="character_class.name", tier=EditTier.PLAYER_APPROVAL, section="Identity"),
    FieldMapping(frontmatter_key="level", model_path="character_class.level", tier=EditTier.PLAYER_APPROVAL, section="Identity"),
    FieldMapping(frontmatter_key="subclass", model_path="character_class.subclass", tier=EditTier.PLAYER_APPROVAL, section="Identity"),
    FieldMapping(frontmatter_key="race", model_path="race.name", tier=EditTier.PLAYER_APPROVAL, section="Identity"),
    FieldMapping(frontmatter_key="subrace", model_path="race.subrace", tier=EditTier.PLAYER_APPROVAL, section="Identity"),
    FieldMapping(frontmatter_key="background", model_path="background", tier=EditTier.PLAYER_APPROVAL, section="Identity"),
    FieldMapping(frontmatter_key="alignment", model_path="alignment", tier=EditTier.PLAYER_APPROVAL, section="Identity"),
    FieldMapping(frontmatter_key="experience_points", model_path="experience_points", tier=EditTier.PLAYER_APPROVAL, section="Identity"),

    # Abilities (player_approval)
    FieldMapping(frontmatter_key="strength", model_path="abilities.strength.score", tier=EditTier.PLAYER_APPROVAL, section="Abilities"),
    FieldMapping(frontmatter_key="dexterity", model_path="abilities.dexterity.score", tier=EditTier.PLAYER_APPROVAL, section="Abilities"),
    FieldMapping(frontmatter_key="constitution", model_path="abilities.constitution.score", tier=EditTier.PLAYER_APPROVAL, section="Abilities"),
    FieldMapping(frontmatter_key="intelligence", model_path="abilities.intelligence.score", tier=EditTier.PLAYER_APPROVAL, section="Abilities"),
    FieldMapping(frontmatter_key="wisdom", model_path="abilities.wisdom.score", tier=EditTier.PLAYER_APPROVAL, section="Abilities"),
    FieldMapping(frontmatter_key="charisma", model_path="abilities.charisma.score", tier=EditTier.PLAYER_APPROVAL, section="Abilities"),

    # Combat (mixed)
    FieldMapping(frontmatter_key="armor_class", model_path="armor_class", tier=EditTier.DM_ONLY, section="Combat"),
    FieldMapping(frontmatter_key="hit_points_max", model_path="hit_points_max", tier=EditTier.DM_ONLY, section="Combat"),
    FieldMapping(frontmatter_key="hit_points_current", model_path="hit_points_current", tier=EditTier.PLAYER_FREE, section="Combat"),
    FieldMapping(frontmatter_key="temporary_hit_points", model_path="temporary_hit_points", tier=EditTier.PLAYER_FREE, section="Combat"),
    FieldMapping(frontmatter_key="speed", model_path="speed", tier=EditTier.DM_ONLY, section="Combat"),
    FieldMapping(frontmatter_key="hit_dice_type", model_path="hit_dice_type", tier=EditTier.DM_ONLY, section="Combat"),
    FieldMapping(frontmatter_key="hit_dice_remaining", model_path="hit_dice_remaining", tier=EditTier.DM_ONLY, section="Combat"),
    FieldMapping(frontmatter_key="inspiration", model_path="inspiration", tier=EditTier.PLAYER_FREE, section="Combat"),

    # Proficiencies (player_approval)
    FieldMapping(frontmatter_key="skill_proficiencies", model_path="skill_proficiencies", tier=EditTier.PLAYER_APPROVAL, section="Proficiencies"),
    FieldMapping(frontmatter_key="saving_throw_proficiencies", model_path="saving_throw_proficiencies", tier=EditTier.PLAYER_APPROVAL, section="Proficiencies"),
    FieldMapping(frontmatter_key="tool_proficiencies", model_path="tool_proficiencies", tier=EditTier.PLAYER_APPROVAL, section="Proficiencies"),
    FieldMapping(frontmatter_key="languages", model_path="languages", tier=EditTier.PLAYER_APPROVAL, section="Proficiencies"),

    # Spellcasting (mixed)
    FieldMapping(frontmatter_key="spellcasting_ability", model_path="spellcasting_ability", tier=EditTier.DM_ONLY, section="Spellcasting"),
    FieldMapping(frontmatter_key="spell_slots", model_path="spell_slots", tier=EditTier.DM_ONLY, section="Spellcasting"),
    FieldMapping(frontmatter_key="spell_slots_used", model_path="spell_slots_used", tier=EditTier.PLAYER_FREE, section="Spellcasting"),
    FieldMapping(frontmatter_key="spells_known", model_path="spells_known", tier=EditTier.PLAYER_APPROVAL, section="Spellcasting"),

    # Equipment (player_approval)
    FieldMapping(frontmatter_key="equipment", model_path="equipment", tier=EditTier.PLAYER_APPROVAL, section="Equipment"),
    FieldMapping(frontmatter_key="inventory", model_path="inventory", tier=EditTier.PLAYER_APPROVAL, section="Equipment"),

    # Features (dm_only)
    FieldMapping(frontmatter_key="features_and_traits", model_path="features_and_traits", tier=EditTier.DM_ONLY, section="Features"),
    FieldMapping(frontmatter_key="features", model_path="features", tier=EditTier.DM_ONLY, section="Features"),

    # Conditions (dm_only)
    FieldMapping(frontmatter_key="conditions", model_path="conditions", tier=EditTier.DM_ONLY, section="Conditions"),
    FieldMapping(frontmatter_key="active_effects", model_path="active_effects", tier=EditTier.DM_ONLY, section="Conditions"),

    # Text (player_free)
    FieldMapping(frontmatter_key="description", model_path="description", tier=EditTier.PLAYER_FREE, section="Text"),
    FieldMapping(frontmatter_key="bio", model_path="bio", tier=EditTier.PLAYER_FREE, section="Text"),
    FieldMapping(frontmatter_key="notes", model_path="notes", tier=EditTier.PLAYER_FREE, section="Text"),
]

# --- Lookup indexes built once at import time ---

_FIELD_BY_KEY: dict[str, FieldMapping] = {fm.frontmatter_key: fm for fm in FIELD_MAPPINGS}
_TIER_BY_KEY: dict[str, EditTier] = {fm.frontmatter_key: fm.tier for fm in FIELD_MAPPINGS}
_SYNC_INTERNAL_KEYS = {"dm20_version", "dm20_last_sync"}


class SheetSchema:
    """Bidirectional conversion between Character and frontmatter dict."""

    @staticmethod
    def get_tier(frontmatter_key: str) -> EditTier:
        """Return the editability tier for a frontmatter key."""
        return _TIER_BY_KEY.get(frontmatter_key, EditTier.DM_ONLY)

    @staticmethod
    def get_mapping(frontmatter_key: str) -> FieldMapping | None:
        """Return the FieldMapping for a frontmatter key."""
        return _FIELD_BY_KEY.get(frontmatter_key)

    @staticmethod
    def character_to_frontmatter(
        character: Character,
        *,
        sync_version: int = 1,
        sync_time: str = "",
    ) -> dict[str, Any]:
        """Convert a Character model to a semi-flat frontmatter dict.

        Nested models (Spell, Item, Feature, etc.) are serialized to
        plain dicts/lists for clean YAML output.
        """
        from datetime import datetime as dt

        if not sync_time:
            sync_time = dt.now().isoformat(timespec="seconds")

        fm: dict[str, Any] = {}

        for mapping in FIELD_MAPPINGS:
            key = mapping.frontmatter_key

            # Sync-internal fields
            if key == "dm20_version":
                fm[key] = sync_version
                continue
            if key == "dm20_last_sync":
                fm[key] = sync_time
                continue

            value = _resolve_model_path(character, mapping.model_path)
            fm[key] = _serialize_value(value)

        return fm

    @staticmethod
    def frontmatter_to_updates(
        frontmatter: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert frontmatter dict back to a flat updates dict.

        Returns a dict suitable for applying updates to a Character.
        Only includes fields that have corresponding model paths
        (skips sync-internal keys).
        """
        updates: dict[str, Any] = {}

        for key, value in frontmatter.items():
            if key in _SYNC_INTERNAL_KEYS:
                continue
            mapping = _FIELD_BY_KEY.get(key)
            if mapping is None:
                continue
            updates[mapping.model_path] = value

        return updates

    @staticmethod
    def apply_updates_to_character(
        character: Character,
        updates: dict[str, Any],
    ) -> list[str]:
        """Apply frontmatter-derived updates to a Character model.

        Args:
            character: The Character to update in-place.
            updates: Dict of model_path → new_value.

        Returns:
            List of field paths that were actually changed.
        """
        changed: list[str] = []

        for path, new_value in updates.items():
            old_value = _resolve_model_path(character, path)
            serialized_old = _serialize_value(old_value)

            if serialized_old == new_value:
                continue

            _set_model_path(character, path, new_value)
            changed.append(path)

        return changed


def _resolve_model_path(obj: Any, path: str) -> Any:
    """Walk a dot-notation path on a Pydantic model or dict.

    Examples:
        _resolve_model_path(char, "name") → "Aldric"
        _resolve_model_path(char, "character_class.name") → "Ranger"
        _resolve_model_path(char, "abilities.strength.score") → 16
    """
    parts = path.split(".")
    current = obj
    for part in parts:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, BaseModel):
            current = getattr(current, part, None)
        else:
            current = getattr(current, part, None)
    return current


def _set_model_path(obj: Any, path: str, value: Any) -> None:
    """Set a value at a dot-notation path on a Pydantic model or dict.

    Handles nested Pydantic models and dicts. For ability scores,
    wraps raw int in AbilityScore. For nested structures like
    equipment/inventory/spells, deserializes from plain dicts.
    """
    from dm20_protocol.models import (
        AbilityScore,
        ActiveEffect,
        Feature,
        Item,
        Spell,
    )

    parts = path.split(".")
    current = obj

    # Navigate to parent
    for part in parts[:-1]:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, BaseModel):
            current = getattr(current, part, None)

    if current is None:
        return

    final_key = parts[-1]

    # Special deserialization for known nested types
    if path.endswith(".score") and isinstance(value, int):
        # Setting an ability score value: parent is an AbilityScore
        if isinstance(current, AbilityScore):
            current.score = value
            return

    if final_key == "spells_known" and isinstance(value, list):
        value = [Spell(**s) if isinstance(s, dict) else s for s in value]
    elif final_key == "inventory" and isinstance(value, list):
        value = [Item(**i) if isinstance(i, dict) else i for i in value]
    elif final_key == "equipment" and isinstance(value, dict):
        value = {
            k: (Item(**v) if isinstance(v, dict) else None if v is None else v)
            for k, v in value.items()
        }
    elif final_key == "features" and isinstance(value, list):
        value = [Feature(**f) if isinstance(f, dict) else f for f in value]
    elif final_key == "active_effects" and isinstance(value, list):
        value = [ActiveEffect(**e) if isinstance(e, dict) else e for e in value]

    # Set the value
    if isinstance(current, dict):
        current[final_key] = value
    elif isinstance(current, BaseModel):
        setattr(current, final_key, value)


def _serialize_value(value: Any) -> Any:
    """Serialize a model value to a plain Python type for YAML output.

    Pydantic models → dicts, lists of models → lists of dicts, etc.
    """
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}
    if isinstance(value, Enum):
        return value.value
    # Primitives: str, int, float, bool
    return value
