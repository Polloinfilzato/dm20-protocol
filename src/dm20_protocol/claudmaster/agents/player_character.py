"""
PlayerCharacterAgent for the Claudmaster multi-agent system.

This agent controls AI-driven player characters in SOLO game mode.
It implements strict information barriers: the AI PC only sees what
a real player would know — character sheet, visible environment,
and recent party actions. It never accesses adventure secrets, NPC
bios, module content, or DM notes.

The agent uses the ReAct pattern:
- Reason: Analyze the situation from the PC's perspective
- Act: Decide an in-character action (attack, cast, investigate, etc.)
- Observe: Report what the PC attempts for the DM to resolve

Personality is driven by the character's bio and archetype, making
each AI companion feel distinct.
"""

import logging
from typing import Any, Protocol

from pydantic import BaseModel, Field

from dm20_protocol.models import Character
from ..base import Agent, AgentRole
from ..companions import (
    CompanionArchetype,
    CombatStyle,
    PersonalityTraits,
    ARCHETYPE_TEMPLATES,
)

logger = logging.getLogger("dm20-protocol")


# ------------------------------------------------------------------
# LLM Client protocol (reused from other agents)
# ------------------------------------------------------------------

class LLMClient(Protocol):
    """Protocol for LLM interaction, enabling easy mocking in tests."""

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """Generate text from a prompt."""
        ...


# ------------------------------------------------------------------
# Restricted Context — what the AI PC is allowed to see
# ------------------------------------------------------------------

class PCContext(BaseModel):
    """The restricted context an AI PC receives.

    This enforces the information barrier: only public knowledge
    that the character would realistically have access to.
    """
    # Character's own sheet (full access)
    character_sheet: dict[str, Any] = Field(
        default_factory=dict,
        description="Full character stats, inventory, spells, HP"
    )
    # Basic party info (names, classes — not full sheets)
    party_members: list[dict[str, str]] = Field(
        default_factory=list,
        description="Name, race, class of each party member (no stats)"
    )
    # What was just described by the narrator
    visible_environment: str = Field(
        default="",
        description="The most recent narrator scene description"
    )
    # Recent party actions (public knowledge only)
    recent_actions: list[str] = Field(
        default_factory=list,
        description="Recent turn descriptions visible to all PCs"
    )
    # Current situation summary
    current_situation: str = Field(
        default="",
        description="Brief situation notes (e.g., 'In combat with goblins')"
    )
    # Optional suggestion from the human player
    player_suggestion: str | None = Field(
        default=None,
        description="Human player's suggestion for this PC's action"
    )
    # Whether the party is currently in combat
    in_combat: bool = Field(
        default=False,
        description="Whether combat is active"
    )


# ------------------------------------------------------------------
# PC Decision output
# ------------------------------------------------------------------

class PCDecision(BaseModel):
    """The AI PC's decided action."""
    action: str = Field(description="What the PC attempts to do")
    reasoning: str = Field(description="Brief IC reasoning for the action")
    dialogue: str | None = Field(
        default=None,
        description="Optional in-character speech"
    )
    target: str | None = Field(
        default=None,
        description="Target of the action (enemy name, object, ally)"
    )


# ------------------------------------------------------------------
# PlayerCharacterAgent
# ------------------------------------------------------------------

