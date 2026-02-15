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

logger = logging.getLogger("dm20-protocol")


# ------------------------------------------------------------------
# Terminology style hint formatting
# ------------------------------------------------------------------

def format_style_hint(preferences: dict[str, str]) -> str:
    """Format language preferences into a natural-language hint for the LLM.

    Converts the StyleTracker preferences summary into a readable prompt
    fragment that instructs the LLM to mirror the player's language style.

    Args:
        preferences: Dict mapping category to language ("en" or "it")
            Example: {"spell": "en", "skill": "it", "combat": "it"}

    Returns:
        A formatted hint string suitable for injection into the narrator prompt.
        Returns empty string if preferences dict is empty.

    Example:
        >>> format_style_hint({"spell": "en", "skill": "it"})
        "Player language preferences (mirror their style):\n- Spells: English (e.g., 'Fireball' not 'Palla di Fuoco')\n- Skills: Italian (e.g., 'Furtività' not 'Stealth')"
    """
    if not preferences:
        return ""

    # Category name mapping for better readability
    category_names = {
        "spell": "Spells",
        "skill": "Skills",
        "ability": "Abilities",
        "condition": "Conditions",
        "combat": "Combat terms",
        "item": "Items",
        "class": "Classes",
        "race": "Races",
        "general": "General terms",
    }

    # Language name mapping
    lang_names = {"en": "English", "it": "Italian"}

    # Build lines
    lines = ["Player language preferences (mirror their style):"]
    for category, lang in sorted(preferences.items()):
        category_display = category_names.get(category, category.capitalize())
        lang_display = lang_names.get(lang, lang.upper())

        # Add examples for common categories
        examples = {
            ("spell", "en"): "(e.g., 'Fireball' not 'Palla di Fuoco')",
            ("spell", "it"): "(e.g., 'Palla di Fuoco' not 'Fireball')",
            ("skill", "en"): "(e.g., 'Stealth' not 'Furtività')",
            ("skill", "it"): "(e.g., 'Furtività' not 'Stealth')",
            ("combat", "en"): "(e.g., 'Initiative' not 'Iniziativa')",
            ("combat", "it"): "(e.g., 'Iniziativa' not 'Initiative')",
        }
        example = examples.get((category, lang), "")

        lines.append(f"- {category_display}: {lang_display} {example}".strip())

    return "\n".join(lines)


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

{style_hint}

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

DIALOGUE_TEMPLATE = """\
You are generating NPC dialogue for a D&D campaign.

NPC: {npc_name}
Description: {description}
Occupation: {occupation}
Attitude: {attitude}
Voice Profile:
  - Speech pattern: {speech_pattern}
  - Vocabulary level: {vocabulary_level}
  - Accent/Regional hints: {accent_hints}
  - Quirks: {quirks}
  - Emotional baseline: {emotional_baseline}

Scene Context:
  - Location: {location}
  - Topic: {topic}
  - Mood: {mood}
  - Listeners: {listeners}
  - Recent events: {recent_events}

Current tone: {tone}

Generate a single line of dialogue for {npc_name}. The dialogue should:
1. Match their voice profile and personality
2. Reflect their current attitude and emotional state
3. Be contextually appropriate to the scene
4. Sound natural and character-specific

Format your response as:
{npc_name}: "The dialogue text here" [optional stage direction in brackets]

Example:
Grumpy Innkeeper: "Ain't got no rooms left, stranger." [wipes a glass without looking up]
"""

CONVERSATION_TEMPLATE = """\
You are generating a multi-party conversation for a D&D campaign.

Participants:
{participants_info}

Scene:
  - Location: {location}
  - Topic: {topic}
  - Number of exchanges: {num_exchanges}

Generate a natural conversation with {num_exchanges} exchanges (each participant speaks once per exchange). \
Each line should match the speaker's voice profile and personality.

Format your response as:
NPC_NAME: "dialogue text" [optional stage direction]
NPC_NAME: "dialogue text" [optional stage direction]
...

Keep the conversation natural, with characters reacting to each other's statements.
"""

