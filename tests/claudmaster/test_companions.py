"""
Tests for the Companion NPC Profiles system (Issue #55).

Tests cover:
- PersonalityTraits validation (0-100 range)
- CompanionProfile creation and defaults
- Archetype template creation
- Custom companion creation
- CompanionManager CRUD operations
- Loyalty mechanics (adjust, clamp, threshold checks)
- Save/load state persistence
- Edge cases (duplicates, non-existent, loyalty overflow/underflow)
"""

import pytest
from pydantic import ValidationError

from gamemaster_mcp.claudmaster.companions import (
    CombatStyle,
    CompanionArchetype,
    PersonalityTraits,
    CompanionProfile,
    CompanionManager,
    ARCHETYPE_TEMPLATES,
)


# ============================================================================
# PersonalityTraits Tests
# ============================================================================

class TestPersonalityTraits:
    """Test PersonalityTraits validation and defaults."""

    def test_default_values(self):
        traits = PersonalityTraits()
        assert traits.bravery == 50
        assert traits.loyalty == 50
        assert traits.aggression == 50
        assert traits.caution == 50
        assert traits.compassion == 50

    def test_valid_values(self):
        traits = PersonalityTraits(
            bravery=0, loyalty=25, aggression=50, caution=75, compassion=100
        )
        assert traits.bravery == 0
        assert traits.compassion == 100

    def test_value_below_zero(self):
        with pytest.raises(ValidationError):
            PersonalityTraits(bravery=-1)

    def test_value_above_100(self):
        with pytest.raises(ValidationError):
            PersonalityTraits(loyalty=101)

    def test_boundary_zero(self):
        traits = PersonalityTraits(aggression=0)
        assert traits.aggression == 0

    def test_boundary_100(self):
        traits = PersonalityTraits(caution=100)
        assert traits.caution == 100

    def test_serialization_roundtrip(self):
        traits = PersonalityTraits(bravery=85, compassion=15)
        data = traits.model_dump()
        restored = PersonalityTraits.model_validate(data)
        assert restored == traits


# ============================================================================
# CompanionProfile Tests
# ============================================================================

class TestCompanionProfile:
    """Test CompanionProfile creation and validation."""

    def test_minimal_creation(self):
        companion = CompanionProfile(
            npc_id="npc_123",
            name="Thorin",
            archetype=CompanionArchetype.TANK,
            combat_style=CombatStyle.DEFENSIVE,
        )
        assert companion.npc_id == "npc_123"
        assert companion.name == "Thorin"
        assert companion.loyalty_score == 50
        assert companion.max_loyalty == 100
        assert companion.active is True
        assert companion.preferred_targets == []
        assert companion.avoided_targets == []
        assert companion.preferred_abilities == []

    def test_full_creation(self):
        personality = PersonalityTraits(bravery=80, loyalty=70, aggression=40)
        companion = CompanionProfile(
            npc_id="npc_456",
            name="Elara",
            archetype=CompanionArchetype.HEALER,
            combat_style=CombatStyle.SUPPORTIVE,
            personality=personality,
            loyalty_score=75,
            max_loyalty=90,
            active=False,
            preferred_targets=["undead"],
            avoided_targets=["dragons"],
            preferred_abilities=["heal", "cure", "bless"],
        )
        assert companion.personality.bravery == 80
        assert companion.loyalty_score == 75
        assert companion.max_loyalty == 90
        assert companion.active is False
        assert "undead" in companion.preferred_targets

    def test_loyalty_score_below_zero(self):
        with pytest.raises(ValidationError):
            CompanionProfile(
                npc_id="x", name="X",
                archetype=CompanionArchetype.STRIKER,
                combat_style=CombatStyle.AGGRESSIVE,
                loyalty_score=-5,
            )

    def test_loyalty_score_above_100(self):
        with pytest.raises(ValidationError):
            CompanionProfile(
                npc_id="x", name="X",
                archetype=CompanionArchetype.STRIKER,
                combat_style=CombatStyle.AGGRESSIVE,
                loyalty_score=150,
            )

    def test_serialization_roundtrip(self):
        companion = CompanionProfile(
            npc_id="npc_rt",
            name="Roundtrip",
            archetype=CompanionArchetype.SUPPORT,
            combat_style=CombatStyle.BALANCED,
            personality=PersonalityTraits(bravery=10, compassion=90),
            loyalty_score=65,
            preferred_abilities=["buff"],
        )
        data = companion.model_dump()
        restored = CompanionProfile.model_validate(data)
        assert restored == companion


# ============================================================================
# Archetype Template Tests
# ============================================================================

