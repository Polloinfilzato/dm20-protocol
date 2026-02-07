"""
Companion Roleplay and Dialogue system for the Claudmaster multi-agent framework.

This module provides personality-driven dialogue generation for companion NPCs,
enabling them to react to game events, engage in banter, respond to players,
and interact with NPCs based on their personality traits and emotional state.

All dialogue is template-based (no LLM calls), ensuring fast, deterministic,
and personality-consistent responses.
"""

import random
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .companions import CompanionProfile, PersonalityTraits


class DialogueTrigger(str, Enum):
    """Events that can trigger companion dialogue reactions."""
    COMBAT_START = "combat_start"
    COMBAT_END = "combat_end"
    ALLY_INJURED = "ally_injured"
    ALLY_DOWNED = "ally_downed"
    ENEMY_KILLED = "enemy_killed"
    DISCOVERY = "discovery"
    REST = "rest"
    QUEST_COMPLETE = "quest_complete"
    NPC_INTERACTION = "npc_interaction"
    PLAYER_DECISION = "player_decision"
    IDLE = "idle"


class EmotionalState(str, Enum):
    """Emotional states that affect dialogue tone and content."""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    ANGRY = "angry"
    FEARFUL = "fearful"
    SAD = "sad"
    EXCITED = "excited"
    CONCERNED = "concerned"


class DialogueContext(BaseModel):
    """Context information for dialogue generation."""
    trigger: DialogueTrigger
    target: str | None = None
    location: str | None = None
    recent_events: list[str] = Field(default_factory=list)
    party_status: dict[str, Any] = Field(default_factory=dict)


class CompanionDialogue(BaseModel):
    """A single line of companion dialogue with metadata."""
    companion_id: str
    companion_name: str
    text: str
    trigger: DialogueTrigger
    emotional_state: EmotionalState
    addressed_to: str | None = None


