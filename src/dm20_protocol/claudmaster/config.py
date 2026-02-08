"""
Configuration model for Claudmaster AI DM system.
"""

from typing import Any, Union
from pydantic import BaseModel, Field, field_validator

from .improvisation import ImprovisationLevel


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
    improvisation_level: ImprovisationLevel = Field(
        default=ImprovisationLevel.MEDIUM,
        description="AI improvisation level controlling module adherence vs creative freedom"
    )
    allow_level_change_mid_session: bool = Field(
        default=True,
        description="Whether to allow improvisation level changes during active sessions"
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

    @field_validator("improvisation_level", mode="before")
    @classmethod
    def validate_improvisation_level(cls, v: Union[int, str, ImprovisationLevel]) -> ImprovisationLevel:
        """
        Ensure improvisation level is valid, with backward compatibility.

        Accepts:
        - ImprovisationLevel enum value
        - String matching enum value ("none", "low", "medium", "high", "full")
        - Integer (0-4) for backward compatibility with old configs
        """
        # Already an enum, pass through
        if isinstance(v, ImprovisationLevel):
            return v

        # String value - let pydantic handle enum conversion
        if isinstance(v, str):
            try:
                return ImprovisationLevel(v.lower())
            except ValueError:
                raise ValueError(
                    f"improvisation_level must be one of: {', '.join(l.value for l in ImprovisationLevel)}"
                )

        # Integer for backward compatibility
        if isinstance(v, int):
            if not 0 <= v <= 4:
                raise ValueError("improvisation_level (as int) must be between 0 and 4")
            level_map = {
                0: ImprovisationLevel.NONE,
                1: ImprovisationLevel.LOW,
                2: ImprovisationLevel.MEDIUM,
                3: ImprovisationLevel.HIGH,
                4: ImprovisationLevel.FULL,
            }
            return level_map[v]

        raise ValueError(
            f"improvisation_level must be ImprovisationLevel, str, or int, got {type(v)}"
        )

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
