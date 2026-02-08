"""
Player Action Interpretation for the Claudmaster multi-agent system.

The ActionInterpreter parses natural language player input into structured
actions, classifies intent, validates against game state, handles ambiguity,
and supports compound actions.

This module provides:
- Intent classification for player actions
- Parsing of natural language into structured ParsedAction objects
- Ambiguity detection and clarification request generation
- Game state validation for actions
- Compound action support (e.g., "I move and attack")
"""

import logging
import re
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field

from dm20_protocol.models import GameState
from .agents.archivist import ArchivistAgent

logger = logging.getLogger("dm20-protocol")


# ============================================================================
# LLM Client Protocol (for ambiguous cases)
# ============================================================================

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


# ============================================================================
# Action Intent Types
# ============================================================================

class ActionIntent(str, Enum):
    """Classification of player action intent."""
    # Combat actions
    COMBAT_ATTACK = "combat_attack"
    COMBAT_SPELL = "combat_spell"
    COMBAT_ABILITY = "combat_ability"
    COMBAT_MOVEMENT = "combat_movement"
    COMBAT_DEFENSIVE = "combat_defensive"

    # Exploration actions
    EXPLORATION_MOVEMENT = "exploration_movement"
    EXPLORATION_SEARCH = "exploration_search"
    EXPLORATION_INTERACT = "exploration_interact"

    # Social actions
    SOCIAL_DIALOGUE = "social_dialogue"
    SOCIAL_PERSUADE = "social_persuade"
    SOCIAL_INTIMIDATE = "social_intimidate"
    SOCIAL_DECEIVE = "social_deceive"

    # Magic actions
    MAGIC_CAST = "magic_cast"
    MAGIC_RITUAL = "magic_ritual"

    # Item actions
    ITEM_USE = "item_use"
    ITEM_EQUIP = "item_equip"

    # Rest actions
    REST_SHORT = "rest_short"
    REST_LONG = "rest_long"

    # Meta actions
    META_OOC = "meta_ooc"
    META_QUESTION = "meta_question"

    # Unknown/fallback
    UNKNOWN = "unknown"


# ============================================================================
# Action Models
# ============================================================================

class ParsedAction(BaseModel):
    """A parsed player action with structured information."""
    intent: ActionIntent = Field(description="The classified action intent")
    actor: str = Field(description="The character performing the action")
    targets: list[str] = Field(
        default_factory=list,
        description="Target entities for this action"
    )
    method: str | None = Field(
        default=None,
        description="Weapon, spell, or ability used"
    )
    modifiers: list[str] = Field(
        default_factory=list,
        description="Action modifiers (advantage, stealth, etc.)"
    )
    raw_input: str = Field(description="The original player input")
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in the parsing (0.0-1.0)"
    )


class AmbiguityType(str, Enum):
    """Types of ambiguity in player input."""
    TARGET = "target"
    METHOD = "method"
    INTENT = "intent"
    LOCATION = "location"
    QUANTITY = "quantity"


class Ambiguity(BaseModel):
    """An ambiguity detected in player input."""
    type: AmbiguityType = Field(description="The type of ambiguity")
    options: list[str] = Field(description="Possible interpretations")
    context_hint: str = Field(description="Context to help resolve the ambiguity")


class ValidationResult(BaseModel):
    """Result of validating an action against game state."""
    is_valid: bool = Field(description="Whether the action is valid")
    action: ParsedAction = Field(description="The validated action")
    issues: list[str] = Field(
        default_factory=list,
        description="Validation issues found"
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Alternative suggestions"
    )
    can_attempt_with_penalty: bool = Field(
        default=False,
        description="Whether action can be attempted with disadvantage/penalty"
    )


class InterpretationResult(BaseModel):
    """Result of interpreting player input."""
    actions: list[ParsedAction] = Field(
        default_factory=list,
        description="Parsed actions from the input"
    )
    ambiguities: list[Ambiguity] = Field(
        default_factory=list,
        description="Detected ambiguities"
    )
    requires_clarification: bool = Field(
        default=False,
        description="Whether clarification is needed"
    )
    clarification_prompt: str | None = Field(
        default=None,
        description="Prompt to request clarification"
    )


class ClarificationRequest(BaseModel):
    """A request for clarification from the player."""
    question: str = Field(description="The clarification question")
    options: list[str] = Field(description="Possible options to choose from")
    context: str = Field(description="Context for the clarification")
    original_input: str = Field(description="The original player input")


