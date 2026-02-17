"""
Active Effects engine for D&D 5e combat mechanics.

This module provides:
- EffectsEngine: A stateless engine that computes effective stats from base + modifiers,
  resolves advantage/disadvantage, and manages effect durations.
- SRD_CONDITIONS: All 14 SRD conditions defined as ActiveEffect templates.

The engine is designed to be stateless: it takes a Character and returns computed values.
No caching, no mutable internal state.
"""

from copy import deepcopy
from typing import TYPE_CHECKING

from shortuuid import random

from ..models import ActiveEffect, Modifier

if TYPE_CHECKING:
    from ..models import Character


# ---------------------------------------------------------------------------
# SRD Condition Templates
# ---------------------------------------------------------------------------
# Each condition is an ActiveEffect template. When applied to a character,
# a deep copy is made with a unique ID. Duration defaults to "permanent"
# since conditions are typically removed explicitly (not by timer).
# ---------------------------------------------------------------------------

SRD_CONDITIONS: dict[str, ActiveEffect] = {
    "blinded": ActiveEffect(
        id="srd_blinded",
        name="Blinded",
        source="SRD Condition",
        modifiers=[],
        duration_type="permanent",
        grants_disadvantage=["attack_roll"],
        # Attacks against blinded creature have advantage (tracked on attacker side)
    ),
    "charmed": ActiveEffect(
        id="srd_charmed",
        name="Charmed",
        source="SRD Condition",
        modifiers=[],
        duration_type="permanent",
        # Charmer has advantage on social ability checks (tracked contextually)
    ),
    "deafened": ActiveEffect(
        id="srd_deafened",
        name="Deafened",
        source="SRD Condition",
        modifiers=[],
        duration_type="permanent",
        # A deafened creature can't hear and automatically fails ability checks
        # that require hearing. This is contextual, not a numeric modifier.
    ),
    "exhaustion": ActiveEffect(
        id="srd_exhaustion",
        name="Exhaustion",
        source="SRD Condition",
        modifiers=[],
        duration_type="permanent",
        grants_disadvantage=["ability_check"],
        # Exhaustion level 1: disadvantage on ability checks.
        # Higher levels are tracked via stacking (multiple instances).
        stackable=True,
    ),
    "frightened": ActiveEffect(
        id="srd_frightened",
        name="Frightened",
        source="SRD Condition",
        modifiers=[],
        duration_type="permanent",
        grants_disadvantage=["ability_check", "attack_roll"],
        # While source of fear is in line of sight.
    ),
    "grappled": ActiveEffect(
        id="srd_grappled",
        name="Grappled",
        source="SRD Condition",
        modifiers=[
            Modifier(stat="speed", operation="set", value=0),
        ],
        duration_type="permanent",
    ),
    "incapacitated": ActiveEffect(
        id="srd_incapacitated",
        name="Incapacitated",
        source="SRD Condition",
        modifiers=[],
        duration_type="permanent",
        # Can't take actions or reactions. This is a state flag, not numeric.
    ),
    "invisible": ActiveEffect(
        id="srd_invisible",
        name="Invisible",
        source="SRD Condition",
        modifiers=[],
        duration_type="permanent",
        grants_advantage=["attack_roll"],
        # Attacks against invisible creature have disadvantage (tracked on attacker side)
    ),
    "paralyzed": ActiveEffect(
        id="srd_paralyzed",
        name="Paralyzed",
        source="SRD Condition",
        modifiers=[
            Modifier(stat="speed", operation="set", value=0),
        ],
        duration_type="permanent",
        grants_disadvantage=["strength_save", "dexterity_save"],
        # Auto-fails STR/DEX saves (modeled as disadvantage for mechanical tracking).
        # Attacks against have advantage, hits within 5ft are crits (tracked on attacker side).
    ),
    "petrified": ActiveEffect(
        id="srd_petrified",
        name="Petrified",
        source="SRD Condition",
        modifiers=[
            Modifier(stat="speed", operation="set", value=0),
        ],
        duration_type="permanent",
        grants_disadvantage=["strength_save", "dexterity_save"],
        immunities=["poison"],
        # Weight x10, auto-fails STR/DEX saves, resistance to all damage.
    ),
    "poisoned": ActiveEffect(
        id="srd_poisoned",
        name="Poisoned",
        source="SRD Condition",
        modifiers=[],
        duration_type="permanent",
        grants_disadvantage=["attack_roll", "ability_check"],
    ),
    "prone": ActiveEffect(
        id="srd_prone",
        name="Prone",
        source="SRD Condition",
        modifiers=[],
        duration_type="permanent",
        grants_disadvantage=["attack_roll"],
        # Attacks from within 5ft have advantage against prone (tracked on attacker side).
        # Attacks from farther have disadvantage against prone (tracked on attacker side).
    ),
    "restrained": ActiveEffect(
        id="srd_restrained",
        name="Restrained",
        source="SRD Condition",
        modifiers=[
            Modifier(stat="speed", operation="set", value=0),
        ],
        duration_type="permanent",
        grants_disadvantage=["attack_roll", "dexterity_save"],
        # Attacks against restrained creature have advantage (tracked on attacker side).
    ),
    "stunned": ActiveEffect(
        id="srd_stunned",
        name="Stunned",
        source="SRD Condition",
        modifiers=[
            Modifier(stat="speed", operation="set", value=0),
        ],
        duration_type="permanent",
        grants_disadvantage=["strength_save", "dexterity_save"],
        # Auto-fails STR/DEX saves (modeled as disadvantage).
        # Attacks against have advantage (tracked on attacker side).
    ),
}


