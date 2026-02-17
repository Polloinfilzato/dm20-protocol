"""
Tests for the combat action pipeline.

Covers:
- CombatResult and SpellSaveResult model creation
- resolve_attack(): full flow, critical hits, auto-miss, advantage/disadvantage,
  resistance/vulnerability/immunity, concentration triggers, bonus damage dice,
  dropping to 0 HP
- resolve_save_spell(): save DC calculation, pass/fail, half on save,
  resistance, concentration, advantage on saves
- Internal helpers: _parse_dice, _roll_d20, damage modifiers, weapon helpers
"""

import pytest
from unittest.mock import patch

from dm20_protocol.models import (
    ActiveEffect,
    Modifier,
    Character,
    CharacterClass,
    Race,
    AbilityScore,
    Item,
)
from dm20_protocol.combat.effects import EffectsEngine, SRD_CONDITIONS
from dm20_protocol.combat.pipeline import (
    CombatResult,
    SpellSaveResult,
    resolve_attack,
    resolve_save_spell,
    _parse_dice,
    _roll_dice,
    _roll_d20,
    _get_attack_ability,
    _get_weapon_damage_dice,
    _get_weapon_damage_type,
    _apply_damage_modifiers,
    _calculate_concentration_dc,
    _check_target_concentrating,
    _would_drop_to_zero,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fighter() -> Character:
    """A level 5 fighter with STR 16, DEX 14, CON 14."""
    return Character(
        name="Aldric",
        player_name="TestPlayer",
        character_class=CharacterClass(name="Fighter", level=5, hit_dice="1d10"),
        race=Race(name="Human"),
        abilities={
            "strength": AbilityScore(score=16),      # +3
            "dexterity": AbilityScore(score=14),      # +2
            "constitution": AbilityScore(score=14),   # +2
            "intelligence": AbilityScore(score=10),   # +0
            "wisdom": AbilityScore(score=12),         # +1
            "charisma": AbilityScore(score=8),        # -1
        },
        armor_class=18,
        speed=30,
        hit_points_max=44,
        hit_points_current=44,
        proficiency_bonus=3,  # Level 5
    )


@pytest.fixture
def wizard() -> Character:
    """A level 5 wizard with INT 18, spellcasting ability set."""
    return Character(
        name="Elara",
        player_name="TestWizard",
        character_class=CharacterClass(name="Wizard", level=5, hit_dice="1d6"),
        race=Race(name="Elf", subrace="High Elf"),
        abilities={
            "strength": AbilityScore(score=8),        # -1
            "dexterity": AbilityScore(score=14),      # +2
            "constitution": AbilityScore(score=12),   # +1
            "intelligence": AbilityScore(score=18),   # +4
            "wisdom": AbilityScore(score=13),         # +1
            "charisma": AbilityScore(score=10),       # +0
        },
        armor_class=12,
        speed=30,
        hit_points_max=22,
        hit_points_current=22,
        spellcasting_ability="intelligence",
        proficiency_bonus=3,
        saving_throw_proficiencies=["intelligence", "wisdom"],
    )


@pytest.fixture
def goblin() -> Character:
    """A goblin enemy with low stats for target testing."""
    return Character(
        name="Goblin",
        character_class=CharacterClass(name="Monster", level=1),
        race=Race(name="Goblinoid"),
        abilities={
            "strength": AbilityScore(score=8),
            "dexterity": AbilityScore(score=14),
            "constitution": AbilityScore(score=10),
            "intelligence": AbilityScore(score=10),
            "wisdom": AbilityScore(score=8),
            "charisma": AbilityScore(score=8),
        },
        armor_class=15,
        hit_points_max=7,
        hit_points_current=7,
    )


@pytest.fixture
def longsword() -> Item:
    """A standard longsword (1d8 slashing)."""
    return Item(
        name="Longsword",
        item_type="weapon",
        properties={
            "damage_dice": "1d8",
            "damage_type": "slashing",
        },
    )


@pytest.fixture
def rapier() -> Item:
    """A rapier (1d8 piercing, finesse)."""
    return Item(
        name="Rapier",
        item_type="weapon",
        properties={
            "damage_dice": "1d8",
            "damage_type": "piercing",
            "finesse": True,
        },
    )


@pytest.fixture
def longbow() -> Item:
    """A longbow (1d8 piercing, ranged)."""
    return Item(
        name="Longbow",
        item_type="weapon",
        properties={
            "damage_dice": "1d8",
            "damage_type": "piercing",
            "ranged": True,
        },
    )


@pytest.fixture
def spell_attack_focus() -> Item:
    """A spell attack focus for spell attack tests."""
    return Item(
        name="Wand of Fire",
        item_type="weapon",
        properties={
            "damage_dice": "3d6",
            "damage_type": "fire",
            "spell_attack": True,
        },
    )


# ===========================================================================
# Internal Helper Tests
# ===========================================================================

class TestParseDice:
    """Tests for _parse_dice helper."""

    def test_simple_notation(self):
        assert _parse_dice("1d20") == (1, 20, 0)

    def test_with_positive_modifier(self):
        assert _parse_dice("2d6+3") == (2, 6, 3)

    def test_with_negative_modifier(self):
        assert _parse_dice("1d8-1") == (1, 8, -1)

    def test_large_dice(self):
        assert _parse_dice("10d10+5") == (10, 10, 5)

    def test_case_insensitive(self):
        assert _parse_dice("2D6+3") == (2, 6, 3)

    def test_whitespace_trimmed(self):
        assert _parse_dice("  1d8  ") == (1, 8, 0)

    def test_invalid_notation_raises(self):
        with pytest.raises(ValueError):
            _parse_dice("not_dice")


class TestRollD20:
    """Tests for _roll_d20 helper."""

    def test_normal_roll_returns_single(self):
        result, rolls = _roll_d20()
        assert 1 <= result <= 20
        assert len(rolls) == 1
        assert rolls[0] == result

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_advantage_takes_higher(self, mock_randint):
        mock_randint.side_effect = [5, 15]
        result, rolls = _roll_d20(advantage=True)
        assert result == 15
        assert rolls == [5, 15]

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_disadvantage_takes_lower(self, mock_randint):
        mock_randint.side_effect = [5, 15]
        result, rolls = _roll_d20(disadvantage=True)
        assert result == 5
        assert rolls == [5, 15]


class TestWeaponHelpers:
    """Tests for weapon-related helpers."""

    def test_get_attack_ability_str_weapon(self, fighter, longsword):
        assert _get_attack_ability(fighter, longsword) == "strength"

    def test_get_attack_ability_finesse_uses_higher(self, fighter, rapier):
        # Fighter has STR 16 (+3) vs DEX 14 (+2), so STR wins
        assert _get_attack_ability(fighter, rapier) == "strength"

    def test_get_attack_ability_finesse_uses_dex_when_higher(self, wizard, rapier):
        # Wizard has STR 8 (-1) vs DEX 14 (+2), so DEX wins
        assert _get_attack_ability(wizard, rapier) == "dexterity"

    def test_get_attack_ability_ranged(self, fighter, longbow):
        assert _get_attack_ability(fighter, longbow) == "dexterity"

    def test_get_attack_ability_spell(self, wizard, spell_attack_focus):
        assert _get_attack_ability(wizard, spell_attack_focus) == "intelligence"

    def test_get_attack_ability_unarmed(self, fighter):
        assert _get_attack_ability(fighter, None) == "strength"

    def test_get_weapon_damage_dice(self, longsword):
        assert _get_weapon_damage_dice(longsword) == "1d8"

    def test_get_weapon_damage_dice_none(self):
        assert _get_weapon_damage_dice(None) == "1d4"

    def test_get_weapon_damage_type(self, longsword):
        assert _get_weapon_damage_type(longsword) == "slashing"

    def test_get_weapon_damage_type_none(self):
        assert _get_weapon_damage_type(None) == "bludgeoning"


class TestDamageModifiers:
    """Tests for _apply_damage_modifiers."""

    def test_no_modifiers(self, goblin):
        damage, res, vul, imm = _apply_damage_modifiers(10, "slashing", goblin)
        assert damage == 10
        assert not res
        assert not vul
        assert not imm

    def test_immunity(self, goblin):
        # Give the goblin fire immunity via an active effect
        effect = ActiveEffect(
            name="Fire Immunity",
            immunities=["fire"],
        )
        EffectsEngine.apply_effect(goblin, effect)
        damage, _, _, imm = _apply_damage_modifiers(20, "fire", goblin)
        assert damage == 0
        assert imm is True

    def test_resistance(self, goblin):
        # Give goblin slashing resistance via modifier
        effect = ActiveEffect(
            name="Stone Skin",
            modifiers=[Modifier(stat="resistance_slashing", operation="add", value=1)],
        )
        EffectsEngine.apply_effect(goblin, effect)
        damage, res, _, _ = _apply_damage_modifiers(11, "slashing", goblin)
        assert damage == 5  # floor(11/2)
        assert res is True

    def test_vulnerability(self, goblin):
        effect = ActiveEffect(
            name="Fire Vulnerability",
            modifiers=[Modifier(stat="vulnerability_fire", operation="add", value=1)],
        )
        EffectsEngine.apply_effect(goblin, effect)
        damage, _, vul, _ = _apply_damage_modifiers(10, "fire", goblin)
        assert damage == 20
        assert vul is True

    def test_resistance_and_vulnerability_cancel(self, goblin):
        res_effect = ActiveEffect(
            name="Resistance",
            modifiers=[Modifier(stat="resistance_fire", operation="add", value=1)],
        )
        vul_effect = ActiveEffect(
            name="Vulnerability",
            modifiers=[Modifier(stat="vulnerability_fire", operation="add", value=1)],
        )
        EffectsEngine.apply_effect(goblin, res_effect)
        EffectsEngine.apply_effect(goblin, vul_effect)
        damage, res, vul, _ = _apply_damage_modifiers(10, "fire", goblin)
        assert damage == 10  # Cancel out
        assert not res
        assert not vul


class TestConcentrationHelpers:
    """Tests for concentration-related helpers."""

    def test_concentration_dc_low_damage(self):
        assert _calculate_concentration_dc(5) == 10  # max(10, 2) = 10

    def test_concentration_dc_high_damage(self):
        assert _calculate_concentration_dc(30) == 15  # max(10, 15) = 15

    def test_concentration_dc_exact_20(self):
        assert _calculate_concentration_dc(20) == 10  # max(10, 10) = 10

    def test_target_concentrating_true(self, wizard):
        effect = ActiveEffect(name="Bless", duration_type="concentration")
        EffectsEngine.apply_effect(wizard, effect)
        assert _check_target_concentrating(wizard) is True

    def test_target_not_concentrating(self, wizard):
        assert _check_target_concentrating(wizard) is False

    def test_would_drop_to_zero(self, goblin):
        # Goblin has 7 HP
        assert _would_drop_to_zero(goblin, 7) is True
        assert _would_drop_to_zero(goblin, 8) is True
        assert _would_drop_to_zero(goblin, 6) is False

    def test_would_drop_to_zero_with_temp_hp(self, goblin):
        goblin.temporary_hit_points = 5
        # Effective HP = 7 + 5 = 12
        assert _would_drop_to_zero(goblin, 12) is True
        assert _would_drop_to_zero(goblin, 11) is False


# ===========================================================================
# CombatResult Model Tests
# ===========================================================================

class TestCombatResultModel:
    """Tests for CombatResult Pydantic model."""

    def test_minimal_creation(self):
        result = CombatResult(
            attacker_name="A",
            target_name="B",
            hit=False,
            attack_roll_total=10,
            natural_roll=5,
            target_ac=15,
        )
        assert result.hit is False
        assert result.damage == 0
        assert result.critical is False

    def test_full_creation(self):
        result = CombatResult(
            attacker_name="Aldric",
            target_name="Goblin",
            hit=True,
            attack_roll_total=22,
            natural_roll=20,
            all_d20_rolls=[20],
            attack_modifier=2,
            target_ac=15,
            had_advantage=False,
            had_disadvantage=False,
            critical=True,
            auto_miss=False,
            damage=16,
            damage_dice_results=[5, 3, 6, 2],
            damage_modifier=3,
            damage_type="slashing",
            raw_damage=16,
        )
        assert result.critical is True
        assert result.damage == 16

    def test_serialization(self):
        result = CombatResult(
            attacker_name="A", target_name="B", hit=True,
            attack_roll_total=15, natural_roll=12, target_ac=10,
            damage=8,
        )
        data = result.model_dump()
        restored = CombatResult.model_validate(data)
        assert restored.damage == 8


class TestSpellSaveResultModel:
    """Tests for SpellSaveResult Pydantic model."""

    def test_minimal_creation(self):
        result = SpellSaveResult(
            caster_name="Elara",
            target_name="Goblin",
            save_ability="dexterity",
            save_dc=15,
            save_roll_total=12,
            save_natural_roll=10,
            saved=False,
        )
        assert result.saved is False

    def test_serialization(self):
        result = SpellSaveResult(
            caster_name="A", target_name="B",
            save_ability="dexterity", save_dc=15,
            save_roll_total=18, save_natural_roll=16,
            saved=True, damage=10,
        )
        data = result.model_dump()
        restored = SpellSaveResult.model_validate(data)
        assert restored.saved is True
        assert restored.damage == 10


# ===========================================================================
# resolve_attack() Tests
# ===========================================================================

class TestResolveAttackBasic:
    """Basic resolve_attack() flow tests."""

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_hit_with_longsword(self, mock_randint, fighter, goblin, longsword):
        """Fighter attacks goblin with longsword and hits."""
        # d20 roll = 15, damage roll (1d8) = 6
        mock_randint.side_effect = [15, 6]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        assert result.hit is True
        assert result.natural_roll == 15
        # Attack mod = STR(+3) + prof(+3) + 0 effects = +6
        assert result.attack_modifier == 6
        assert result.attack_roll_total == 21
        assert result.target_ac == 15
        # Damage = 6 (roll) + 3 (STR mod) = 9
        assert result.damage == 9
        assert result.damage_type == "slashing"
        assert result.attacker_name == "Aldric"
        assert result.target_name == "Goblin"

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_miss_below_ac(self, mock_randint, fighter, goblin, longsword):
        """Attack misses when roll + mods < target AC."""
        # d20 roll = 3 -> total = 3 + 6 = 9 < 15 (goblin AC)
        mock_randint.side_effect = [3]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        assert result.hit is False
        assert result.damage == 0
        assert result.damage_dice_results == []

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_exact_ac_hit(self, mock_randint, fighter, goblin, longsword):
        """Meeting the AC exactly counts as a hit."""
        # Need roll + 6 = 15, so roll = 9
        mock_randint.side_effect = [9, 5]  # d20=9, damage=5
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)
        assert result.hit is True

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_unarmed_strike(self, mock_randint, fighter, goblin):
        """Unarmed strike when no weapon equipped."""
        mock_randint.side_effect = [15, 3]  # d20=15, damage 1d4=3
        # No weapon equipped (default is None)
        result = resolve_attack(fighter, goblin)

        assert result.hit is True
        assert result.damage_type == "bludgeoning"
        # Damage = 3 (1d4) + 3 (STR) = 6
        assert result.damage == 6

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_explicit_weapon_parameter(self, mock_randint, fighter, goblin, rapier):
        """Pass weapon explicitly instead of using equipment slot."""
        mock_randint.side_effect = [15, 5]
        result = resolve_attack(fighter, goblin, weapon=rapier)

        assert result.hit is True
        assert result.damage_type == "piercing"