RECAP_TEMPLATE = """\
You are the Narrator of a D&D campaign. A player is resuming their session. Generate a \
"Previously on..." recap using ONLY the verified facts below — do not invent or embellish \
beyond what is stated.

Current Location: {location}
Active Quests: {active_quests}
Recent Events:
{recent_events}
Party Status: {party_status}

Generate a concise, atmospheric recap (2-3 short paragraphs) that:
1. Reminds the player where they are and what they were doing
2. Highlights the most significant recent events
3. Ends with a hook suggesting what to do next
4. Is written in second person ("You...")

Keep it under 200 words. Be vivid but factual.
"""


# ------------------------------------------------------------------
# Dialogue models
# ------------------------------------------------------------------

class VoiceProfile(BaseModel):
    """Voice characteristics for an NPC."""
    speech_pattern: str = "casual"  # formal, casual, archaic, crude, etc.
    vocabulary_level: str = "common"  # simple, common, educated, scholarly
    accent_hints: str = ""  # regional speech patterns
    quirks: list[str] = Field(default_factory=list)  # catchphrases, verbal tics
    emotional_baseline: str = "calm"  # calm, excitable, melancholic, etc.


class DialogueLine(BaseModel):
    """A single line of NPC dialogue."""
    speaker_name: str
    text: str
    tone: str = "neutral"  # friendly, hostile, nervous, etc.
    stage_direction: str = ""  # optional action/emotion note


class DialogueContext(BaseModel):
    """Context for dialogue generation."""
    speaker_name: str
    speaker_description: str = ""
    speaker_attitude: str = "neutral"
    speaker_occupation: str = ""
    listeners: list[str] = Field(default_factory=list)
    location: str = ""
    topic: str = ""
    mood: str = "neutral"
    recent_events: list[str] = Field(default_factory=list)


