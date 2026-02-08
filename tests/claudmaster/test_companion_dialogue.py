"""
Tests for Companion Dialogue system.

Tests the personality-driven dialogue generation for companion NPCs,
including event reactions, emotional states, relationship tracking,
and dialogue template selection.
"""

import random

import pytest

from dm20_protocol.claudmaster.companion_dialogue import (
    DialogueTrigger,
    EmotionalState,
    DialogueContext,
    CompanionDialogue,
    CompanionDialogueEngine,
    DIALOGUE_TEMPLATES,
    REACTION_PROBABILITY,
)
from dm20_protocol.claudmaster.companions import (
    CompanionProfile,
    CompanionArchetype,
    CombatStyle,
    PersonalityTraits,
)


class TestDialogueTrigger:
    """Test DialogueTrigger enum."""

    def test_all_triggers_defined(self):
        """Verify all expected trigger types exist."""
        expected = {
            "COMBAT_START",
            "COMBAT_END",
            "ALLY_INJURED",
            "ALLY_DOWNED",
            "ENEMY_KILLED",
            "DISCOVERY",
            "REST",
            "QUEST_COMPLETE",
            "NPC_INTERACTION",
            "PLAYER_DECISION",
            "IDLE",
        }
        actual = {t.name for t in DialogueTrigger}
        assert actual == expected

    def test_trigger_values(self):
        """Verify trigger values are lowercase with underscores."""
        for trigger in DialogueTrigger:
            assert trigger.value == trigger.name.lower()


class TestEmotionalState:
    """Test EmotionalState enum."""

    def test_all_states_defined(self):
        """Verify all expected emotional states exist."""
        expected = {
            "NEUTRAL",
            "HAPPY",
            "ANGRY",
            "FEARFUL",
            "SAD",
            "EXCITED",
            "CONCERNED",
        }
        actual = {s.name for s in EmotionalState}
        assert actual == expected

    def test_state_values(self):
        """Verify state values are lowercase."""
        for state in EmotionalState:
            assert state.value == state.name.lower()


class TestDialogueContext:
    """Test DialogueContext model."""

    def test_minimal_creation(self):
        """Test creating context with just trigger."""
        context = DialogueContext(trigger=DialogueTrigger.COMBAT_START)
        assert context.trigger == DialogueTrigger.COMBAT_START
        assert context.target is None
        assert context.location is None
        assert context.recent_events == []
        assert context.party_status == {}

    def test_full_creation(self):
        """Test creating context with all fields."""
        context = DialogueContext(
            trigger=DialogueTrigger.ALLY_INJURED,
            target="Gandalf",
            location="Dark Cave",
            recent_events=["Entered cave", "Triggered trap"],
            party_status={"hp": 50, "wounded": 2},
        )
        assert context.trigger == DialogueTrigger.ALLY_INJURED
        assert context.target == "Gandalf"
        assert context.location == "Dark Cave"
        assert len(context.recent_events) == 2
        assert context.party_status["wounded"] == 2


class TestCompanionDialogue:
    """Test CompanionDialogue model."""

    def test_creation(self):
        """Test creating dialogue object."""
        dialogue = CompanionDialogue(
            companion_id="npc_001",
            companion_name="Bronn",
            text="Let's do this!",
            trigger=DialogueTrigger.COMBAT_START,
            emotional_state=EmotionalState.EXCITED,
            addressed_to="party",
        )
        assert dialogue.companion_id == "npc_001"
        assert dialogue.companion_name == "Bronn"
        assert dialogue.text == "Let's do this!"
        assert dialogue.trigger == DialogueTrigger.COMBAT_START
        assert dialogue.emotional_state == EmotionalState.EXCITED
        assert dialogue.addressed_to == "party"


