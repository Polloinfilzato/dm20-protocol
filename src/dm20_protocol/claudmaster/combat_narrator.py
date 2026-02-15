"""
Combat Narration System for the Claudmaster multi-agent AI DM.

Generates engaging narrative descriptions for combat encounters, including:
- Round start announcements with initiative order
- Attack rolls (hits, misses, criticals, fumbles)
- Damage descriptions with severity-based narrative
- Spell effects with school-specific flavor
- Death and unconsciousness dramatic moments

Uses an LLM to generate varied, contextual combat narration that avoids
repetition and maintains immersion.
"""

import logging
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field

logger = logging.getLogger("dm20-protocol")


# ------------------------------------------------------------------
# LLM Client Protocol
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
# Damage severity classification
# ------------------------------------------------------------------

class DamageSeverity(str, Enum):
    """Classification of damage severity based on percentage of max HP."""
    SCRATCH = "scratch"          # < 10% max HP
    LIGHT = "light"              # 10-25%
    MODERATE = "moderate"        # 25-50%
    HEAVY = "heavy"              # 50-75%
    DEVASTATING = "devastating"  # > 75%


# ------------------------------------------------------------------
# Spell and effect models
# ------------------------------------------------------------------

class SpellInfo(BaseModel):
    """Information about a spell being cast."""
    name: str = Field(description="Spell name")
    school: str = Field(default="evocation", description="School of magic")
    level: int = Field(default=0, description="Spell level (0 for cantrips)")
    damage_type: str | None = Field(default=None, description="Type of damage (fire, cold, etc.)")


class SpellEffect(BaseModel):
    """Effect of a spell on a target."""
    target: str = Field(description="Name of the affected target")
    effect_type: str = Field(description="Type of effect: damage, heal, condition, etc.")
    value: int = Field(default=0, description="Numeric value (damage, healing, etc.)")
    description: str = Field(default="", description="Text description of the effect")


# ------------------------------------------------------------------
# Dramatic moments
# ------------------------------------------------------------------

class DramaticMoment(BaseModel):
    """A dramatic combat moment requiring special narration."""
    character: str = Field(description="Character name")
    event_type: str = Field(description="Type of event: death, unconscious, stabilized, critical_hit")
    context: str = Field(description="Context about what caused this moment")
    is_player: bool = Field(default=False, description="Whether this is a player character")


# ------------------------------------------------------------------
# Description tracking to avoid repetition
# ------------------------------------------------------------------

class DescriptionTracker:
    """Track recent descriptions to avoid repetition.

    Maintains a history of generated descriptions and provides methods
    to check similarity and select least-used templates.
    """

    def __init__(self, history_size: int = 20) -> None:
        """Initialize the tracker.

        Args:
            history_size: Maximum number of descriptions to track.
        """
        self._history: list[str] = []
        self._template_usage: dict[str, int] = {}
        self._history_size = history_size

    def record(self, description: str, template_key: str | None = None) -> None:
        """Record a generated description.

        Args:
            description: The generated text to track.
            template_key: Optional template identifier for usage tracking.
        """
        # Add to history with size limit
        self._history.append(description)
        if len(self._history) > self._history_size:
            self._history.pop(0)

        # Track template usage
        if template_key:
            self._template_usage[template_key] = self._template_usage.get(template_key, 0) + 1

    def is_too_similar(self, new_description: str, threshold: float = 0.5) -> bool:
        """Check if a new description is too similar to recent ones.

        Uses Jaccard similarity (word overlap) to detect repetition.

        Args:
            new_description: The new description to check.
            threshold: Similarity threshold (0.0-1.0) above which to flag as too similar.

        Returns:
            True if the description is too similar to any recent description.
        """
        if not self._history:
            return False

        new_words = set(new_description.lower().split())
        if not new_words:
            return False

        for old_description in self._history[-5:]:  # Check last 5
            old_words = set(old_description.lower().split())
            if not old_words:
                continue

            # Jaccard similarity: intersection / union
            intersection = new_words & old_words
            union = new_words | old_words
            similarity = len(intersection) / len(union) if union else 0.0

            if similarity >= threshold:
                return True

        return False

    def get_least_used_template(self, templates: list[str]) -> str:
        """Get the template that has been used least recently.

        Args:
            templates: List of template keys to choose from.

        Returns:
            The template key with the lowest usage count.
        """
        if not templates:
            return ""

        # Return template with lowest usage count
        return min(templates, key=lambda t: self._template_usage.get(t, 0))


# ------------------------------------------------------------------
# Prompt templates
# ------------------------------------------------------------------

