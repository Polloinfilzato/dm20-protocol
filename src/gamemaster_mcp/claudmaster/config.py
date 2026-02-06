"""
Configuration model for Claudmaster AI DM system.
"""

from typing import Any
from pydantic import BaseModel, Field, field_validator


class ClaudmasterConfig(BaseModel):
    """Configuration settings for the Claudmaster multi-agent AI DM.

    This configuration controls the behavior of the AI Game Master,
    including LLM settings, agent behavior, narrative style, and game difficulty.
    """

    # LLM Configuration
    llm_provider: str = Field(
        default="anthropic",
        description="LLM backend provider (e.g., 'anthropic', 'openai')"
    )
    llm_model: str = Field(
        default="claude-sonnet-4-5-20250929",
        description="Model identifier for the LLM"
    )
    max_tokens: int = Field(
        default=4096,
        ge=256,
        le=200000,
        description="Maximum tokens in LLM response"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="LLM temperature parameter for creativity (0.0-2.0)"
    )

    # Agent Behavior
    improvisation_level: int = Field(
        default=2,
        ge=0,
        le=4,
        description="AI improvisation level: 0=None, 1=Low, 2=Medium, 3=High, 4=Full"
    )
    agent_timeout: float = Field(
        default=30.0,
        gt=0.0,
        description="Maximum seconds per agent call before timeout"
    )

    # Narrative Style
    narrative_style: str = Field(
        default="descriptive",
        description="Narrative style: descriptive, concise, dramatic, cinematic, etc."
    )
    dialogue_style: str = Field(
        default="natural",
        description="Dialogue style: natural, theatrical, formal, casual, etc."
    )

    # Difficulty Settings
    difficulty: str = Field(
        default="normal",
        description="Game difficulty: easy, normal, hard, deadly"
    )
    fudge_rolls: bool = Field(
        default=False,
        description="Whether DM can fudge dice rolls for narrative purposes"
    )

    # House Rules
    house_rules: dict[str, Any] = Field(
        default_factory=dict,
        description="Custom house rules as arbitrary key-value pairs"
    )

    # Intent Classification Settings
    ambiguity_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="Score gap below which two intents are considered ambiguous"
    )
    intent_weight_overrides: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Per-intent keyword weight overrides: {'combat': {'attack': 0.9}}"
    )
    fallback_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence for ACTION fallback when no patterns match"
    )

    @field_validator("improvisation_level")
    @classmethod
    def validate_improvisation_level(cls, v: int) -> int:
        """Ensure improvisation level is between 0 and 4."""
        if not 0 <= v <= 4:
            raise ValueError("improvisation_level must be between 0 and 4")
        return v

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Ensure temperature is within valid range."""
        if not 0.0 <= v <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        return v

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        """Ensure difficulty is a valid option."""
        valid_difficulties = {"easy", "normal", "hard", "deadly"}
        if v.lower() not in valid_difficulties:
            raise ValueError(
                f"difficulty must be one of: {', '.join(valid_difficulties)}"
            )
        return v.lower()

    @field_validator("narrative_style")
    @classmethod
    def validate_narrative_style(cls, v: str) -> str:
        """Ensure narrative style is non-empty."""
        if not v or not v.strip():
            raise ValueError("narrative_style cannot be empty")
        return v.strip().lower()

    @field_validator("dialogue_style")
    @classmethod
    def validate_dialogue_style(cls, v: str) -> str:
        """Ensure dialogue style is non-empty."""
        if not v or not v.strip():
            raise ValueError("dialogue_style cannot be empty")
        return v.strip().lower()


__all__ = ["ClaudmasterConfig"]
