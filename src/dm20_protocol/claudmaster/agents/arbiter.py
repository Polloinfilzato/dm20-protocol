"""
Arbiter Agent for the Claudmaster multi-agent system.

The Arbiter is responsible for mechanical resolution of player actions:
- Rules adjudication for creative player actions
- Dice roll interpretation and outcome determination
- State change proposals (HP changes, condition additions, etc.)
- Combat mechanical resolution

Implements the ReAct pattern: reason about what mechanics apply,
use LLM to resolve them, then observe and structure the results.
"""

import json
import logging
from typing import Any, Protocol

from pydantic import BaseModel, Field

from dm20_protocol.models import Campaign
from ..base import Agent, AgentRole

logger = logging.getLogger("dm20-protocol")


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
# Mechanical Resolution Models
# ------------------------------------------------------------------

class DiceRollResult(BaseModel):
    """Result of a dice roll."""
    description: str = Field(description="Type of roll (e.g., 'Attack roll', 'Damage roll')")
    notation: str = Field(description="Dice notation (e.g., '1d20+5', '2d6+3')")
    result: int = Field(description="The actual roll result")
    success: bool | None = Field(default=None, description="True if check succeeded, False if failed, None if not applicable")
    dc: int | None = Field(default=None, description="Difficulty class if applicable")


class StateChange(BaseModel):
    """A proposed change to game state."""
    target: str = Field(description="Character or NPC name")
    change_type: str = Field(description="Type of change: 'hp', 'condition', 'inventory', 'position', etc.")
    description: str = Field(description="Human-readable description of the change")
    value: Any = Field(description="The change value (e.g., -8 for damage, 'poisoned' for condition)")


class MechanicalResolution(BaseModel):
    """Structured output from the Arbiter's mechanical resolution."""
    success: bool = Field(description="Whether the player's action succeeds")
    dice_rolls: list[DiceRollResult] = Field(default_factory=list, description="Dice rolls made")
    state_changes: list[StateChange] = Field(default_factory=list, description="Proposed state changes")
    rules_applied: list[str] = Field(default_factory=list, description="Rules/mechanics referenced")
    narrative_hooks: list[str] = Field(default_factory=list, description="Brief outcome summaries for Narrator")
    reasoning: str = Field(description="Explanation of the mechanical logic")


# ------------------------------------------------------------------
# Prompt template
# ------------------------------------------------------------------

MECHANICAL_RESOLUTION_TEMPLATE = """\
You are the Arbiter, the rules engine for a D&D 5e campaign. Your task is to resolve the mechanical aspects of player actions.

Player Action: {player_action}
Player Intent: {player_intent}

Character Context:
{character_context}

Game State:
{game_state_context}

Applicable Rules/Context:
{rules_context}

---

Your task is to determine the mechanical outcome of this action. Provide a JSON response with the following structure:

{{
  "success": true/false,
  "dice_rolls": [
    {{
      "description": "Attack roll",
      "notation": "1d20+5",
      "result": 18,
      "success": true,
      "dc": 15
    }}
  ],
  "state_changes": [
    {{
      "target": "Goblin",
      "change_type": "hp",
      "description": "Goblin takes 8 slashing damage",
      "value": -8
    }}
  ],
  "rules_applied": ["PHB p.194: Attack action", "PHB p.196: Melee attack"],
  "narrative_hooks": ["Your blade strikes true, cutting deep into the goblin's shoulder."],
  "reasoning": "Player is making a melee weapon attack. Roll 1d20+5 (STR modifier) against goblin's AC 13. Roll of 18 hits. Roll damage 1d8+3 for 8 damage."
}}

Guidelines:
1. Be accurate with D&D 5e rules
2. Specify all dice rolls with notation
3. Propose realistic state changes based on the action
4. Provide 1-2 narrative hooks (1-2 sentences each) for the Narrator agent. These hooks should \
be vivid, specific, and varied — describe the physical reality of the outcome, not just the \
result. Examples:
   - Instead of "You hit the goblin": "The blade bites into the goblin's shoulder, wrenching \
a shriek from it as it stumbles sideways"
   - Instead of "You miss": "The orc twists away at the last moment, your sword scoring a \
bright line across its breastplate"
   - Include environmental consequences when relevant: "The force of the blow sends the goblin \
crashing into a stack of barrels, scattering ale across the tavern floor"
5. Include clear reasoning for your mechanical decisions
6. For ambiguous actions, make reasonable rulings favoring player agency

Return ONLY valid JSON, no additional text.
"""