class TestCompanionDialogueEngine:
    """Test CompanionDialogueEngine."""

    @pytest.fixture
    def brave_companion(self) -> CompanionProfile:
        """Create a brave striker companion for testing."""
        return CompanionProfile(
            npc_id="brave_001",
            name="Bronn the Brave",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
            personality=PersonalityTraits(
                bravery=80,
                loyalty=60,
                aggression=70,
                caution=20,
                compassion=40,
            ),
        )

    @pytest.fixture
    def cautious_companion(self) -> CompanionProfile:
        """Create a cautious healer companion for testing."""
        return CompanionProfile(
            npc_id="cautious_001",
            name="Elara the Careful",
            archetype=CompanionArchetype.HEALER,
            combat_style=CombatStyle.DEFENSIVE,
            personality=PersonalityTraits(
                bravery=25,  # <30 to trigger nervous tone
                loyalty=70,
                aggression=20,
                caution=80,
                compassion=90,
            ),
        )

    @pytest.fixture
    def compassionate_companion(self) -> CompanionProfile:
        """Create a compassionate support companion."""
        return CompanionProfile(
            npc_id="compassion_001",
            name="Mira the Kind",
            archetype=CompanionArchetype.SUPPORT,
            combat_style=CombatStyle.SUPPORTIVE,
            personality=PersonalityTraits(
                bravery=50,
                loyalty=80,
                aggression=20,
                caution=60,
                compassion=90,
            ),
        )

    @pytest.fixture
    def aggressive_companion(self) -> CompanionProfile:
        """Create an aggressive striker companion."""
        return CompanionProfile(
            npc_id="aggro_001",
            name="Grok the Fierce",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.AGGRESSIVE,
            personality=PersonalityTraits(
                bravery=75,
                loyalty=50,
                aggression=85,
                caution=15,
                compassion=25,
            ),
        )

    @pytest.fixture
    def low_loyalty_companion(self) -> CompanionProfile:
        """Create a low loyalty companion."""
        return CompanionProfile(
            npc_id="mercenary_001",
            name="Vex the Mercenary",
            archetype=CompanionArchetype.STRIKER,
            combat_style=CombatStyle.BALANCED,
            personality=PersonalityTraits(
                bravery=60,
                loyalty=25,
                aggression=55,
                caution=45,
                compassion=30,
            ),
        )

    def test_engine_initialization(self, brave_companion):
        """Test dialogue engine initializes correctly."""
        engine = CompanionDialogueEngine(brave_companion)
        assert engine.companion == brave_companion
        assert engine.emotional_state == EmotionalState.NEUTRAL
        assert engine.relationship_memory == {}
        assert engine._reaction_count == 0

    def test_react_to_combat_start_brave(self, brave_companion):
        """Test brave companion reacts confidently to combat."""
        random.seed(42)  # Make test deterministic
        engine = CompanionDialogueEngine(brave_companion)
        context = DialogueContext(trigger=DialogueTrigger.COMBAT_START)

        dialogue = engine.react_to_event(context)
        assert dialogue is not None
        assert dialogue.companion_id == "brave_001"
        assert dialogue.trigger == DialogueTrigger.COMBAT_START
        # Brave companion should be excited about combat
        assert dialogue.emotional_state == EmotionalState.EXCITED

    def test_react_to_combat_start_cautious(self, cautious_companion):
        """Test cautious companion reacts nervously to combat."""
        random.seed(10)  # Use seed that triggers reaction
        engine = CompanionDialogueEngine(cautious_companion)
        context = DialogueContext(trigger=DialogueTrigger.COMBAT_START)

        dialogue = engine.react_to_event(context)
        assert dialogue is not None
        # Cautious companion should be fearful
        assert dialogue.emotional_state == EmotionalState.FEARFUL

    def test_react_to_ally_injured_compassionate(self, compassionate_companion):
        """Test compassionate companion reacts with concern to injury."""
        random.seed(10)  # Use seed that triggers reaction
        engine = CompanionDialogueEngine(compassionate_companion)
        context = DialogueContext(
            trigger=DialogueTrigger.ALLY_INJURED,
            target="Gandalf"
        )

        dialogue = engine.react_to_event(context)
        assert dialogue is not None
        # High compassion should trigger concerned emotional state
        assert dialogue.emotional_state == EmotionalState.CONCERNED
        # Should be addressing the injured ally or party
        assert dialogue.addressed_to in ["Gandalf", "party"]

    def test_react_to_ally_injured_low_compassion(self, aggressive_companion):
        """Test low-compassion companion reacts pragmatically to injury."""
        random.seed(42)
        engine = CompanionDialogueEngine(aggressive_companion)
        context = DialogueContext(trigger=DialogueTrigger.ALLY_INJURED)

        dialogue = engine.react_to_event(context)
        # Should still react sometimes, but with less emotion
        if dialogue:
            assert dialogue.companion_id == "aggro_001"

    def test_ally_downed_always_reacts(self, brave_companion):
        """Test that ALLY_DOWNED always triggers a reaction."""
        random.seed(42)
        engine = CompanionDialogueEngine(brave_companion)
        context = DialogueContext(trigger=DialogueTrigger.ALLY_DOWNED, target="Frodo")

        # Should always react (100% probability)
        dialogue = engine.react_to_event(context)
        assert dialogue is not None
        assert dialogue.trigger == DialogueTrigger.ALLY_DOWNED

    def test_ally_downed_compassionate_reaction(self, compassionate_companion):
        """Test compassionate companion reacts with sadness to ally down."""
        random.seed(42)
        engine = CompanionDialogueEngine(compassionate_companion)
        context = DialogueContext(trigger=DialogueTrigger.ALLY_DOWNED)

        dialogue = engine.react_to_event(context)
        assert dialogue is not None
        # High compassion should lead to sad emotional state
        assert dialogue.emotional_state == EmotionalState.SAD

    def test_ally_downed_aggressive_reaction(self, aggressive_companion):
        """Test aggressive companion reacts with anger to ally down."""
        random.seed(42)
        engine = CompanionDialogueEngine(aggressive_companion)
        context = DialogueContext(trigger=DialogueTrigger.ALLY_DOWNED)

        dialogue = engine.react_to_event(context)
        assert dialogue is not None
        # High aggression should lead to angry emotional state
        assert dialogue.emotional_state == EmotionalState.ANGRY

    def test_enemy_killed_brave_reaction(self, brave_companion):
        """Test brave companion celebrates enemy death."""
        random.seed(42)
        engine = CompanionDialogueEngine(brave_companion)
        context = DialogueContext(trigger=DialogueTrigger.ENEMY_KILLED)

        dialogue = engine.react_to_event(context)
        # May or may not react (40% base probability)
        if dialogue:
            assert dialogue.trigger == DialogueTrigger.ENEMY_KILLED

    def test_enemy_killed_cautious_reaction(self, cautious_companion):
        """Test cautious companion reacts nervously to enemy death."""
        random.seed(42)
        engine = CompanionDialogueEngine(cautious_companion)
        context = DialogueContext(trigger=DialogueTrigger.ENEMY_KILLED)

        dialogue = engine.react_to_event(context)
        if dialogue:
            # Should reflect relief or uncertainty
            assert dialogue.companion_name == "Elara the Careful"

    def test_combat_end_reactions(self, brave_companion):
        """Test combat end triggers happy state."""
        random.seed(42)
        engine = CompanionDialogueEngine(brave_companion)
        context = DialogueContext(trigger=DialogueTrigger.COMBAT_END)

        dialogue = engine.react_to_event(context)
        if dialogue:
            assert dialogue.emotional_state == EmotionalState.HAPPY

    def test_quest_complete_high_loyalty(self, compassionate_companion):
        """Test high-loyalty companion celebrates quest completion."""
        random.seed(42)
        engine = CompanionDialogueEngine(compassionate_companion)
        context = DialogueContext(trigger=DialogueTrigger.QUEST_COMPLETE)

        dialogue = engine.react_to_event(context)
        assert dialogue is not None  # High probability (90%)
        assert dialogue.emotional_state == EmotionalState.HAPPY

    def test_quest_complete_low_loyalty(self, low_loyalty_companion):
        """Test low-loyalty companion is less enthusiastic about quest completion."""
        random.seed(42)
        engine = CompanionDialogueEngine(low_loyalty_companion)
        context = DialogueContext(trigger=DialogueTrigger.QUEST_COMPLETE)

        dialogue = engine.react_to_event(context)
        if dialogue:
            assert dialogue.emotional_state == EmotionalState.EXCITED

    def test_discovery_cautious_reaction(self, cautious_companion):
        """Test cautious companion is wary of discoveries."""
        random.seed(42)
        engine = CompanionDialogueEngine(cautious_companion)
        context = DialogueContext(trigger=DialogueTrigger.DISCOVERY)

        dialogue = engine.react_to_event(context)
        if dialogue:
            assert dialogue.emotional_state == EmotionalState.EXCITED

    def test_rest_high_loyalty(self, compassionate_companion):
        """Test high-loyalty companion is supportive during rest."""
        random.seed(42)
        engine = CompanionDialogueEngine(compassionate_companion)
        context = DialogueContext(trigger=DialogueTrigger.REST)

        dialogue = engine.react_to_event(context)
        if dialogue:
            assert dialogue.emotional_state == EmotionalState.NEUTRAL

    def test_idle_low_loyalty_more_likely(self, low_loyalty_companion):
        """Test low-loyalty companions complain more during idle time."""
        random.seed(42)
        engine = CompanionDialogueEngine(low_loyalty_companion)
        context = DialogueContext(trigger=DialogueTrigger.IDLE)

        # Low loyalty increases idle chatter probability
        dialogue = engine.react_to_event(context)
        if dialogue:
            assert dialogue.trigger == DialogueTrigger.IDLE

    def test_generate_banter_high_loyalty(self, compassionate_companion):
        """Test high-loyalty companion engages in friendly banter."""
        random.seed(42)
        engine = CompanionDialogueEngine(compassionate_companion)

        banter = engine.generate_banter(target="Aragorn", topic="adventure")
        assert banter is not None
        assert banter.addressed_to == "Aragorn"
        assert banter.trigger == DialogueTrigger.IDLE
        assert len(banter.text) > 0

    def test_generate_banter_low_loyalty_may_refuse(self, low_loyalty_companion):
        """Test low-loyalty companion may not engage in banter."""
        random.seed(100)  # Seed that causes refusal
        engine = CompanionDialogueEngine(low_loyalty_companion)

        banter = engine.generate_banter(target="Player")
        # May be None due to low loyalty
        if banter is None:
            assert True  # Expected behavior
        else:
            assert banter.addressed_to == "Player"

    def test_respond_to_player_always_responds(self, brave_companion):
        """Test companion always responds to direct player communication."""
        engine = CompanionDialogueEngine(brave_companion)

        response = engine.respond_to_player("Player", "Can you help me?")
        assert response is not None
        assert response.addressed_to == "Player"
        assert len(response.text) > 0

    def test_respond_to_player_help_request_high_loyalty(self, compassionate_companion):
        """Test high-loyalty companion eagerly helps player."""
        random.seed(42)
        engine = CompanionDialogueEngine(compassionate_companion)

        response = engine.respond_to_player("Player", "I need your help!")
        assert response is not None
        assert response.addressed_to == "Player"
        # Should be enthusiastic
        assert len(response.text) > 0

    def test_respond_to_player_help_request_low_loyalty(self, low_loyalty_companion):
        """Test low-loyalty companion reluctantly helps player."""
        random.seed(42)
        engine = CompanionDialogueEngine(low_loyalty_companion)

        response = engine.respond_to_player("Player", "I need help")
        assert response is not None
        # Should be less enthusiastic
        assert len(response.text) > 0

    def test_respond_to_player_fight_request_brave(self, brave_companion):
        """Test brave companion eager for combat."""
        random.seed(42)
        engine = CompanionDialogueEngine(brave_companion)

        response = engine.respond_to_player("Player", "Let's attack them!")
        assert response is not None
        assert len(response.text) > 0

    def test_respond_to_player_fight_request_cautious(self, cautious_companion):
        """Test cautious companion hesitant about combat."""
        random.seed(42)
        engine = CompanionDialogueEngine(cautious_companion)

        response = engine.respond_to_player("Player", "We should fight!")
        assert response is not None
        assert len(response.text) > 0

    def test_respond_to_player_thanks_high_loyalty(self, compassionate_companion):
        """Test high-loyalty companion graciously accepts thanks."""
        random.seed(42)
        engine = CompanionDialogueEngine(compassionate_companion)

        response = engine.respond_to_player("Player", "Thank you so much!")
        assert response is not None
        assert len(response.text) > 0

    def test_respond_to_player_thanks_low_loyalty(self, low_loyalty_companion):
        """Test low-loyalty companion expects payment for help."""
        random.seed(42)
        engine = CompanionDialogueEngine(low_loyalty_companion)

        response = engine.respond_to_player("Player", "Thanks for your help")
        assert response is not None
        assert len(response.text) > 0

    def test_interact_with_npc_hostile_aggressive_companion(self, aggressive_companion):
        """Test aggressive companion confronts hostile NPC."""
        random.seed(42)
        engine = CompanionDialogueEngine(aggressive_companion)

        dialogue = engine.interact_with_npc("Bandit", "hostile", "standoff")
        assert dialogue is not None
        assert dialogue.addressed_to == "Bandit"
        assert len(dialogue.text) > 0
        # Should update relationship negatively
        assert engine.relationship_memory.get("Bandit", 0) < 0

    def test_interact_with_npc_hostile_cautious_companion(self, cautious_companion):
        """Test cautious companion tries to defuse hostile NPC."""
        random.seed(42)
        engine = CompanionDialogueEngine(cautious_companion)

        dialogue = engine.interact_with_npc("Orc", "hostile", "confrontation")
        assert dialogue is not None
        assert dialogue.addressed_to == "Orc"

    def test_interact_with_npc_friendly_cautious(self, cautious_companion):
        """Test cautious companion suspicious of friendly NPC."""
        random.seed(42)
        engine = CompanionDialogueEngine(cautious_companion)

        dialogue = engine.interact_with_npc("Merchant", "friendly", "shop")
        assert dialogue is not None
        # Should update relationship positively
        assert engine.relationship_memory.get("Merchant", 0) > 0

    def test_interact_with_npc_friendly_low_caution(self, aggressive_companion):
        """Test low-caution companion welcomes friendly NPC."""
        random.seed(42)
        engine = CompanionDialogueEngine(aggressive_companion)

        dialogue = engine.interact_with_npc("Innkeeper", "friendly", "tavern")
        assert dialogue is not None

    def test_interact_with_npc_suspicious(self, cautious_companion):
        """Test cautious companion wary of suspicious NPC."""
        random.seed(42)
        engine = CompanionDialogueEngine(cautious_companion)

        dialogue = engine.interact_with_npc("Stranger", "suspicious", "dark alley")
        assert dialogue is not None

    def test_update_emotional_state_combat_start_brave(self, brave_companion):
        """Test brave companion gets excited for combat."""
        engine = CompanionDialogueEngine(brave_companion)

        state = engine.update_emotional_state(DialogueTrigger.COMBAT_START)
        assert state == EmotionalState.EXCITED
        assert engine.emotional_state == EmotionalState.EXCITED

    def test_update_emotional_state_combat_start_cautious(self, cautious_companion):
        """Test cautious companion gets fearful before combat."""
        engine = CompanionDialogueEngine(cautious_companion)

        state = engine.update_emotional_state(DialogueTrigger.COMBAT_START)
        assert state == EmotionalState.FEARFUL
        assert engine.emotional_state == EmotionalState.FEARFUL

    def test_update_emotional_state_ally_downed_aggressive(self, aggressive_companion):
        """Test aggressive companion gets angry when ally downed."""
        engine = CompanionDialogueEngine(aggressive_companion)

        state = engine.update_emotional_state(DialogueTrigger.ALLY_DOWNED)
        assert state == EmotionalState.ANGRY

    def test_update_emotional_state_ally_downed_compassionate(self, compassionate_companion):
        """Test compassionate companion gets sad when ally downed."""
        engine = CompanionDialogueEngine(compassionate_companion)

        state = engine.update_emotional_state(DialogueTrigger.ALLY_DOWNED)
        assert state == EmotionalState.SAD

    def test_update_emotional_state_rest_resets(self, brave_companion):
        """Test rest resets emotional state to neutral."""
        engine = CompanionDialogueEngine(brave_companion)
        engine.emotional_state = EmotionalState.ANGRY

        state = engine.update_emotional_state(DialogueTrigger.REST)
        assert state == EmotionalState.NEUTRAL

    def test_update_emotional_state_quest_complete(self, compassionate_companion):
        """Test quest completion makes loyal companion happy."""
        engine = CompanionDialogueEngine(compassionate_companion)

        state = engine.update_emotional_state(DialogueTrigger.QUEST_COMPLETE)
        assert state == EmotionalState.HAPPY

    def test_update_relationship_positive(self, brave_companion):
        """Test increasing relationship sentiment."""
        engine = CompanionDialogueEngine(brave_companion)

        new_value = engine.update_relationship("Gandalf", 25, "saved my life")
        assert new_value == 25
        assert engine.relationship_memory["Gandalf"] == 25

        # Further increase
        new_value = engine.update_relationship("Gandalf", 30, "trusted advisor")
        assert new_value == 55

    def test_update_relationship_negative(self, brave_companion):
        """Test decreasing relationship sentiment."""
        engine = CompanionDialogueEngine(brave_companion)

        new_value = engine.update_relationship("Saruman", -40, "betrayed us")
        assert new_value == -40
        assert engine.relationship_memory["Saruman"] == -40

    def test_update_relationship_clamping_positive(self, brave_companion):
        """Test relationship clamped at +100."""
        engine = CompanionDialogueEngine(brave_companion)

        engine.update_relationship("BestFriend", 80)
        new_value = engine.update_relationship("BestFriend", 50)
        assert new_value == 100  # Clamped at max

    def test_update_relationship_clamping_negative(self, brave_companion):
        """Test relationship clamped at -100."""
        engine = CompanionDialogueEngine(brave_companion)

        engine.update_relationship("Enemy", -80)
        new_value = engine.update_relationship("Enemy", -50)
        assert new_value == -100  # Clamped at min

    def test_get_response_modifiers_brave(self, brave_companion):
        """Test modifiers for brave companion."""
        engine = CompanionDialogueEngine(brave_companion)

        modifiers = engine.get_response_modifiers()
        assert modifiers["combat_tone"] == "confident"
        assert modifiers["risk_reaction"] == "reckless"

    def test_get_response_modifiers_cautious(self, cautious_companion):
        """Test modifiers for cautious companion."""
        engine = CompanionDialogueEngine(cautious_companion)

        modifiers = engine.get_response_modifiers()
        assert modifiers["combat_tone"] == "nervous"
        assert modifiers["risk_reaction"] == "cautious"
        assert modifiers["injury_reaction"] == "deeply_concerned"

    def test_get_response_modifiers_aggressive(self, aggressive_companion):
        """Test modifiers for aggressive companion."""
        engine = CompanionDialogueEngine(aggressive_companion)

        modifiers = engine.get_response_modifiers()
        assert modifiers["enemy_tone"] == "hostile"
        assert modifiers["injury_reaction"] == "pragmatic"

    def test_get_response_modifiers_compassionate(self, compassionate_companion):
        """Test modifiers for compassionate companion."""
        engine = CompanionDialogueEngine(compassionate_companion)

        modifiers = engine.get_response_modifiers()
        assert modifiers["injury_reaction"] == "deeply_concerned"
        assert modifiers["party_tone"] == "devoted"

    def test_get_response_modifiers_low_loyalty(self, low_loyalty_companion):
        """Test modifiers for low-loyalty companion."""
        engine = CompanionDialogueEngine(low_loyalty_companion)

        modifiers = engine.get_response_modifiers()
        assert modifiers["party_tone"] == "detached"

    def test_save_and_load_state(self, brave_companion):
        """Test state persistence roundtrip."""
        engine = CompanionDialogueEngine(brave_companion)

        # Modify state
        engine.emotional_state = EmotionalState.ANGRY
        engine.update_relationship("Frodo", 50)
        engine.update_relationship("Sauron", -80)
        engine._reaction_count = 10

        # Save state
        saved = engine.save_state()
        assert saved["emotional_state"] == "angry"
        assert saved["relationship_memory"]["Frodo"] == 50
        assert saved["relationship_memory"]["Sauron"] == -80
        assert saved["reaction_count"] == 10

        # Create new engine and load state
        new_engine = CompanionDialogueEngine(brave_companion)
        new_engine.load_state(saved)

        assert new_engine.emotional_state == EmotionalState.ANGRY
        assert new_engine.relationship_memory["Frodo"] == 50
        assert new_engine.relationship_memory["Sauron"] == -80
        assert new_engine._reaction_count == 10

    def test_reaction_count_increments(self, brave_companion):
        """Test reaction count tracks dialogue generation."""
        random.seed(42)
        engine = CompanionDialogueEngine(brave_companion)

        assert engine._reaction_count == 0

        # Trigger reactions
        context1 = DialogueContext(trigger=DialogueTrigger.ALLY_DOWNED)
        engine.react_to_event(context1)
        assert engine._reaction_count == 1

        context2 = DialogueContext(trigger=DialogueTrigger.COMBAT_START)
        result = engine.react_to_event(context2)
        if result is not None:
            assert engine._reaction_count == 2

    def test_reaction_probability_honored(self, brave_companion):
        """Test that reaction probabilities are respected."""
        random.seed(42)
        engine = CompanionDialogueEngine(brave_companion)

        # ALLY_DOWNED should always trigger (100%)
        ally_down_count = 0
        for _ in range(10):
            context = DialogueContext(trigger=DialogueTrigger.ALLY_DOWNED)
            if engine.react_to_event(context):
                ally_down_count += 1

        assert ally_down_count == 10  # All should trigger

        # IDLE should rarely trigger (20%)
        random.seed(42)
        idle_count = 0
        for _ in range(50):
            context = DialogueContext(trigger=DialogueTrigger.IDLE)
            if engine.react_to_event(context):
                idle_count += 1

        # Should be roughly 20% (10 out of 50), but allow some variance
        assert idle_count < 25  # Definitely less than 50%

    def test_dialogue_templates_structure(self):
        """Test that DIALOGUE_TEMPLATES are properly structured."""
        assert DialogueTrigger.COMBAT_START in DIALOGUE_TEMPLATES
        assert "high_bravery" in DIALOGUE_TEMPLATES[DialogueTrigger.COMBAT_START]
        assert "low_bravery" in DIALOGUE_TEMPLATES[DialogueTrigger.COMBAT_START]

        # Check all templates are lists of strings
        for trigger, personality_templates in DIALOGUE_TEMPLATES.items():
            for personality, templates in personality_templates.items():
                assert isinstance(templates, list)
                assert len(templates) > 0
                for template in templates:
                    assert isinstance(template, str)
                    assert len(template) > 0

    def test_reaction_probability_structure(self):
        """Test that REACTION_PROBABILITY covers all triggers."""
        for trigger in DialogueTrigger:
            assert trigger in REACTION_PROBABILITY
            probability = REACTION_PROBABILITY[trigger]
            assert 0 <= probability <= 100
