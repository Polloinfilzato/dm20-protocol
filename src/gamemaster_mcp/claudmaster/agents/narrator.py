"""
Narrator Agent for the Claudmaster multi-agent system.

The Narrator is responsible for generating evocative scene descriptions,
NPC dialogue stubs, and atmospheric text. It uses an LLM (Claude API)
for text generation and supports configurable narrative styles.

Implements the ReAct pattern: reason about what description is needed,
generate it via the LLM, then observe/validate the output quality.
"""

import logging
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from ..base import Agent, AgentRole

logger = logging.getLogger("gamemaster-mcp")


# ------------------------------------------------------------------
# Narrative styles
# ------------------------------------------------------------------

class NarrativeStyle(str, Enum):
    """Supported narrative styles for scene descriptions."""
    DESCRIPTIVE = "descriptive"  # Rich, detailed prose
    TERSE = "terse"              # Brief, action-focused
    DRAMATIC = "dramatic"        # Theatrical, tension-building
    MYSTERIOUS = "mysterious"    # Hints and atmosphere


# ------------------------------------------------------------------
# LLM Client protocol
# ------------------------------------------------------------------

class LLMClient(Protocol):
    """Protocol for LLM interaction, enabling easy mocking in tests."""

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """Generate text from a prompt.

        Args:
            prompt: The full prompt to send to the LLM.
            max_tokens: Maximum tokens in the response.

        Returns:
            The generated text.
        """
        ...


# ------------------------------------------------------------------
# Prompt templates
# ------------------------------------------------------------------

SCENE_DESCRIPTION_TEMPLATE = """\
You are the Narrator of a D&D campaign. Your task: {reasoning}

Narration style: {style}

Bring every scene alive through layered sensory detail — sounds echoing off stone, the bite of \
cold air, the stench of rot or the warmth of hearth-smoke. When describing a new place, character, \
or situation for the first time, paint a rich and evocative picture that gives players multiple \
threads to pull on: curious details, half-noticed oddities, things that beg questions. On follow-up \
requests for more detail, narrow your focus precisely to what was asked, and calibrate the depth of \
revealed information to the difficulty of any check involved — not every secret is freely given.

Occasionally, without forcing it, weave in fragments of history or culture — a faded crest on a \
wall, a local superstition muttered by a passerby, the architectural echo of a fallen empire — so \
the world feels lived-in and layered beyond the immediate scene.

Adapt your emotional register to match the moment. Let mystery seep in when the unknown stretches \
ahead and adventure hangs in the air. Let excitement and breathless anticipation build when hidden \
riches or discoveries feel tantalizingly close. Let dread and creeping tension take hold in dark, \
threatening places where danger could erupt without warning. And when the heroes have triumphed — \
whether the feat concluded moments ago or began sessions past — rise to meet the occasion: recount \
their deeds with the weight and sweep they deserve, reminding everyone at the table why these \
moments matter.

Never follow a predictable pattern. Vary your sentence structure, your openings, your rhythm. \
Sometimes begin mid-action, sometimes with a single sensory detail, sometimes with dialogue or \
silence. The players should never feel they are reading output from a template — they should feel \
a living voice telling their story.
"""


# ------------------------------------------------------------------
# NarratorAgent
# ------------------------------------------------------------------

class NarratorAgent(Agent):
    """Agent responsible for narrative scene descriptions.

    Uses an LLM to generate atmospheric text based on the current game
    context, location, recent events, and the configured narrative style.

    Args:
        llm: An object implementing the LLMClient protocol.
        style: The narrative style to use for descriptions.
        max_tokens: Maximum tokens for LLM responses.
    """

    def __init__(
        self,
        llm: LLMClient,
        style: NarrativeStyle = NarrativeStyle.DESCRIPTIVE,
        max_tokens: int = 1024,
    ) -> None:
        super().__init__(name="narrator", role=AgentRole.NARRATOR)
        self.llm = llm
        self.style = style
        self.max_tokens = max_tokens

    async def reason(self, context: dict[str, Any]) -> str:
        """Analyze context to determine what kind of description is needed.

        Examines the player action, current location, and recent events
        to decide on the appropriate narrative response type.

        Args:
            context: Game context dict with keys like 'player_action',
                'location', 'recent_events', 'setting', etc.

        Returns:
            A reasoning string describing the intended narrative approach.
        """
        player_action = context.get("player_action", "")
        location = context.get("location", {})
        location_name = location.get("name", "unknown location") if isinstance(location, dict) else str(location)

        # Determine the narrative task
        if not player_action:
            return f"No player action provided. Generating ambient description for {location_name}."

        # Classify what kind of narrative response is appropriate
        action_words = set(player_action.lower().split())
        if action_words & {"look", "examine", "inspect", "observe", "search"}:
            return f"Player is observing. Generate detailed description of {location_name}."
        elif action_words & {"enter", "go", "move", "walk", "travel"}:
            return f"Player is moving. Generate transition scene to/within {location_name}."
        elif action_words & {"talk", "speak", "ask", "greet"}:
            return f"Player initiating dialogue. Set the social scene at {location_name}."
        else:
            return f"Player action: '{player_action}'. Narrate the result at {location_name}."

    async def act(self, reasoning: str) -> Any:
        """Generate the narrative description using the LLM.

        Builds a prompt from the reasoning and context, then calls the
        LLM to generate atmospheric text.

        Args:
            reasoning: Output from the reason() phase.

        Returns:
            The generated narrative text string.
        """
        prompt = self._build_prompt(reasoning)
        response = await self.llm.generate(prompt, max_tokens=self.max_tokens)
        return response.strip()

    async def observe(self, result: Any) -> dict[str, Any]:
        """Validate and annotate the generated narrative.

        Checks basic quality metrics and returns observations about
        the generated text.

        Args:
            result: The narrative text from act().

        Returns:
            Dict with observations: word_count, style, has_dialogue, etc.
        """
        text = str(result)
        return {
            "word_count": len(text.split()),
            "style": self.style.value,
            "has_dialogue": '"' in text or "\u201c" in text,
            "empty": len(text.strip()) == 0,
        }

    def _build_prompt(self, reasoning: str) -> str:
        """Build the full LLM prompt from reasoning and the template.

        Args:
            reasoning: The reasoning output describing what to narrate.

        Returns:
            Complete prompt string ready for the LLM.
        """
        return SCENE_DESCRIPTION_TEMPLATE.format(
            reasoning=reasoning,
            style=self.style.value,
        )


__all__ = [
    "NarratorAgent",
    "NarrativeStyle",
    "LLMClient",
    "SCENE_DESCRIPTION_TEMPLATE",
]
