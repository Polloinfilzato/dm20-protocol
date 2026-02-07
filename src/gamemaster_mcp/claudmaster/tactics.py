"""
AI Combat Tactics System for Claudmaster companion NPCs.

This module implements intelligent combat decision-making for companion characters
based on their archetype (tank, healer, striker, support), personality traits,
and loyalty scores. The TacticsEngine evaluates battlefield state and makes
tactical decisions aligned with each companion's role and character.

Tactical Priorities:
- SURVIVE: Self-preservation when low HP or threatened
- PROTECT_ALLY: Shield/defend party members (tank default)
- ELIMINATE_THREAT: Focus fire on dangerous enemies (striker default)
- SUPPORT_PARTY: Heal, buff, or assist allies (healer/support default)
- CONTROL_BATTLEFIELD: Area control, debuffs, positioning

Archetype Strategies:
- Tank: Front line positioning, prioritize threats to allies, use defensive abilities
- Healer: Back line, heal wounded allies, support when all healthy
- Striker: Flanking position, target low HP or high value enemies, aggressive abilities
- Support: Mid-line, buff allies early, debuff enemies, inspire actions
"""

from enum import Enum
from pydantic import BaseModel, Field

from .companions import CompanionProfile, CompanionArchetype, PersonalityTraits, CombatStyle


class TacticalPriority(str, Enum):
    """Strategic priorities that drive tactical decision-making."""
    SURVIVE = "survive"
    PROTECT_ALLY = "protect_ally"
    ELIMINATE_THREAT = "eliminate_threat"
    SUPPORT_PARTY = "support_party"
    CONTROL_BATTLEFIELD = "control_battlefield"


class Combatant(BaseModel):
    """Represents a combatant in the battlefield for tactical evaluation."""
    name: str = Field(description="Combatant name")
    hp_current: int = Field(description="Current hit points")
    hp_max: int = Field(description="Maximum hit points")
    armor_class: int = Field(default=10, description="Armor class (difficulty to hit)")
    is_ally: bool = Field(default=False, description="Whether this is an ally")
    is_player: bool = Field(default=False, description="Whether this is the player character")
    position: tuple[int, int] | None = Field(default=None, description="Grid position (x, y)")
    conditions: list[str] = Field(default_factory=list, description="Active conditions")
    damage_potential: float = Field(default=5.0, description="Estimated damage per round")
    threat_to_allies: float = Field(default=0.5, ge=0.0, le=1.0, description="Threat level 0-1")
    value: float = Field(default=0.5, ge=0.0, le=1.0, description="Tactical value 0-1")

    @property
    def hp_percentage(self) -> float:
        """Calculate HP as percentage of maximum (0.0-1.0)."""
        if self.hp_max <= 0:
            return 0.0
        return self.hp_current / self.hp_max


class TacticalDecision(BaseModel):
    """A tactical decision made by the TacticsEngine."""
    action_type: str = Field(
        description="Type of action: attack, move, ability, item, dodge, help, disengage"
    )
    target: str | None = Field(default=None, description="Target name if applicable")
    ability: str | None = Field(default=None, description="Ability/spell name if applicable")
    priority: TacticalPriority = Field(description="Strategic priority driving this decision")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in this decision 0-1")
    reasoning: str = Field(description="Human-readable explanation for the decision")
    action_economy: str = Field(
        default="action",
        description="Action economy slot: action, bonus_action, movement"
    )


class BattlefieldState(BaseModel):
    """Full state of the battlefield for tactical decision-making."""
    combatants: list[Combatant] = Field(
        default_factory=list,
        description="All combatants in the encounter"
    )
    round_number: int = Field(default=1, description="Current combat round")
    companion_hp_current: int = Field(default=0, description="Companion's current HP")
    companion_hp_max: int = Field(default=1, description="Companion's max HP")
    companion_conditions: list[str] = Field(
        default_factory=list,
        description="Active conditions on the companion"
    )