class TestArchetypeTemplates:
    """Test that archetype templates are properly defined."""

    def test_all_archetypes_have_templates(self):
        for archetype in CompanionArchetype:
            assert archetype in ARCHETYPE_TEMPLATES

    def test_tank_template(self):
        template = ARCHETYPE_TEMPLATES[CompanionArchetype.TANK]
        assert template["combat_style"] == CombatStyle.DEFENSIVE
        assert template["personality"].bravery == 80
        assert template["personality"].caution == 30
        assert "shield" in template["preferred_abilities"]

    def test_healer_template(self):
        template = ARCHETYPE_TEMPLATES[CompanionArchetype.HEALER]
        assert template["combat_style"] == CombatStyle.SUPPORTIVE
        assert template["personality"].compassion == 90
        assert template["personality"].caution == 70
        assert "heal" in template["preferred_abilities"]

    def test_striker_template(self):
        template = ARCHETYPE_TEMPLATES[CompanionArchetype.STRIKER]
        assert template["combat_style"] == CombatStyle.AGGRESSIVE
        assert template["personality"].aggression == 80
        assert "sneak_attack" in template["preferred_abilities"]

    def test_support_template(self):
        template = ARCHETYPE_TEMPLATES[CompanionArchetype.SUPPORT]
        assert template["combat_style"] == CombatStyle.SUPPORTIVE
        assert template["personality"].compassion == 70
        assert "buff" in template["preferred_abilities"]

    def test_template_values_are_valid(self):
        """All templates produce valid CompanionProfile instances."""
        for archetype, template in ARCHETYPE_TEMPLATES.items():
            companion = CompanionProfile(
                npc_id=f"test_{archetype.value}",
                name=f"Test {archetype.value}",
                archetype=archetype,
                **template,
            )
            assert companion.archetype == archetype


# ============================================================================
# CompanionManager Tests
# ============================================================================

