"""Pydantic models for the character sheet sync system."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ChangeStatus(str, Enum):
    """Status of a pending change."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPLIED = "auto_applied"


class FieldChange(BaseModel):
    """A single field change detected between MD frontmatter and JSON data."""
    field: str = Field(description="Dot-notation field path (e.g. 'strength', 'spells_known')")
    old_value: object = Field(description="Value from the current Character JSON")
    new_value: object = Field(description="Value from the edited MD frontmatter")
    tier: str = Field(description="Editability tier: player_free, player_approval, dm_only")
    display: str = Field(default="", description="Human-readable description of the change")

    model_config = {"arbitrary_types_allowed": True}


class SheetDiff(BaseModel):
    """Complete diff between MD frontmatter and Character JSON."""
    character_name: str
    character_id: str
    changes: list[FieldChange] = Field(default_factory=list)
    free_changes: list[FieldChange] = Field(default_factory=list)
    approval_changes: list[FieldChange] = Field(default_factory=list)
    rejected_changes: list[FieldChange] = Field(default_factory=list)
    has_changes: bool = False
    timestamp: datetime = Field(default_factory=datetime.now)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def needs_approval(self) -> bool:
        """Whether any changes require DM approval."""
        return len(self.approval_changes) > 0


class PendingChange(BaseModel):
    """A set of changes from a player edit awaiting DM approval."""
    character_name: str
    character_id: str
    diff: SheetDiff
    status: ChangeStatus = ChangeStatus.PENDING
    submitted_at: datetime = Field(default_factory=datetime.now)
    resolved_at: datetime | None = None
    dm_notes: str = ""

    model_config = {"arbitrary_types_allowed": True}


class SyncState(BaseModel):
    """Tracks sync state for a single character sheet."""
    character_id: str
    character_name: str
    md_path: str = ""
    last_md_hash: str = ""
    last_json_hash: str = ""
    dm20_version: int = 1
    last_sync: datetime = Field(default_factory=datetime.now)
    pending_changes: list[PendingChange] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