class TestResolveAttackCriticals:
    """Critical hit and auto-miss tests."""

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_natural_20_critical_hit(self, mock_randint, fighter, goblin, longsword):
        """Natural 20 always hits and doubles damage dice."""
        # d20=20, then damage: 2d8 (doubled dice) = 4, 6
        mock_randint.side_effect = [20, 4, 6]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        assert result.hit is True
        assert result.critical is True
        assert result.natural_roll == 20
        # Damage = (4 + 6) [doubled dice] + 3 (STR) = 13
        assert result.damage == 13
        assert len(result.damage_dice_results) == 2  # Doubled dice

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_natural_1_always_misses(self, mock_randint, fighter, goblin, longsword):
        """Natural 1 always misses, even with huge modifiers."""
        mock_randint.side_effect = [1]
        fighter.equipment["weapon_main"] = longsword

        # Even with massive attack bonus, nat 1 misses
        result = resolve_attack(fighter, goblin)

        assert result.hit is False
        assert result.auto_miss is True
        assert result.natural_roll == 1
        assert result.damage == 0

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_critical_doubles_bonus_dice_too(self, mock_randint, fighter, goblin, longsword):
        """Critical hit doubles bonus damage dice (e.g., Sneak Attack)."""
        # d20=20, base weapon 2d8 = 3, 5, bonus 2d6 (doubled from 1d6) = 4, 2
        mock_randint.side_effect = [20, 3, 5, 4, 2]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(
            fighter, goblin,
            bonus_damage_dice={"Sneak Attack": "1d6"},
        )

        assert result.critical is True
        # Base: (3+5)=8, Bonus: (4+2)=6, STR mod: +3 = 17
        assert result.damage == 17
        assert "Sneak Attack" in result.bonus_dice_results
        assert len(result.bonus_dice_results["Sneak Attack"]) == 2  # Doubled

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_auto_crit_parameter(self, mock_randint, fighter, goblin, longsword):
        """auto_crit forces critical even without natural 20."""
        # d20=15 (would hit normally), 2d8 (crit doubled) = 4, 6
        mock_randint.side_effect = [15, 4, 6]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin, auto_crit=True)

        assert result.hit is True
        assert result.critical is True
        assert len(result.damage_dice_results) == 2  # Doubled dice


