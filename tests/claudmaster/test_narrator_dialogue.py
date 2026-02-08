"""
Unit tests for NarratorAgent dialogue generation capabilities.

Tests the enhanced narrator with NPC dialogue, voice profiles,
and multi-party conversations. All tests use mocked LLM clients.
"""

import asyncio
import pytest
from typing import Any

from dm20_protocol.claudmaster.agents.narrator import (
    NarratorAgent,
    NarrativeStyle,
    VoiceProfile,
    DialogueLine,
    DialogueContext,
    Conversation,
    DIALOGUE_TEMPLATE,
    CONVERSATION_TEMPLATE,
)


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------

class MockLLM:
    """LLM client that returns canned responses and records calls."""

    def __init__(self, response: str = 'Innkeeper: "Welcome to me tavern!" [grins widely]') -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens})
        return self.response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm() -> MockLLM:
    return MockLLM()


@pytest.fixture
def narrator(mock_llm: MockLLM) -> NarratorAgent:
    return NarratorAgent(llm=mock_llm, style=NarrativeStyle.DESCRIPTIVE)


@pytest.fixture
def dialogue_context() -> DialogueContext:
    return DialogueContext(
        speaker_name="Grimbold",
        speaker_description="A gruff dwarf merchant",
        speaker_attitude="friendly",
        speaker_occupation="merchant",
        listeners=["Player"],
        location="Market Square",
        topic="buying supplies",
        mood="cheerful",
        recent_events=["Player just arrived in town"],
    )


@pytest.fixture
def multi_context() -> list[DialogueContext]:
    return [
        DialogueContext(
            speaker_name="Guard",
            speaker_occupation="guard",
            speaker_attitude="suspicious",
            location="City Gate",
        ),
        DialogueContext(
            speaker_name="Merchant",
            speaker_occupation="merchant",
            speaker_attitude="friendly",
            location="City Gate",
        ),
    ]


# ---------------------------------------------------------------------------
# Pydantic Model Tests
# ---------------------------------------------------------------------------

class TestVoiceProfile:
    """Tests for VoiceProfile model."""

    def test_default_values(self) -> None:
        profile = VoiceProfile()
        assert profile.speech_pattern == "casual"
        assert profile.vocabulary_level == "common"
        assert profile.accent_hints == ""
        assert profile.quirks == []
        assert profile.emotional_baseline == "calm"

    def test_custom_values(self) -> None:
        profile = VoiceProfile(
            speech_pattern="formal",
            vocabulary_level="scholarly",
            accent_hints="Scottish",
            quirks=["says 'indeed' often"],
            emotional_baseline="excitable",
        )
        assert profile.speech_pattern == "formal"
        assert profile.vocabulary_level == "scholarly"
        assert profile.accent_hints == "Scottish"
        assert len(profile.quirks) == 1
        assert profile.emotional_baseline == "excitable"


class TestDialogueLine:
    """Tests for DialogueLine model."""

    def test_required_fields(self) -> None:
        line = DialogueLine(speaker_name="Bob", text="Hello there")
        assert line.speaker_name == "Bob"
        assert line.text == "Hello there"
        assert line.tone == "neutral"
        assert line.stage_direction == ""

    def test_all_fields(self) -> None:
        line = DialogueLine(
            speaker_name="Alice",
            text="What brings you here?",
            tone="curious",
            stage_direction="leans forward",
        )
        assert line.speaker_name == "Alice"
        assert line.text == "What brings you here?"
        assert line.tone == "curious"
        assert line.stage_direction == "leans forward"


class TestDialogueContext:
    """Tests for DialogueContext model."""

    def test_minimal_context(self) -> None:
        ctx = DialogueContext(speaker_name="NPC")
        assert ctx.speaker_name == "NPC"
        assert ctx.speaker_description == ""
        assert ctx.speaker_attitude == "neutral"
        assert ctx.listeners == []

    def test_full_context(self) -> None:
        ctx = DialogueContext(
            speaker_name="Wizard",
            speaker_description="Old and wise",
            speaker_attitude="helpful",
            speaker_occupation="wizard",
            listeners=["Fighter", "Rogue"],
            location="Tower",
            topic="ancient spell",
            mood="serious",
            recent_events=["Dragon attack"],
        )
        assert ctx.speaker_name == "Wizard"
        assert ctx.speaker_occupation == "wizard"
        assert len(ctx.listeners) == 2
        assert ctx.topic == "ancient spell"