class EffectsEngine:
    """Stateless engine for computing character stats with active effects.

    All methods are static or class methods. The engine takes a Character
    and returns computed values without modifying the character's base stats.

    Design principle: the Character model holds the raw data; the EffectsEngine
    provides computed views of that data.
    """

    # -----------------------------------------------------------------
    # Effect Management
    # -----------------------------------------------------------------

    @staticmethod
    def apply_effect(character: "Character", effect: ActiveEffect) -> ActiveEffect:
        """Apply an active effect to a character.

        Creates a deep copy of the effect with a unique ID and adds it to the
        character's active_effects list. Non-stackable effects with the same name
        will not be duplicated; the existing one is kept.

        Args:
            character: The character to apply the effect to.
            effect: The effect template to apply.

        Returns:
            The applied ActiveEffect instance (with unique ID), or the existing
            one if a non-stackable duplicate was found.
        """
        # Check for non-stackable duplicates
        if not effect.stackable:
            for existing in character.active_effects:
                if existing.name == effect.name:
                    return existing

        # Deep copy to avoid shared state between characters
        applied = deepcopy(effect)
        applied.id = random(length=8)
        character.active_effects.append(applied)
        return applied

    @staticmethod
    def remove_effect(character: "Character", effect_id: str) -> ActiveEffect | None:
        """Remove an active effect from a character by its ID.

        Args:
            character: The character to remove the effect from.
            effect_id: The unique ID of the effect to remove.

        Returns:
            The removed ActiveEffect, or None if not found.
        """
        for i, effect in enumerate(character.active_effects):
            if effect.id == effect_id:
                return character.active_effects.pop(i)
        return None

    @staticmethod
    def remove_effects_by_name(character: "Character", name: str) -> list[ActiveEffect]:
        """Remove all active effects with a given name from a character.

        Args:
            character: The character to remove effects from.
            name: The name of effects to remove.

        Returns:
            List of removed ActiveEffect instances.
        """
        removed = []
        remaining = []
        for effect in character.active_effects:
            if effect.name == name:
                removed.append(effect)
            else:
                remaining.append(effect)
        character.active_effects = remaining
        return removed

    # -----------------------------------------------------------------
    # Stat Computation
    # -----------------------------------------------------------------

    @staticmethod
    def effective_stat(character: "Character", stat_name: str) -> int:
        """Calculate the effective value of a stat after all active effect modifiers.

        Resolution order:
        1. Get the base stat value from the character.
        2. Collect all modifiers targeting this stat from active effects.
        3. Apply "set" operations (last one wins if multiple).
        4. Apply "add" operations (cumulative).
        5. "dice" operations are not resolved here (they require a roll at use time).

        Args:
            character: The character to compute the stat for.
            stat_name: The stat to compute (e.g., "armor_class", "speed", "strength").

        Returns:
            The effective stat value as an integer.
        """
        base_value = EffectsEngine._get_base_stat(character, stat_name)

        # Collect all applicable modifiers
        set_value: int | None = None
        add_total: int = 0

        for effect in character.active_effects:
            for mod in effect.modifiers:
                if mod.stat != stat_name:
                    continue

                if mod.operation == "set":
                    # Last "set" wins
                    set_value = int(mod.value) if isinstance(mod.value, (int, float)) else 0
                elif mod.operation == "add":
                    add_total += int(mod.value) if isinstance(mod.value, (int, float)) else 0
                # "dice" modifiers are not resolved statically

        # Apply: set overrides base, then add is cumulative on top
        if set_value is not None:
            return set_value + add_total
        return base_value + add_total

    @staticmethod
    def get_dice_modifiers(character: "Character", stat_name: str) -> list[str]:
        """Get all dice-based modifiers for a stat (e.g., Bless's +1d4).

        These modifiers need to be rolled at use time and cannot be pre-computed.

        Args:
            character: The character to check.
            stat_name: The stat to check for dice modifiers.

        Returns:
            List of dice notation strings (e.g., ["1d4", "2d6"]).
        """
        dice_mods = []
        for effect in character.active_effects:
            for mod in effect.modifiers:
                if mod.stat == stat_name and mod.operation == "dice":
                    dice_mods.append(str(mod.value))
        return dice_mods

    # -----------------------------------------------------------------
    # Advantage / Disadvantage Resolution
    # -----------------------------------------------------------------

    @staticmethod
    def has_advantage(character: "Character", check_type: str) -> bool:
        """Check if a character has advantage on a given check type.

        Per 5e rules: if a character has both advantage and disadvantage on the
        same check, they cancel out (result: no advantage).

        Args:
            character: The character to check.
            check_type: The type of check (e.g., "attack_roll", "dexterity_save").

        Returns:
            True if the character has net advantage (advantage without disadvantage).
        """
        has_adv = any(
            check_type in effect.grants_advantage
            for effect in character.active_effects
        )
        has_disadv = any(
            check_type in effect.grants_disadvantage
            for effect in character.active_effects
        )
        # 5e rule: advantage + disadvantage cancel out
        if has_adv and has_disadv:
            return False
        return has_adv

    @staticmethod
    def has_disadvantage(character: "Character", check_type: str) -> bool:
        """Check if a character has disadvantage on a given check type.

        Per 5e rules: if a character has both advantage and disadvantage on the
        same check, they cancel out (result: no disadvantage).

        Args:
            character: The character to check.
            check_type: The type of check (e.g., "attack_roll", "ability_check").

        Returns:
            True if the character has net disadvantage (disadvantage without advantage).
        """
        has_adv = any(
            check_type in effect.grants_advantage
            for effect in character.active_effects
        )
        has_disadv = any(
            check_type in effect.grants_disadvantage
            for effect in character.active_effects
        )
        # 5e rule: advantage + disadvantage cancel out
        if has_adv and has_disadv:
            return False
        return has_disadv

    # -----------------------------------------------------------------
    # Duration Management
    # -----------------------------------------------------------------

    @staticmethod
    def tick_effects(character: "Character", event: str = "turn") -> list[ActiveEffect]:
        """Advance effect durations and remove expired effects.

        Decrements duration_remaining for effects matching the tick event:
        - "turn": decrements effects with duration_type="rounds"
        - "round": decrements effects with duration_type="minutes"

        Effects with duration_type="concentration" or "permanent" are never
        auto-ticked (they must be removed explicitly).

        Args:
            character: The character whose effects to tick.
            event: The tick event type: "turn" or "round".

        Returns:
            List of effects that expired and were removed.
        """
        expired: list[ActiveEffect] = []
        remaining: list[ActiveEffect] = []

        for effect in character.active_effects:
            should_tick = (
                (event == "turn" and effect.duration_type == "rounds")
                or (event == "round" and effect.duration_type == "minutes")
            )

            if should_tick and effect.duration_remaining is not None:
                effect.duration_remaining -= 1
                if effect.duration_remaining <= 0:
                    expired.append(effect)
                    continue

            remaining.append(effect)

        character.active_effects = remaining
        return expired

    # -----------------------------------------------------------------
    # Query Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def get_active_effects_by_name(character: "Character", name: str) -> list[ActiveEffect]:
        """Get all active effects with a given name.

        Args:
            character: The character to search.
            name: The effect name to search for.

        Returns:
            List of matching ActiveEffect instances.
        """
        return [e for e in character.active_effects if e.name == name]

    @staticmethod
    def has_effect(character: "Character", name: str) -> bool:
        """Check if a character has an active effect with the given name.

        Args:
            character: The character to check.
            name: The effect name to search for.

        Returns:
            True if the character has at least one effect with that name.
        """
        return any(e.name == name for e in character.active_effects)

    @staticmethod
    def get_immunities(character: "Character") -> set[str]:
        """Get the set of all immunities granted by active effects.

        Args:
            character: The character to check.

        Returns:
            Set of immunity strings (damage types or condition names).
        """
        immunities: set[str] = set()
        for effect in character.active_effects:
            immunities.update(effect.immunities)
        return immunities

    # -----------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------

    @staticmethod
    def _get_base_stat(character: "Character", stat_name: str) -> int:
        """Retrieve the base value of a stat from a Character model.

        Supports:
        - Ability scores: "strength", "dexterity", etc. (returns the raw score)
        - Ability modifiers: "strength_mod", "dexterity_mod", etc.
        - Direct fields: "armor_class", "speed", "hit_points_max", "hit_points_current",
          "proficiency_bonus", "temporary_hit_points"

        Args:
            character: The character to read from.
            stat_name: The stat to look up.

        Returns:
            The base integer value. Returns 0 for unknown stats.
        """
        # Ability scores
        if stat_name in character.abilities:
            return character.abilities[stat_name].score

        # Ability modifiers
        if stat_name.endswith("_mod"):
            ability_name = stat_name[:-4]  # Strip "_mod"
            if ability_name in character.abilities:
                return character.abilities[ability_name].mod

        # Direct numeric fields on Character
        direct_fields = {
            "armor_class": "armor_class",
            "speed": "speed",
            "hit_points_max": "hit_points_max",
            "hit_points_current": "hit_points_current",
            "temporary_hit_points": "temporary_hit_points",
            "proficiency_bonus": "proficiency_bonus",
        }

        if stat_name in direct_fields:
            return getattr(character, direct_fields[stat_name], 0)

        # Unknown stat -- return 0 as neutral base (e.g., for "attack_roll" which
        # is computed contextually, not stored as a base field)
        return 0