ROUND_START_TEMPLATE = """\
You are narrating the start of combat round {round_number} in a D&D battle.

Initiative order:
{initiative_list}

Generate a brief, dynamic transition to round {round_number}. Keep it to 1-2 sentences.

Adapt the tone to the combat's phase:
- Early rounds (1-2): tension, sizing each other up, first blood
- Mid rounds (3-5): fatigue, desperation, the battle's rhythm
- Late rounds (6+): exhaustion, last stands, do-or-die moments

Vary your narrative lens each round — cycle unpredictably between these approaches:
- The combatants: a bead of sweat, a snarl, a prayer whispered between breaths
- The environment: crumbling terrain, shifting shadows, blood-slicked floors
- The stakes: what happens if they fail, what drives them to fight on
- The tempo: sudden stillness, a collective inhale, the clash resuming

Do NOT list initiative order. Do NOT repeat your opening structure from previous rounds.
"""

ATTACK_TEMPLATE = """\
You are narrating a combat attack in a D&D battle.

Attacker: {attacker}
Defender: {defender}
Weapon/Method: {weapon}
Attack Roll: {roll}
Result: {result}

Generate a visceral, specific description of the attack. Match the energy to the result:
- A perfect critical: describe the exact anatomy of the devastating blow. \
Time slows. The hit reshapes the fight.
- A solid hit: effective — describe the weapon's path, the point of impact, the defender's \
reaction. Each hit should feel different: a clean slash, a bruising chop, a piercing thrust.
- A miss: the near-miss is as important as the hit — was it a dodge, a parry, armor deflection, \
or the attacker overextending? Show the defender's skill or the attacker's frustration.
- A fumble: dangerous, specific, consequential — a weapon slips, a foot catches, balance fails. \
Not slapstick; this is a real fight where mistakes cost.

Keep it to 1-2 sentences. NEVER repeat a description structure you just used. Vary everything:
- Start with the attacker, the defender, the weapon, the environment, or the result
- Use different verbs (lunges/drives/arcs/whips/hammers, not just "swings")
- Include physical detail: the sound, the smell of blood, sparks on armor
"""

DAMAGE_TEMPLATE = """\
You are narrating damage taken in a D&D battle.

Target: {target}
Damage: {damage} {damage_type} damage
Severity: {severity}
Current Status: {hp_current}/{hp_max} HP

Describe the wound and the target's reaction. Be anatomically specific — where on the body? \
What does the wound look like? How does the target move differently now?

Scale the drama to the severity:
- Scratch: a red line, a torn sleeve, a grunt of annoyance — the fight goes on
- Light: a flesh wound that bleeds freely — painful but manageable, gritted teeth
- Moderate: a wound that changes the fight — favoring one side, blood flowing, vision blurring
- Heavy: a wound that threatens to end it — staggering, gasping, fighting through agony
- Devastating: the body failing — knees buckling, consciousness slipping, last reserves burning

Match the damage type to the physical description:
- Slashing: cuts, gashes, severed straps, parted flesh
- Piercing: punctures, blood welling from a single point, the shock of impalement
- Bludgeoning: crunching bone, bruised organs, the dull impact that steals breath
- Fire: searing flesh, smoking cloth, the scream before thought
- Cold: numbing limbs, frost-rimed skin, sluggish movements
- Other: match the element to its physical reality

Keep it to 1-2 sentences. Show, don't tell — the severity should be felt, not stated.
"""

SPELL_TEMPLATE = """\
You are narrating a spell being cast in a D&D battle.

Caster: {caster}
Spell: {spell_name} ({school} magic, level {level})
Targets: {targets}
Effects:
{effects_list}

Describe the spell in three beats: the casting (gesture, incantation, focus), the manifestation \
(what appears in the world), and the impact (what it does to the targets).

Match the magical aesthetic to the school:
- Abjuration: geometric wards, humming barriers, light that solidifies into shields
- Conjuration: reality tearing open, things stepping through from elsewhere, sudden materialization
- Divination: eyes glowing, whispered knowledge, the veil between seen and unseen thinning
- Enchantment: honeyed words, eyes glazing, willpower crumbling like sand
- Evocation: raw elemental fury, blinding light, the roar of unleashed energy
- Illusion: shimmering air, images that flicker at the edges, doubt made manifest
- Necromancy: cold that seeps into bone, shadows lengthening, the boundary between life and death bending
- Transmutation: flesh rippling, matter flowing like water, the laws of nature rewritten

Scale the spectacle to the spell level: a cantrip is a flick of the wrist; a 5th+ level spell \
reshapes the battlefield and demands awe.

For healing spells: warmth, light closing wounds, the relief of pain receding — but also the cost. \
Magic is not free; show the caster's focus and effort.

Keep it to 2-3 sentences. The spell should feel like the caster's personality expressed through magic.
"""

