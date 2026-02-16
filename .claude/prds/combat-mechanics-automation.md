---
name: combat-mechanics-automation
description: Active Effects, Area Templates, Concentration Tracking, Combat Automation, Encounter Builder, and ASCII Tactical Maps to bring Foundry VTT-level mechanical precision to dm20-protocol's text-based combat
status: backlog
created: 2026-02-17T12:00:00Z
---

# PRD: Combat Mechanics Automation

## Executive Summary

dm20-protocol's combat system currently handles initiative tracking, turn order, and basic HP management — but all mechanical resolution (hit/miss, damage application, condition effects, area targeting) relies entirely on the AI DM's judgment or manual tool calls. This PRD brings **Foundry VTT-level mechanical automation** to the text-based combat experience.

**Key deliverables:**

1. **Active Effects System** — Structured buff/debuff engine that automatically modifies character stats, saves, and rolls based on active spells and conditions
2. **Area-of-Effect Templates** — Automatic target calculation for AoE spells/abilities using relative positioning (no graphical map required)
3. **Concentration Tracking** — Automatic concentration enforcement: CON saves on damage, single-concentration limit, effect cleanup on break
4. **Combat Automation Pipeline** — End-to-end attack→hit/miss→damage→apply→trigger effects flow as a single orchestrated action
5. **Encounter Builder** — CR-based encounter balancing tool with difficulty calculation, monster selection, and XP budget management
6. **ASCII Tactical Maps** — Text-based spatial representation with token positions, movement tracking, and range/AoE visualization

**Value proposition:** The Arbiter agent becomes mechanically precise rather than approximate. Combat encounters feel fair, consistent, and rules-accurate — while the Narrator agent can focus purely on storytelling without worrying about math.

## Problem Statement

### Current State

```
Combat resolution today:
├── Initiative tracking           ✅ Works (ordered list in GameState)
├── Turn advancement              ✅ Works (next_turn skips dead)
├── HP management                 ✅ Works (manual update_character)
├── Dice rolling                  ✅ Works (roll_dice with advantage)
├── Conditions                    ⚠️  String list only — no mechanical effects
├── Buff/debuff application       ❌ Manual — AI must remember and apply
├── Concentration                 ❌ Not tracked at all
├── AoE targeting                 ❌ AI guesses who's in range
├── Attack→damage pipeline        ❌ Multiple manual tool calls per attack
├── Encounter balancing           ❌ Only calculate_experience (post-combat)
├── Spatial positioning           ❌ No position data exists
└── Condition expiration          ❌ Never auto-removed
```

### Pain Points

1. **Inconsistent rule application** — The AI DM might forget that a character has Bless (+1d4 to attacks/saves) or that Shield spell gives +5 AC. Active effects solve this by making buffs/debuffs structural.

2. **Combat is slow** — Each attack requires 3-4 separate tool calls (roll attack, check AC, roll damage, update HP). A pipeline reduces this to one action.

3. **Concentration is honor-system** — Casters can stack concentration spells because nothing enforces the single-concentration rule or triggers CON saves on damage.

4. **AoE is narrative guesswork** — "I cast Fireball in the middle of the goblins" has no deterministic answer for which goblins are hit. Positioning data makes this calculable.

5. **Encounter balance is reactive** — DMs can only calculate XP after combat, not design balanced encounters before they happen.

### Target User

Solo player using Claudmaster AI DM who wants:
- Fair, rules-accurate combat that doesn't feel arbitrary
- Faster combat resolution (fewer tool calls per round)
- Trust that buffs/debuffs are being applied correctly
- Tactical positioning that matters in a text-based game

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  Combat Automation                    │
│                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ Active       │  │ Concentration│  │ Encounter  │ │
│  │ Effects      │◄─┤ Tracker      │  │ Builder    │ │
│  │ Engine       │  └──────────────┘  └────────────┘ │
│  └──────┬───────┘                                    │
│         │ modifies                                    │
│  ┌──────▼───────┐  ┌──────────────┐  ┌────────────┐ │
│  │ Combat       │  │ AoE Template │  │ ASCII Map  │ │
│  │ Pipeline     │◄─┤ Engine       │◄─┤ System     │ │
│  └──────┬───────┘  └──────────────┘  └────────────┘ │
│         │ updates                                     │
│  ┌──────▼───────┐                                    │
│  │ Character    │  (existing models.py)              │
│  │ Model        │                                    │
│  └──────────────┘                                    │
└─────────────────────────────────────────────────────┘