class PlayerCharacterAgent(Agent):
    """Agent that controls an AI player character in SOLO mode.

    Each AI companion gets its own PlayerCharacterAgent instance.
    The agent receives a restricted context (PCContext) and decides
    actions based on the character's personality, class abilities,
    and the visible situation.

    Information barrier guarantees:
    - NO access to adventure module content
    - NO access to NPC secret bios or motivations
    - NO access to trap locations, hidden doors, enemy stats
    - NO access to DM notes, difficulty settings, or plot points
    - NO access to other PCs' private rolls or thoughts

    Args:
        character: The Character model for this PC.
        llm: An object implementing the LLMClient protocol.
        archetype: Combat/personality archetype (tank, healer, etc.).
        personality: Personality trait scores affecting behavior.
        combat_style: Preferred combat behavior.
        max_tokens: Maximum tokens for LLM responses.
    """

    def __init__(
        self,
        character: Character,
        llm: LLMClient,
        archetype: CompanionArchetype = CompanionArchetype.SUPPORT,
        personality: PersonalityTraits | None = None,
        combat_style: CombatStyle = CombatStyle.BALANCED,
        max_tokens: int = 512,
    ) -> None:
        super().__init__(
            name=f"pc_agent_{character.name.lower().replace(' ', '_')}",
            role=AgentRole.PLAYER_CHARACTER,
        )
        self.character = character
        self.llm = llm
        self.archetype = archetype
        self.personality = personality or PersonalityTraits()
        self.combat_style = combat_style
        self.max_tokens = max_tokens

        # Apply archetype defaults if no personality was provided
        if personality is None and archetype in ARCHETYPE_TEMPLATES:
            template = ARCHETYPE_TEMPLATES[archetype]
            self.personality = template.get("personality", PersonalityTraits())
            self.combat_style = template.get("combat_style", CombatStyle.BALANCED)

    def build_restricted_context(
        self,
        full_context: dict[str, Any],
        party_characters: list[Character] | None = None,
    ) -> PCContext:
        """Build a restricted context from the full orchestrator context.

        This is the information barrier enforcement point. It extracts
        only public knowledge from the full game context.

        Args:
            full_context: The complete orchestrator context (with secrets).
            party_characters: Other PCs in the party (for basic info only).

        Returns:
            PCContext with only public knowledge.
        """
        # Character sheet — full access to own stats
        char_sheet = self.character.model_dump(
            exclude={"id"},
            mode="json",
        )

        # Party members — basic info only (no stats/inventory)
        party_info = []
        if party_characters:
            for pc in party_characters:
                if pc.name != self.character.name:
                    party_info.append({
                        "name": pc.name,
                        "race": pc.race.name if pc.race else "Unknown",
                        "class": pc.character_class.name if pc.character_class else "Unknown",
                    })

        # Visible environment — last narrator description
        visible = ""
        conversation = full_context.get("conversation_history", [])
        for msg in reversed(conversation):
            if msg.get("role") == "assistant":
                visible = msg.get("content", "")[:2000]
                break

        # Recent actions — last few user/assistant exchanges (public)
        recent = []
        for msg in conversation[-6:]:
            if msg.get("content"):
                role_label = "Player" if msg["role"] == "user" else "DM"
                recent.append(f"{role_label}: {msg['content'][:300]}")

        # Current situation from game state
        game_state = full_context.get("game_state", {})
        situation = game_state.get("notes", "")
        in_combat = game_state.get("in_combat", False)

        return PCContext(
            character_sheet=char_sheet,
            party_members=party_info,
            visible_environment=visible,
            recent_actions=recent,
            current_situation=situation,
            in_combat=in_combat,
            player_suggestion=full_context.get("player_suggestion"),
        )

    async def reason(self, context: dict[str, Any]) -> str:
        """Analyze the situation from the PC's perspective.

        Uses the restricted PCContext to understand what the character
        knows and what would be an appropriate action.

        Args:
            context: Must contain a 'pc_context' key with PCContext data,
                or full context to be filtered through build_restricted_context.

        Returns:
            Reasoning string describing the PC's assessment.
        """
        # Extract or build restricted context
        if "pc_context" in context:
            pc_ctx = context["pc_context"]
            if isinstance(pc_ctx, dict):
                pc_ctx = PCContext(**pc_ctx)
        else:
            pc_ctx = self.build_restricted_context(context)

        # Build reasoning based on situation
        char = self.character
        class_name = char.character_class.name if char.character_class else "Adventurer"
        reasoning_parts = [
            f"character:{char.name}|class:{class_name}|level:{char.character_class.level if char.character_class else 1}",
            f"archetype:{self.archetype.value}|combat_style:{self.combat_style.value}",
            f"in_combat:{pc_ctx.in_combat}",
            f"situation:{pc_ctx.current_situation[:200]}",
        ]

        if pc_ctx.player_suggestion:
            reasoning_parts.append(f"player_suggests:{pc_ctx.player_suggestion}")

        # Personality influence on reasoning
        p = self.personality
        if p.bravery > 70:
            reasoning_parts.append("trait:brave_eager_to_act")
        elif p.caution > 70:
            reasoning_parts.append("trait:cautious_prefers_safety")
        if p.compassion > 70:
            reasoning_parts.append("trait:compassionate_protects_allies")
        if p.aggression > 70:
            reasoning_parts.append("trait:aggressive_prefers_offense")

        return "|".join(reasoning_parts)

    async def act(self, reasoning: str) -> Any:
        """Decide what action the PC takes using the LLM.

        Builds a prompt with the character's perspective and personality,
        then asks the LLM to decide an in-character action.

        Args:
            reasoning: Output from the reason() phase.

        Returns:
            PCDecision with the chosen action.
        """
        prompt = self._build_prompt(reasoning)

        try:
            response = await self.llm.generate(prompt, max_tokens=self.max_tokens)
            return self._parse_decision(response)
        except Exception as e:
            logger.error(f"PC agent {self.name} decision failed: {e}")
            return PCDecision(
                action=self._fallback_action(),
                reasoning="Could not decide an action, falling back to default behavior.",
            )

    async def observe(self, result: Any) -> dict[str, Any]:
        """Extract observations from the PC's action for the orchestrator.

        Args:
            result: The PCDecision from the act() phase.

        Returns:
            Dictionary with action details for the narrator to integrate.
        """
        if isinstance(result, PCDecision):
            obs = {
                "pc_name": self.character.name,
                "action": result.action,
                "reasoning": result.reasoning,
                "target": result.target,
            }
            if result.dialogue:
                obs["dialogue"] = result.dialogue
            return obs

        return {
            "pc_name": self.character.name,
            "action": str(result),
            "reasoning": "Unknown",
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, reasoning: str) -> str:
        """Build the LLM prompt for action decision."""
        char = self.character
        class_name = char.character_class.name if char.character_class else "Adventurer"
        level = char.character_class.level if char.character_class else 1

        personality_desc = self._describe_personality()

        prompt = f"""You are {char.name}, a level {level} {char.race.name if char.race else 'Unknown'} {class_name}.

PERSONALITY: {personality_desc}
BIO: {char.bio or 'A seasoned adventurer.'}
COMBAT STYLE: {self.combat_style.value}

SITUATION CONTEXT:
{reasoning}

Based on your character's personality and the current situation, decide what you do.
Consider your class abilities, available equipment, and the party's needs.

Respond in this exact JSON format:
{{
  "action": "Brief description of what you do (1-2 sentences)",
  "reasoning": "Brief IC reason why (1 sentence)",
  "dialogue": "Optional: something you say out loud, or null",
  "target": "Who/what you target, or null"
}}

RULES:
- Stay in character. Act as {char.name} would based on personality.
- You can ONLY know what you've seen and heard — no metagaming.
- If the human player suggested an action, consider it but you may disagree.
- In combat: use your class abilities effectively.
- Out of combat: contribute to exploration, roleplay, or investigation.
- Keep actions concise — the DM will narrate the outcome.

Respond with ONLY the JSON object, no other text."""

        return prompt

    def _describe_personality(self) -> str:
        """Generate a natural language personality description."""
        p = self.personality
        traits = []

        if p.bravery >= 70:
            traits.append("brave and bold")
        elif p.bravery <= 30:
            traits.append("cautious about danger")

        if p.aggression >= 70:
            traits.append("aggressive in combat")
        elif p.aggression <= 30:
            traits.append("preferring peaceful solutions")

        if p.compassion >= 70:
            traits.append("deeply caring about allies")
        elif p.compassion <= 30:
            traits.append("pragmatic and self-interested")

        if p.caution >= 70:
            traits.append("careful and methodical")
        elif p.caution <= 30:
            traits.append("impulsive and reckless")

        if p.loyalty >= 70:
            traits.append("fiercely loyal to the party")

        return ", ".join(traits) if traits else "balanced and adaptable"

    def _parse_decision(self, response: str) -> PCDecision:
        """Parse the LLM response into a PCDecision."""
        import json

        # Try to extract JSON from the response
        text = response.strip()

        # Handle markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        try:
            data = json.loads(text)
            return PCDecision(
                action=data.get("action", "Stands ready."),
                reasoning=data.get("reasoning", "Assessing the situation."),
                dialogue=data.get("dialogue"),
                target=data.get("target"),
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning(f"PC agent {self.name}: Could not parse JSON, using raw response")
            return PCDecision(
                action=text[:200] if text else self._fallback_action(),
                reasoning="Action parsed from free-form response.",
            )

    def _fallback_action(self) -> str:
        """Generate a sensible fallback action based on archetype."""
        fallbacks = {
            CompanionArchetype.TANK: "Takes a defensive stance, shield raised, ready to protect the party.",
            CompanionArchetype.HEALER: "Scans the party for injuries, preparing to provide aid.",
            CompanionArchetype.STRIKER: "Watches for an opening to strike, moving to a flanking position.",
            CompanionArchetype.SUPPORT: "Stays alert and ready to assist where needed.",
        }
        return fallbacks.get(self.archetype, "Stands ready, watching the situation carefully.")


__all__ = [
    "PlayerCharacterAgent",
    "PCContext",
    "PCDecision",
    "LLMClient",
]