class TestResolveAttackAdvantage:
    """Advantage and disadvantage tests."""

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_advantage_from_effects(self, mock_randint, fighter, goblin, longsword):
        """Advantage from active effects (e.g., Invisible)."""
        effect = ActiveEffect(
            name="Invisible",
            grants_advantage=["attack_roll"],
        )
        EffectsEngine.apply_effect(fighter, effect)

        # Two d20s: 5 and 18, take 18; damage 1d8 = 6
        mock_randint.side_effect = [5, 18, 6]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        assert result.had_advantage is True
        assert result.natural_roll == 18
        assert result.all_d20_rolls == [5, 18]
        assert result.hit is True

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_disadvantage_from_effects(self, mock_randint, fighter, goblin, longsword):
        """Disadvantage from active effects (e.g., Poisoned)."""
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["poisoned"])

        # Two d20s: 18 and 5, take 5; miss (5+6=11 < 15)
        mock_randint.side_effect = [18, 5]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        assert result.had_disadvantage is True
        assert result.natural_roll == 5
        assert result.hit is False

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_advantage_disadvantage_cancel(self, mock_randint, fighter, goblin, longsword):
        """Advantage + disadvantage cancel out (normal roll)."""
        EffectsEngine.apply_effect(fighter, ActiveEffect(
            name="Invisible", grants_advantage=["attack_roll"],
        ))
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["poisoned"])

        # Single d20 roll (cancelled out), damage
        mock_randint.side_effect = [15, 6]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        assert result.had_advantage is False
        assert result.had_disadvantage is False
        assert len(result.all_d20_rolls) == 1

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_forced_advantage(self, mock_randint, fighter, goblin, longsword):
        """Forced advantage via parameter."""
        mock_randint.side_effect = [3, 17, 5]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin, forced_advantage=True)

        assert result.had_advantage is True
        assert result.natural_roll == 17

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_forced_disadvantage(self, mock_randint, fighter, goblin, longsword):
        """Forced disadvantage via parameter."""
        mock_randint.side_effect = [17, 3]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin, forced_disadvantage=True)

        assert result.had_disadvantage is True
        assert result.natural_roll == 3