# ------------------------------------------------------------------
# Action type classification
# ------------------------------------------------------------------

class ActionType:
    """Constants for classifying player action types."""
    ATTACK = "attack"
    SPELL = "spell"
    ABILITY_CHECK = "ability_check"
    SAVING_THROW = "saving_throw"
    SKILL_CHECK = "skill_check"
    MOVEMENT = "movement"
    INTERACTION = "interaction"
    UNKNOWN = "unknown"


# ------------------------------------------------------------------
# ArbiterAgent
# ------------------------------------------------------------------

class ArbiterAgent(Agent):
    """Agent responsible for mechanical resolution of player actions.

    The Arbiter uses an LLM (Sonnet) to adjudicate D&D mechanics,
    interpret dice rolls, and propose state changes based on rules.

    Args:
        llm: An object implementing the LLMClient protocol.
        campaign: The active D&D campaign to reference.
        max_tokens: Maximum tokens for LLM responses.
    """

    def __init__(
        self,
        llm: LLMClient,
        campaign: Campaign,
        max_tokens: int = 1024,
    ) -> None:
        super().__init__(name="arbiter", role=AgentRole.ARBITER)
        self.llm = llm
        self.campaign = campaign
        self.max_tokens = max_tokens

    async def reason(self, context: dict[str, Any]) -> str:
        """Analyze player action and game state to determine what mechanics apply.

        This is pure Python pattern matching to classify the action type
        and identify relevant mechanical systems (like Archivist's reason()).

        Args:
            context: Game context dict with keys like 'player_action',
                'player_intent', 'character', 'game_state', etc.

        Returns:
            A reasoning string describing the action type and mechanical context.
        """
        player_action = context.get("player_action", "")
        player_intent = context.get("player_intent", {})
        intent_type = player_intent.get("intent_type", "")

        action_lower = player_action.lower()

        # Combat actions
        if any(kw in action_lower for kw in ["attack", "strike", "hit", "swing", "stab", "slash", "shoot"]):
            return f"action_type:{ActionType.ATTACK}|Player is making an attack. Need to resolve attack roll, damage, and AC comparison."

        # Spell casting
        if any(kw in action_lower for kw in ["cast", "spell", "fireball", "magic missile", "heal", "cure wounds"]):
            return f"action_type:{ActionType.SPELL}|Player is casting a spell. Need to resolve spell mechanics, saves if applicable, and effects."

        # Skill checks
        if any(kw in action_lower for kw in ["sneak", "hide", "persuade", "deceive", "investigate", "perception", "insight", "charm", "wit"]):
            return f"action_type:{ActionType.SKILL_CHECK}|Player is attempting a skill check. Need to determine DC and roll modifier."

        # Saving throws
        if any(kw in action_lower for kw in ["save", "resist", "dodge trap", "avoid"]) or intent_type == "saving_throw":
            return f"action_type:{ActionType.SAVING_THROW}|Player is making a saving throw. Need to determine save type and DC."

        # Ability checks (general)
        if any(kw in action_lower for kw in ["check", "try to", "attempt to", "strength check", "dexterity check"]):
            return f"action_type:{ActionType.ABILITY_CHECK}|Player is making an ability check. Need to determine DC and modifier."

        # Movement
        if any(kw in action_lower for kw in ["move", "run", "dash", "walk", "climb", "jump"]):
            return f"action_type:{ActionType.MOVEMENT}|Player is moving. Need to check movement speed and terrain."

        # Interaction
        if any(kw in action_lower for kw in ["open", "pull", "press", "push", "activate", "interact", "lever", "button"]):
            return f"action_type:{ActionType.INTERACTION}|Player is interacting with an object. May require ability check."

        # Default: general action requiring adjudication
        return f"action_type:{ActionType.UNKNOWN}|Creative player action requiring rules adjudication."

    async def act(self, reasoning: str) -> Any:
        """Execute mechanical resolution using the LLM.

        Builds a prompt with the mechanical context and calls the LLM
        to get a structured mechanical resolution.

        Args:
            reasoning: Output from the reason() phase.

        Returns:
            A MechanicalResolution with dice rolls and state changes.
        """
        # Parse action type from reasoning
        action_type = ActionType.UNKNOWN
        if reasoning.startswith("action_type:"):
            parts = reasoning.split("|", 1)
            action_type = parts[0].replace("action_type:", "")

        # Build prompt
        prompt = self._build_prompt(action_type, reasoning)

        # Call LLM
        try:
            response = await self.llm.generate(prompt, max_tokens=self.max_tokens)

            # Parse JSON response
            resolution = self._parse_resolution(response)
            return resolution

        except Exception as e:
            logger.error(f"Arbiter resolution failed: {e}")
            # Return fallback resolution
            return MechanicalResolution(
                success=False,
                dice_rolls=[],
                state_changes=[],
                rules_applied=[],
                narrative_hooks=["The action cannot be resolved at this time."],
                reasoning=f"Error during mechanical resolution: {e}",
            )

    async def observe(self, result: Any) -> dict[str, Any]:
        """Extract key observations for the orchestrator.

        Args:
            result: The MechanicalResolution from act().

        Returns:
            Dict with observations: success, state_changes, narrative_hooks, etc.
        """
        if not isinstance(result, MechanicalResolution):
            return {"success": False, "error": "Unexpected result type"}

        observations: dict[str, Any] = {
            "success": result.success,
            "num_dice_rolls": len(result.dice_rolls),
            "num_state_changes": len(result.state_changes),
            "has_narrative_hooks": len(result.narrative_hooks) > 0,
        }

        # Extract state changes for orchestrator
        if result.state_changes:
            observations["state_changes"] = [
                {
                    "target": sc.target,
                    "type": sc.change_type,
                    "value": sc.value,
                    "description": sc.description,
                }
                for sc in result.state_changes
            ]

        # Extract narrative hooks for Narrator
        if result.narrative_hooks:
            observations["narrative_hooks"] = result.narrative_hooks

        # Extract dice roll summaries
        if result.dice_rolls:
            observations["dice_rolls"] = [
                {
                    "description": dr.description,
                    "notation": dr.notation,
                    "result": dr.result,
                    "success": dr.success,
                }
                for dr in result.dice_rolls
            ]

        return observations

    def _build_prompt(self, action_type: str, reasoning: str) -> str:
        """Build the full LLM prompt for mechanical resolution.

        Args:
            action_type: The classified action type.
            reasoning: The full reasoning output.

        Returns:
            Complete prompt string ready for the LLM.
        """
        # Extract context from the campaign (simplified for now)
        character_context = self._get_character_context()
        game_state_context = self._get_game_state_context()
        rules_context = self._get_rules_context(action_type)

        # Get player action from reasoning (simplified extraction)
        player_action = "Player action"
        player_intent = "Player intent"

        return MECHANICAL_RESOLUTION_TEMPLATE.format(
            player_action=player_action,
            player_intent=player_intent,
            character_context=character_context,
            game_state_context=game_state_context,
            rules_context=rules_context,
        )

    def _parse_resolution(self, response: str) -> MechanicalResolution:
        """Parse LLM JSON response into a MechanicalResolution.

        Args:
            response: Raw LLM response (expected to be JSON).

        Returns:
            Parsed MechanicalResolution.

        Raises:
            ValueError: If response is not valid JSON or missing required fields.
        """
        try:
            # Strip any markdown code fences if present
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()

            # Parse JSON
            data = json.loads(response)

            # Validate required fields
            if "success" not in data:
                raise ValueError("Missing 'success' field in resolution")
            if "reasoning" not in data:
                raise ValueError("Missing 'reasoning' field in resolution")

            # Parse dice rolls
            dice_rolls = [
                DiceRollResult(**roll) for roll in data.get("dice_rolls", [])
            ]

            # Parse state changes
            state_changes = [
                StateChange(**change) for change in data.get("state_changes", [])
            ]

            return MechanicalResolution(
                success=data["success"],
                dice_rolls=dice_rolls,
                state_changes=state_changes,
                rules_applied=data.get("rules_applied", []),
                narrative_hooks=data.get("narrative_hooks", []),
                reasoning=data["reasoning"],
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            raise ValueError(f"Invalid JSON response: {e}")
        except Exception as e:
            logger.error(f"Failed to parse mechanical resolution: {e}")
            raise ValueError(f"Failed to parse resolution: {e}")

    def _get_character_context(self) -> str:
        """Extract relevant character information for mechanical resolution.

        Returns:
            Formatted string with character stats and abilities.
        """
        if not self.campaign.characters:
            return "No character information available."

        # Get first character (simplified)
        char = next(iter(self.campaign.characters.values()))

        context_lines = [
            f"Character: {char.name}",
            f"Class: {char.character_class.name} {char.character_class.level}",
            f"Race: {char.race.name}",
            f"HP: {char.hit_points_current}/{char.hit_points_max}",
            f"AC: {char.armor_class}",
            f"Proficiency Bonus: +{char.proficiency_bonus}",
            "Ability Scores:",
        ]

        for ability_name, ability in char.abilities.items():
            modifier = (ability.score - 10) // 2
            sign = "+" if modifier >= 0 else ""
            context_lines.append(f"  {ability_name}: {ability.score} ({sign}{modifier})")

        return "\n".join(context_lines)

    def _get_game_state_context(self) -> str:
        """Extract relevant game state information.

        Returns:
            Formatted string with game state details.
        """
        gs = self.campaign.game_state

        context_lines = [
            f"In Combat: {gs.in_combat}",
        ]

        if gs.in_combat:
            context_lines.append(f"Current Turn: {gs.current_turn or 'Unknown'}")
            if gs.initiative_order:
                context_lines.append("Initiative Order:")
                for entry in gs.initiative_order:
                    name = entry.get("name", "Unknown")
                    init = entry.get("initiative", 0)
                    context_lines.append(f"  {name}: {init}")

        return "\n".join(context_lines)

    def _get_rules_context(self, action_type: str) -> str:
        """Get relevant rules context for the action type.

        Args:
            action_type: The classified action type.

        Returns:
            Formatted string with relevant rules reminders.
        """
        rules_map = {
            ActionType.ATTACK: (
                "Attack action: Roll 1d20 + ability modifier + proficiency (if proficient).\n"
                "Compare to target AC. On hit, roll weapon damage + ability modifier.\n"
                "Critical hit (natural 20): Roll damage dice twice."
            ),
            ActionType.SPELL: (
                "Spell casting: Check spell slot availability and casting time.\n"
                "For attack spells: Roll 1d20 + spellcasting ability + proficiency.\n"
                "For save spells: Target makes saving throw vs spell save DC.\n"
                "Spell save DC = 8 + proficiency + spellcasting ability modifier."
            ),
            ActionType.SKILL_CHECK: (
                "Skill check: Roll 1d20 + ability modifier + proficiency (if proficient).\n"
                "Compare to DC (Easy: 10, Medium: 15, Hard: 20, Very Hard: 25).\n"
                "Natural 1 is not automatic failure. Natural 20 is not automatic success."
            ),
            ActionType.ABILITY_CHECK: (
                "Ability check: Roll 1d20 + ability modifier.\n"
                "Compare to DC set by DM based on difficulty.\n"
                "No proficiency bonus unless it's a skill check."
            ),
            ActionType.SAVING_THROW: (
                "Saving throw: Roll 1d20 + ability modifier + proficiency (if proficient).\n"
                "Compare to DC. Success may halve damage or negate effect.\n"
                "Natural 1 is not automatic failure. Natural 20 is not automatic success."
            ),
        }

        return rules_map.get(action_type, "Apply D&D 5e rules as appropriate for this action.")


__all__ = [
    "ArbiterAgent",
    "MechanicalResolution",
    "DiceRollResult",
    "StateChange",
    "ActionType",
    "LLMClient",
]