class TestConversation:
    """Tests for Conversation model."""

    def test_empty_conversation(self) -> None:
        conv = Conversation(participants=["A", "B"])
        assert conv.participants == ["A", "B"]
        assert conv.lines == []
        assert conv.scene_description == ""

    def test_conversation_with_lines(self) -> None:
        lines = [
            DialogueLine(speaker_name="A", text="Hi"),
            DialogueLine(speaker_name="B", text="Hello"),
        ]
        conv = Conversation(
            participants=["A", "B"],
            lines=lines,
            scene_description="A quiet room",
        )
        assert len(conv.lines) == 2
        assert conv.scene_description == "A quiet room"


# ---------------------------------------------------------------------------
# Voice Profile Building
# ---------------------------------------------------------------------------

class TestBuildVoiceProfile:
    """Tests for build_voice_profile method."""

    def test_merchant_profile(self, narrator: NarratorAgent) -> None:
        profile = narrator.build_voice_profile(
            npc_name="Trader Joe",
            occupation="merchant",
            attitude="friendly",
        )
        assert profile.speech_pattern == "formal"
        assert "customer-focused" in profile.quirks or "mentions prices" in profile.quirks

    def test_guard_profile(self, narrator: NarratorAgent) -> None:
        profile = narrator.build_voice_profile(
            npc_name="Captain",
            occupation="guard",
            attitude="neutral",
        )
        assert profile.speech_pattern == "terse"
        assert any("military" in q or "command" in q for q in profile.quirks)

    def test_scholar_profile(self, narrator: NarratorAgent) -> None:
        profile = narrator.build_voice_profile(
            npc_name="Professor",
            occupation="wizard",
            attitude="neutral",
        )
        assert profile.speech_pattern == "formal"
        assert profile.vocabulary_level == "scholarly"

    def test_thief_profile(self, narrator: NarratorAgent) -> None:
        profile = narrator.build_voice_profile(
            npc_name="Sneaky Pete",
            occupation="thief",
            attitude="neutral",
        )
        assert profile.speech_pattern == "casual"
        assert any("slang" in q or "evasive" in q for q in profile.quirks)

    def test_hostile_attitude(self, narrator: NarratorAgent) -> None:
        profile = narrator.build_voice_profile(
            npc_name="Bully",
            occupation="peasant",
            attitude="hostile",
        )
        assert profile.emotional_baseline == "aggressive"
        assert "threatening" in profile.quirks

    def test_friendly_attitude(self, narrator: NarratorAgent) -> None:
        profile = narrator.build_voice_profile(
            npc_name="Friend",
            occupation="innkeeper",
            attitude="friendly",
        )
        assert profile.emotional_baseline == "warm"
        assert "welcoming" in profile.quirks

    def test_caching_behavior(self, narrator: NarratorAgent) -> None:
        # First call creates profile
        profile1 = narrator.build_voice_profile(
            npc_name="Cached NPC",
            occupation="merchant",
        )
        # Second call should return cached profile
        profile2 = narrator.build_voice_profile(
            npc_name="Cached NPC",
            occupation="guard",  # Different occupation should be ignored
        )
        assert profile1 is profile2
        assert profile2.speech_pattern == "formal"  # Original merchant pattern

    def test_different_npcs_different_profiles(self, narrator: NarratorAgent) -> None:
        profile1 = narrator.build_voice_profile(npc_name="NPC1", occupation="merchant")
        profile2 = narrator.build_voice_profile(npc_name="NPC2", occupation="guard")
        assert profile1 is not profile2
        assert profile1.speech_pattern != profile2.speech_pattern