# ============================================================================
# Action Keywords (for classification)
# ============================================================================

# Keywords for each action intent type
ACTION_KEYWORDS: dict[ActionIntent, list[str]] = {
    # Combat attacks
    ActionIntent.COMBAT_ATTACK: [
        "attack", "strike", "hit", "slash", "stab", "shoot", "fire",
        "punch", "kick", "smite", "swing", "thrust"
    ],

    # Combat spells (specific spell names)
    ActionIntent.COMBAT_SPELL: [
        "fireball", "magic missile", "eldritch blast", "sacred flame",
        "guiding bolt", "scorching ray", "lightning bolt", "cone of cold"
    ],

    # Combat abilities
    ActionIntent.COMBAT_ABILITY: [
        "rage", "sneak attack", "divine smite", "action surge",
        "flurry of blows", "cunning action", "superiority"
    ],

    # Combat movement
    ActionIntent.COMBAT_MOVEMENT: [
        "move to", "dash", "run to", "approach", "retreat", "flee",
        "circle around", "flank"
    ],

    # Combat defensive
    ActionIntent.COMBAT_DEFENSIVE: [
        "dodge", "disengage", "hide", "take cover", "defend",
        "parry", "block", "shield"
    ],

    # Exploration movement
    ActionIntent.EXPLORATION_MOVEMENT: [
        "go to", "walk to", "enter", "leave", "exit", "climb",
        "jump", "swim", "crawl", "descend", "ascend"
    ],

    # Exploration search
    ActionIntent.EXPLORATION_SEARCH: [
        "search", "look for", "examine", "inspect", "investigate",
        "check for traps", "checking for traps", "check for",
        "checking for", "perception check", "scan", "survey"
    ],

    # Exploration interact
    ActionIntent.EXPLORATION_INTERACT: [
        "open", "close", "pull", "push", "touch", "take", "pick up",
        "grab", "use", "activate", "press", "turn"
    ],

    # Social dialogue
    ActionIntent.SOCIAL_DIALOGUE: [
        "talk to", "speak with", "greet", "ask", "tell", "say",
        "converse", "chat", "question", "inquire"
    ],

    # Social persuade
    ActionIntent.SOCIAL_PERSUADE: [
        "persuade", "convince", "negotiate", "bargain", "appeal",
        "persuasion check", "try to convince"
    ],

    # Social intimidate
    ActionIntent.SOCIAL_INTIMIDATE: [
        "intimidate", "threaten", "menace", "scare", "frighten",
        "intimidation check", "loom over"
    ],

    # Social deceive
    ActionIntent.SOCIAL_DECEIVE: [
        "lie", "deceive", "bluff", "trick", "mislead", "deception check",
        "feint", "distract"
    ],

    # Magic casting (general)
    ActionIntent.MAGIC_CAST: [
        "cast", "casting", "spell", "magic", "invoke", "channel",
        "conjure", "summon"
    ],

    # Magic ritual
    ActionIntent.MAGIC_RITUAL: [
        "ritual", "ritual cast", "perform ritual", "prepare ritual"
    ],

    # Item use
    ActionIntent.ITEM_USE: [
        "drink", "eat", "consume", "apply", "read scroll",
        "use potion", "throw", "deploy"
    ],

    # Item equip
    ActionIntent.ITEM_EQUIP: [
        "equip", "wear", "don", "wield", "unequip", "remove",
        "sheathe", "draw"
    ],

    # Rest
    ActionIntent.REST_SHORT: [
        "short rest", "rest briefly", "take a break", "catch my breath"
    ],
    ActionIntent.REST_LONG: [
        "long rest", "sleep", "camp", "rest for the night", "make camp"
    ],

    # Meta OOC
    ActionIntent.META_OOC: [
        "ooc", "out of character", "quick question", "real quick"
    ],

    # Meta question
    ActionIntent.META_QUESTION: [
        "how do", "can i", "what happens if", "rule question",
        "does it work", "is it possible"
    ],
}

# Compound action separators
COMPOUND_SEPARATORS = ["and", "then", "while", "before", "after"]


# ============================================================================
# ActionInterpreter
# ============================================================================

