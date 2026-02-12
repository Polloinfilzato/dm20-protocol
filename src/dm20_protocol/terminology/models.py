"""
Data models for terminology resolution.
"""

from pydantic import BaseModel, Field


class TermEntry(BaseModel):
    """A bilingual term entry mapping Italian and English variants to a canonical game entity.

    Represents a single D&D game term with its canonical English form,
    primary Italian translation, and optional colloquial variants.

    Attributes:
        canonical: Canonical English key (e.g., "fireball")
        category: Term category - one of: spell, skill, condition, ability,
                  combat, item, class, race, general
        en: English display name (e.g., "Fireball")
        it_primary: Primary Italian name (e.g., "Palla di Fuoco")
        it_variants: List of Italian variants including colloquial forms
    """
    canonical: str = Field(..., description="Canonical English key")
    category: str = Field(..., description="Term category")
    en: str = Field(..., description="English display name")
    it_primary: str = Field(..., description="Primary Italian name")
    it_variants: list[str] = Field(default_factory=list, description="Italian variant forms")