# ---------------------------------------------------------------------------
# Dialogue Generation
# ---------------------------------------------------------------------------

class TestGenerateDialogue:
    """Tests for generate_dialogue method."""

    def test_generates_dialogue_line(
        self, narrator: NarratorAgent, dialogue_context: DialogueContext, mock_llm: MockLLM,
    ) -> None:
        result = asyncio.run(narrator.generate_dialogue(dialogue_context))
        assert isinstance(result, DialogueLine)
        assert result.speaker_name == "Grimbold"
        assert len(mock_llm.calls) == 1

    def test_calls_llm_with_prompt(
        self, narrator: NarratorAgent, dialogue_context: DialogueContext, mock_llm: MockLLM,
    ) -> None:
        asyncio.run(narrator.generate_dialogue(dialogue_context))
        prompt = mock_llm.calls[0]["prompt"]
        assert "Grimbold" in prompt
        assert "merchant" in prompt

    def test_uses_voice_profile(
        self, narrator: NarratorAgent, dialogue_context: DialogueContext, mock_llm: MockLLM,
    ) -> None:
        asyncio.run(narrator.generate_dialogue(dialogue_context))
        prompt = mock_llm.calls[0]["prompt"]
        # Check that voice profile characteristics are in prompt
        assert "speech_pattern" in prompt.lower() or "formal" in prompt or "casual" in prompt

    def test_tone_override(
        self, narrator: NarratorAgent, dialogue_context: DialogueContext, mock_llm: MockLLM,
    ) -> None:
        result = asyncio.run(narrator.generate_dialogue(dialogue_context, tone_override="angry"))
        assert result.tone == "angry"

    def test_parsing_dialogue_with_stage_direction(
        self, narrator: NarratorAgent, dialogue_context: DialogueContext, mock_llm: MockLLM,
    ) -> None:
        mock_llm.response = 'Grimbold: "Ye want supplies?" [scratches beard]'
        result = asyncio.run(narrator.generate_dialogue(dialogue_context))
        assert result.text == "Ye want supplies?"
        assert result.stage_direction == "scratches beard"

    def test_parsing_dialogue_without_stage_direction(
        self, narrator: NarratorAgent, dialogue_context: DialogueContext, mock_llm: MockLLM,
    ) -> None:
        mock_llm.response = 'Grimbold: "Welcome stranger!"'
        result = asyncio.run(narrator.generate_dialogue(dialogue_context))
        assert result.text == "Welcome stranger!"
        assert result.stage_direction == ""


# ---------------------------------------------------------------------------
# Conversation Generation
# ---------------------------------------------------------------------------

class TestGenerateConversation:
    """Tests for generate_conversation method."""

    def test_generates_conversation(
        self, narrator: NarratorAgent, multi_context: list[DialogueContext], mock_llm: MockLLM,
    ) -> None:
        mock_llm.response = 'Guard: "Halt!"\nMerchant: "Good day!"'
        result = asyncio.run(narrator.generate_conversation(multi_context, topic="greeting", num_exchanges=1))
        assert isinstance(result, Conversation)
        assert len(result.participants) == 2
        assert len(mock_llm.calls) == 1

    def test_conversation_has_multiple_lines(
        self, narrator: NarratorAgent, multi_context: list[DialogueContext], mock_llm: MockLLM,
    ) -> None:
        mock_llm.response = 'Guard: "State your business."\nMerchant: "Just passing through."'
        result = asyncio.run(narrator.generate_conversation(multi_context, topic="checkpoint", num_exchanges=1))
        assert len(result.lines) == 2

    def test_conversation_respects_num_exchanges(
        self, narrator: NarratorAgent, multi_context: list[DialogueContext], mock_llm: MockLLM,
    ) -> None:
        asyncio.run(narrator.generate_conversation(multi_context, topic="test", num_exchanges=5))
        prompt = mock_llm.calls[0]["prompt"]
        assert "5" in prompt

    def test_conversation_uses_voice_profiles(
        self, narrator: NarratorAgent, multi_context: list[DialogueContext], mock_llm: MockLLM,
    ) -> None:
        mock_llm.response = 'Guard: "Halt."\nMerchant: "Hello friend!"'
        result = asyncio.run(narrator.generate_conversation(multi_context, topic="greeting", num_exchanges=1))
        # Verify that voice profiles were built (cached)
        assert "Guard" in narrator._voice_profiles
        assert "Merchant" in narrator._voice_profiles

    def test_conversation_max_tokens_doubled(
        self, narrator: NarratorAgent, multi_context: list[DialogueContext], mock_llm: MockLLM,
    ) -> None:
        asyncio.run(narrator.generate_conversation(multi_context, topic="test", num_exchanges=2))
        # Conversation should use 2x max_tokens
        assert mock_llm.calls[0]["max_tokens"] == narrator.max_tokens * 2


