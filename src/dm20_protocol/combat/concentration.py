"""
Concentration tracking for D&D 5e spellcasting.

This module enforces the D&D 5e concentration mechanic:
- A character can only concentrate on one spell at a time.
- Starting a new concentration spell ends the previous one.
- Taking damage triggers a CON saving throw (DC = max(10, damage // 2)).
- Concentration automatically breaks on incapacitation or death (HP = 0).
- When concentration breaks, all associated ActiveEffects are cleaned up.

The ConcentrationTracker is stateless: it operates on a Character model
and returns result dicts describing what happened.
"""

import random as _random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .effects import EffectsEngine

if TYPE_CHECKING:
    from ..models import Character


@dataclass
class ConcentrationCheckResult:
    """Result of a concentration saving throw.

    Attributes:
        success: Whether the save succeeded (concentration maintained).
        roll: The raw d20 roll.
        total: The total save value (roll + modifiers).
        dc: The difficulty class of the save.
        spell_name: The spell the character was concentrating on.
        broke: Whether concentration broke as a result.
        effects_removed: IDs of ActiveEffects that were removed (empty if maintained).
        detail: Human-readable description of the result.
    """
    success: bool
    roll: int
    total: int
    dc: int
    spell_name: str
    broke: bool
    effects_removed: list[str]
    detail: str


