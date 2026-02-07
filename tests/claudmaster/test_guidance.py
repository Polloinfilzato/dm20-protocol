"""
Tests for the Player Guidance System (Issue #58).

This module tests natural language command parsing and tactical guidance management
for AI companions in the Claudmaster framework.
"""

import pytest
from gamemaster_mcp.claudmaster.guidance import (
    GuidanceType,
    ParsedGuidance,
    CompanionGuidance,
    GuidanceParser,
    GuidanceManager,
    ACKNOWLEDGMENTS,
)


# ===========================================================================
# GuidanceParser Tests
# ===========================================================================

class TestGuidanceParser:
    """Tests for natural language command parsing."""

    def test_parse_stay_back(self):
        """Test parsing 'stay back' command."""
        parser = GuidanceParser()
        result = parser.parse("stay back")
        assert result is not None
        assert result.guidance_type == GuidanceType.POSITIONING
        assert result.modifier == "back"

    def test_parse_stay_behind(self):
        """Test parsing 'stay behind' command."""
        parser = GuidanceParser()
        result = parser.parse("stay behind")
        assert result is not None
        assert result.guidance_type == GuidanceType.POSITIONING
        assert result.modifier == "back"

    def test_parse_go_front(self):
        """Test parsing 'go to the front' command."""
        parser = GuidanceParser()
        result = parser.parse("go to the front")
        assert result is not None
        assert result.guidance_type == GuidanceType.POSITIONING
        assert result.modifier == "front"

    def test_parse_move_forward(self):
        """Test parsing 'move forward' command."""
        parser = GuidanceParser()
        result = parser.parse("move forward")
        assert result is not None
        assert result.guidance_type == GuidanceType.POSITIONING
        assert result.modifier == "front"

    def test_parse_flank(self):
        """Test parsing 'flank' command."""
        parser = GuidanceParser()
        result = parser.parse("flank")
        assert result is not None
        assert result.guidance_type == GuidanceType.POSITIONING
        assert result.modifier == "flank"

    def test_parse_stay_close(self):
        """Test parsing 'stay close' command."""
        parser = GuidanceParser()
        result = parser.parse("stay close")
        assert result is not None
        assert result.guidance_type == GuidanceType.POSITIONING
        assert result.modifier == "close"

    def test_parse_go_middle(self):
        """Test parsing 'go to the middle' command."""
        parser = GuidanceParser()
        result = parser.parse("go to the middle")
        assert result is not None
        assert result.guidance_type == GuidanceType.POSITIONING
        assert result.modifier == "middle"

    def test_parse_focus_target(self):
        """Test parsing 'focus on the healer' command."""
        parser = GuidanceParser()
        result = parser.parse("focus on the healer")
        assert result is not None
        assert result.guidance_type == GuidanceType.TARGET_FOCUS
        assert result.target == "the healer"

    def test_parse_attack_target(self):
        """Test parsing 'attack goblins' command."""
        parser = GuidanceParser()
        result = parser.parse("attack goblins")
        assert result is not None
        assert result.guidance_type == GuidanceType.TARGET_FOCUS
        assert result.target == "goblins"

    def test_parse_target_keyword(self):
        """Test parsing 'target the wizard' command."""
        parser = GuidanceParser()
        result = parser.parse("target the wizard")
        assert result is not None
        assert result.guidance_type == GuidanceType.TARGET_FOCUS
        assert result.target == "the wizard"

    def test_parse_kill_target(self):
        """Test parsing 'kill the dragon' command."""
        parser = GuidanceParser()
        result = parser.parse("kill the dragon")
        assert result is not None
        assert result.guidance_type == GuidanceType.TARGET_FOCUS
        assert result.target == "the dragon"

    def test_parse_ignore_target(self):
        """Test parsing 'ignore the minions' command."""
        parser = GuidanceParser()
        result = parser.parse("ignore the minions")
        assert result is not None
        assert result.guidance_type == GuidanceType.TARGET_AVOID
        assert result.target == "the minions"

    def test_parse_avoid_target(self):
        """Test parsing 'avoid the boss' command."""
        parser = GuidanceParser()
        result = parser.parse("avoid the boss")
        assert result is not None
        assert result.guidance_type == GuidanceType.TARGET_AVOID
        assert result.target == "the boss"

    def test_parse_dont_attack(self):
        """Test parsing 'don't attack goblins' command."""
        parser = GuidanceParser()
        result = parser.parse("don't attack goblins")
        assert result is not None
        assert result.guidance_type == GuidanceType.TARGET_AVOID
        assert result.target == "goblins"

    def test_parse_protect(self):
        """Test parsing 'protect Aragorn' command."""
        parser = GuidanceParser()
        result = parser.parse("protect Aragorn")
        assert result is not None
        assert result.guidance_type == GuidanceType.PROTECTION
        assert result.target == "Aragorn"

    def test_parse_guard(self):
        """Test parsing 'guard the wizard' command."""
        parser = GuidanceParser()
        result = parser.parse("guard the wizard")
        assert result is not None
        assert result.guidance_type == GuidanceType.PROTECTION
        assert result.target == "the wizard"

    def test_parse_keep_safe(self):
        """Test parsing 'keep Gandalf safe' command."""
        parser = GuidanceParser()
        result = parser.parse("keep Gandalf safe")
        assert result is not None
        assert result.guidance_type == GuidanceType.PROTECTION
        assert result.target == "Gandalf"

    def test_parse_defend(self):
        """Test parsing 'defend the healer' command."""
        parser = GuidanceParser()
        result = parser.parse("defend the healer")
        assert result is not None
        assert result.guidance_type == GuidanceType.PROTECTION
        assert result.target == "the healer"

    def test_parse_be_aggressive(self):
        """Test parsing 'be aggressive' command."""
        parser = GuidanceParser()
        result = parser.parse("be aggressive")
        assert result is not None
        assert result.guidance_type == GuidanceType.AGGRESSION
        assert result.modifier == "aggressive"

    def test_parse_go_aggressive(self):
        """Test parsing 'go aggressive' command."""
        parser = GuidanceParser()
        result = parser.parse("go aggressive")
        assert result is not None
        assert result.guidance_type == GuidanceType.AGGRESSION
        assert result.modifier == "aggressive"

    def test_parse_play_safe(self):
        """Test parsing 'play it safe' command."""
        parser = GuidanceParser()
        result = parser.parse("play it safe")
        assert result is not None
        assert result.guidance_type == GuidanceType.AGGRESSION
        assert result.modifier == "safe"

    def test_parse_be_cautious(self):
        """Test parsing 'be cautious' command."""
        parser = GuidanceParser()
        result = parser.parse("be cautious")
        assert result is not None
        assert result.guidance_type == GuidanceType.AGGRESSION
        assert result.modifier == "cautious"

    def test_parse_be_reckless(self):
        """Test parsing 'go reckless' command."""
        parser = GuidanceParser()
        result = parser.parse("go reckless")
        assert result is not None
        assert result.guidance_type == GuidanceType.AGGRESSION
        assert result.modifier == "reckless"

    def test_parse_save_spells(self):
        """Test parsing 'save your spells' command."""
        parser = GuidanceParser()
        result = parser.parse("save your spells")
        assert result is not None
        assert result.guidance_type == GuidanceType.ABILITY_USE
        assert result.modifier == "conserve"

    def test_parse_save_big_attacks(self):
        """Test parsing 'save your big attacks' command."""
        parser = GuidanceParser()
        result = parser.parse("save your big attacks")
        assert result is not None
        assert result.guidance_type == GuidanceType.ABILITY_USE
        assert result.modifier == "conserve"

    def test_parse_healing_only(self):
        """Test parsing 'use only healing spells' command."""
        parser = GuidanceParser()
        result = parser.parse("use only healing spells")
        assert result is not None
        assert result.guidance_type == GuidanceType.ABILITY_USE
        assert result.modifier == "healing_only"

    def test_parse_cast_healing(self):
        """Test parsing 'cast healing' command."""
        parser = GuidanceParser()
        result = parser.parse("cast healing")
        assert result is not None
        assert result.guidance_type == GuidanceType.ABILITY_USE
        assert result.modifier == "healing_only"

    def test_parse_go_nova(self):
        """Test parsing 'go all out' command."""
        parser = GuidanceParser()
        result = parser.parse("go all out")
        assert result is not None
        assert result.guidance_type == GuidanceType.ABILITY_USE
        assert result.modifier == "nova"

    def test_parse_use_nova(self):
        """Test parsing 'use nova' command."""
        parser = GuidanceParser()
        result = parser.parse("use nova")
        assert result is not None
        assert result.guidance_type == GuidanceType.ABILITY_USE
        assert result.modifier == "nova"

    def test_parse_ranged_only(self):
        """Test parsing 'use only ranged' command."""
        parser = GuidanceParser()
        result = parser.parse("use only ranged")
        assert result is not None
        assert result.guidance_type == GuidanceType.ABILITY_USE
        assert result.modifier == "ranged_only"

    def test_parse_melee_only(self):
        """Test parsing 'use only melee' command."""
        parser = GuidanceParser()
        result = parser.parse("use only melee")
        assert result is not None
        assert result.guidance_type == GuidanceType.ABILITY_USE
        assert result.modifier == "melee_only"

    def test_parse_do_your_thing(self):
        """Test parsing 'do your thing' command."""
        parser = GuidanceParser()
        result = parser.parse("do your thing")
        assert result is not None
        assert result.guidance_type == GuidanceType.GENERAL
        assert result.modifier == "autonomous"

    def test_parse_do_your_best(self):
        """Test parsing 'do your best' command."""
        parser = GuidanceParser()
        result = parser.parse("do your best")
        assert result is not None
        assert result.guidance_type == GuidanceType.GENERAL
        assert result.modifier == "autonomous"

    def test_parse_follow_lead(self):
        """Test parsing 'follow my lead' command."""
        parser = GuidanceParser()
        result = parser.parse("follow my lead")
        assert result is not None
        assert result.guidance_type == GuidanceType.GENERAL
        assert result.modifier == "follow"

    def test_parse_as_you_wish(self):
        """Test parsing 'as you wish' command."""
        parser = GuidanceParser()
        result = parser.parse("as you wish")
        assert result is not None
        assert result.guidance_type == GuidanceType.GENERAL
        assert result.modifier == "obedient"

    def test_parse_empty(self):
        """Test parsing empty command returns None."""
        parser = GuidanceParser()
        result = parser.parse("")
        assert result is None

    def test_parse_whitespace(self):
        """Test parsing whitespace-only command returns None."""
        parser = GuidanceParser()
        result = parser.parse("   ")
        assert result is None

    def test_parse_unknown(self):
        """Test parsing unknown command returns None."""
        parser = GuidanceParser()
        result = parser.parse("quantum entangle the dragon")
        assert result is None

    def test_parse_case_insensitive(self):
        """Test parsing is case-insensitive."""
        parser = GuidanceParser()
        result1 = parser.parse("STAY BACK")
        result2 = parser.parse("Stay Back")
        result3 = parser.parse("stay back")
        assert result1 is not None
        assert result2 is not None
        assert result3 is not None
        assert result1.guidance_type == result2.guidance_type == result3.guidance_type

    def test_acknowledgment_positioning(self):
        """Test acknowledgment for positioning guidance."""
        parser = GuidanceParser()
        guidance = ParsedGuidance(
            guidance_type=GuidanceType.POSITIONING,
            modifier="back"
        )
        ack = parser.get_acknowledgment(guidance)
        assert "back" in ack.lower()

    def test_acknowledgment_target_focus(self):
        """Test acknowledgment for target focus guidance."""
        parser = GuidanceParser()
        guidance = ParsedGuidance(
            guidance_type=GuidanceType.TARGET_FOCUS,
            target="the healer"
        )
        ack = parser.get_acknowledgment(guidance)
        assert "the healer" in ack.lower()

    def test_acknowledgment_protection(self):
        """Test acknowledgment for protection guidance."""
        parser = GuidanceParser()
        guidance = ParsedGuidance(
            guidance_type=GuidanceType.PROTECTION,
            target="Gandalf"
        )
        ack = parser.get_acknowledgment(guidance)
        assert "Gandalf" in ack.lower()

    def test_acknowledgment_aggression(self):
        """Test acknowledgment for aggression guidance."""
        parser = GuidanceParser()
        guidance = ParsedGuidance(
            guidance_type=GuidanceType.AGGRESSION,
            modifier="aggressive"
        )
        ack = parser.get_acknowledgment(guidance)
        assert "aggressive" in ack.lower()

    def test_acknowledgment_ability(self):
        """Test acknowledgment for ability use guidance."""
        parser = GuidanceParser()
        guidance = ParsedGuidance(
            guidance_type=GuidanceType.ABILITY_USE,
            modifier="healing_only"
        )
        ack = parser.get_acknowledgment(guidance)
        assert "healing_only" in ack.lower()

    def test_acknowledgment_general(self):
        """Test acknowledgment for general guidance."""
        parser = GuidanceParser()
        guidance = ParsedGuidance(
            guidance_type=GuidanceType.GENERAL,
            modifier="autonomous"
        )
        ack = parser.get_acknowledgment(guidance)
        assert ack  # Should return some acknowledgment