DEATH_TEMPLATE = """\
You are narrating a character's death in a D&D battle.

Character: {character}
Killing Blow: {killing_blow}
Character Type: {character_type}

{player_note}

For a Player Character death:
This is the most dramatic moment in the game. Time slows. Describe the killing blow in \
cinematic detail, then the character's final moment — a last word, a defiant gesture, eyes \
finding an ally. The world should feel the loss: the battle pauses, light changes, sound \
dims. This death must mean something. It must haunt the survivors.

For an Enemy/NPC death:
Match the drama to their importance. A minor monster dies quickly — a wet crunch, a final \
twitch, done. A lieutenant falls with some weight — the other enemies falter. A villain's \
death is an event — they don't go quietly, they rage, curse, or whisper a terrible secret \
with their last breath.

Keep it to 2-3 sentences. The player will remember this moment — make it worth remembering.
"""

UNCONSCIOUS_TEMPLATE = """\
You are narrating a character falling unconscious in a D&D battle.

Character: {character}
Cause: {cause}

Describe the exact moment consciousness leaves — the weapon clattering from loosened fingers, \
knees folding, the body crumpling in a way that makes allies' stomachs drop. The sound of \
armor hitting stone. The sudden absence where a fighter stood.

Make the danger visceral: this character is one failed death save from permanent death. Allies \
need to react NOW. The enemy might finish them off. The clock is ticking.

Keep it to 1-2 sentences. This is the moment between life and death — make it feel that way.
"""


# ------------------------------------------------------------------
# CombatNarrator
# ------------------------------------------------------------------