# ---------------------------------------------------------------------------
# Prompt Building
# ---------------------------------------------------------------------------

class TestBuildDialoguePrompt:
    """Tests for _build_dialogue_prompt method."""

    def test_includes_npc_name(self, narrator: NarratorAgent, dialogue_context: DialogueContext) -> None:
        voice = narrator.build_voice_profile(npc_name=dialogue_context.speaker_name, occupation="merchant")
        prompt = narrator._build_dialogue_prompt(dialogue_context, voice)
        assert dialogue_context.speaker_name in prompt

    def test_includes_voice_profile(self, narrator: NarratorAgent, dialogue_context: DialogueContext) -> None:
        voice = narrator.build_voice_profile(npc_name=dialogue_context.speaker_name, occupation="merchant")
        prompt = narrator._build_dialogue_prompt(dialogue_context, voice)
        assert voice.speech_pattern in prompt
        assert voice.vocabulary_level in prompt

    def test_includes_context_details(self, narrator: NarratorAgent, dialogue_context: DialogueContext) -> None:
        voice = narrator.build_voice_profile(npc_name=dialogue_context.speaker_name, occupation="merchant")
        prompt = narrator._build_dialogue_prompt(dialogue_context, voice)
        assert dialogue_context.location in prompt
        assert dialogue_context.topic in prompt

    def test_tone_override(self, narrator: NarratorAgent, dialogue_context: DialogueContext) -> None:
        voice = narrator.build_voice_profile(npc_name=dialogue_context.speaker_name, occupation="merchant")
        prompt = narrator._build_dialogue_prompt(dialogue_context, voice, tone_override="angry")
        assert "angry" in prompt


class TestBuildConversationPrompt:
    """Tests for _build_conversation_prompt method."""

    def test_includes_all_participants(self, narrator: NarratorAgent, multi_context: list[DialogueContext]) -> None:
        voices = {
            ctx.speaker_name: narrator.build_voice_profile(
                npc_name=ctx.speaker_name,
                occupation=ctx.speaker_occupation,
            )
            for ctx in multi_context
        }
        prompt = narrator._build_conversation_prompt(multi_context, voices, topic="test", num_exchanges=2)
        for ctx in multi_context:
            assert ctx.speaker_name in prompt

    def test_includes_voice_profiles(self, narrator: NarratorAgent, multi_context: list[DialogueContext]) -> None:
        voices = {
            ctx.speaker_name: narrator.build_voice_profile(
                npc_name=ctx.speaker_name,
                occupation=ctx.speaker_occupation,
            )
            for ctx in multi_context
        }
        prompt = narrator._build_conversation_prompt(multi_context, voices, topic="test", num_exchanges=2)
        for voice in voices.values():
            assert voice.speech_pattern in prompt

    def test_includes_topic(self, narrator: NarratorAgent, multi_context: list[DialogueContext]) -> None:
        voices = {
            ctx.speaker_name: narrator.build_voice_profile(
                npc_name=ctx.speaker_name,
                occupation=ctx.speaker_occupation,
            )
            for ctx in multi_context
        }
        prompt = narrator._build_conversation_prompt(multi_context, voices, topic="ancient artifact", num_exchanges=2)
        assert "ancient artifact" in prompt


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