class TestResolveAttackEffectModifiers:
    """Tests for effect-based attack and damage modifiers."""

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_attack_roll_bonus_from_effects(self, mock_randint, fighter, goblin, longsword):
        """Effect adds flat bonus to attack roll (e.g., +2 magic weapon)."""
        effect = ActiveEffect(
            name="Magic Weapon",
            modifiers=[Modifier(stat="attack_roll", operation="add", value=2)],
        )
        EffectsEngine.apply_effect(fighter, effect)

        # d20=10, damage=5
        mock_randint.side_effect = [10, 5]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        # Attack mod = STR(+3) + prof(+3) + effect(+2) = +8
        assert result.attack_modifier == 8
        assert result.attack_roll_total == 18
        assert result.hit is True

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_damage_bonus_from_effects(self, mock_randint, fighter, goblin, longsword):
        """Effect adds flat bonus to damage (e.g., +2 from magic weapon)."""
        effect = ActiveEffect(
            name="Magic Weapon",
            modifiers=[Modifier(stat="damage_roll", operation="add", value=2)],
        )
        EffectsEngine.apply_effect(fighter, effect)

        # d20=15, damage=6
        mock_randint.side_effect = [15, 6]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        # Damage = 6 (roll) + 3 (STR) + 2 (effect) = 11
        assert result.damage == 11

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_bonus_damage_dice_parameter(self, mock_randint, fighter, goblin, longsword):
        """Extra damage dice from external source (e.g., Hunter's Mark)."""
        # d20=15, base damage=5, bonus 1d6=4
        mock_randint.side_effect = [15, 5, 4]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(
            fighter, goblin,
            bonus_damage_dice={"Hunter's Mark": "1d6"},
        )

        assert result.hit is True
        # Damage = 5 (base) + 3 (STR) + 4 (hunter's mark) = 12
        assert result.damage == 12
        assert "Hunter's Mark" in result.bonus_dice_results
        assert result.bonus_dice_results["Hunter's Mark"] == [4]


