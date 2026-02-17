"""Diff engine: compare YAML frontmatter with Character JSON data.

Detects changes, classifies them by editability tier, and produces
human-readable diffs for DM review.
"""

from __future__ import annotations

import logging
from typing import Any

from dm20_protocol.models import Character
from dm20_protocol.sheets.models import FieldChange, SheetDiff
from dm20_protocol.sheets.schema import (
    FIELD_MAPPINGS,
    EditTier,
    SheetSchema,
    _resolve_model_path,
    _serialize_value,
)

logger = logging.getLogger(__name__)


class SheetDiffEngine:
    """Compares frontmatter dict against Character JSON, classifying changes by tier."""

    @staticmethod
    def compute_diff(
        character: Character,
        frontmatter: dict[str, Any],
    ) -> SheetDiff:
        """Compare frontmatter against character data and produce a classified diff.

        Args:
            character: The current Character model (source of truth).
            frontmatter: Parsed YAML frontmatter from the edited MD file.

        Returns:
            SheetDiff with changes categorized into free/approval/rejected.
        """
        all_changes: list[FieldChange] = []
        free: list[FieldChange] = []
        approval: list[FieldChange] = []
        rejected: list[FieldChange] = []

        for mapping in FIELD_MAPPINGS:
            key = mapping.frontmatter_key

            # Skip sync-internal fields (dm20_version, dm20_last_sync)
            if key in {"dm20_version", "dm20_last_sync"}:
                continue

            # Skip if the key is not in the edited frontmatter
            if key not in frontmatter:
                continue

            new_value = frontmatter[key]
            old_value = _resolve_model_path(character, mapping.model_path)
            old_serialized = _serialize_value(old_value)

            if _values_equal(old_serialized, new_value):
                continue

            display = _format_change(key, old_serialized, new_value)
            change = FieldChange(
                field=key,
                old_value=old_serialized,
                new_value=new_value,
                tier=mapping.tier.value,
                display=display,
            )

            all_changes.append(change)
            if mapping.tier == EditTier.PLAYER_FREE:
                free.append(change)
            elif mapping.tier == EditTier.PLAYER_APPROVAL:
                approval.append(change)
            else:  # DM_ONLY
                rejected.append(change)

        has_changes = len(all_changes) > 0

        if rejected:
            logger.warning(
                "Player attempted to change dm_only fields for %s: %s",
                character.name,
                [c.field for c in rejected],
            )

        return SheetDiff(
            character_name=character.name,
            character_id=character.id,
            changes=all_changes,
            free_changes=free,
            approval_changes=approval,
            rejected_changes=rejected,
            has_changes=has_changes,
        )

    @staticmethod
    def format_diff_report(diff: SheetDiff) -> str:
        """Format a diff into a human-readable report for DM review."""
        if not diff.has_changes:
            return f"No changes detected for {diff.character_name}."

        lines: list[str] = [f"## Sheet Changes: {diff.character_name}\n"]

        if diff.free_changes:
            lines.append("### Auto-Applied (player_free)")
            for c in diff.free_changes:
                lines.append(f"  - {c.display}")
            lines.append("")

        if diff.approval_changes:
            lines.append("### Pending DM Approval (player_approval)")
            for c in diff.approval_changes:
                lines.append(f"  - {c.display}")
            lines.append("")

        if diff.rejected_changes:
            lines.append("### Rejected (dm_only)")
            for c in diff.rejected_changes:
                lines.append(f"  - {c.display}")
            lines.append("")

        return "\n".join(lines)


def _values_equal(old: Any, new: Any) -> bool:
    """Compare two values for equality, handling type coercions.

    YAML may parse integers from string keys (e.g. spell_slots),
    and None vs missing needs special handling.
    """
    if old is None and new is None:
        return True
    if old is None or new is None:
        # "" and None are equivalent for optional string fields
        if (old is None and new == "") or (old == "" and new is None):
            return True
        return False

    # Normalize dicts with numeric keys (YAML may parse "1" as int 1)
    if isinstance(old, dict) and isinstance(new, dict):
        old_norm = {str(k): v for k, v in old.items()}
        new_norm = {str(k): v for k, v in new.items()}
        return old_norm == new_norm

    return old == new


def _format_change(field: str, old_value: Any, new_value: Any) -> str:
    """Create a human-readable change description."""
    old_display = _truncate(str(old_value), 60)
    new_display = _truncate(str(new_value), 60)
    return f"**{field}**: `{old_display}` → `{new_display}`"


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."