class Conversation(BaseModel):
    """A multi-line conversation between characters."""
    participants: list[str]
    lines: list[DialogueLine] = Field(default_factory=list)
    scene_description: str = ""


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
        self._voice_profiles: dict[str, VoiceProfile] = {}  # cache for consistency
        self._current_style_preferences: dict[str, str] = {}  # populated during reason() phase

    async def reason(self, context: dict[str, Any]) -> str:
        """Analyze context to determine what kind of description is needed.

        Examines the player action, current location, and recent events
        to decide on the appropriate narrative response type.

        Args:
            context: Game context dict with keys like 'player_action',
                'location', 'recent_events', 'setting', 'style_preferences', etc.

        Returns:
            A reasoning string describing the intended narrative approach.
        """
        player_action = context.get("player_action", "")
        location = context.get("location", {})
        location_name = location.get("name", "unknown location") if isinstance(location, dict) else str(location)

        # Store style preferences for use in act() phase
        self._current_style_preferences = context.get("style_preferences", {})

        # Determine the narrative task
        if not player_action:
            return f"No player action provided. Generating ambient description for {location_name}."

        # Classify what kind of narrative response is appropriate
        action_words = set(player_action.lower().split())
        if action_words & {"look", "examine", "inspect", "observe", "search"}:
            return f"Player is observing. Generate detailed description of {location_name}."
        elif action_words & {"enter", "go", "move", "walk", "travel"}:
            return f"Player is moving. Generate transition scene to/within {location_name}."
        elif action_words & {"talk", "speak", "ask", "greet", "converse", "chat", "question"}:
            return f"Player initiating dialogue. Generate NPC dialogue for {location_name}."
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
        # Format style hint from current preferences
        style_hint = format_style_hint(self._current_style_preferences)
        if style_hint:
            style_hint = f"\n{style_hint}\n"  # Add spacing

        return SCENE_DESCRIPTION_TEMPLATE.format(
            reasoning=reasoning,
            style=self.style.value,
            style_hint=style_hint,
        )

    def build_voice_profile(
        self,
        npc_name: str,
        description: str | None = None,
        occupation: str | None = None,
        attitude: str | None = None,
        bio: str | None = None,
    ) -> VoiceProfile:
        """Build voice profile from NPC attributes. Cache for consistency.

        Derives voice characteristics from NPC traits. For example:
        - Merchants: formal speech, sales-oriented
        - Guards: terse, authoritative
        - Scholars: educated vocabulary, formal
        - Thieves: casual, slang-heavy

        Args:
            npc_name: The NPC's name (used as cache key).
            description: Physical or personality description.
            occupation: The NPC's job or role.
            attitude: Current attitude (friendly, hostile, etc.).
            bio: Backstory and motivations.

        Returns:
            A VoiceProfile with derived speech characteristics.
        """
        # Return cached profile if available
        if npc_name in self._voice_profiles:
            return self._voice_profiles[npc_name]

        # Derive voice characteristics from occupation and attitude
        speech_pattern = "casual"
        vocabulary_level = "common"
        emotional_baseline = "calm"
        quirks: list[str] = []

        occupation_lower = (occupation or "").lower()
        attitude_lower = (attitude or "neutral").lower()

        # Derive from occupation
        if any(word in occupation_lower for word in ["merchant", "trader", "shopkeeper"]):
            speech_pattern = "formal"
            vocabulary_level = "common"
            quirks = ["customer-focused", "mentions prices"]
        elif any(word in occupation_lower for word in ["guard", "soldier", "captain"]):
            speech_pattern = "terse"
            vocabulary_level = "common"
            quirks = ["military precision", "commands"]
        elif any(word in occupation_lower for word in ["scholar", "wizard", "sage", "librarian"]):
            speech_pattern = "formal"
            vocabulary_level = "scholarly"
            quirks = ["pedantic", "cites sources"]
        elif any(word in occupation_lower for word in ["thief", "rogue", "pickpocket"]):
            speech_pattern = "casual"
            vocabulary_level = "common"
            quirks = ["street slang", "evasive"]
        elif any(word in occupation_lower for word in ["noble", "lord", "lady", "baron"]):
            speech_pattern = "formal"
            vocabulary_level = "educated"
            quirks = ["mentions titles", "proper etiquette"]
        elif any(word in occupation_lower for word in ["innkeeper", "bartender", "tavern"]):
            speech_pattern = "casual"
            vocabulary_level = "common"
            quirks = ["hospitable", "local gossip"]
        elif any(word in occupation_lower for word in ["priest", "cleric", "monk"]):
            speech_pattern = "formal"
            vocabulary_level = "educated"
            quirks = ["religious references", "blessings"]
        elif any(word in occupation_lower for word in ["peasant", "farmer", "laborer"]):
            speech_pattern = "casual"
            vocabulary_level = "simple"
            quirks = ["rural dialect", "practical concerns"]

        # Adjust for attitude
        if "hostile" in attitude_lower or "aggressive" in attitude_lower:
            emotional_baseline = "aggressive"
            quirks.append("threatening")
        elif "friendly" in attitude_lower or "helpful" in attitude_lower:
            emotional_baseline = "warm"
            quirks.append("welcoming")
        elif "nervous" in attitude_lower or "fearful" in attitude_lower:
            emotional_baseline = "anxious"
            quirks.append("stammers")
        elif "suspicious" in attitude_lower or "wary" in attitude_lower:
            emotional_baseline = "guarded"
            quirks.append("evasive")

        profile = VoiceProfile(
            speech_pattern=speech_pattern,
            vocabulary_level=vocabulary_level,
            accent_hints="",
            quirks=quirks,
            emotional_baseline=emotional_baseline,
        )

        # Cache the profile
        self._voice_profiles[npc_name] = profile
        return profile

    async def generate_recap(
        self,
        location: str,
        active_quests: str,
        recent_events: str,
        party_status: str,
    ) -> str:
        """Generate an atmospheric session recap using the LLM.

        Formats verified session facts into a narrative "Previously on..."
        recap suitable for session resumption.

        Args:
            location: Current party location.
            active_quests: Summary of active quests/objectives.
            recent_events: Formatted string of recent significant events.
            party_status: Brief party condition summary (HP, conditions).

        Returns:
            Atmospheric recap text (2-3 paragraphs).
        """
        prompt = RECAP_TEMPLATE.format(
            location=location or "Unknown",
            active_quests=active_quests or "None active",
            recent_events=recent_events or "- No recent events recorded",
            party_status=party_status or "Unknown",
        )
        response = await self.llm.generate(prompt, max_tokens=self.max_tokens)
        return response.strip()

    async def generate_dialogue(
        self,
        dialogue_context: DialogueContext,
        tone_override: str | None = None,
    ) -> DialogueLine:
        """Generate a single line of NPC dialogue using LLM.

        Args:
            dialogue_context: Context information for dialogue generation.
            tone_override: Optional tone to override the context mood.

        Returns:
            A DialogueLine with the generated speech.
        """
        # Build or retrieve voice profile
        voice = self.build_voice_profile(
            npc_name=dialogue_context.speaker_name,
            description=dialogue_context.speaker_description,
            occupation=dialogue_context.speaker_occupation,
            attitude=dialogue_context.speaker_attitude,
        )

        # Build prompt
        prompt = self._build_dialogue_prompt(dialogue_context, voice, tone_override)

        # Generate dialogue
        response = await self.llm.generate(prompt, max_tokens=self.max_tokens)

        # Parse response
        return self._parse_dialogue_line(response, dialogue_context.speaker_name, tone_override)

    async def generate_conversation(
        self,
        participants: list[DialogueContext],
        topic: str,
        num_exchanges: int = 3,
    ) -> Conversation:
        """Generate a multi-party conversation.

        Args:
            participants: List of DialogueContext for each participant.
            topic: The conversation topic or prompt.
            num_exchanges: Number of back-and-forth exchanges (each participant speaks once per exchange).

        Returns:
            A Conversation with multiple DialogueLines.
        """
        # Build voice profiles for all participants
        voices = {
            ctx.speaker_name: self.build_voice_profile(
                npc_name=ctx.speaker_name,
                description=ctx.speaker_description,
                occupation=ctx.speaker_occupation,
                attitude=ctx.speaker_attitude,
            )
            for ctx in participants
        }

        # Build conversation prompt
        prompt = self._build_conversation_prompt(participants, voices, topic, num_exchanges)

        # Generate conversation
        response = await self.llm.generate(prompt, max_tokens=self.max_tokens * 2)

        # Parse response
        lines = self._parse_conversation(response)

        return Conversation(
            participants=[ctx.speaker_name for ctx in participants],
            lines=lines,
            scene_description="",
        )

    def _build_dialogue_prompt(
        self,
        context: DialogueContext,
        voice: VoiceProfile,
        tone_override: str | None = None,
    ) -> str:
        """Build LLM prompt for dialogue generation.

        Args:
            context: The dialogue context.
            voice: The NPC's voice profile.
            tone_override: Optional tone override.

        Returns:
            Formatted prompt string.
        """
        tone = tone_override or context.mood
        recent_events_str = "; ".join(context.recent_events) if context.recent_events else "None"
        listeners_str = ", ".join(context.listeners) if context.listeners else "None"
        quirks_str = ", ".join(voice.quirks) if voice.quirks else "None"

        return DIALOGUE_TEMPLATE.format(
            npc_name=context.speaker_name,
            description=context.speaker_description or "Unknown",
            occupation=context.speaker_occupation or "Unknown",
            attitude=context.speaker_attitude or "neutral",
            speech_pattern=voice.speech_pattern,
            vocabulary_level=voice.vocabulary_level,
            accent_hints=voice.accent_hints or "None",
            quirks=quirks_str,
            emotional_baseline=voice.emotional_baseline,
            location=context.location or "Unknown location",
            topic=context.topic or "General conversation",
            mood=context.mood,
            tone=tone,
            listeners=listeners_str,
            recent_events=recent_events_str,
        )

    def _build_conversation_prompt(
        self,
        participants: list[DialogueContext],
        voices: dict[str, VoiceProfile],
        topic: str,
        num_exchanges: int,
    ) -> str:
        """Build LLM prompt for multi-party conversation.

        Args:
            participants: List of participant contexts.
            voices: Voice profiles by name.
            topic: Conversation topic.
            num_exchanges: Number of exchanges.

        Returns:
            Formatted prompt string.
        """
        # Build participant info
        participants_info_lines = []
        for ctx in participants:
            voice = voices[ctx.speaker_name]
            quirks_str = ", ".join(voice.quirks) if voice.quirks else "None"
            participants_info_lines.append(
                f"- {ctx.speaker_name} ({ctx.speaker_occupation or 'Unknown'})\n"
                f"  Attitude: {ctx.speaker_attitude or 'neutral'}\n"
                f"  Speech: {voice.speech_pattern}, {voice.vocabulary_level} vocabulary\n"
                f"  Baseline: {voice.emotional_baseline}\n"
                f"  Quirks: {quirks_str}"
            )

        participants_info = "\n\n".join(participants_info_lines)
        location = participants[0].location if participants else "Unknown location"

        return CONVERSATION_TEMPLATE.format(
            participants_info=participants_info,
            location=location,
            topic=topic,
            num_exchanges=num_exchanges,
        )

    def _parse_dialogue_line(
        self,
        response: str,
        speaker_name: str,
        tone: str | None = None,
    ) -> DialogueLine:
        """Parse LLM response into a DialogueLine.

        Expected format:
        SPEAKER_NAME: "dialogue text" [stage direction]

        Args:
            response: Raw LLM response.
            speaker_name: Expected speaker name.
            tone: Optional tone.

        Returns:
            Parsed DialogueLine.
        """
        response = response.strip()

        # Try to extract dialogue and stage direction
        text = ""
        stage_direction = ""

        # Look for pattern: NAME: "text" [direction]
        if ":" in response:
            parts = response.split(":", 1)
            if len(parts) == 2:
                dialogue_part = parts[1].strip()

                # Extract quoted text
                if '"' in dialogue_part:
                    quote_start = dialogue_part.index('"')
                    quote_end = dialogue_part.rfind('"')
                    if quote_start < quote_end:
                        text = dialogue_part[quote_start + 1 : quote_end]

                        # Extract stage direction if present
                        after_quote = dialogue_part[quote_end + 1 :].strip()
                        if after_quote.startswith("[") and after_quote.endswith("]"):
                            stage_direction = after_quote[1:-1].strip()

        # Fallback: use entire response if parsing failed
        if not text:
            text = response

        return DialogueLine(
            speaker_name=speaker_name,
            text=text,
            tone=tone or "neutral",
            stage_direction=stage_direction,
        )

    def _parse_conversation(self, response: str) -> list[DialogueLine]:
        """Parse LLM response into multiple DialogueLines.

        Expected format:
        NAME: "text" [direction]
        NAME: "text" [direction]
        ...

        Args:
            response: Raw LLM response.

        Returns:
            List of parsed DialogueLines.
        """
        lines: list[DialogueLine] = []
        response_lines = response.strip().split("\n")

        for line in response_lines:
            line = line.strip()
            if not line or not ":" in line:
                continue

            # Extract speaker name
            parts = line.split(":", 1)
            speaker_name = parts[0].strip()

            # Parse the rest as a dialogue line
            dialogue_line = self._parse_dialogue_line(line, speaker_name)
            lines.append(dialogue_line)

        return lines


__all__ = [
    "NarratorAgent",
    "NarrativeStyle",
    "LLMClient",
    "SCENE_DESCRIPTION_TEMPLATE",
    "DIALOGUE_TEMPLATE",
    "CONVERSATION_TEMPLATE",
    "VoiceProfile",
    "DialogueLine",
    "DialogueContext",
    "Conversation",
    "format_style_hint",
]