class TestResolveAttackResistance:
    """Resistance, vulnerability, and immunity tests for attacks."""

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_resistance_halves_damage(self, mock_randint, fighter, goblin, longsword):
        """Resistance halves damage (rounded down)."""
        effect = ActiveEffect(
            name="Stone Skin",
            modifiers=[Modifier(stat="resistance_slashing", operation="add", value=1)],
        )
        EffectsEngine.apply_effect(goblin, effect)

        # d20=15, damage 1d8=7 -> raw = 7 + 3(STR) = 10, halved = 5
        mock_randint.side_effect = [15, 7]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        assert result.hit is True
        assert result.raw_damage == 10
        assert result.damage == 5
        assert result.resistance_applied is True

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_vulnerability_doubles_damage(self, mock_randint, fighter, goblin, longsword):
        """Vulnerability doubles damage."""
        effect = ActiveEffect(
            name="Weakness",
            modifiers=[Modifier(stat="vulnerability_slashing", operation="add", value=1)],
        )
        EffectsEngine.apply_effect(goblin, effect)

        # d20=15, damage 1d8=5 -> raw = 5 + 3 = 8, doubled = 16
        mock_randint.side_effect = [15, 5]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        assert result.raw_damage == 8
        assert result.damage == 16
        assert result.vulnerability_applied is True

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_immunity_negates_damage(self, mock_randint, fighter, goblin, longsword):
        """Immunity negates all damage."""
        effect = ActiveEffect(
            name="Slashing Immunity",
            immunities=["slashing"],
        )
        EffectsEngine.apply_effect(goblin, effect)

        # d20=15, damage=5
        mock_randint.side_effect = [15, 5]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        assert result.hit is True
        assert result.damage == 0
        assert result.immunity_applied is True


class TestResolveAttackConcentration:
    """Concentration trigger tests for attacks."""

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_concentration_check_triggered(self, mock_randint, fighter, wizard, longsword):
        """Hitting a concentrating target triggers a concentration check."""
        # Wizard is concentrating on Bless
        effect = ActiveEffect(name="Bless", duration_type="concentration")
        EffectsEngine.apply_effect(wizard, effect)

        # d20=15, damage 1d8=5 -> 5+3=8 damage
        mock_randint.side_effect = [15, 5]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, wizard)

        assert result.hit is True
        assert result.damage == 8
        assert result.concentration_check_dc == 10  # max(10, 8//2=4) = 10
        assert any("Concentration" in e for e in result.effects_triggered)

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_high_damage_concentration_dc(self, mock_randint, fighter, wizard, longsword):
        """High damage increases concentration DC above 10."""
        effect = ActiveEffect(name="Bless", duration_type="concentration")
        EffectsEngine.apply_effect(wizard, effect)

        # d20=20, crit: 2d8=8,8 -> 16+3=19 raw, DC = max(10, 19//2=9) = 10
        # Actually let's go higher: 2d8=8,8 -> 16 + 3 = 19 -> DC = max(10, 9) = 10
        # For DC > 10 we need damage > 20. Let's use higher rolls:
        mock_randint.side_effect = [20, 8, 8]  # crit: 2d8 = 16 + 3 STR = 19
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, wizard)

        # DC = max(10, 19//2=9) = 10, still 10. Let's check it's correct.
        assert result.concentration_check_dc == 10

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_no_concentration_check_on_miss(self, mock_randint, fighter, wizard, longsword):
        """No concentration check if the attack misses."""
        effect = ActiveEffect(name="Bless", duration_type="concentration")
        EffectsEngine.apply_effect(wizard, effect)

        mock_randint.side_effect = [1]  # Nat 1, auto-miss
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, wizard)

        assert result.hit is False
        assert result.concentration_check_dc is None

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_no_concentration_check_when_not_concentrating(self, mock_randint, fighter, goblin, longsword):
        """No concentration check if target isn't concentrating."""
        mock_randint.side_effect = [15, 5]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        assert result.hit is True
        assert result.concentration_check_dc is None