class ConcentrationTracker:
    """Stateless engine for D&D 5e concentration tracking.

    All methods are static. The tracker reads and mutates the Character model's
    ``concentration`` field and ``active_effects`` list directly.

    Typical workflow:
    1. Caster casts a concentration spell -> ``start_concentration()``
    2. Caster takes damage -> ``check_concentration()``
    3. Caster becomes incapacitated -> ``check_auto_break()``
    4. Caster drops to 0 HP -> ``check_auto_break()``
    """

    # -----------------------------------------------------------------
    # Starting / Ending Concentration
    # -----------------------------------------------------------------

    @staticmethod
    def start_concentration(
        character: "Character",
        spell_name: str,
        effect_ids: list[str] | None = None,
        current_round: int = 0,
    ) -> dict:
        """Begin concentrating on a spell.

        If the character is already concentrating on another spell, the old
        concentration is broken first (its effects are removed).

        Args:
            character: The character who is concentrating.
            spell_name: Name of the spell being concentrated on.
            effect_ids: IDs of ActiveEffects tied to this concentration.
                        These will be removed when concentration breaks.
            current_round: The current combat round (0 if out of combat).

        Returns:
            A dict with keys:
                - ``spell_name``: The new spell being concentrated on.
                - ``previous_spell``: Name of the spell that was ended, or None.
                - ``previous_effects_removed``: IDs of effects removed from the old spell.
        """
        from ..models import ConcentrationState

        effect_ids = effect_ids or []
        previous_spell = None
        previous_effects_removed: list[str] = []

        # If already concentrating, break old concentration first
        if character.concentration is not None:
            previous_spell = character.concentration.spell_name
            previous_effects_removed = ConcentrationTracker._break_concentration(character)

        # Set new concentration state
        character.concentration = ConcentrationState(
            spell_name=spell_name,
            effect_ids=list(effect_ids),
            started_round=current_round,
        )

        return {
            "spell_name": spell_name,
            "previous_spell": previous_spell,
            "previous_effects_removed": previous_effects_removed,
        }

    @staticmethod
    def end_concentration(character: "Character") -> dict:
        """Voluntarily end concentration on the current spell.

        Removes all associated ActiveEffects and clears concentration state.

        Args:
            character: The character ending concentration.

        Returns:
            A dict with keys:
                - ``spell_name``: The spell that was ended, or None if not concentrating.
                - ``effects_removed``: IDs of ActiveEffects that were removed.
        """
        if character.concentration is None:
            return {"spell_name": None, "effects_removed": []}

        spell_name = character.concentration.spell_name
        effects_removed = ConcentrationTracker._break_concentration(character)

        return {
            "spell_name": spell_name,
            "effects_removed": effects_removed,
        }

    # -----------------------------------------------------------------
    # Concentration Saves
    # -----------------------------------------------------------------

    @staticmethod
    def check_concentration(
        character: "Character",
        damage_taken: int,
    ) -> ConcentrationCheckResult | None:
        """Trigger a concentration saving throw due to damage.

        Calculates the DC as ``max(10, damage_taken // 2)``, then rolls
        a CON save using the character's CON modifier, proficiency bonus
        (if proficient in CON saves), and any active effect modifiers.

        Args:
            character: The character being checked.
            damage_taken: The amount of damage taken.

        Returns:
            A ConcentrationCheckResult if the character was concentrating,
            or None if the character is not concentrating.
        """
        if character.concentration is None:
            return None

        spell_name = character.concentration.spell_name

        # Calculate DC: max(10, damage // 2)
        dc = max(10, damage_taken // 2)

        # Calculate CON save bonus
        save_bonus = ConcentrationTracker._calculate_con_save_bonus(character)

        # Roll d20
        roll = _random.randint(1, 20)

        # Check advantage/disadvantage on constitution_save
        has_adv = EffectsEngine.has_advantage(character, "constitution_save")
        has_disadv = EffectsEngine.has_disadvantage(character, "constitution_save")

        if has_adv and not has_disadv:
            roll2 = _random.randint(1, 20)
            roll = max(roll, roll2)
        elif has_disadv and not has_adv:
            roll2 = _random.randint(1, 20)
            roll = min(roll, roll2)

        total = roll + save_bonus
        success = total >= dc

        effects_removed: list[str] = []
        if success:
            detail = (
                f"{character.name} maintains concentration on {spell_name}! "
                f"(Rolled {roll} + {save_bonus} = {total} vs DC {dc})"
            )
        else:
            effects_removed = ConcentrationTracker._break_concentration(character)
            detail = (
                f"{character.name} loses concentration on {spell_name}! "
                f"(Rolled {roll} + {save_bonus} = {total} vs DC {dc})"
            )

        return ConcentrationCheckResult(
            success=success,
            roll=roll,
            total=total,
            dc=dc,
            spell_name=spell_name,
            broke=not success,
            effects_removed=effects_removed,
            detail=detail,
        )

    # -----------------------------------------------------------------
    # Auto-break Checks
    # -----------------------------------------------------------------

    @staticmethod
    def check_auto_break(character: "Character") -> dict | None:
        """Check if concentration should automatically break.

        Concentration automatically breaks when:
        - The character is incapacitated (has the "incapacitated" condition
          or an active effect named "Incapacitated").
        - The character drops to 0 HP (death/unconsciousness).

        Args:
            character: The character to check.

        Returns:
            A dict with break details if concentration was broken, or None
            if the character is not concentrating or no auto-break triggered.
        """
        if character.concentration is None:
            return None

        reason = None

        # Check for death (HP = 0)
        if character.hit_points_current <= 0:
            reason = "dropped to 0 HP"

        # Check for incapacitated condition
        if reason is None:
            incapacitated_conditions = {"incapacitated", "stunned", "paralyzed", "petrified", "unconscious"}
            for condition in character.conditions:
                if condition.lower() in incapacitated_conditions:
                    reason = f"{condition} condition"
                    break

        # Check for Incapacitated active effect
        if reason is None:
            if EffectsEngine.has_effect(character, "Incapacitated"):
                reason = "Incapacitated effect"
            elif EffectsEngine.has_effect(character, "Stunned"):
                reason = "Stunned effect"
            elif EffectsEngine.has_effect(character, "Paralyzed"):
                reason = "Paralyzed effect"
            elif EffectsEngine.has_effect(character, "Petrified"):
                reason = "Petrified effect"

        if reason is None:
            return None

        spell_name = character.concentration.spell_name
        effects_removed = ConcentrationTracker._break_concentration(character)

        return {
            "spell_name": spell_name,
            "reason": reason,
            "effects_removed": effects_removed,
            "detail": (
                f"{character.name} loses concentration on {spell_name} "
                f"due to {reason}."
            ),
        }

    # -----------------------------------------------------------------
    # Query Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def is_concentrating(character: "Character") -> bool:
        """Check if a character is currently concentrating on a spell.

        Args:
            character: The character to check.

        Returns:
            True if the character has an active concentration state.
        """
        return character.concentration is not None

    @staticmethod
    def get_concentration_info(character: "Character") -> dict | None:
        """Get information about the character's current concentration.

        Args:
            character: The character to query.

        Returns:
            A dict with spell_name, effect_ids, and started_round,
            or None if not concentrating.
        """
        if character.concentration is None:
            return None

        return {
            "spell_name": character.concentration.spell_name,
            "effect_ids": list(character.concentration.effect_ids),
            "started_round": character.concentration.started_round,
        }

    # -----------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _break_concentration(character: "Character") -> list[str]:
        """Break concentration and clean up associated effects.

        Removes all ActiveEffects whose IDs are listed in the character's
        ConcentrationState, then clears the concentration state.

        Args:
            character: The character whose concentration is breaking.

        Returns:
            List of effect IDs that were removed.
        """
        if character.concentration is None:
            return []

        removed_ids: list[str] = []
        for effect_id in character.concentration.effect_ids:
            removed = EffectsEngine.remove_effect(character, effect_id)
            if removed is not None:
                removed_ids.append(effect_id)

        character.concentration = None
        return removed_ids

    @staticmethod
    def _calculate_con_save_bonus(character: "Character") -> int:
        """Calculate the total CON saving throw bonus for a character.

        Combines:
        - Base CON modifier from ability score
        - Proficiency bonus (if proficient in CON saves)
        - Any active effect modifiers to constitution_save

        Args:
            character: The character to calculate the bonus for.

        Returns:
            The total CON save modifier as an integer.
        """
        # Base CON modifier
        con_mod = character.abilities["constitution"].mod

        # Proficiency bonus for CON saves
        prof_bonus = 0
        if "constitution" in [s.lower() for s in character.saving_throw_proficiencies]:
            prof_bonus = character.proficiency_bonus

        # Active effect modifiers on constitution_save
        effect_bonus = EffectsEngine.effective_stat(character, "constitution_save")

        return con_mod + prof_bonus + effect_bonus