class TestCompanionManagerCRUD:
    """Test CompanionManager CRUD operations."""

    def test_initialization(self):
        manager = CompanionManager()
        assert manager.get_active() == []
        assert manager.get("any") is None

    def test_create_from_archetype(self):
        manager = CompanionManager()
        companion = manager.create_from_archetype(
            npc_id="npc_tank", name="Brunhilde", archetype=CompanionArchetype.TANK,
        )
        assert companion.npc_id == "npc_tank"
        assert companion.combat_style == CombatStyle.DEFENSIVE
        assert companion.personality.bravery == 80
        assert "shield" in companion.preferred_abilities

    def test_create_from_archetype_with_overrides(self):
        manager = CompanionManager()
        companion = manager.create_from_archetype(
            npc_id="npc_healer", name="Lyra",
            archetype=CompanionArchetype.HEALER,
            loyalty_score=80, combat_style=CombatStyle.BALANCED,
        )
        assert companion.combat_style == CombatStyle.BALANCED  # overridden
        assert companion.loyalty_score == 80  # overridden
        assert companion.personality.compassion == 90  # from template

    def test_create_custom(self):
        manager = CompanionManager()
        personality = PersonalityTraits(bravery=60, compassion=90)
        companion = manager.create_custom(
            npc_id="npc_custom", name="Zephyr",
            archetype=CompanionArchetype.SUPPORT,
            combat_style=CombatStyle.BALANCED,
            personality=personality,
            preferred_abilities=["inspire", "disarm"],
        )
        assert companion.personality.bravery == 60
        assert companion.preferred_abilities == ["inspire", "disarm"]

    def test_duplicate_npc_id_archetype(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_dup", "First", CompanionArchetype.TANK)
        with pytest.raises(ValueError, match="already exists"):
            manager.create_from_archetype("npc_dup", "Second", CompanionArchetype.HEALER)

    def test_duplicate_npc_id_custom(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_dup2", "First", CompanionArchetype.TANK)
        with pytest.raises(ValueError, match="already exists"):
            manager.create_custom(
                "npc_dup2", "Second", CompanionArchetype.HEALER,
                CombatStyle.BALANCED, PersonalityTraits(),
            )

    def test_get_existing(self):
        manager = CompanionManager()
        created = manager.create_from_archetype("npc_get", "Finder", CompanionArchetype.STRIKER)
        retrieved = manager.get("npc_get")
        assert retrieved is not None
        assert retrieved.npc_id == created.npc_id

    def test_get_nonexistent(self):
        manager = CompanionManager()
        assert manager.get("nonexistent") is None

    def test_get_active_all(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_1", "One", CompanionArchetype.TANK)
        manager.create_from_archetype("npc_2", "Two", CompanionArchetype.HEALER)
        active = manager.get_active()
        assert len(active) == 2

    def test_get_active_mixed(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_a", "Active", CompanionArchetype.TANK)
        manager.create_from_archetype("npc_i", "Inactive", CompanionArchetype.HEALER)
        manager.deactivate("npc_i")
        active = manager.get_active()
        assert len(active) == 1
        assert active[0].npc_id == "npc_a"

    def test_activate(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_act", "Name", CompanionArchetype.TANK)
        manager.deactivate("npc_act")
        assert manager.get("npc_act").active is False
        assert manager.activate("npc_act") is True
        assert manager.get("npc_act").active is True

    def test_activate_nonexistent(self):
        manager = CompanionManager()
        assert manager.activate("nonexistent") is False

    def test_deactivate(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_deact", "Name", CompanionArchetype.TANK)
        assert manager.deactivate("npc_deact") is True
        assert manager.get("npc_deact").active is False

    def test_deactivate_nonexistent(self):
        manager = CompanionManager()
        assert manager.deactivate("nonexistent") is False

    def test_remove(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_rem", "Name", CompanionArchetype.TANK)
        assert manager.remove("npc_rem") is True
        assert manager.get("npc_rem") is None

    def test_remove_nonexistent(self):
        manager = CompanionManager()
        assert manager.remove("nonexistent") is False


# ============================================================================
# Loyalty Mechanics Tests
# ============================================================================

class TestLoyaltyMechanics:
    """Test loyalty adjustment and threshold checking."""

    def test_adjust_positive(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_loy", "Name", CompanionArchetype.TANK)
        new = manager.adjust_loyalty("npc_loy", delta=20, reason="saved party")
        assert new == 70

    def test_adjust_negative(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_loy", "Name", CompanionArchetype.TANK)
        new = manager.adjust_loyalty("npc_loy", delta=-25, reason="endangered ally")
        assert new == 25

    def test_clamp_to_max_loyalty(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_loy", "Name", CompanionArchetype.TANK)
        new = manager.adjust_loyalty("npc_loy", delta=100)
        assert new == 100

    def test_clamp_to_zero(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_loy", "Name", CompanionArchetype.TANK)
        new = manager.adjust_loyalty("npc_loy", delta=-100)
        assert new == 0

    def test_clamp_custom_max(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_loy", "Name", CompanionArchetype.TANK, max_loyalty=75)
        new = manager.adjust_loyalty("npc_loy", delta=50)
        assert new == 75

    def test_adjust_nonexistent(self):
        manager = CompanionManager()
        with pytest.raises(ValueError, match="not found"):
            manager.adjust_loyalty("nonexistent", delta=10)

    def test_threshold_pass(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_t", "Name", CompanionArchetype.TANK)
        manager.adjust_loyalty("npc_t", delta=30)  # loyalty = 80
        assert manager.check_loyalty_threshold("npc_t", required=80) is True
        assert manager.check_loyalty_threshold("npc_t", required=50) is True

    def test_threshold_fail(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_t", "Name", CompanionArchetype.TANK)
        manager.adjust_loyalty("npc_t", delta=-20)  # loyalty = 30
        assert manager.check_loyalty_threshold("npc_t", required=40) is False

    def test_threshold_nonexistent(self):
        manager = CompanionManager()
        with pytest.raises(ValueError, match="not found"):
            manager.check_loyalty_threshold("nonexistent", required=50)


# ============================================================================
# Persistence Tests
# ============================================================================

class TestPersistence:
    """Test save/load state for campaign persistence."""

    def test_save_empty(self):
        manager = CompanionManager()
        assert manager.save_state() == {}

    def test_save_with_companions(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_1", "One", CompanionArchetype.TANK)
        manager.create_from_archetype("npc_2", "Two", CompanionArchetype.HEALER)
        manager.adjust_loyalty("npc_1", delta=20)
        manager.deactivate("npc_2")

        state = manager.save_state()
        assert "npc_1" in state
        assert "npc_2" in state
        assert state["npc_1"]["loyalty_score"] == 70
        assert state["npc_2"]["active"] is False

    def test_load_empty(self):
        manager = CompanionManager()
        manager.create_from_archetype("npc_temp", "Temp", CompanionArchetype.TANK)
        manager.load_state({})
        assert manager.get_active() == []

    def test_load_with_companions(self):
        manager1 = CompanionManager()
        manager1.create_from_archetype("npc_1", "Alpha", CompanionArchetype.STRIKER)
        manager1.create_from_archetype("npc_2", "Beta", CompanionArchetype.SUPPORT)
        manager1.adjust_loyalty("npc_1", delta=30)
        manager1.deactivate("npc_2")
        state = manager1.save_state()

        manager2 = CompanionManager()
        manager2.load_state(state)
        assert manager2.get("npc_1").name == "Alpha"
        assert manager2.get("npc_1").loyalty_score == 80
        assert manager2.get("npc_2").active is False
        assert len(manager2.get_active()) == 1

    def test_full_roundtrip(self):
        """Complete save/load cycle preserves all companion data."""
        manager1 = CompanionManager()
        manager1.create_custom(
            npc_id="npc_rt", name="Roundtripper",
            archetype=CompanionArchetype.HEALER,
            combat_style=CombatStyle.SUPPORTIVE,
            personality=PersonalityTraits(bravery=85, compassion=95),
            loyalty_score=65, max_loyalty=80, active=False,
            preferred_targets=["undead", "fiends"],
            avoided_targets=["innocents"],
            preferred_abilities=["heal", "bless", "sanctuary"],
        )

        state = manager1.save_state()
        manager2 = CompanionManager()
        manager2.load_state(state)

        c = manager2.get("npc_rt")
        assert c.name == "Roundtripper"
        assert c.archetype == CompanionArchetype.HEALER
        assert c.combat_style == CombatStyle.SUPPORTIVE
        assert c.personality.bravery == 85
        assert c.personality.compassion == 95
        assert c.loyalty_score == 65
        assert c.max_loyalty == 80
        assert c.active is False
        assert c.preferred_targets == ["undead", "fiends"]
        assert c.avoided_targets == ["innocents"]
        assert c.preferred_abilities == ["heal", "bless", "sanctuary"]
