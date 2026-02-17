"""
Base models and exceptions for the character import system.
"""

from pydantic import BaseModel, Field

from ..models import Character


class ImportError(Exception):
    """Raised when a character import fails.

    Provides a user-facing message explaining what went wrong
    and, where possible, how to fix it.
    """


class ImportResult(BaseModel):
    """Result of a character import operation."""

    character: Character = Field(description="The created dm20 Character")
    mapped_fields: list[str] = Field(
        default_factory=list,
        description="Field names that were successfully mapped from the source",
    )
    unmapped_fields: list[str] = Field(
        default_factory=list,
        description="Field names that could not be mapped (missing or unsupported)",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal issues encountered during import (homebrew, unknown items, etc.)",
    )
    source: str = Field(description='Import source: "url" or "file"')
    source_id: int | None = Field(
        default=None,
        description="Original character ID from the source platform (e.g., DDB numeric ID)",
    )