class TestParseDialogueLine:
    """Tests for _parse_dialogue_line method."""

    def test_parses_standard_format(self, narrator: NarratorAgent) -> None:
        response = 'Bob: "Hello there" [waves]'
        result = narrator._parse_dialogue_line(response, "Bob", "friendly")
        assert result.speaker_name == "Bob"
        assert result.text == "Hello there"
        assert result.stage_direction == "waves"
        assert result.tone == "friendly"

    def test_parses_without_stage_direction(self, narrator: NarratorAgent) -> None:
        response = 'Alice: "How are you?"'
        result = narrator._parse_dialogue_line(response, "Alice")
        assert result.text == "How are you?"
        assert result.stage_direction == ""

    def test_handles_malformed_response(self, narrator: NarratorAgent) -> None:
        response = "Some random text without proper format"
        result = narrator._parse_dialogue_line(response, "NPC")
        assert result.speaker_name == "NPC"
        assert result.text == response  # Fallback to entire response


class TestParseConversation:
    """Tests for _parse_conversation method."""

    def test_parses_multiple_lines(self, narrator: NarratorAgent) -> None:
        response = 'A: "Hi"\nB: "Hello"\nA: "How are you?"'
        result = narrator._parse_conversation(response)
        assert len(result) == 3
        assert result[0].speaker_name == "A"
        assert result[1].speaker_name == "B"

    def test_ignores_empty_lines(self, narrator: NarratorAgent) -> None:
        response = 'A: "Hi"\n\nB: "Hello"\n'
        result = narrator._parse_conversation(response)
        assert len(result) == 2

    def test_handles_lines_without_colon(self, narrator: NarratorAgent) -> None:
        response = 'A: "Hi"\nSome narration text\nB: "Hello"'
        result = narrator._parse_conversation(response)
        # Should only parse lines with colons
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Extended reason() method
# ---------------------------------------------------------------------------

class TestExtendedReason:
    """Tests for extended reason() method with dialogue detection."""

    def test_detects_talk_action(self, narrator: NarratorAgent) -> None:
        result = asyncio.run(narrator.reason({
            "player_action": "talk to the guard",
            "location": {"name": "Gate"},
        }))
        assert "dialogue" in result.lower()

    def test_detects_speak_action(self, narrator: NarratorAgent) -> None:
        result = asyncio.run(narrator.reason({
            "player_action": "speak with the wizard",
            "location": {"name": "Tower"},
        }))
        assert "dialogue" in result.lower()

    def test_detects_ask_action(self, narrator: NarratorAgent) -> None:
        result = asyncio.run(narrator.reason({
            "player_action": "ask about the quest",
            "location": {"name": "Tavern"},
        }))
        assert "dialogue" in result.lower()

    def test_detects_greet_action(self, narrator: NarratorAgent) -> None:
        result = asyncio.run(narrator.reason({
            "player_action": "greet the innkeeper",
            "location": {"name": "Inn"},
        }))
        assert "dialogue" in result.lower()

    def test_detects_converse_action(self, narrator: NarratorAgent) -> None:
        result = asyncio.run(narrator.reason({
            "player_action": "converse with the merchant",
            "location": {"name": "Market"},
        }))
        assert "dialogue" in result.lower()


# ---------------------------------------------------------------------------
# Template Constants
# ---------------------------------------------------------------------------

class TestTemplateConstants:
    """Tests for template constant definitions."""

    def test_dialogue_template_exists(self) -> None:
        assert DIALOGUE_TEMPLATE
        assert "NPC:" in DIALOGUE_TEMPLATE
        assert "{npc_name}" in DIALOGUE_TEMPLATE

    def test_conversation_template_exists(self) -> None:
        assert CONVERSATION_TEMPLATE
        assert "Participants:" in CONVERSATION_TEMPLATE
        assert "{num_exchanges}" in CONVERSATION_TEMPLATE