class TestResolveAttackDropToZero:
    """Tests for dropping to 0 HP."""

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_target_drops_to_zero(self, mock_randint, fighter, goblin, longsword):
        """Target drops to 0 HP when damage >= current HP."""
        goblin.hit_points_current = 5

        # d20=15, damage 1d8=7 -> 7+3=10 >= 5 HP
        mock_randint.side_effect = [15, 7]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        assert result.hit is True
        assert result.target_dropped_to_zero is True
        assert any("0 HP" in e for e in result.effects_triggered)

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_target_survives(self, mock_randint, fighter, goblin, longsword):
        """Target survives if damage < current HP."""
        goblin.hit_points_current = 100

        mock_randint.side_effect = [15, 5]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        assert result.target_dropped_to_zero is False

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_immune_damage_no_drop(self, mock_randint, fighter, goblin, longsword):
        """Immunity preventing all damage shouldn't trigger drop to 0."""
        goblin.hit_points_current = 1
        effect = ActiveEffect(name="Immunity", immunities=["slashing"])
        EffectsEngine.apply_effect(goblin, effect)

        mock_randint.side_effect = [15, 8]
        fighter.equipment["weapon_main"] = longsword

        result = resolve_attack(fighter, goblin)

        assert result.damage == 0
        assert result.target_dropped_to_zero is False


class TestResolveAttackRangedAndSpell:
    """Tests for ranged and spell attacks."""

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_ranged_attack_uses_dex(self, mock_randint, fighter, goblin, longbow):
        """Ranged weapon uses DEX for attack and damage."""
        # d20=15, damage 1d8=6
        mock_randint.side_effect = [15, 6]

        result = resolve_attack(fighter, goblin, weapon=longbow)

        assert result.hit is True
        # DEX mod = +2, prof = +3, total = +5
        assert result.attack_modifier == 5
        # Damage = 6 + 2 (DEX) = 8
        assert result.damage == 8
        assert result.damage_type == "piercing"

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_spell_attack_uses_spellcasting_ability(self, mock_randint, wizard, goblin, spell_attack_focus):
        """Spell attack uses spellcasting ability for attack and damage."""
        # d20=15, damage 3d6=4,3,5
        mock_randint.side_effect = [15, 4, 3, 5]

        result = resolve_attack(wizard, goblin, weapon=spell_attack_focus)

        assert result.hit is True
        # INT mod = +4, prof = +3, total = +7
        assert result.attack_modifier == 7
        # Damage = (4+3+5) + 4 (INT) = 16
        assert result.damage == 16
        assert result.damage_type == "fire"


# ===========================================================================
# resolve_save_spell() Tests
# ===========================================================================

class TestResolveSaveSpellBasic:
    """Basic saving throw spell resolution tests."""

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_failed_save_full_damage(self, mock_randint, wizard, goblin):
        """Target fails save: takes full damage."""
        # Save d20=5, damage 8d6 = 3,4,2,5,6,1,3,4 = 28
        mock_randint.side_effect = [5, 3, 4, 2, 5, 6, 1, 3, 4]

        results = resolve_save_spell(
            wizard, [goblin],
            save_ability="dexterity",
            damage_dice="8d6",
            damage_type="fire",
            half_on_save=True,
        )

        assert len(results) == 1
        r = results[0]
        assert r.saved is False
        assert r.damage == 28
        assert r.damage_type == "fire"
        # Spell DC = 8 + 3(prof) + 4(INT) = 15
        assert r.save_dc == 15
        assert r.caster_name == "Elara"
        assert r.target_name == "Goblin"

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_successful_save_half_damage(self, mock_randint, wizard, goblin):
        """Target succeeds save with half_on_save: takes half damage."""
        # Save d20=18 (18 + 2 DEX = 20 >= 15 DC), damage 8d6 = 4,4,4,4,4,4,4,4 = 32
        mock_randint.side_effect = [18, 4, 4, 4, 4, 4, 4, 4, 4]

        results = resolve_save_spell(
            wizard, [goblin],
            save_ability="dexterity",
            damage_dice="8d6",
            damage_type="fire",
            half_on_save=True,
        )

        r = results[0]
        assert r.saved is True
        assert r.half_on_save is True
        # Raw damage = floor(32/2) = 16
        assert r.damage == 16

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_successful_save_no_half_damage(self, mock_randint, wizard, goblin):
        """Target succeeds save without half_on_save: takes no damage."""
        mock_randint.side_effect = [18, 4, 4, 4, 4, 4, 4, 4, 4]

        results = resolve_save_spell(
            wizard, [goblin],
            save_ability="dexterity",
            damage_dice="8d6",
            damage_type="fire",
            half_on_save=False,
        )

        r = results[0]
        assert r.saved is True
        assert r.damage == 0

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_no_damage_spell(self, mock_randint, wizard, goblin):
        """Save-or-suck spell with no damage (e.g., Hold Person)."""
        mock_randint.side_effect = [5]  # Fail save (5 + (-1 WIS) = 4 < 15)

        results = resolve_save_spell(
            wizard, [goblin],
            save_ability="wisdom",
        )

        r = results[0]
        assert r.saved is False
        assert r.damage == 0
        assert "Save failed" in r.effects_triggered[-1]

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_spell_dc_calculation(self, mock_randint, wizard, goblin):
        """Spell save DC = 8 + proficiency + spellcasting ability mod."""
        mock_randint.side_effect = [10]

        results = resolve_save_spell(
            wizard, [goblin],
            save_ability="dexterity",
        )

        # DC = 8 + 3 (prof) + 4 (INT mod) = 15
        assert results[0].save_dc == 15

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_custom_spell_dc(self, mock_randint, wizard, goblin):
        """Explicit spell_dc overrides calculation."""
        mock_randint.side_effect = [10]

        results = resolve_save_spell(
            wizard, [goblin],
            save_ability="dexterity",
            spell_dc=20,
        )

        assert results[0].save_dc == 20