class TacticsEngine:
    """Makes combat decisions for companion NPCs based on archetype, personality, and battlefield state.

    The TacticsEngine evaluates the current battlefield state and companion profile
    to make intelligent tactical decisions. Each archetype has distinct priorities
    and target selection criteria, modified by personality traits and loyalty.

    Example:
        >>> companion = CompanionProfile(...)
        >>> battlefield = BattlefieldState(combatants=[...], ...)
        >>> engine = TacticsEngine(companion, battlefield)
        >>> decision = engine.decide_action()
        >>> print(decision.action_type, decision.target, decision.reasoning)

    Args:
        companion: The companion profile making the decision
        battlefield: Current state of the battlefield
    """

    def __init__(self, companion: CompanionProfile, battlefield: BattlefieldState):
        """Initialize the tactics engine.

        Args:
            companion: CompanionProfile of the acting companion
            battlefield: BattlefieldState containing all combatants
        """
        self.companion = companion
        self.battlefield = battlefield
        self._allies: list[Combatant] = []
        self._enemies: list[Combatant] = []

        # Partition combatants into allies and enemies
        for combatant in battlefield.combatants:
            if combatant.is_ally or combatant.is_player:
                self._allies.append(combatant)
            else:
                self._enemies.append(combatant)

    def decide_action(self) -> TacticalDecision:
        """Main entry point: determine the best action for this companion's turn.

        Evaluates the battlefield state and companion archetype to select
        the most appropriate action. Considers:
        - Companion HP and survival needs
        - Ally HP and support needs
        - Enemy threats and elimination opportunities
        - Personality traits and loyalty

        Returns:
            TacticalDecision with action type, target, and reasoning
        """
        # Check self-preservation override
        companion_hp_pct = self.battlefield.companion_hp_current / max(
            self.battlefield.companion_hp_max, 1
        )

        # Low loyalty + low HP = prioritize survival
        if self.companion.loyalty_score < 30 and companion_hp_pct < 0.3:
            return TacticalDecision(
                action_type="disengage",
                priority=TacticalPriority.SURVIVE,
                confidence=0.9,
                reasoning=f"{self.companion.name} has low loyalty and is badly wounded - prioritizing survival",
                action_economy="action",
            )

        # High loyalty override: protect allies even at personal risk
        if self.companion.loyalty_score > 80:
            wounded_ally = self._find_most_wounded_ally()
            if wounded_ally and wounded_ally.hp_percentage < 0.2:
                # Very high loyalty = sacrifice to protect
                return self._decide_tank_action()

        # Dispatch to archetype-specific logic
        if self.companion.archetype == CompanionArchetype.TANK:
            return self._decide_tank_action()
        elif self.companion.archetype == CompanionArchetype.HEALER:
            return self._decide_healer_action()
        elif self.companion.archetype == CompanionArchetype.STRIKER:
            return self._decide_striker_action()
        elif self.companion.archetype == CompanionArchetype.SUPPORT:
            return self._decide_support_action()
        else:
            # Fallback: basic attack
            targets = self.evaluate_targets()
            if targets:
                target_name = targets[0][0]
                return TacticalDecision(
                    action_type="attack",
                    target=target_name,
                    priority=TacticalPriority.ELIMINATE_THREAT,
                    confidence=0.5,
                    reasoning="Default attack action",
                    action_economy="action",
                )
            else:
                return TacticalDecision(
                    action_type="dodge",
                    priority=TacticalPriority.SURVIVE,
                    confidence=0.5,
                    reasoning="No valid targets - taking defensive stance",
                    action_economy="action",
                )

    def evaluate_targets(self) -> list[tuple[str, float]]:
        """Score all potential targets by tactical value.

        Applies archetype-specific scoring criteria and personality modifiers
        to rank enemies by tactical priority.

        Returns:
            List of (name, score) tuples sorted by score descending
        """
        scored_targets: list[tuple[str, float]] = []

        for enemy in self._enemies:
            score = self._calculate_target_score(enemy)
            scored_targets.append((enemy.name, score))

        # Sort by score descending
        scored_targets.sort(key=lambda x: x[1], reverse=True)
        return scored_targets

    def select_ability(self, target: str) -> str | None:
        """Choose the best ability to use against a target.

        Selects from preferred_abilities based on archetype and situation.

        Args:
            target: Target name (ally or enemy)

        Returns:
            Ability name from preferred_abilities, or None if none available
        """
        if not self.companion.preferred_abilities:
            return None

        # For healers/support, check if target is ally
        target_combatant = self._find_combatant(target)
        if target_combatant and (target_combatant.is_ally or target_combatant.is_player):
            # Healing/support ability
            healing_abilities = [a for a in self.companion.preferred_abilities if a in ["heal", "cure", "bless", "buff"]]
            if healing_abilities:
                return healing_abilities[0]

        # Offensive ability
        offensive_abilities = [
            a for a in self.companion.preferred_abilities
            if a not in ["heal", "cure", "bless", "buff"]
        ]
        if offensive_abilities:
            return offensive_abilities[0]

        # Fallback: first preferred ability
        return self.companion.preferred_abilities[0]

    def calculate_positioning(self) -> tuple[int, int] | None:
        """Determine optimal position on battlefield.

        Considers archetype positioning strategy:
        - Tank: Front line (close to enemies)
        - Healer: Back line (away from enemies)
        - Striker: Flanking (behind enemies if possible)
        - Support: Mid-line (sightlines to allies and enemies)

        Returns:
            (x, y) grid position, or None if positioning not implemented
        """
        # Placeholder for future grid-based positioning system
        # Currently returns None as grid combat is not yet implemented
        return None

    # ===========================================================================
    # Archetype-specific decision methods
    # ===========================================================================

    def _decide_tank_action(self) -> TacticalDecision:
        """Make tactical decision for tank archetype.

        Tanks prioritize protecting allies by:
        1. Targeting enemies threatening allies
        2. Using defensive/taunt abilities
        3. Positioning between enemies and allies
        """
        # Find most threatened ally
        most_threatened = self._find_most_threatened_ally()

        if most_threatened:
            # Target the enemy threatening that ally
            threatening_enemy = self._find_most_threatening_enemy()
            if threatening_enemy:
                ability = self.select_ability(threatening_enemy.name)
                confidence = 0.8
                if self.companion.personality.bravery > 70:
                    confidence += 0.1

                return TacticalDecision(
                    action_type="ability" if ability else "attack",
                    target=threatening_enemy.name,
                    ability=ability,
                    priority=TacticalPriority.PROTECT_ALLY,
                    confidence=min(confidence, 1.0),
                    reasoning=f"Protecting {most_threatened.name} from {threatening_enemy.name}",
                    action_economy="action",
                )

        # No immediate threat - target highest threat enemy
        targets = self.evaluate_targets()
        if targets:
            target_name = targets[0][0]
            ability = self.select_ability(target_name)
            return TacticalDecision(
                action_type="ability" if ability else "attack",
                target=target_name,
                ability=ability,
                priority=TacticalPriority.PROTECT_ALLY,
                confidence=0.7,
                reasoning=f"Engaging most dangerous enemy: {target_name}",
                action_economy="action",
            )

        # No enemies - defensive stance
        return TacticalDecision(
            action_type="dodge",
            priority=TacticalPriority.SURVIVE,
            confidence=0.6,
            reasoning="No enemies in range - defensive stance",
            action_economy="action",
        )

    def _decide_healer_action(self) -> TacticalDecision:
        """Make tactical decision for healer archetype.

        Healers prioritize supporting allies by:
        1. Healing wounded allies (< 50% HP)
        2. Using cure/buff abilities
        3. Light damage when all allies healthy
        """
        # Find most wounded ally
        wounded_ally = self._find_most_wounded_ally()

        if wounded_ally and wounded_ally.hp_percentage < 0.5:
            # Heal the wounded ally
            ability = self.select_ability(wounded_ally.name)
            confidence = 0.9
            if self.companion.personality.compassion > 70:
                confidence = 0.95

            return TacticalDecision(
                action_type="ability",
                target=wounded_ally.name,
                ability=ability or "heal",
                priority=TacticalPriority.SUPPORT_PARTY,
                confidence=min(confidence, 1.0),
                reasoning=f"Healing {wounded_ally.name} ({int(wounded_ally.hp_percentage * 100)}% HP)",
                action_economy="action",
            )

        # No healing needed - support or light damage
        if self.battlefield.round_number <= 2 and self.companion.preferred_abilities:
            # Early rounds: buff allies
            if self._allies:
                strongest_ally = max(self._allies, key=lambda a: a.damage_potential)
                ability = self.select_ability(strongest_ally.name)
                if ability and ability in ["bless", "buff"]:
                    return TacticalDecision(
                        action_type="ability",
                        target=strongest_ally.name,
                        ability=ability,
                        priority=TacticalPriority.SUPPORT_PARTY,
                        confidence=0.75,
                        reasoning=f"Buffing {strongest_ally.name} for combat",
                        action_economy="action",
                    )

        # Attack mode
        targets = self.evaluate_targets()
        if targets:
            target_name = targets[0][0]
            return TacticalDecision(
                action_type="attack",
                target=target_name,
                priority=TacticalPriority.ELIMINATE_THREAT,
                confidence=0.6,
                reasoning=f"All allies healthy - attacking {target_name}",
                action_economy="action",
            )

        # Fallback
        return TacticalDecision(
            action_type="dodge",
            priority=TacticalPriority.SURVIVE,
            confidence=0.5,
            reasoning="No actions needed - defensive stance",
            action_economy="action",
        )

    def _decide_striker_action(self) -> TacticalDecision:
        """Make tactical decision for striker archetype.

        Strikers prioritize eliminating threats by:
        1. Targeting low HP enemies (easy kills)
        2. Targeting high value enemies (spellcasters, commanders)
        3. Using aggressive strike abilities
        """
        targets = self.evaluate_targets()

        if not targets:
            return TacticalDecision(
                action_type="dodge",
                priority=TacticalPriority.SURVIVE,
                confidence=0.5,
                reasoning="No targets available",
                action_economy="action",
            )

        # Select top target
        target_name = targets[0][0]
        target_combatant = self._find_combatant(target_name)

        ability = self.select_ability(target_name)
        confidence = 0.8

        # Aggression boost
        if self.companion.personality.aggression > 70:
            confidence += 0.1

        # Low caution = more confident attacks
        if self.companion.personality.caution < 30:
            confidence += 0.05

        reasoning = f"Attacking {target_name}"
        if target_combatant:
            if target_combatant.hp_percentage < 0.3:
                reasoning = f"Finishing off {target_name} ({int(target_combatant.hp_percentage * 100)}% HP)"
            elif target_combatant.value > 0.7:
                reasoning = f"Eliminating high-value target {target_name}"

        return TacticalDecision(
            action_type="ability" if ability else "attack",
            target=target_name,
            ability=ability,
            priority=TacticalPriority.ELIMINATE_THREAT,
            confidence=min(confidence, 1.0),
            reasoning=reasoning,
            action_economy="action",
        )

    def _decide_support_action(self) -> TacticalDecision:
        """Make tactical decision for support archetype.

        Support prioritizes party effectiveness by:
        1. Buffing allies in early rounds
        2. Debuffing dangerous enemies
        3. Using inspire/help actions
        """
        # Early combat: buff allies
        if self.battlefield.round_number <= 2 and self._allies:
            # Buff strongest DPS ally
            strongest_ally = max(self._allies, key=lambda a: a.damage_potential)
            ability = self.select_ability(strongest_ally.name)

            if ability and ability in ["buff", "bless", "inspire"]:
                return TacticalDecision(
                    action_type="ability",
                    target=strongest_ally.name,
                    ability=ability,
                    priority=TacticalPriority.SUPPORT_PARTY,
                    confidence=0.85,
                    reasoning=f"Buffing {strongest_ally.name} at combat start",
                    action_economy="action",
                )

        # Mid/late combat: debuff dangerous enemies or help allies
        targets = self.evaluate_targets()
        if targets:
            # Debuff the most dangerous enemy
            target_name = targets[0][0]
            ability = self.select_ability(target_name)

            if ability and ability in ["debuff"]:
                return TacticalDecision(
                    action_type="ability",
                    target=target_name,
                    ability=ability,
                    priority=TacticalPriority.CONTROL_BATTLEFIELD,
                    confidence=0.75,
                    reasoning=f"Debuffing dangerous enemy {target_name}",
                    action_economy="action",
                )

        # Help action for allies
        if self._allies:
            strongest_ally = max(self._allies, key=lambda a: a.damage_potential)
            return TacticalDecision(
                action_type="help",
                target=strongest_ally.name,
                priority=TacticalPriority.SUPPORT_PARTY,
                confidence=0.7,
                reasoning=f"Helping {strongest_ally.name} with their attack",
                action_economy="action",
            )

        # Fallback: attack
        if targets:
            return TacticalDecision(
                action_type="attack",
                target=targets[0][0],
                priority=TacticalPriority.ELIMINATE_THREAT,
                confidence=0.6,
                reasoning=f"Attacking {targets[0][0]}",
                action_economy="action",
            )

        return TacticalDecision(
            action_type="dodge",
            priority=TacticalPriority.SURVIVE,
            confidence=0.5,
            reasoning="No support actions available",
            action_economy="action",
        )

    # ===========================================================================
    # Target scoring and selection
    # ===========================================================================

    def _calculate_target_score(self, target: Combatant) -> float:
        """Calculate tactical score for a target enemy.

        Combines base threat, HP percentage, archetype preferences, and
        personality modifiers to produce a target priority score.

        Args:
            target: Enemy combatant to score

        Returns:
            Score value (higher = higher priority)
        """
        score = 0.0

        # Base threat from damage potential
        score += target.damage_potential * 0.3

        # Prefer lower HP targets (easier to eliminate)
        score += (1.0 - target.hp_percentage) * 0.2

        # Archetype-specific scoring
        if self.companion.archetype == CompanionArchetype.TANK:
            # Tanks prioritize threats to allies
            score += target.threat_to_allies * 0.4

        elif self.companion.archetype == CompanionArchetype.STRIKER:
            # Strikers prefer low HP (execute) and high value targets
            score += (1.0 - target.hp_percentage) * 0.3
            score += target.value * 0.3

        elif self.companion.archetype == CompanionArchetype.HEALER:
            # Healers prefer moderate threats (not too dangerous)
            score += target.damage_potential * 0.2
            score += target.value * 0.2

        elif self.companion.archetype == CompanionArchetype.SUPPORT:
            # Support prefers high-value targets to debuff
            score += target.value * 0.4
            score += target.damage_potential * 0.2

        # Personality modifiers
        if self.companion.personality.aggression > 70:
            # High aggression = prefer more dangerous targets
            score *= 1.2
        elif self.companion.personality.aggression < 30:
            # Low aggression = prefer safer targets
            score *= 0.8

        if self.companion.personality.caution > 70:
            # High caution = prefer safer targets (lower threat)
            score -= target.threat_to_allies * 0.2
        elif self.companion.personality.caution < 30:
            # Low caution = willing to engage dangerous targets
            score += target.threat_to_allies * 0.1

        # Preferred/avoided target modifiers
        if target.name in self.companion.preferred_targets:
            score *= 1.5
        if target.name in self.companion.avoided_targets:
            score *= 0.3

        return max(score, 0.0)  # Ensure non-negative

    # ===========================================================================
    # Ally assessment helpers
    # ===========================================================================

    def _find_most_wounded_ally(self) -> Combatant | None:
        """Find the ally with the lowest HP percentage.

        Returns:
            Most wounded ally, or None if no allies
        """
        if not self._allies:
            return None
        return min(self._allies, key=lambda a: a.hp_percentage)

    def _find_most_threatened_ally(self) -> Combatant | None:
        """Find the ally facing the most threat.

        Currently uses lowest HP as proxy for threat. Future versions
        may consider enemy proximity and targeting patterns.

        Returns:
            Most threatened ally, or None if no allies
        """
        # Placeholder: use most wounded as proxy for most threatened
        return self._find_most_wounded_ally()

    def _find_most_threatening_enemy(self) -> Combatant | None:
        """Find the enemy posing the greatest threat to allies.

        Returns:
            Most threatening enemy, or None if no enemies
        """
        if not self._enemies:
            return None
        return max(self._enemies, key=lambda e: e.threat_to_allies)

    def _find_combatant(self, name: str) -> Combatant | None:
        """Find a combatant by name.

        Args:
            name: Combatant name to search for

        Returns:
            Combatant if found, None otherwise
        """
        for combatant in self.battlefield.combatants:
            if combatant.name == name:
                return combatant
        return None


__all__ = [
    "TacticalPriority",
    "Combatant",
    "TacticalDecision",
    "BattlefieldState",
    "TacticsEngine",
]
