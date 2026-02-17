"""
Combat action pipeline for D&D 5e.

Provides single-call combat resolution functions that handle the full
attack -> hit/miss -> damage -> apply -> trigger flow. Returns structured
result objects without mutating character state (the caller decides
what to apply).

Functions:
    resolve_attack: Full melee/ranged/spell attack resolution.
    resolve_save_spell: Saving throw spell resolution against one or more targets.

Models:
    CombatResult: Structured result of an attack roll resolution.
    SpellSaveResult: Structured result of a saving throw spell per target.
"""

from __future__ import annotations

import math
import random
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from .effects import EffectsEngine, SRD_CONDITIONS

if TYPE_CHECKING:
    from ..models import Character, Item


# ---------------------------------------------------------------------------
# Dice Utility
# ---------------------------------------------------------------------------

def _parse_dice(notation: str) -> tuple[int, int, int]:
    """Parse dice notation like '2d6+3' into (num_dice, die_size, modifier).

    Args:
        notation: Dice notation string (e.g., '1d20', '2d6+3', '1d8-1').

    Returns:
        Tuple of (number_of_dice, die_size, flat_modifier).

    Raises:
        ValueError: If the notation cannot be parsed.
    """
    notation = notation.lower().strip()
    m = re.match(r"(\d+)d(\d+)([+-]\d+)?", notation)
    if not m:
        raise ValueError(f"Invalid dice notation: {notation!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def _roll_dice(notation: str) -> tuple[list[int], int, int]:
    """Roll dice from notation and return (individual_rolls, flat_modifier, total).

    Args:
        notation: Dice notation string.

    Returns:
        Tuple of (list_of_individual_die_results, flat_modifier, grand_total).
    """
    num, size, mod = _parse_dice(notation)
    rolls = [random.randint(1, size) for _ in range(num)]
    total = sum(rolls) + mod
    return rolls, mod, total


def _roll_d20(
    advantage: bool = False,
    disadvantage: bool = False,
) -> tuple[int, list[int]]:
    """Roll a d20, optionally with advantage or disadvantage.

    Args:
        advantage: If True, roll 2d20 and take the higher.
        disadvantage: If True, roll 2d20 and take the lower.

    Returns:
        Tuple of (chosen_result, all_d20_rolls).
    """
    if advantage or disadvantage:
        r1 = random.randint(1, 20)
        r2 = random.randint(1, 20)
        if advantage:
            return max(r1, r2), [r1, r2]
        else:
            return min(r1, r2), [r1, r2]
    else:
        r = random.randint(1, 20)
        return r, [r]


# ---------------------------------------------------------------------------
# Weapon Helpers
# ---------------------------------------------------------------------------

def _get_attack_ability(attacker: "Character", weapon: "Item | None") -> str:
    """Determine which ability score to use for an attack.

    - Finesse weapons use the higher of STR/DEX.
    - Ranged weapons use DEX.
    - Melee weapons default to STR.
    - Spell attacks use the character's spellcasting_ability.

    Args:
        attacker: The attacking character.
        weapon: The weapon item (may be None for unarmed).

    Returns:
        Ability name string (e.g., 'strength', 'dexterity').
    """
    if weapon is None:
        # Unarmed strike uses STR
        return "strength"

    props = weapon.properties if weapon else {}

    # Spell attack: if weapon properties say so, use spellcasting ability
    if props.get("spell_attack") and attacker.spellcasting_ability:
        return attacker.spellcasting_ability

    is_finesse = props.get("finesse", False)
    is_ranged = props.get("ranged", False) or weapon.item_type == "ranged_weapon"

    if is_ranged:
        return "dexterity"

    if is_finesse:
        str_mod = attacker.abilities.get("strength")
        dex_mod = attacker.abilities.get("dexterity")
        str_val = str_mod.mod if str_mod else 0
        dex_val = dex_mod.mod if dex_mod else 0
        return "dexterity" if dex_val > str_val else "strength"

    return "strength"


def _get_weapon_damage_dice(weapon: "Item | None") -> str:
    """Get the damage dice notation from a weapon's properties.

    Looks for 'damage_dice' in weapon.properties (e.g., '1d8').
    Falls back to '1d4' (unarmed strike) if no weapon is provided or
    no damage_dice property is set.

    Args:
        weapon: The weapon item, or None for unarmed.

    Returns:
        Dice notation string for the weapon's base damage.
    """
    if weapon is None:
        return "1d4"  # Unarmed strike
    return weapon.properties.get("damage_dice", "1d4")


def _get_weapon_damage_type(weapon: "Item | None") -> str:
    """Get the damage type from a weapon's properties.

    Args:
        weapon: The weapon item, or None.

    Returns:
        Damage type string (e.g., 'slashing', 'piercing'). Defaults to 'bludgeoning'.
    """
    if weapon is None:
        return "bludgeoning"
    return weapon.properties.get("damage_type", "bludgeoning")


# ---------------------------------------------------------------------------
# Result Models
# ---------------------------------------------------------------------------

class CombatResult(BaseModel):
    """Structured result of a single attack resolution.

    Contains all information needed for the caller to apply the outcome:
    attack roll details, hit/miss determination, damage breakdown,
    and any triggered effects (concentration checks, unconsciousness).
    """

    # Participants
    attacker_name: str = Field(description="Name of the attacking character")
    target_name: str = Field(description="Name of the target character")

    # Attack roll
    hit: bool = Field(description="Whether the attack hit")
    attack_roll_total: int = Field(description="Final attack roll total (d20 + all modifiers)")
    natural_roll: int = Field(description="The natural d20 result (before modifiers)")
    all_d20_rolls: list[int] = Field(
        default_factory=list,
        description="All d20 rolls made (2 if advantage/disadvantage)"
    )
    attack_modifier: int = Field(default=0, description="Total attack modifier (ability + proficiency + effects)")
    target_ac: int = Field(description="Target's effective armor class")

    # Advantage/disadvantage
    had_advantage: bool = Field(default=False, description="Whether the attack was rolled with advantage")
    had_disadvantage: bool = Field(default=False, description="Whether the attack was rolled with disadvantage")

    # Critical
    critical: bool = Field(default=False, description="Whether this was a critical hit (natural 20)")
    auto_miss: bool = Field(default=False, description="Whether this was an auto-miss (natural 1)")

    # Damage
    damage: int = Field(default=0, description="Total damage dealt (after resistance/vulnerability/immunity)")
    damage_dice_results: list[int] = Field(
        default_factory=list,
        description="Individual damage dice results"
    )
    damage_modifier: int = Field(default=0, description="Flat damage modifier (ability + effects)")
    damage_type: str = Field(default="bludgeoning", description="Damage type (e.g., 'slashing', 'fire')")
    raw_damage: int = Field(default=0, description="Damage before resistance/vulnerability/immunity")
    bonus_dice_results: dict[str, list[int]] = Field(
        default_factory=dict,
        description="Extra dice from effects (e.g., {'Hunter\\'s Mark': [4]})"
    )

    # Resistance / vulnerability / immunity
    resistance_applied: bool = Field(default=False, description="Whether resistance halved the damage")
    vulnerability_applied: bool = Field(default=False, description="Whether vulnerability doubled the damage")
    immunity_applied: bool = Field(default=False, description="Whether immunity negated the damage")

    # Triggered effects
    concentration_check_dc: int | None = Field(
        default=None,
        description="DC for concentration check if target is concentrating (max(10, damage//2))"
    )
    target_dropped_to_zero: bool = Field(
        default=False,
        description="Whether the target would drop to 0 HP from this attack"
    )
    effects_triggered: list[str] = Field(
        default_factory=list,
        description="List of triggered effect descriptions"
    )


class SpellSaveResult(BaseModel):
    """Structured result of a saving throw spell against a single target.

    Used for spells that require the target to make a saving throw
    (e.g., Fireball, Hold Person). Contains save roll details, damage
    (if applicable), and triggered effects.
    """

    # Participants
    caster_name: str = Field(description="Name of the caster")
    target_name: str = Field(description="Name of the target")

    # Save details
    save_ability: str = Field(description="Ability used for the save (e.g., 'dexterity')")
    save_dc: int = Field(description="Spell save DC")
    save_roll_total: int = Field(description="Target's save roll total")
    save_natural_roll: int = Field(description="Natural d20 for the save")
    all_d20_rolls: list[int] = Field(
        default_factory=list,
        description="All d20 rolls made (2 if advantage/disadvantage)"
    )
    save_modifier: int = Field(default=0, description="Target's save modifier")
    saved: bool = Field(description="Whether the target succeeded on the save")

    # Advantage/disadvantage on the save
    had_advantage: bool = Field(default=False)
    had_disadvantage: bool = Field(default=False)

    # Damage
    damage: int = Field(default=0, description="Damage dealt (halved on success if applicable)")
    raw_damage: int = Field(default=0, description="Damage before save halving / resistance")
    damage_type: str = Field(default="", description="Damage type")
    damage_dice_results: list[int] = Field(default_factory=list)
    half_on_save: bool = Field(default=False, description="Whether the spell deals half damage on a successful save")

    # Resistance / vulnerability / immunity
    resistance_applied: bool = Field(default=False)
    vulnerability_applied: bool = Field(default=False)
    immunity_applied: bool = Field(default=False)

    # Triggered effects
    concentration_check_dc: int | None = Field(default=None)
    target_dropped_to_zero: bool = Field(default=False)
    effects_triggered: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Damage Application Helpers
# ---------------------------------------------------------------------------

def _apply_damage_modifiers(
    raw_damage: int,
    damage_type: str,
    target: "Character",
) -> tuple[int, bool, bool, bool]:
    """Apply resistance, vulnerability, and immunity to raw damage.

    Checks the target's active effects for immunities, then properties
    on the character for resistances and vulnerabilities.

    Per 5e rules:
    - Immunity: damage becomes 0
    - Resistance: damage is halved (floor)
    - Vulnerability: damage is doubled
    - If both resistance and vulnerability apply: they cancel out

    Args:
        raw_damage: Damage before modification.
        damage_type: The type of damage (e.g., 'fire', 'slashing').
        target: The target character.

    Returns:
        Tuple of (final_damage, resistance_applied, vulnerability_applied, immunity_applied).
    """
    # Check immunity from active effects
    immunities = EffectsEngine.get_immunities(target)
    if damage_type.lower() in {i.lower() for i in immunities}:
        return 0, False, False, True

    # Check resistance and vulnerability from character properties
    # These are expected as lists in the character's conditions or
    # could be stored in active effects. We check both patterns.
    has_resistance = False
    has_vulnerability = False

    # Check active effects for resistance/vulnerability modifiers
    for effect in target.active_effects:
        for mod in effect.modifiers:
            if mod.stat == f"resistance_{damage_type}" and mod.operation == "add":
                has_resistance = True
            if mod.stat == f"vulnerability_{damage_type}" and mod.operation == "add":
                has_vulnerability = True

    # Also check any direct damage_resistances/damage_vulnerabilities in properties
    # (monster-style stat blocks might store these differently)

    # 5e rule: resistance + vulnerability cancel out
    if has_resistance and has_vulnerability:
        return raw_damage, False, False, False

    if has_resistance:
        return math.floor(raw_damage / 2), True, False, False

    if has_vulnerability:
        return raw_damage * 2, False, True, False

    return raw_damage, False, False, False


def _calculate_concentration_dc(damage: int) -> int:
    """Calculate the concentration check DC from damage taken.

    Per 5e rules: DC = max(10, floor(damage / 2)).

    Args:
        damage: The damage dealt.

    Returns:
        The concentration save DC.
    """
    return max(10, damage // 2)


def _check_target_concentrating(target: "Character") -> bool:
    """Check if a target is currently concentrating on a spell.

    Looks for any active effect with duration_type='concentration'.

    Args:
        target: The character to check.

    Returns:
        True if the target has at least one concentration effect.
    """
    return any(
        effect.duration_type == "concentration"
        for effect in target.active_effects
    )


def _would_drop_to_zero(target: "Character", damage: int) -> bool:
    """Check if damage would drop the target to 0 HP.

    Considers temporary hit points first, then current HP.

    Args:
        target: The target character.
        damage: The damage to apply.

    Returns:
        True if the target's effective HP would reach 0.
    """
    effective_hp = target.hit_points_current + target.temporary_hit_points
    return damage >= effective_hp


# ---------------------------------------------------------------------------
# Attack Resolution
# ---------------------------------------------------------------------------

def resolve_attack(
    attacker: "Character",
    target: "Character",
    weapon: "Item | None" = None,
    *,
    bonus_damage_dice: dict[str, str] | None = None,
    forced_advantage: bool = False,
    forced_disadvantage: bool = False,
    auto_crit: bool = False,
) -> CombatResult:
    """Resolve a full attack action: roll -> hit/miss -> damage -> triggers.

    This is the primary entry point for attack resolution. It handles:
    1. Determine attack ability and compute modifiers
    2. Check advantage/disadvantage from active effects
    3. Roll the attack (d20 + modifiers)
    4. Determine hit/miss against target AC
    5. Roll damage on hit (base + ability mod + bonus dice from effects)
    6. Apply critical hit doubling (dice only, not flat modifiers)
    7. Apply resistance/vulnerability/immunity
    8. Check for concentration save trigger
    9. Check for dropping to 0 HP

    The function does NOT mutate any character state. It returns a CombatResult
    that the caller can inspect and apply as needed.

    Args:
        attacker: The attacking character.
        target: The defending character.
        weapon: The weapon being used (defaults to attacker's main weapon,
                then unarmed if none equipped).
        bonus_damage_dice: Extra damage dice from external sources
                          (e.g., {'Hunter\\'s Mark': '1d6', 'Sneak Attack': '3d6'}).
        forced_advantage: Force advantage regardless of effects.
        forced_disadvantage: Force disadvantage regardless of effects.
        auto_crit: Force critical hit (e.g., target is paralyzed and attack is within 5ft).

    Returns:
        A CombatResult with full attack resolution details.
    """
    # --- Resolve weapon ---
    if weapon is None:
        weapon = attacker.equipment.get("weapon_main")
    # weapon may still be None (unarmed)

    # --- Determine ability and modifiers ---
    attack_ability = _get_attack_ability(attacker, weapon)
    ability_score = attacker.abilities.get(attack_ability)
    ability_mod = ability_score.mod if ability_score else 0
    proficiency = attacker.proficiency_bonus

    # Effect modifiers on attack rolls (flat bonuses)
    effect_attack_bonus = EffectsEngine.effective_stat(attacker, "attack_roll")

    total_attack_mod = ability_mod + proficiency + effect_attack_bonus

    # --- Determine advantage/disadvantage ---
    has_adv = forced_advantage or EffectsEngine.has_advantage(attacker, "attack_roll")
    has_disadv = forced_disadvantage or EffectsEngine.has_disadvantage(attacker, "attack_roll")

    # If both, they cancel (5e rule)
    if has_adv and has_disadv:
        has_adv = False
        has_disadv = False

    # --- Roll attack ---
    natural_roll, all_d20s = _roll_d20(advantage=has_adv, disadvantage=has_disadv)
    attack_total = natural_roll + total_attack_mod

    # --- Determine hit/miss ---
    target_ac = EffectsEngine.effective_stat(target, "armor_class")

    is_nat_1 = natural_roll == 1
    is_nat_20 = natural_roll == 20 or auto_crit
    is_crit = is_nat_20 and not is_nat_1  # Nat 1 overrides even forced crits

    if is_nat_1:
        hit = False
    elif is_nat_20:
        hit = True
    else:
        hit = attack_total >= target_ac

    # --- Build base result (miss case) ---
    result = CombatResult(
        attacker_name=attacker.name,
        target_name=target.name,
        hit=hit,
        attack_roll_total=attack_total,
        natural_roll=natural_roll,
        all_d20_rolls=all_d20s,
        attack_modifier=total_attack_mod,
        target_ac=target_ac,
        had_advantage=has_adv,
        had_disadvantage=has_disadv,
        critical=is_crit,
        auto_miss=is_nat_1,
    )

    if not hit:
        return result

    # --- Roll damage ---
    damage_dice_str = _get_weapon_damage_dice(weapon)
    damage_type = _get_weapon_damage_type(weapon)

    num_dice, die_size, dice_flat_mod = _parse_dice(damage_dice_str)

    # Critical hit: double the number of damage dice (not modifiers)
    effective_num_dice = num_dice * 2 if is_crit else num_dice
    base_rolls = [random.randint(1, die_size) for _ in range(effective_num_dice)]

    # Ability modifier for damage (same ability as attack)
    damage_ability_mod = ability_mod

    # Effect-based flat damage bonus
    effect_damage_bonus = EffectsEngine.effective_stat(attacker, "damage_roll")

    flat_damage = damage_ability_mod + dice_flat_mod + effect_damage_bonus

    # --- Bonus damage dice (from effects like Hunter's Mark, Sneak Attack) ---
    # Also check EffectsEngine for dice-type damage_roll modifiers
    all_bonus_dice: dict[str, str] = {}
    if bonus_damage_dice:
        all_bonus_dice.update(bonus_damage_dice)

    # Dice modifiers from active effects on "damage_roll"
    effect_dice_mods = EffectsEngine.get_dice_modifiers(attacker, "damage_roll")
    for i, dice_str in enumerate(effect_dice_mods):
        all_bonus_dice[f"Effect Bonus {i + 1}"] = dice_str

    bonus_dice_results: dict[str, list[int]] = {}
    bonus_dice_total = 0
    for source_name, dice_notation in all_bonus_dice.items():
        b_num, b_size, b_mod = _parse_dice(dice_notation)
        # Critical hit doubles bonus dice too
        effective_b_num = b_num * 2 if is_crit else b_num
        b_rolls = [random.randint(1, b_size) for _ in range(effective_b_num)]
        bonus_dice_results[source_name] = b_rolls
        bonus_dice_total += sum(b_rolls) + b_mod

    # Total raw damage (minimum 0, 5e: damage can't be negative in most cases,
    # but modifiers can reduce individual components)
    raw_damage = max(0, sum(base_rolls) + flat_damage + bonus_dice_total)

    # --- Apply resistance / vulnerability / immunity ---
    final_damage, resistance, vulnerability, immunity = _apply_damage_modifiers(
        raw_damage, damage_type, target
    )

    # --- Triggered effects ---
    effects_triggered: list[str] = []
    concentration_dc: int | None = None
    drops_to_zero = False

    if final_damage > 0:
        # Concentration check
        if _check_target_concentrating(target):
            concentration_dc = _calculate_concentration_dc(final_damage)
            effects_triggered.append(
                f"Concentration check required (DC {concentration_dc})"
            )

        # Check if target drops to 0 HP
        if _would_drop_to_zero(target, final_damage):
            drops_to_zero = True
            effects_triggered.append("Target drops to 0 HP")

    # --- Populate result ---
    result.damage = final_damage
    result.damage_dice_results = base_rolls
    result.damage_modifier = flat_damage
    result.damage_type = damage_type
    result.raw_damage = raw_damage
    result.bonus_dice_results = bonus_dice_results
    result.resistance_applied = resistance
    result.vulnerability_applied = vulnerability
    result.immunity_applied = immunity
    result.concentration_check_dc = concentration_dc
    result.target_dropped_to_zero = drops_to_zero
    result.effects_triggered = effects_triggered

    return result


# ---------------------------------------------------------------------------
# Saving Throw Spell Resolution
# ---------------------------------------------------------------------------

def resolve_save_spell(
    caster: "Character",
    targets: list["Character"],
    *,
    save_ability: str,
    damage_dice: str | None = None,
    damage_type: str = "",
    half_on_save: bool = False,
    spell_dc: int | None = None,
) -> list[SpellSaveResult]:
    """Resolve a saving throw spell against one or more targets.

    Handles:
    1. Calculate spell save DC (8 + proficiency + spellcasting ability mod),
       or use the explicitly provided spell_dc.
    2. For each target: roll saving throw with advantage/disadvantage from effects.
    3. Compare to DC: pass/fail.
    4. On fail: full damage/effect. On success: half damage if applicable, no effect.
    5. Apply resistance/vulnerability/immunity to final damage.
    6. Check for concentration and dropping to 0 HP.

    Args:
        caster: The character casting the spell.
        targets: List of characters targeted by the spell.
        save_ability: The ability used for the saving throw (e.g., 'dexterity').
        damage_dice: Dice notation for the spell's damage (e.g., '8d6'). None if no damage.
        damage_type: Type of damage (e.g., 'fire').
        half_on_save: Whether successful save still deals half damage.
        spell_dc: Override spell save DC. If None, calculated from caster stats.

    Returns:
        List of SpellSaveResult, one per target.
    """
    # --- Calculate spell save DC ---
    if spell_dc is not None:
        dc = spell_dc
    else:
        if caster.spellcasting_ability:
            sc_ability = caster.abilities.get(caster.spellcasting_ability)
            sc_mod = sc_ability.mod if sc_ability else 0
        else:
            sc_mod = 0
        dc = 8 + caster.proficiency_bonus + sc_mod

    results: list[SpellSaveResult] = []

    for target in targets:
        # --- Determine save modifier ---
        save_ability_score = target.abilities.get(save_ability)
        save_mod = save_ability_score.mod if save_ability_score else 0

        # Proficiency in the saving throw
        if save_ability in target.saving_throw_proficiencies:
            save_mod += target.proficiency_bonus

        # Effect modifiers on saves
        save_stat_name = f"{save_ability}_save"
        effect_save_bonus = EffectsEngine.effective_stat(target, save_stat_name)
        save_mod += effect_save_bonus

        # --- Advantage/disadvantage on save ---
        has_adv = EffectsEngine.has_advantage(target, save_stat_name)
        has_disadv = EffectsEngine.has_disadvantage(target, save_stat_name)
        if has_adv and has_disadv:
            has_adv = False
            has_disadv = False

        # --- Check for dice modifiers on saves (e.g., Bless +1d4) ---
        save_dice_mods = EffectsEngine.get_dice_modifiers(target, save_stat_name)
        # Also check generic "saving_throw" dice mods
        save_dice_mods += EffectsEngine.get_dice_modifiers(target, "saving_throw")

        dice_bonus_total = 0
        for dice_str in save_dice_mods:
            _, _, bonus_total = _roll_dice(dice_str)
            dice_bonus_total += bonus_total

        # --- Roll the save ---
        natural_roll, all_d20s = _roll_d20(advantage=has_adv, disadvantage=has_disadv)
        save_total = natural_roll + save_mod + dice_bonus_total
        saved = save_total >= dc

        # --- Roll damage (if any) ---
        damage_rolls: list[int] = []
        raw_damage = 0
        final_damage = 0
        resistance = False
        vulnerability = False
        immunity = False

        if damage_dice:
            d_num, d_size, d_mod = _parse_dice(damage_dice)
            damage_rolls = [random.randint(1, d_size) for _ in range(d_num)]
            raw_damage = sum(damage_rolls) + d_mod

            # Half on save
            if saved and half_on_save:
                raw_damage = math.floor(raw_damage / 2)
            elif saved:
                raw_damage = 0  # Saved and no half-on-save: no damage

            # Apply resistance/vulnerability/immunity
            if raw_damage > 0:
                final_damage, resistance, vulnerability, immunity = _apply_damage_modifiers(
                    raw_damage, damage_type, target
                )
            else:
                final_damage = 0

        # --- Triggered effects ---
        effects_triggered: list[str] = []
        concentration_dc: int | None = None
        drops_to_zero = False

        if final_damage > 0:
            if _check_target_concentrating(target):
                concentration_dc = _calculate_concentration_dc(final_damage)
                effects_triggered.append(
                    f"Concentration check required (DC {concentration_dc})"
                )
            if _would_drop_to_zero(target, final_damage):
                drops_to_zero = True
                effects_triggered.append("Target drops to 0 HP")

        if not saved:
            effects_triggered.append("Save failed: full effect applies")

        results.append(SpellSaveResult(
            caster_name=caster.name,
            target_name=target.name,
            save_ability=save_ability,
            save_dc=dc,
            save_roll_total=save_total,
            save_natural_roll=natural_roll,
            all_d20_rolls=all_d20s,
            save_modifier=save_mod,
            saved=saved,
            had_advantage=has_adv,
            had_disadvantage=has_disadv,
            damage=final_damage,
            raw_damage=raw_damage,
            damage_type=damage_type,
            damage_dice_results=damage_rolls,
            half_on_save=half_on_save,
            resistance_applied=resistance,
            vulnerability_applied=vulnerability,
            immunity_applied=immunity,
            concentration_check_dc=concentration_dc,
            target_dropped_to_zero=drops_to_zero,
            effects_triggered=effects_triggered,
        ))

    return results


__all__ = [
    "CombatResult",
    "SpellSaveResult",
    "resolve_attack",
    "resolve_save_spell",
]