# Template-based dialogue responses by trigger and personality
# Format: {trigger: {personality_type: [template1, template2, ...]}}
DIALOGUE_TEMPLATES: dict[DialogueTrigger, dict[str, list[str]]] = {
    DialogueTrigger.COMBAT_START: {
        "high_bravery": [
            "Finally, some action! Let's show them what we're made of!",
            "Time to put these skills to use. Stay sharp!",
            "I've been waiting for this. Let's go!",
        ],
        "low_bravery": [
            "Stay close, everyone. We'll get through this together.",
            "Be careful... this could get dangerous.",
            "Let's be smart about this. No unnecessary risks.",
        ],
    },
    DialogueTrigger.ALLY_INJURED: {
        "high_compassion": [
            "Hold on! I'm coming to help you!",
            "Don't worry, we'll get you patched up!",
            "Stay with us! You're going to be okay!",
        ],
        "low_compassion": [
            "Get back up. We're not done yet.",
            "Shake it off. We need everyone fighting.",
            "You'll live. Focus on the enemy.",
        ],
        "high_bravery": [
            "Hold on! We've got this under control!",
            "Don't worry about it—we'll finish this quick!",
            "Just a scratch! Keep fighting!",
        ],
        "low_bravery": [
            "We need to be more careful... this is getting dangerous.",
            "Maybe we should fall back and regroup?",
            "This isn't looking good. Stay alert!",
        ],
    },
    DialogueTrigger.ALLY_DOWNED: {
        "high_compassion": [
            "No! Stay with me! Someone help!",
            "We can't lose you! Hold on!",
            "I won't let you die! Not today!",
        ],
        "high_aggression": [
            "They're going to pay for that!",
            "Nobody hurts my friends and gets away with it!",
            "That's it. No more mercy!",
        ],
        "low_bravery": [
            "Oh no... this is bad. Really bad.",
            "We need to get out of here NOW!",
            "I... I don't know if we can win this...",
        ],
    },
    DialogueTrigger.ENEMY_KILLED: {
        "high_bravery": [
            "One down! Who's next?",
            "That's how it's done!",
            "They didn't stand a chance!",
        ],
        "low_bravery": [
            "Is... is it over? Are there more?",
            "Thank the gods. I thought we were done for.",
            "That was too close for comfort.",
        ],
        "high_aggression": [
            "Another one bites the dust!",
            "Yes! That felt good!",
            "Who wants to be next?",
        ],
        "low_aggression": [
            "It's done. Let's move on.",
            "I didn't enjoy that, but it was necessary.",
            "I wish it hadn't come to this.",
        ],
    },
    DialogueTrigger.COMBAT_END: {
        "high_bravery": [
            "Now THAT was a fight! Everyone okay?",
            "We showed them! Good work, everyone!",
            "Ha! Piece of cake. What's next?",
        ],
        "low_bravery": [
            "Thank goodness that's over. Is everyone alright?",
            "I'm just glad we made it through.",
            "Let's not do that again anytime soon.",
        ],
        "high_loyalty": [
            "Great teamwork, everyone. I'm proud to fight alongside you.",
            "We did it together. That's what matters.",
            "As long as we stick together, nothing can stop us.",
        ],
    },
    DialogueTrigger.REST: {
        "high_loyalty": [
            "Good idea. We all need to recover our strength.",
            "Rest well, friends. I'll keep watch.",
            "Let's take a moment. We've earned it.",
        ],
        "low_loyalty": [
            "Finally. I was wondering when we'd stop.",
            "About time we took a break.",
            "Don't expect me to stay up all night on watch.",
        ],
    },
    DialogueTrigger.QUEST_COMPLETE: {
        "high_bravery": [
            "We did it! I knew we could pull it off!",
            "That's what I'm talking about! Victory!",
            "Another quest down. What's our next adventure?",
        ],
        "high_loyalty": [
            "We make a great team. I'm honored to be part of this.",
            "Couldn't have done it without all of you.",
            "This is why I follow you. You always see things through.",
        ],
        "low_loyalty": [
            "About time. Do I get my share now?",
            "Well, that's done. What's in it for me?",
            "Fine. One more off the list.",
        ],
    },
    DialogueTrigger.DISCOVERY: {
        "high_caution": [
            "Wait. Let's examine this carefully before touching anything.",
            "Interesting... but it could be dangerous. Proceed with caution.",
            "This could be a trap. Everyone stay alert.",
        ],
        "low_caution": [
            "Ooh, what's this? Let me take a closer look!",
            "Now this is exciting! What do you think it is?",
            "Finders keepers! This looks valuable!",
        ],
    },
    DialogueTrigger.NPC_INTERACTION: {
        "high_aggression": [
            "Get to the point. We don't have all day.",
            "I don't trust this one. Keep your guard up.",
            "Say what you need to say and step aside.",
        ],
        "low_aggression": [
            "Hello there! How can we help you?",
            "Nice to meet you. What brings you here?",
            "We come in peace. Is there something we can do for you?",
        ],
    },
    DialogueTrigger.IDLE: {
        "high_loyalty": [
            "So, what's the plan? I'm ready for whatever comes next.",
            "Just thinking about how far we've come together.",
            "You know, I'm really starting to like this group.",
        ],
        "low_loyalty": [
            "Are we just going to stand around all day?",
            "This is boring. When's the next challenge?",
            "I could be doing something more profitable right now.",
        ],
        "neutral": [
            "The weather's nice today, at least.",
            "Anyone else hungry? I could eat.",
            "So... what now?",
        ],
    },
}

# Reaction probability by trigger (0-100)
REACTION_PROBABILITY: dict[DialogueTrigger, int] = {
    DialogueTrigger.ALLY_DOWNED: 100,
    DialogueTrigger.COMBAT_START: 80,
    DialogueTrigger.COMBAT_END: 70,
    DialogueTrigger.QUEST_COMPLETE: 90,
    DialogueTrigger.DISCOVERY: 60,
    DialogueTrigger.ALLY_INJURED: 75,
    DialogueTrigger.ENEMY_KILLED: 40,
    DialogueTrigger.REST: 50,
    DialogueTrigger.NPC_INTERACTION: 30,
    DialogueTrigger.PLAYER_DECISION: 35,
    DialogueTrigger.IDLE: 20,
}