class ActionInterpreter:
    """
    Interprets natural language player input into structured actions.

    The ActionInterpreter:
    1. Detects OOC/meta input
    2. Splits compound actions
    3. Classifies action intent using keyword matching
    4. Extracts targets, methods, and modifiers
    5. Validates actions against game state
    6. Detects ambiguities and generates clarification requests

    Attributes:
        archivist: ArchivistAgent for querying game state
        llm: LLMClient for handling ambiguous cases
    """

    def __init__(self, archivist: ArchivistAgent, llm: LLMClient) -> None:
        """
        Initialize the ActionInterpreter.

        Args:
            archivist: ArchivistAgent instance for game state queries
            llm: LLMClient instance for LLM-based clarification
        """
        self.archivist = archivist
        self.llm = llm
        logger.info("ActionInterpreter initialized")

    async def interpret(
        self,
        player_input: str,
        character_name: str,
        game_state: GameState
    ) -> InterpretationResult:
        """
        Interpret player input into structured actions.

        This method:
        1. Detects OOC/meta input
        2. Splits compound actions
        3. Classifies each action's intent
        4. Extracts targets, methods, modifiers
        5. Detects ambiguities

        Args:
            player_input: Raw natural language input from player
            character_name: Name of the acting character
            game_state: Current game state

        Returns:
            InterpretationResult with parsed actions and ambiguities
        """
        if not player_input or not player_input.strip():
            return InterpretationResult(
                actions=[],
                requires_clarification=True,
                clarification_prompt="I didn't catch that. What would you like to do?"
            )

        input_lower = player_input.strip().lower()

        # Step 1: Detect OOC/meta input first
        if self._is_ooc_input(input_lower):
            action = ParsedAction(
                intent=ActionIntent.META_OOC,
                actor=character_name,
                raw_input=player_input,
                confidence=1.0
            )
            return InterpretationResult(actions=[action])

        if self._is_meta_question(input_lower):
            action = ParsedAction(
                intent=ActionIntent.META_QUESTION,
                actor=character_name,
                raw_input=player_input,
                confidence=0.9
            )
            return InterpretationResult(actions=[action])

        # Step 2: Split compound actions
        sub_inputs = self._split_compound_actions(player_input)

        # Step 3: Parse each sub-action
        actions: list[ParsedAction] = []
        ambiguities: list[Ambiguity] = []

        for sub_input in sub_inputs:
            action = self._parse_single_action(sub_input.strip(), character_name, game_state)
            actions.append(action)

            # Check for ambiguity (low confidence)
            if action.confidence < 0.5:
                ambiguity = Ambiguity(
                    type=AmbiguityType.INTENT,
                    options=[action.intent.value, "unknown"],
                    context_hint=f"Action '{sub_input}' is unclear"
                )
                ambiguities.append(ambiguity)

        # Step 4: Build result
        requires_clarification = bool(ambiguities)
        clarification_prompt = None

        if requires_clarification and ambiguities:
            clarification_prompt = (
                f"I'm not sure I understand. Did you mean to "
                f"{ambiguities[0].options[0].replace('_', ' ')}?"
            )

        return InterpretationResult(
            actions=actions,
            ambiguities=ambiguities,
            requires_clarification=requires_clarification,
            clarification_prompt=clarification_prompt
        )

    async def validate(
        self,
        action: ParsedAction,
        game_state: GameState
    ) -> ValidationResult:
        """
        Validate an action against the current game state.

        Checks:
        - Is the action valid for the current context (combat vs exploration)?
        - Does the character exist?
        - Are there basic resource/capability issues?

        Args:
            action: The parsed action to validate
            game_state: Current game state

        Returns:
            ValidationResult with validity status and issues
        """
        issues: list[str] = []
        suggestions: list[str] = []
        can_attempt_with_penalty = False

        # Check if combat action is valid outside combat
        combat_intents = {
            ActionIntent.COMBAT_ATTACK,
            ActionIntent.COMBAT_SPELL,
            ActionIntent.COMBAT_ABILITY,
            ActionIntent.COMBAT_MOVEMENT,
            ActionIntent.COMBAT_DEFENSIVE
        }

        if action.intent in combat_intents and not game_state.in_combat:
            issues.append("This is a combat action, but combat is not active")
            suggestions.append("Try using exploration actions instead")
            can_attempt_with_penalty = True

        # Check if character exists
        try:
            await self.archivist.get_character_stats(action.actor)
        except KeyError:
            issues.append(f"Character '{action.actor}' not found")
            suggestions.append("Check your character name")

        # Check if action has targets when needed
        attack_intents = {
            ActionIntent.COMBAT_ATTACK,
            ActionIntent.COMBAT_SPELL,
            ActionIntent.SOCIAL_PERSUADE,
            ActionIntent.SOCIAL_INTIMIDATE,
            ActionIntent.SOCIAL_DECEIVE
        }

        if action.intent in attack_intents and not action.targets:
            issues.append("This action requires a target")
            suggestions.append("Specify who or what you're targeting")

        # Determine overall validity
        is_valid = len(issues) == 0

        return ValidationResult(
            is_valid=is_valid,
            action=action,
            issues=issues,
            suggestions=suggestions,
            can_attempt_with_penalty=can_attempt_with_penalty
        )

    async def request_clarification(
        self,
        ambiguity: Ambiguity,
        original_input: str
    ) -> ClarificationRequest:
        """
        Generate a clarification request for an ambiguity.

        Args:
            ambiguity: The detected ambiguity
            original_input: The original player input

        Returns:
            ClarificationRequest with question and options
        """
        question_templates = {
            AmbiguityType.TARGET: "Who or what do you want to target?",
            AmbiguityType.METHOD: "How do you want to do this?",
            AmbiguityType.INTENT: "What exactly do you want to do?",
            AmbiguityType.LOCATION: "Where do you want to go?",
            AmbiguityType.QUANTITY: "How many do you want to use?"
        }

        question = question_templates.get(
            ambiguity.type,
            "Can you clarify what you mean?"
        )

        return ClarificationRequest(
            question=question,
            options=ambiguity.options,
            context=ambiguity.context_hint,
            original_input=original_input
        )

    # ========================================================================
    # Private helper methods
    # ========================================================================

    def _is_ooc_input(self, input_lower: str) -> bool:
        """Check if input is out-of-character."""
        # Starts with OOC marker
        if input_lower.startswith("ooc"):
            return True
        if input_lower.startswith("(") and ")" in input_lower:
            return True

        return False

    def _is_meta_question(self, input_lower: str) -> bool:
        """Check if input is a meta/rules question."""
        question_starters = [
            "how do", "how does", "can i", "could i", "is it possible",
            "what happens if", "what's the rule", "does the rule"
        ]

        for starter in question_starters:
            if input_lower.startswith(starter):
                return True

        return False

    def _split_compound_actions(self, player_input: str) -> list[str]:
        """
        Split compound actions on separators like 'and', 'then', 'while'.

        Args:
            player_input: Raw player input

        Returns:
            List of individual action strings
        """
        input_lower = player_input.lower()

        # Find separator positions
        separator_positions: list[tuple[int, str]] = []
        for sep in COMPOUND_SEPARATORS:
            # Look for separator as whole word
            sep_with_space = f" {sep} "
            pos = input_lower.find(sep_with_space)
            while pos != -1:
                separator_positions.append((pos, sep))
                pos = input_lower.find(sep_with_space, pos + len(sep_with_space))

        # If no separators found, return original input
        if not separator_positions:
            return [player_input]

        # Sort by position
        separator_positions.sort(key=lambda x: x[0])

        # Split into sub-actions
        sub_actions: list[str] = []
        last_pos = 0

        for pos, sep in separator_positions:
            sub_action = player_input[last_pos:pos].strip()
            if sub_action:
                sub_actions.append(sub_action)
            last_pos = pos + len(sep) + 2  # +2 for the spaces

        # Add final sub-action
        final_sub_action = player_input[last_pos:].strip()
        if final_sub_action:
            sub_actions.append(final_sub_action)

        return sub_actions

    def _parse_single_action(
        self,
        action_input: str,
        character_name: str,
        game_state: GameState
    ) -> ParsedAction:
        """
        Parse a single action into a ParsedAction.

        Uses keyword matching to classify intent and extract components.

        Args:
            action_input: Single action string (no compound separators)
            character_name: Name of the acting character
            game_state: Current game state

        Returns:
            ParsedAction with classified intent and extracted components
        """
        input_lower = action_input.lower()

        # Classify intent using keyword matching
        intent, confidence = self._classify_action_intent(input_lower)

        # Extract targets
        targets = self._extract_targets(input_lower)

        # Extract method (weapon, spell, ability)
        method = self._extract_method(input_lower, intent)

        # Extract modifiers (advantage, stealth, etc.)
        modifiers = self._extract_modifiers(input_lower)

        return ParsedAction(
            intent=intent,
            actor=character_name,
            targets=targets,
            method=method,
            modifiers=modifiers,
            raw_input=action_input,
            confidence=confidence
        )

    def _classify_action_intent(self, input_lower: str) -> tuple[ActionIntent, float]:
        """
        Classify action intent using weighted keyword matching.

        Multi-word phrases are scored higher than single-word keywords
        (weight = word count). Single-word keywords use word-boundary
        matching to avoid false positives (e.g., "fire" inside "fireball").

        Args:
            input_lower: Lowercased action input

        Returns:
            Tuple of (ActionIntent, confidence_score)
        """
        scores: dict[ActionIntent, float] = {}

        for intent, keywords in ACTION_KEYWORDS.items():
            total_weight = 0.0
            for kw in keywords:
                if " " in kw:
                    # Multi-word phrase: substring match, weighted by word count
                    if kw in input_lower:
                        total_weight += len(kw.split())
                else:
                    # Single word: word-boundary match to avoid partial hits
                    if re.search(r'\b' + re.escape(kw) + r'\b', input_lower):
                        total_weight += 1.0

            if total_weight > 0:
                scores[intent] = total_weight

        # No matches → unknown
        if not scores:
            return (ActionIntent.UNKNOWN, 0.2)

        # Find best match
        best_intent = max(scores, key=scores.get)  # type: ignore
        best_score = scores[best_intent]

        # Calculate confidence: more weight = higher confidence (0.5-1.0 range)
        confidence = min(0.5 + (best_score * 0.15), 1.0)

        return (best_intent, confidence)

    def _extract_targets(self, input_lower: str) -> list[str]:
        """
        Extract target entities from the input.

        Looks for common target patterns like "the X", "at X", "on X".

        Args:
            input_lower: Lowercased action input

        Returns:
            List of target strings
        """
        targets: list[str] = []

        # Target indicators
        target_patterns = [
            " the ", " at ", " on ", " with ", " to ", " towards "
        ]

        for pattern in target_patterns:
            if pattern in input_lower:
                # Extract word after the pattern
                parts = input_lower.split(pattern, 1)
                if len(parts) > 1:
                    # Take first 1-3 words after pattern
                    target_words = parts[1].split()[:3]
                    target = " ".join(target_words)
                    if target and target not in targets:
                        targets.append(target)

        return targets

    def _extract_method(self, input_lower: str, intent: ActionIntent) -> str | None:
        """
        Extract the method (weapon, spell, ability) used.

        Args:
            input_lower: Lowercased action input
            intent: The classified action intent

        Returns:
            Method string or None if not found
        """
        # For spell intents, look for spell names
        if intent in {ActionIntent.COMBAT_SPELL, ActionIntent.MAGIC_CAST}:
            spell_names = [
                "fireball", "magic missile", "eldritch blast", "sacred flame",
                "healing word", "cure wounds", "shield", "mage armor"
            ]
            for spell in spell_names:
                if spell in input_lower:
                    return spell

        # For attack intents, look for weapon types
        if intent == ActionIntent.COMBAT_ATTACK:
            weapon_types = [
                "sword", "dagger", "bow", "crossbow", "axe", "mace",
                "staff", "wand", "fist", "fists", "claws"
            ]
            for weapon in weapon_types:
                if weapon in input_lower:
                    return weapon

        # For ability intents, look for ability names
        if intent == ActionIntent.COMBAT_ABILITY:
            abilities = [
                "rage", "sneak attack", "divine smite", "action surge",
                "flurry of blows", "cunning action"
            ]
            for ability in abilities:
                if ability in input_lower:
                    return ability

        return None

    def _extract_modifiers(self, input_lower: str) -> list[str]:
        """
        Extract action modifiers like advantage, stealth, etc.

        Args:
            input_lower: Lowercased action input

        Returns:
            List of modifier strings
        """
        modifiers: list[str] = []

        modifier_keywords = {
            "advantage": ["advantage", "with advantage"],
            "disadvantage": ["disadvantage", "with disadvantage"],
            "stealth": ["stealth", "stealthily", "quietly", "sneakily"],
            "careful": ["carefully", "cautiously", "gently"],
            "reckless": ["recklessly", "wildly", "aggressively"],
            "precise": ["precisely", "accurately", "carefully aimed"]
        }

        for modifier, keywords in modifier_keywords.items():
            if any(kw in input_lower for kw in keywords):
                modifiers.append(modifier)

        return modifiers


__all__ = [
    "ActionIntent",
    "ParsedAction",
    "AmbiguityType",
    "Ambiguity",
    "ValidationResult",
    "InterpretationResult",
    "ClarificationRequest",
    "ActionInterpreter",
    "LLMClient",
]