Data flow for a single attack:
  Player: "I attack the goblin with my longsword"
  │
  ├─ 1. Pipeline resolves attacker stats + active effects
  │     (STR mod, proficiency, Bless +1d4, etc.)
  │
  ├─ 2. Roll attack (1d20 + modifiers from effects)
  │     Check advantage/disadvantage from conditions
  │
  ├─ 3. Compare vs target AC (modified by effects: Shield, etc.)
  │
  ├─ 4. On hit: roll damage + modifiers (Hunter's Mark, etc.)
  │     Apply resistance/vulnerability from conditions
  │
  ├─ 5. Apply damage to target HP
  │     Trigger concentration check if target is concentrating
  │
  └─ 6. Return structured result for Narrator to describe
```

## User Stories

### US-1: Active Effects System
**As a** player with a buffed character,
**I want** my Bless spell to automatically add +1d4 to my attack rolls and saving throws,
**So that** I don't have to remind the DM every turn.

**Acceptance Criteria:**
- [ ] Effects can modify: ability scores, AC, attack rolls, damage rolls, saving throws, skill checks, speed, HP max
- [ ] Effects have duration (rounds, minutes, concentration, until-dispelled)
- [ ] Effects auto-expire when their duration ends
- [ ] Effects stack according to 5e rules (same-name effects don't stack)
- [ ] SRD conditions (blinded, charmed, frightened, etc.) have predefined mechanical effects
- [ ] Custom effects can be created for non-SRD spells/abilities
- [ ] `get_character` shows active effects and their remaining duration

### US-2: Area-of-Effect Templates
**As a** spellcaster targeting a group,
**I want** the system to automatically determine which creatures are in my Fireball's radius,
**So that** AoE targeting is fair and deterministic.

**Acceptance Criteria:**
- [ ] Support standard 5e AoE shapes: sphere, cube, cone, line, cylinder
- [ ] Calculate affected targets based on position data (from ASCII map or relative positioning)
- [ ] Handle partial overlap / edge cases using 5e rules (center-of-square method)
- [ ] Report which targets are affected before applying damage (player can confirm)
- [ ] Work without ASCII maps by using relative position estimates ("near", "far", "adjacent")

### US-3: Concentration Tracking
**As a** spellcaster maintaining concentration,
**I want** the system to automatically enforce concentration rules,
**So that** I can't accidentally stack concentration spells.

**Acceptance Criteria:**
- [ ] Track which character is concentrating on which spell
- [ ] Prevent casting a new concentration spell while already concentrating (warn player)
- [ ] Auto-trigger CON save when concentrating character takes damage (DC = max(10, damage/2))
- [ ] On failed save: end concentration, remove the spell's active effects
- [ ] On successful save: concentration continues
- [ ] Concentration ends on incapacitation or death
- [ ] `get_character` shows current concentration spell and duration remaining

### US-4: Combat Automation Pipeline
**As a** player in combat,
**I want** to say "I attack the goblin" and have the full attack resolved automatically,
**So that** combat flows quickly without multiple manual tool calls.

**Acceptance Criteria:**
- [ ] Single `combat_action` tool that resolves: attack roll → AC check → damage roll → HP update → effect triggers
- [ ] Automatically applies all relevant modifiers from active effects
- [ ] Handles advantage/disadvantage from conditions (prone, restrained, etc.)
- [ ] Supports melee attacks, ranged attacks, spell attacks, and saving throw spells
- [ ] Returns structured result: {hit: bool, attack_roll: int, damage: int, effects_triggered: [...]}
- [ ] Arbiter agent can use this pipeline for NPC/monster attacks
- [ ] Critical hits (nat 20) double damage dice automatically
- [ ] Fumbles (nat 1) auto-miss regardless of modifiers

### US-5: Encounter Builder
**As a** DM (or AI DM),
**I want** to build balanced encounters by CR and party composition,
**So that** combat difficulty matches the intended challenge level.

**Acceptance Criteria:**
- [ ] Input: party size, party level, desired difficulty (easy/medium/hard/deadly)
- [ ] Output: XP budget, suggested monster combinations from loaded rulebooks
- [ ] Use 5e encounter building rules (XP thresholds per level, multipliers for monster count)
- [ ] Filter monsters by environment, type, CR range
- [ ] Suggest multiple alternative compositions
- [ ] `build_encounter` MCP tool available for manual use
- [ ] Arbiter agent uses encounter builder for random encounter generation

### US-6: ASCII Tactical Maps
**As a** player in tactical combat,
**I want** a text-based map showing positions of all combatants,
**So that** I can make informed tactical decisions about movement and targeting.

**Acceptance Criteria:**
- [ ] Grid-based coordinate system (e.g., 20x20, configurable)
- [ ] Token representation: `P1`, `P2` for players; `G1`, `G2` for goblins; etc.
- [ ] Terrain features: walls (`#`), doors (`D`), difficult terrain (`~`), obstacles (`X`)
- [ ] Display range circles for spells/abilities when requested
- [ ] Movement tracking: enforce speed limits per turn
- [ ] Opportunity attack detection when moving out of melee range
- [ ] `show_map` tool that renders current tactical map
- [ ] Map auto-generated from location description or manually defined
- [ ] Legend explaining all symbols included in output

## Functional Requirements

| ID | Requirement | Priority | Complexity |
|----|-------------|----------|------------|
| FR-1 | ActiveEffect Pydantic model with modifiers, duration, source, stacking rules | P0 | M |
| FR-2 | EffectsEngine class that calculates effective stats from base + active effects | P0 | L |
| FR-3 | SRD condition definitions (14 conditions with mechanical effects) | P0 | M |
| FR-4 | Effect duration tick-down on turn/round advancement | P0 | M |
| FR-5 | Concentration state per character (spell reference, start time) | P0 | S |
| FR-6 | CON save trigger on damage to concentrating character | P0 | M |
| FR-7 | CombatAction pipeline: single-call attack resolution | P1 | L |
| FR-8 | AoE shape definitions (sphere, cube, cone, line, cylinder) | P1 | M |
| FR-9 | Position model for combat participants (x, y coordinates) | P1 | M |
| FR-10 | AoE target calculation from positions + shape | P1 | L |
| FR-11 | EncounterBuilder with XP budget and monster selection | P1 | M |
| FR-12 | XP threshold tables per level (from SRD) | P1 | S |
| FR-13 | Monster count multiplier for encounter difficulty | P1 | S |
| FR-14 | ASCII map renderer from grid + tokens + terrain | P2 | L |
| FR-15 | Movement validation (speed limits, difficult terrain, opportunity attacks) | P2 | L |
| FR-16 | Saving throw spell resolution (target rolls save, half damage on success) | P1 | M |
| FR-17 | Resistance/vulnerability/immunity damage modification | P1 | M |
| FR-18 | `combat_action`, `show_map`, `build_encounter` MCP tools | P0 | M |
| FR-19 | Integration with Arbiter agent for NPC action resolution | P1 | M |
| FR-20 | Effect persistence across sessions (save/load with campaign) | P0 | S |

## Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | Combat action resolution time | < 2 seconds (excluding LLM calls) |
| NFR-2 | ASCII map rendering time | < 500ms for 30x30 grid |
| NFR-3 | Active effects calculation | O(n) where n = number of active effects |
| NFR-4 | No breaking changes to existing Character model | Additive fields only |
| NFR-5 | All 14 SRD conditions mechanically defined | 100% coverage |
| NFR-6 | Encounter builder suggestions | < 1 second for up to 50 candidate monsters |
| NFR-7 | Test coverage for combat pipeline | > 90% line coverage |
| NFR-8 | Backward compatibility | Campaigns without effects data load normally |

## Dependencies

### Internal Dependencies
- `models.py` — Character, GameState, CombatEncounter models (will be extended)
- `storage.py` — DnDStorage for persistence (active effects stored per character)
- `main.py` — New MCP tools registration
- `claudmaster/agents/arbiter.py` — Integration for NPC combat automation
- `claudmaster/combat_narrator.py` — Receives structured combat results for narration
- `claudmaster/turn_manager.py` — Effect duration tick-down on turn/round events

### External Dependencies
- None (pure Python, no new packages)

## Implementation Order

### Phase 1: Active Effects Foundation (P0)
1. `ActiveEffect` model and `EffectsEngine` class
2. SRD condition definitions (14 conditions)
3. Effect application to character stat calculations
4. Effect duration tracking and auto-expiration
5. Persistence in campaign storage

### Phase 2: Concentration & Combat Pipeline (P0-P1)
6. Concentration tracking model and enforcement
7. CON save trigger on damage
8. `CombatAction` pipeline (attack resolution)
9. Saving throw spell resolution
10. Resistance/vulnerability/immunity handling

### Phase 3: Encounter Building (P1)
11. XP threshold tables and difficulty calculation
12. Monster selection algorithm
13. `build_encounter` MCP tool
14. Integration with Arbiter for random encounters

### Phase 4: Positioning & AoE (P1-P2)
15. Position model for combat participants
16. AoE shape definitions and target calculation
17. Relative positioning fallback (without full grid)

### Phase 5: ASCII Maps (P2)
18. Grid model with terrain features
19. ASCII renderer
20. Movement validation and opportunity attacks
21. `show_map` MCP tool

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Active effects add complexity to every stat check | High | EffectsEngine as a clean abstraction layer; cache computed stats |
| ASCII maps may feel clunky in text | Medium | Make maps optional; relative positioning as lightweight alternative |
| Combat automation may feel "robotic" | Medium | Pipeline returns structured data; Narrator agent adds flavor text |
| SRD conditions don't cover all spells | Low | Custom effect creation API for non-SRD content |
| Position tracking adds overhead to every combat | Medium | Positions are optional; system degrades gracefully to narrative-only |