# ===========================================================================
# CompanionGuidance Tests
# ===========================================================================

class TestCompanionGuidance:
    """Tests for individual companion guidance management."""

    def test_add_guidance(self):
        """Test adding guidance to a companion."""
        companion = CompanionGuidance(companion_id="comp_1")
        guidance = ParsedGuidance(
            guidance_type=GuidanceType.POSITIONING,
            modifier="back"
        )
        companion.add_guidance(guidance)
        assert len(companion.active_guidance) == 1
        assert companion.active_guidance[0] == guidance

    def test_add_replaces_same_type(self):
        """Test that adding guidance replaces existing guidance of same type."""
        companion = CompanionGuidance(companion_id="comp_1")

        # Add first positioning guidance
        guidance1 = ParsedGuidance(
            guidance_type=GuidanceType.POSITIONING,
            modifier="back"
        )
        companion.add_guidance(guidance1)
        assert len(companion.active_guidance) == 1

        # Add second positioning guidance - should replace first
        guidance2 = ParsedGuidance(
            guidance_type=GuidanceType.POSITIONING,
            modifier="front"
        )
        companion.add_guidance(guidance2)
        assert len(companion.active_guidance) == 1
        assert companion.active_guidance[0].modifier == "front"

    def test_add_different_types(self):
        """Test that adding different types of guidance accumulates."""
        companion = CompanionGuidance(companion_id="comp_1")

        guidance1 = ParsedGuidance(
            guidance_type=GuidanceType.POSITIONING,
            modifier="back"
        )
        guidance2 = ParsedGuidance(
            guidance_type=GuidanceType.AGGRESSION,
            modifier="aggressive"
        )

        companion.add_guidance(guidance1)
        companion.add_guidance(guidance2)

        assert len(companion.active_guidance) == 2

    def test_clear_all(self):
        """Test clearing all guidance."""
        companion = CompanionGuidance(companion_id="comp_1")

        guidance1 = ParsedGuidance(
            guidance_type=GuidanceType.POSITIONING,
            modifier="back"
        )
        guidance2 = ParsedGuidance(
            guidance_type=GuidanceType.AGGRESSION,
            modifier="aggressive"
        )

        companion.add_guidance(guidance1)
        companion.add_guidance(guidance2)

        count = companion.clear_guidance()
        assert count == 2
        assert len(companion.active_guidance) == 0

    def test_clear_by_type(self):
        """Test clearing guidance by type."""
        companion = CompanionGuidance(companion_id="comp_1")

        guidance1 = ParsedGuidance(
            guidance_type=GuidanceType.POSITIONING,
            modifier="back"
        )
        guidance2 = ParsedGuidance(
            guidance_type=GuidanceType.AGGRESSION,
            modifier="aggressive"
        )

        companion.add_guidance(guidance1)
        companion.add_guidance(guidance2)

        count = companion.clear_guidance(GuidanceType.POSITIONING)
        assert count == 1
        assert len(companion.active_guidance) == 1
        assert companion.active_guidance[0].guidance_type == GuidanceType.AGGRESSION

    def test_clear_nonexistent_type(self):
        """Test clearing a type that doesn't exist returns 0."""
        companion = CompanionGuidance(companion_id="comp_1")

        guidance = ParsedGuidance(
            guidance_type=GuidanceType.POSITIONING,
            modifier="back"
        )
        companion.add_guidance(guidance)

        count = companion.clear_guidance(GuidanceType.AGGRESSION)
        assert count == 0
        assert len(companion.active_guidance) == 1

    def test_get_by_type(self):
        """Test getting guidance by type."""
        companion = CompanionGuidance(companion_id="comp_1")

        guidance = ParsedGuidance(
            guidance_type=GuidanceType.POSITIONING,
            modifier="back"
        )
        companion.add_guidance(guidance)

        retrieved = companion.get_by_type(GuidanceType.POSITIONING)
        assert retrieved is not None
        assert retrieved.modifier == "back"

    def test_get_by_type_not_found(self):
        """Test getting guidance by type when not found returns None."""
        companion = CompanionGuidance(companion_id="comp_1")

        guidance = ParsedGuidance(
            guidance_type=GuidanceType.POSITIONING,
            modifier="back"
        )
        companion.add_guidance(guidance)

        retrieved = companion.get_by_type(GuidanceType.AGGRESSION)
        assert retrieved is None