class CombatNarrator:
    """Generate narrative descriptions for combat events.

    Uses an LLM to create varied, contextual combat narration that maintains
    immersion and avoids repetition. Tracks generated descriptions to ensure
    variety across the combat encounter.

    Args:
        llm: An object implementing the LLMClient protocol.
        max_tokens: Maximum tokens for LLM responses (default 512 for combat brevity).
    """

    def __init__(self, llm: LLMClient, max_tokens: int = 512) -> None:
        self.llm = llm
        self.max_tokens = max_tokens
        self._tracker = DescriptionTracker()

    @staticmethod
    def get_damage_severity(damage: int, max_hp: int) -> DamageSeverity:
        """Classify damage severity based on percentage of max HP.

        Args:
            damage: Amount of damage dealt.
            max_hp: Target's maximum hit points.

        Returns:
            DamageSeverity classification.
        """
        if max_hp <= 0:
            return DamageSeverity.MODERATE

        percentage = (damage / max_hp) * 100.0

        if percentage < 10:
            return DamageSeverity.SCRATCH
        elif percentage < 25:
            return DamageSeverity.LIGHT
        elif percentage < 50:
            return DamageSeverity.MODERATE
        elif percentage < 75:
            return DamageSeverity.HEAVY
        else:
            return DamageSeverity.DEVASTATING

    async def narrate_round_start(
        self,
        round_number: int,
        initiative_order: list,
    ) -> str:
        """Narrate the start of a new combat round.

        Args:
            round_number: The current combat round number.
            initiative_order: List of InitiativeEntry objects in turn order.

        Returns:
            Generated narrative text for round start.
        """
        # Build initiative list for prompt
        initiative_list = "\n".join(
            f"- {entry.name} (Initiative {entry.initiative})"
            + (" <- current turn" if entry.is_current else "")
            for entry in initiative_order
        )

        prompt = ROUND_START_TEMPLATE.format(
            round_number=round_number,
            initiative_list=initiative_list,
        )

        description = await self.llm.generate(prompt, max_tokens=self.max_tokens)
        description = description.strip()

        self._tracker.record(description, f"round_start_{round_number}")
        return description

    async def narrate_attack(
        self,
        attacker: str,
        defender: str,
        weapon: str,
        roll: int,
        hit: bool,
        critical: bool = False,
        fumble: bool = False,
    ) -> str:
        """Narrate an attack roll.

        Args:
            attacker: Name of the attacking character.
            defender: Name of the defending character.
            weapon: Weapon or attack method used.
            roll: The attack roll result.
            hit: Whether the attack hit.
            critical: Whether this was a critical hit.
            fumble: Whether this was a critical fumble.

        Returns:
            Generated narrative text for the attack.
        """
        # Determine result text
        if critical:
            result = "CRITICAL HIT! Devastating success!"
        elif fumble:
            result = "CRITICAL FUMBLE! Something went terribly wrong!"
        elif hit:
            result = "Hit! The attack connects!"
        else:
            result = "Miss! The attack fails to connect."

        prompt = ATTACK_TEMPLATE.format(
            attacker=attacker,
            defender=defender,
            weapon=weapon,
            roll=roll,
            result=result,
        )

        description = await self.llm.generate(prompt, max_tokens=self.max_tokens)
        description = description.strip()

        template_key = "attack_critical" if critical else "attack_fumble" if fumble else "attack_hit" if hit else "attack_miss"
        self._tracker.record(description, template_key)
        return description

    async def narrate_damage(
        self,
        target: str,
        damage: int,
        damage_type: str,
        current_hp: int,
        max_hp: int,
    ) -> str:
        """Narrate damage taken by a character.

        Args:
            target: Name of the character taking damage.
            damage: Amount of damage dealt.
            damage_type: Type of damage (slashing, fire, etc.).
            current_hp: Target's current HP after damage.
            max_hp: Target's maximum HP.

        Returns:
            Generated narrative text for the damage.
        """
        severity = self.get_damage_severity(damage, max_hp)

        prompt = DAMAGE_TEMPLATE.format(
            target=target,
            damage=damage,
            damage_type=damage_type,
            severity=severity.value,
            hp_current=current_hp,
            hp_max=max_hp,
        )

        description = await self.llm.generate(prompt, max_tokens=self.max_tokens)
        description = description.strip()

        self._tracker.record(description, f"damage_{severity.value}")
        return description

    async def narrate_spell(
        self,
        caster: str,
        spell: SpellInfo,
        targets: list[str],
        effects: list[SpellEffect],
    ) -> str:
        """Narrate a spell being cast.

        Args:
            caster: Name of the spellcaster.
            spell: SpellInfo with spell details.
            targets: List of target names.
            effects: List of SpellEffect describing what happened.

        Returns:
            Generated narrative text for the spell.
        """
        targets_str = ", ".join(targets) if targets else "the area"

        effects_list = "\n".join(
            f"- {effect.target}: {effect.effect_type} ({effect.value if effect.value else effect.description})"
            for effect in effects
        )

        prompt = SPELL_TEMPLATE.format(
            caster=caster,
            spell_name=spell.name,
            school=spell.school,
            level=spell.level,
            targets=targets_str,
            effects_list=effects_list,
        )

        description = await self.llm.generate(prompt, max_tokens=self.max_tokens)
        description = description.strip()

        self._tracker.record(description, f"spell_{spell.school}")
        return description

    async def narrate_death(
        self,
        character: str,
        killing_blow: str,
        is_player: bool,
    ) -> str:
        """Narrate a character's death.

        Args:
            character: Name of the dying character.
            killing_blow: Description of what killed them.
            is_player: Whether this is a player character (more dramatic).

        Returns:
            Generated narrative text for the death.
        """
        player_note = (
            "Remember: this is a player character's death. Make it heroic and meaningful."
            if is_player else ""
        )

        character_type = "Player Character (heroic death)" if is_player else "Enemy/NPC"
        prompt = DEATH_TEMPLATE.format(
            character=character,
            killing_blow=killing_blow,
            character_type=character_type,
            player_note=player_note,
        )

        description = await self.llm.generate(prompt, max_tokens=self.max_tokens)
        description = description.strip()

        template_key = "death_player" if is_player else "death_npc"
        self._tracker.record(description, template_key)
        return description

    async def narrate_unconscious(
        self,
        character: str,
        cause: str,
    ) -> str:
        """Narrate a character falling unconscious.

        Args:
            character: Name of the character falling unconscious.
            cause: What caused them to fall unconscious.

        Returns:
            Generated narrative text for unconsciousness.
        """
        prompt = UNCONSCIOUS_TEMPLATE.format(
            character=character,
            cause=cause,
        )

        description = await self.llm.generate(prompt, max_tokens=self.max_tokens)
        description = description.strip()

        self._tracker.record(description, "unconscious")
        return description


__all__ = [
    "CombatNarrator",
    "LLMClient",
    "DamageSeverity",
    "SpellInfo",
    "SpellEffect",
    "DramaticMoment",
    "DescriptionTracker",
    "ROUND_START_TEMPLATE",
    "ATTACK_TEMPLATE",
    "DAMAGE_TEMPLATE",
    "SPELL_TEMPLATE",
    "DEATH_TEMPLATE",
    "UNCONSCIOUS_TEMPLATE",
]