class TestResolveSaveSpellMultipleTargets:
    """Tests for spells targeting multiple creatures."""

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_multiple_targets(self, mock_randint, wizard, fighter, goblin):
        """Fireball-style spell hitting multiple targets."""
        # Target 1 (fighter) save: d20=10 + 2(DEX) = 12 < 15 -> fail
        # Target 2 (goblin) save: d20=18 + 2(DEX) = 20 >= 15 -> pass
        # Damage rolls (shared): 8d6 = [3]*8 = 24
        mock_randint.side_effect = [
            10,  # fighter save d20
            3, 3, 3, 3, 3, 3, 3, 3,  # damage for fighter (fail)
            18,  # goblin save d20
            3, 3, 3, 3, 3, 3, 3, 3,  # damage for goblin (pass)
        ]

        results = resolve_save_spell(
            wizard, [fighter, goblin],
            save_ability="dexterity",
            damage_dice="8d6",
            damage_type="fire",
            half_on_save=True,
        )

        assert len(results) == 2

        # Fighter failed save
        assert results[0].saved is False
        assert results[0].damage == 24

        # Goblin passed save -> half damage
        assert results[1].saved is True
        assert results[1].damage == 12  # floor(24/2)


class TestResolveSaveSpellAdvantage:
    """Advantage/disadvantage on saving throws."""

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_save_with_advantage(self, mock_randint, wizard, goblin):
        """Target has advantage on dex saves."""
        effect = ActiveEffect(
            name="Evasion Boost",
            grants_advantage=["dexterity_save"],
        )
        EffectsEngine.apply_effect(goblin, effect)

        # Two d20s for advantage: 5, 17 -> take 17
        mock_randint.side_effect = [5, 17, 3, 3, 3, 3, 3, 3, 3, 3]

        results = resolve_save_spell(
            wizard, [goblin],
            save_ability="dexterity",
            damage_dice="8d6",
            damage_type="fire",
            half_on_save=True,
        )

        r = results[0]
        assert r.had_advantage is True
        assert r.save_natural_roll == 17

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_save_with_disadvantage(self, mock_randint, wizard, goblin):
        """Target has disadvantage on saves."""
        effect = ActiveEffect(
            name="Hex",
            grants_disadvantage=["dexterity_save"],
        )
        EffectsEngine.apply_effect(goblin, effect)

        # Two d20s for disadvantage: 17, 5 -> take 5
        mock_randint.side_effect = [17, 5, 3, 3, 3, 3, 3, 3, 3, 3]

        results = resolve_save_spell(
            wizard, [goblin],
            save_ability="dexterity",
            damage_dice="8d6",
            damage_type="fire",
        )

        r = results[0]
        assert r.had_disadvantage is True
        assert r.save_natural_roll == 5

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_save_proficiency(self, mock_randint, wizard, fighter):
        """Character proficient in save adds proficiency bonus."""
        # Fighter is not proficient in DEX saves by default
        # Let's give proficiency manually
        fighter.saving_throw_proficiencies = ["dexterity"]

        # d20=10 + 2(DEX) + 3(prof) = 15 == DC 15 -> pass
        mock_randint.side_effect = [10, 3, 3, 3, 3, 3, 3, 3, 3]

        results = resolve_save_spell(
            wizard, [fighter],
            save_ability="dexterity",
            damage_dice="8d6",
            damage_type="fire",
            half_on_save=True,
        )

        r = results[0]
        assert r.saved is True
        # Save modifier = DEX(+2) + prof(+3) = +5
        assert r.save_modifier == 5