class CompanionDialogueEngine:
    """Generates personality-driven dialogue for companions."""

    def __init__(self, companion: CompanionProfile):
        """Initialize dialogue engine for a specific companion.

        Args:
            companion: The companion profile containing personality traits
        """
        self.companion = companion
        self.emotional_state = EmotionalState.NEUTRAL
        self.relationship_memory: dict[str, int] = {}
        self._reaction_count: int = 0

    def react_to_event(self, context: DialogueContext) -> CompanionDialogue | None:
        """Generate a reaction to a game event based on personality.

        Not every event should trigger dialogue. Use personality traits and
        trigger type to decide if the companion speaks up.
        Returns None if the companion wouldn't react to this event.

        Args:
            context: The context of the event triggering potential dialogue

        Returns:
            CompanionDialogue if the companion reacts, None otherwise
        """
        # Check reaction probability
        base_probability = REACTION_PROBABILITY.get(context.trigger, 50)

        # Adjust probability based on personality
        if context.trigger == DialogueTrigger.COMBAT_START:
            if self.companion.personality.bravery > 70:
                base_probability += 15
        elif context.trigger == DialogueTrigger.IDLE:
            if self.companion.personality.loyalty < 30:
                base_probability += 20  # More likely to complain

        # Random roll
        if random.randint(0, 100) > base_probability:
            return None

        # Update emotional state
        new_state = self.update_emotional_state(context.trigger)

        # Select appropriate dialogue based on personality
        text = self._select_dialogue(context)
        if not text:
            return None

        self._reaction_count += 1

        return CompanionDialogue(
            companion_id=self.companion.npc_id,
            companion_name=self.companion.name,
            text=text,
            trigger=context.trigger,
            emotional_state=new_state,
            addressed_to=context.target or "party",
        )

    def generate_banter(self, target: str, topic: str = "") -> CompanionDialogue | None:
        """Generate casual dialogue during downtime.

        Args:
            target: Who the banter is directed at (player name, NPC name, or "party")
            topic: Optional conversation topic

        Returns:
            CompanionDialogue with banter, or None if companion wouldn't engage
        """
        # Low loyalty companions are less likely to engage in friendly banter
        if self.companion.personality.loyalty < 30 and random.randint(0, 100) > 30:
            return None

        # Generate topic-appropriate banter
        banter_templates = [
            f"Hey {target}, ever wonder what we're really doing out here?",
            f"So {target}, what's your story? How'd you end up on this adventure?",
            f"{target}, I've been meaning to ask... where are we heading next?",
            "Anyone else think this whole situation is a bit odd?",
            "I've got a good feeling about this group, you know.",
        ]

        # Adjust based on loyalty
        if self.companion.personality.loyalty > 70:
            banter_templates.extend([
                f"I'm glad I'm here with all of you, especially you, {target}.",
                "You know, I'd follow this group anywhere.",
            ])
        elif self.companion.personality.loyalty < 30:
            banter_templates.extend([
                "Don't suppose anyone's thought about what happens when this is over?",
                "Just making sure everyone remembers our agreement about splitting loot.",
            ])

        text = random.choice(banter_templates)

        return CompanionDialogue(
            companion_id=self.companion.npc_id,
            companion_name=self.companion.name,
            text=text,
            trigger=DialogueTrigger.IDLE,
            emotional_state=self.emotional_state,
            addressed_to=target,
        )

    def respond_to_player(self, player_name: str, player_message: str) -> CompanionDialogue:
        """Generate response to direct player communication. Always responds.

        Args:
            player_name: Name of the player speaking to the companion
            player_message: What the player said

        Returns:
            CompanionDialogue with the response (always generates a response)
        """
        # Analyze player message for keywords
        message_lower = player_message.lower()

        # Determine response based on message content and personality
        if any(word in message_lower for word in ["help", "assist", "need you"]):
            if self.companion.personality.loyalty > 60:
                responses = [
                    "Of course! What do you need?",
                    "I'm here for you. Just say the word.",
                    "Always ready to help. What's going on?",
                ]
            else:
                responses = [
                    "I suppose I can help. What is it?",
                    "Fine. What do you need?",
                    "This better be important.",
                ]
        elif any(word in message_lower for word in ["attack", "fight", "battle"]):
            if self.companion.personality.bravery > 60:
                responses = [
                    "Now we're talking! Let's do this!",
                    "Finally, some action! I'm ready!",
                    "Point me at them!",
                ]
            else:
                responses = [
                    "If we must... I'll do my best.",
                    "Are you sure about this? Well, here goes.",
                    "Okay, but let's be careful.",
                ]
        elif any(word in message_lower for word in ["thank", "thanks", "appreciate"]):
            if self.companion.personality.loyalty > 60:
                responses = [
                    "You're welcome! Anytime.",
                    "No need to thank me. We're a team.",
                    "That's what friends are for!",
                ]
            else:
                responses = [
                    "Sure. Just don't forget about it.",
                    "Yeah, well, you owe me one.",
                    "Whatever.",
                ]
        else:
            # Generic responses
            if self.companion.personality.loyalty > 60:
                responses = [
                    "I hear you. What do you think we should do?",
                    "Interesting point. Tell me more.",
                    "I trust your judgment on this.",
                ]
            else:
                responses = [
                    "Hmm. If you say so.",
                    "I'm listening.",
                    "And?",
                ]

        text = random.choice(responses)

        return CompanionDialogue(
            companion_id=self.companion.npc_id,
            companion_name=self.companion.name,
            text=text,
            trigger=DialogueTrigger.PLAYER_DECISION,
            emotional_state=self.emotional_state,
            addressed_to=player_name,
        )

    def interact_with_npc(self, npc_name: str, npc_attitude: str, context: str) -> CompanionDialogue:
        """Generate dialogue when interacting with an NPC.

        Args:
            npc_name: Name of the NPC being interacted with
            npc_attitude: The NPC's attitude (friendly, hostile, neutral, suspicious, etc.)
            context: Context about the interaction

        Returns:
            CompanionDialogue with the interaction response
        """
        attitude_lower = npc_attitude.lower()

        # React based on NPC attitude and companion personality
        if "hostile" in attitude_lower or "aggressive" in attitude_lower:
            if self.companion.personality.aggression > 60:
                responses = [
                    f"Watch your tone with us, {npc_name}.",
                    "You want to try that again?",
                    "I don't like your attitude.",
                ]
            else:
                responses = [
                    f"Let's everyone calm down. We don't want trouble, {npc_name}.",
                    "Easy now. We're all friends here, right?",
                    "There's no need for hostility.",
                ]
        elif "friendly" in attitude_lower or "helpful" in attitude_lower:
            if self.companion.personality.caution > 60:
                responses = [
                    "Seems friendly enough, but stay alert.",
                    f"Nice to meet you, {npc_name}. Though we should still be careful.",
                    "I appreciate the help, but what's in it for you?",
                ]
            else:
                responses = [
                    f"Great to meet you, {npc_name}!",
                    "Finally, someone friendly! Nice to meet you.",
                    "I like you already!",
                ]
        elif "suspicious" in attitude_lower:
            if self.companion.personality.caution > 60:
                responses = [
                    "I don't trust this. Something's off.",
                    f"Why so suspicious, {npc_name}? We're just passing through.",
                    "We should be careful here.",
                ]
            else:
                responses = [
                    f"What's wrong, {npc_name}? We're harmless!",
                    "No need to be suspicious. We're friendly!",
                    "Relax! We're the good guys!",
                ]
        else:  # neutral
            responses = [
                f"Greetings, {npc_name}.",
                "Hello there.",
                f"Nice to meet you, {npc_name}.",
            ]

        text = random.choice(responses)

        # Update relationship memory
        sentiment_delta = 0
        if "hostile" in attitude_lower:
            sentiment_delta = -10
        elif "friendly" in attitude_lower:
            sentiment_delta = 10

        if sentiment_delta != 0:
            self.update_relationship(npc_name, sentiment_delta, f"First impression: {npc_attitude}")

        return CompanionDialogue(
            companion_id=self.companion.npc_id,
            companion_name=self.companion.name,
            text=text,
            trigger=DialogueTrigger.NPC_INTERACTION,
            emotional_state=self.emotional_state,
            addressed_to=npc_name,
        )

    def update_emotional_state(self, trigger: DialogueTrigger) -> EmotionalState:
        """Update emotional state based on event. Returns new state.

        Args:
            trigger: The event that occurred

        Returns:
            The new emotional state
        """
        personality = self.companion.personality

        if trigger == DialogueTrigger.COMBAT_START:
            if personality.bravery > 60:
                self.emotional_state = EmotionalState.EXCITED
            else:
                self.emotional_state = EmotionalState.FEARFUL
        elif trigger == DialogueTrigger.ALLY_DOWNED:
            if personality.aggression > 60:
                self.emotional_state = EmotionalState.ANGRY
            elif personality.compassion > 60:
                self.emotional_state = EmotionalState.SAD
            else:
                self.emotional_state = EmotionalState.FEARFUL
        elif trigger == DialogueTrigger.COMBAT_END:
            # Check party status if available
            self.emotional_state = EmotionalState.HAPPY
        elif trigger == DialogueTrigger.REST:
            self.emotional_state = EmotionalState.NEUTRAL
        elif trigger == DialogueTrigger.QUEST_COMPLETE:
            if personality.loyalty > 60:
                self.emotional_state = EmotionalState.HAPPY
            else:
                self.emotional_state = EmotionalState.EXCITED
        elif trigger == DialogueTrigger.DISCOVERY:
            self.emotional_state = EmotionalState.EXCITED
        elif trigger == DialogueTrigger.ALLY_INJURED:
            if personality.compassion > 60:
                self.emotional_state = EmotionalState.CONCERNED
            else:
                self.emotional_state = EmotionalState.NEUTRAL

        return self.emotional_state

    def update_relationship(self, target: str, delta: int, reason: str = "") -> int:
        """Adjust relationship sentiment toward a target. Clamp to [-100, 100]. Returns new value.

        Args:
            target: Who the relationship is with (NPC name, player name, etc.)
            delta: How much to adjust the relationship (positive or negative)
            reason: Optional explanation for the change

        Returns:
            The new relationship sentiment value
        """
        current = self.relationship_memory.get(target, 0)
        new_value = max(-100, min(100, current + delta))
        self.relationship_memory[target] = new_value
        return new_value

    def get_response_modifiers(self) -> dict[str, str]:
        """Get dialogue modifiers based on personality traits.

        Returns:
            Dictionary mapping modifier categories to values based on personality
        """
        personality = self.companion.personality
        modifiers: dict[str, str] = {}

        # Combat tone based on bravery
        if personality.bravery > 70:
            modifiers["combat_tone"] = "confident"
        elif personality.bravery < 30:
            modifiers["combat_tone"] = "nervous"
        else:
            modifiers["combat_tone"] = "steady"

        # Injury reaction based on compassion
        if personality.compassion > 70:
            modifiers["injury_reaction"] = "deeply_concerned"
        elif personality.compassion < 30:
            modifiers["injury_reaction"] = "pragmatic"
        else:
            modifiers["injury_reaction"] = "concerned"

        # Enemy tone based on aggression
        if personality.aggression > 70:
            modifiers["enemy_tone"] = "hostile"
        elif personality.aggression < 30:
            modifiers["enemy_tone"] = "diplomatic"
        else:
            modifiers["enemy_tone"] = "neutral"

        # Risk reaction based on caution
        if personality.caution > 70:
            modifiers["risk_reaction"] = "cautious"
        elif personality.caution < 30:
            modifiers["risk_reaction"] = "reckless"
        else:
            modifiers["risk_reaction"] = "balanced"

        # Party tone based on loyalty
        if personality.loyalty > 70:
            modifiers["party_tone"] = "devoted"
        elif personality.loyalty < 30:
            modifiers["party_tone"] = "detached"
        else:
            modifiers["party_tone"] = "cooperative"

        return modifiers

    def save_state(self) -> dict:
        """Serialize engine state for persistence.

        Returns:
            Dictionary containing all state that needs to be saved
        """
        return {
            "emotional_state": self.emotional_state.value,
            "relationship_memory": self.relationship_memory.copy(),
            "reaction_count": self._reaction_count,
        }

    def load_state(self, data: dict) -> None:
        """Restore engine state from saved data.

        Args:
            data: Dictionary from save_state() containing state to restore
        """
        self.emotional_state = EmotionalState(data.get("emotional_state", "neutral"))
        self.relationship_memory = data.get("relationship_memory", {}).copy()
        self._reaction_count = data.get("reaction_count", 0)

    def _select_dialogue(self, context: DialogueContext) -> str | None:
        """Select appropriate dialogue template based on context and personality.

        Args:
            context: The dialogue context

        Returns:
            Selected dialogue text, or None if no appropriate template found
        """
        templates = DIALOGUE_TEMPLATES.get(context.trigger)
        if not templates:
            return None

        personality = self.companion.personality

        # Determine which personality type to use
        selected_templates: list[str] | None = None

        if context.trigger == DialogueTrigger.COMBAT_START:
            if personality.bravery > 60:
                selected_templates = templates.get("high_bravery")
            else:
                selected_templates = templates.get("low_bravery")
        elif context.trigger == DialogueTrigger.ALLY_INJURED:
            # Prioritize compassion, then bravery
            if personality.compassion > 60:
                selected_templates = templates.get("high_compassion")
            elif personality.compassion < 40:
                selected_templates = templates.get("low_compassion")
            elif personality.bravery > 60:
                selected_templates = templates.get("high_bravery")
            else:
                selected_templates = templates.get("low_bravery")
        elif context.trigger == DialogueTrigger.ALLY_DOWNED:
            # Choose based on dominant personality trait
            if personality.compassion > 60 and personality.compassion >= personality.aggression:
                selected_templates = templates.get("high_compassion")
            elif personality.aggression > 60:
                selected_templates = templates.get("high_aggression")
            elif personality.bravery < 40:
                selected_templates = templates.get("low_bravery")
            else:
                # Default to compassion if no strong trait
                selected_templates = templates.get("high_compassion")
        elif context.trigger == DialogueTrigger.ENEMY_KILLED:
            if personality.bravery > 60:
                selected_templates = templates.get("high_bravery")
            elif personality.bravery < 40:
                selected_templates = templates.get("low_bravery")
            elif personality.aggression > 60:
                selected_templates = templates.get("high_aggression")
            else:
                selected_templates = templates.get("low_aggression")
        elif context.trigger == DialogueTrigger.COMBAT_END:
            if personality.bravery > 60:
                selected_templates = templates.get("high_bravery")
            elif personality.bravery < 40:
                selected_templates = templates.get("low_bravery")
            else:
                selected_templates = templates.get("high_loyalty")
        elif context.trigger == DialogueTrigger.REST:
            if personality.loyalty > 60:
                selected_templates = templates.get("high_loyalty")
            else:
                selected_templates = templates.get("low_loyalty")
        elif context.trigger == DialogueTrigger.QUEST_COMPLETE:
            if personality.bravery > 60:
                selected_templates = templates.get("high_bravery")
            elif personality.loyalty > 60:
                selected_templates = templates.get("high_loyalty")
            else:
                selected_templates = templates.get("low_loyalty")
        elif context.trigger == DialogueTrigger.DISCOVERY:
            if personality.caution > 60:
                selected_templates = templates.get("high_caution")
            else:
                selected_templates = templates.get("low_caution")
        elif context.trigger == DialogueTrigger.NPC_INTERACTION:
            if personality.aggression > 60:
                selected_templates = templates.get("high_aggression")
            else:
                selected_templates = templates.get("low_aggression")
        elif context.trigger == DialogueTrigger.IDLE:
            if personality.loyalty > 60:
                selected_templates = templates.get("high_loyalty")
            elif personality.loyalty < 40:
                selected_templates = templates.get("low_loyalty")
            else:
                selected_templates = templates.get("neutral")

        if not selected_templates:
            return None

        return random.choice(selected_templates)


__all__ = [
    "DialogueTrigger",
    "EmotionalState",
    "DialogueContext",
    "CompanionDialogue",
    "CompanionDialogueEngine",
    "DIALOGUE_TEMPLATES",
    "REACTION_PROBABILITY",
]