# ===========================================================================
# GuidanceManager Tests
# ===========================================================================

class TestGuidanceManager:
    """Tests for the guidance manager."""

    def test_apply_guidance_valid(self):
        """Test applying valid guidance."""
        manager = GuidanceManager()
        guidance, ack = manager.apply_guidance("comp_1", "stay back")

        assert guidance is not None
        assert guidance.guidance_type == GuidanceType.POSITIONING
        assert guidance.modifier == "back"
        assert "back" in ack.lower()

    def test_apply_guidance_invalid(self):
        """Test applying invalid guidance."""
        manager = GuidanceManager()
        guidance, ack = manager.apply_guidance("comp_1", "quantum teleport")

        assert guidance is None
        assert "don't understand" in ack.lower()

    def test_get_active_guidance(self):
        """Test getting active guidance for a companion."""
        manager = GuidanceManager()
        manager.apply_guidance("comp_1", "stay back")
        manager.apply_guidance("comp_1", "be aggressive")

        active = manager.get_active_guidance("comp_1")
        assert len(active) == 2

    def test_get_active_guidance_nonexistent(self):
        """Test getting active guidance for nonexistent companion returns empty list."""
        manager = GuidanceManager()
        active = manager.get_active_guidance("comp_999")
        assert active == []

    def test_tick_round_expires_temporary(self):
        """Test that tick_round expires temporary guidance."""
        manager = GuidanceManager()

        # Apply guidance with duration
        guidance, _ = manager.apply_guidance("comp_1", "stay back")
        guidance.duration = 2

        # After 1 tick, still active
        manager.tick_round()
        active = manager.get_active_guidance("comp_1")
        assert len(active) == 1
        assert active[0].duration == 1

        # After 2nd tick, expired
        manager.tick_round()
        active = manager.get_active_guidance("comp_1")
        assert len(active) == 0

    def test_tick_round_permanent(self):
        """Test that tick_round preserves permanent guidance."""
        manager = GuidanceManager()

        # Apply permanent guidance (duration=None)
        manager.apply_guidance("comp_1", "stay back")

        # Tick multiple rounds
        for _ in range(10):
            manager.tick_round()

        # Should still be active
        active = manager.get_active_guidance("comp_1")
        assert len(active) == 1

    def test_reset_combat_end(self):
        """Test that reset_combat_end clears all guidance."""
        manager = GuidanceManager()

        manager.apply_guidance("comp_1", "stay back")
        manager.apply_guidance("comp_2", "be aggressive")

        assert manager.companion_count == 2

        manager.reset_combat_end()

        assert manager.companion_count == 0
        assert manager.get_active_guidance("comp_1") == []
        assert manager.get_active_guidance("comp_2") == []

    def test_clear_companion_all(self):
        """Test clearing all guidance for a companion."""
        manager = GuidanceManager()

        manager.apply_guidance("comp_1", "stay back")
        manager.apply_guidance("comp_1", "be aggressive")

        count = manager.clear_companion("comp_1")
        assert count == 2
        assert len(manager.get_active_guidance("comp_1")) == 0

    def test_clear_companion_by_type(self):
        """Test clearing specific type of guidance for a companion."""
        manager = GuidanceManager()

        manager.apply_guidance("comp_1", "stay back")
        manager.apply_guidance("comp_1", "be aggressive")

        count = manager.clear_companion("comp_1", GuidanceType.POSITIONING)
        assert count == 1

        active = manager.get_active_guidance("comp_1")
        assert len(active) == 1
        assert active[0].guidance_type == GuidanceType.AGGRESSION

    def test_clear_companion_nonexistent(self):
        """Test clearing guidance for nonexistent companion returns 0."""
        manager = GuidanceManager()
        count = manager.clear_companion("comp_999")
        assert count == 0

    def test_multiple_companions(self):
        """Test managing guidance for multiple companions independently."""
        manager = GuidanceManager()

        manager.apply_guidance("comp_1", "stay back")
        manager.apply_guidance("comp_2", "go front")

        active1 = manager.get_active_guidance("comp_1")
        active2 = manager.get_active_guidance("comp_2")

        assert len(active1) == 1
        assert len(active2) == 1
        assert active1[0].modifier == "back"
        assert active2[0].modifier == "front"

    def test_companion_count(self):
        """Test companion count property."""
        manager = GuidanceManager()

        assert manager.companion_count == 0

        manager.apply_guidance("comp_1", "stay back")
        assert manager.companion_count == 1

        manager.apply_guidance("comp_2", "be aggressive")
        assert manager.companion_count == 2

        manager.clear_companion("comp_1")
        # Clearing guidance doesn't remove the companion from registry
        assert manager.companion_count == 2

    def test_priority_default(self):
        """Test that parsed guidance has default priority of 1."""
        manager = GuidanceManager()
        guidance, _ = manager.apply_guidance("comp_1", "stay back")
        assert guidance.priority == 1

    def test_duration_default(self):
        """Test that parsed guidance has default duration of None (permanent)."""
        manager = GuidanceManager()
        guidance, _ = manager.apply_guidance("comp_1", "stay back")
        assert guidance.duration is None