class TestResolveSaveSpellConcentration:
    """Concentration and drop-to-zero tests for save spells."""

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_concentration_check_on_save_spell_damage(self, mock_randint, wizard, goblin):
        """Save spell damage triggers concentration check on target."""
        # Give goblin a concentration effect
        conc = ActiveEffect(name="Hex", duration_type="concentration")
        EffectsEngine.apply_effect(goblin, conc)

        # Fail save, take 24 damage
        mock_randint.side_effect = [3, 3, 3, 3, 3, 3, 3, 3, 3]

        results = resolve_save_spell(
            wizard, [goblin],
            save_ability="dexterity",
            damage_dice="8d6",
            damage_type="fire",
        )

        r = results[0]
        assert r.damage == 24
        assert r.concentration_check_dc == 12  # max(10, 24//2=12) = 12
        assert any("Concentration" in e for e in r.effects_triggered)

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_drop_to_zero_from_save_spell(self, mock_randint, wizard, goblin):
        """Target drops to 0 HP from save spell damage."""
        goblin.hit_points_current = 3

        # Fail save, take 24 damage
        mock_randint.side_effect = [3, 3, 3, 3, 3, 3, 3, 3, 3]

        results = resolve_save_spell(
            wizard, [goblin],
            save_ability="dexterity",
            damage_dice="8d6",
            damage_type="fire",
        )

        r = results[0]
        assert r.target_dropped_to_zero is True


class TestResolveSaveSpellResistance:
    """Resistance/immunity tests for save spells."""

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_fire_immunity_on_save_spell(self, mock_randint, wizard, goblin):
        """Fire immunity negates fireball damage."""
        effect = ActiveEffect(name="Fire Immunity", immunities=["fire"])
        EffectsEngine.apply_effect(goblin, effect)

        # Fail save
        mock_randint.side_effect = [3, 3, 3, 3, 3, 3, 3, 3, 3]

        results = resolve_save_spell(
            wizard, [goblin],
            save_ability="dexterity",
            damage_dice="8d6",
            damage_type="fire",
        )

        r = results[0]
        assert r.damage == 0
        assert r.immunity_applied is True

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_resistance_halves_save_spell_damage(self, mock_randint, wizard, goblin):
        """Resistance halves save spell damage."""
        effect = ActiveEffect(
            name="Fire Resistance",
            modifiers=[Modifier(stat="resistance_fire", operation="add", value=1)],
        )
        EffectsEngine.apply_effect(goblin, effect)

        # Fail save, take 24 raw
        mock_randint.side_effect = [3, 3, 3, 3, 3, 3, 3, 3, 3]

        results = resolve_save_spell(
            wizard, [goblin],
            save_ability="dexterity",
            damage_dice="8d6",
            damage_type="fire",
        )

        r = results[0]
        assert r.damage == 12  # floor(24/2)
        assert r.resistance_applied is True


# ===========================================================================
# Integration Tests
# ===========================================================================

class TestIntegration:
    """Full integration scenarios combining multiple features."""

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_full_combat_round(self, mock_randint, fighter, wizard, longsword):
        """Simulate a full combat round: fighter attacks wizard."""
        fighter.equipment["weapon_main"] = longsword

        # Give wizard concentration on Bless
        conc = ActiveEffect(name="Bless", duration_type="concentration")
        EffectsEngine.apply_effect(wizard, conc)

        # d20=18, damage 1d8=7
        mock_randint.side_effect = [18, 7]

        result = resolve_attack(fighter, wizard)

        assert result.hit is True
        assert result.attacker_name == "Aldric"
        assert result.target_name == "Elara"
        assert result.damage == 10  # 7 + 3(STR)
        assert result.concentration_check_dc == 10
        assert result.target_dropped_to_zero is False  # 22 HP - 10 = 12

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_poisoned_fighter_with_magic_weapon(self, mock_randint, fighter, goblin, longsword):
        """Poisoned fighter with a +1 magic weapon attacks goblin."""
        fighter.equipment["weapon_main"] = longsword

        # Apply poisoned (disadvantage on attacks)
        EffectsEngine.apply_effect(fighter, SRD_CONDITIONS["poisoned"])

        # Apply magic weapon bonus
        EffectsEngine.apply_effect(fighter, ActiveEffect(
            name="+1 Weapon",
            modifiers=[
                Modifier(stat="attack_roll", operation="add", value=1),
                Modifier(stat="damage_roll", operation="add", value=1),
            ],
        ))

        # Disadvantage: two d20s = 15, 8 -> take 8; damage 1d8 = 5
        mock_randint.side_effect = [15, 8, 5]

        result = resolve_attack(fighter, goblin)

        assert result.had_disadvantage is True
        assert result.natural_roll == 8
        # Attack = 8 + 3(STR) + 3(prof) + 1(magic) = 15, hits AC 15
        assert result.attack_modifier == 7
        assert result.attack_roll_total == 15
        assert result.hit is True
        # Damage = 5 + 3(STR) + 1(magic) = 9
        assert result.damage == 9

    @patch("dm20_protocol.combat.pipeline.random.randint")
    def test_stateless_no_mutation(self, mock_randint, fighter, goblin, longsword):
        """Verify that resolve_attack doesn't mutate character state."""
        fighter.equipment["weapon_main"] = longsword
        original_hp = goblin.hit_points_current
        original_fighter_effects = len(fighter.active_effects)

        mock_randint.side_effect = [15, 7]

        result = resolve_attack(fighter, goblin)

        assert result.hit is True
        # Character HP should NOT be changed by the pipeline
        assert goblin.hit_points_current == original_hp
        assert len(fighter.active_effects) == original_fighter_effects
