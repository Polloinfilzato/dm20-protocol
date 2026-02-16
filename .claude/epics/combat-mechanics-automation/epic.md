---
name: combat-mechanics-automation
status: in_progress
created: 2026-02-16T23:28:02Z
progress: 0%
prd: .claude/prds/combat-mechanics-automation.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/132
---

# Epic: Combat Mechanics Automation

## Overview

Bring Foundry VTT-level mechanical precision to dm20-protocol's text-based combat. This epic adds an Active Effects engine, concentration enforcement, a single-call combat resolution pipeline, an encounter builder, positional AoE targeting, and optional ASCII tactical maps. All features are additive — no breaking changes to existing Character model or combat tools.

## Architecture Decisions

### 1. New `combat/` package
All combat mechanics live in a new `src/dm20_protocol/combat/` package, keeping `models.py` and `main.py` changes minimal. This mirrors the existing `claudmaster/` and `library/` package pattern.

```
src/dm20_protocol/combat/
├── __init__.py
├── effects.py          # ActiveEffect model, EffectsEngine, SRD conditions
├── concentration.py    # Concentration tracker
├── pipeline.py         # CombatAction single-call resolver
├── encounter_builder.py # XP budget + monster selection
├── positioning.py      # Position model, AoE shapes, target calculation
└── ascii_map.py        # Grid model + ASCII renderer
```

### 2. ActiveEffect as first-class model in `models.py`
`ActiveEffect` is a Pydantic model stored on the Character (new field: `active_effects: list[ActiveEffect]`). The existing `conditions: list[str]` field is preserved for backward compatibility but SRD conditions (blinded, prone, etc.) are now also represented as ActiveEffects with predefined mechanical modifiers.

### 3. EffectsEngine as stateless calculator
`EffectsEngine.effective_stat(character, stat_name) -> int` computes base stat + all active effect modifiers. This is called by the combat pipeline and can be used anywhere. No caching needed — effects lists are small (typically < 10).

### 4. Combat Pipeline returns structured data
`CombatAction` resolves mechanics and returns a `CombatResult` dataclass. The Narrator agent receives this structured data and generates flavor text. The pipeline never generates narrative — clean separation of mechanics and storytelling.

### 5. Positions are optional
The `Position(x, y)` model on combat participants is nullable. When positions are absent, AoE falls back to relative proximity tags (`adjacent`, `nearby`, `far`) estimated by the AI DM. This means positioning and ASCII maps are fully opt-in — combat works fine without them.

### 6. Leverage existing infrastructure
- `roll_dice` tool (already exists) is called internally by the pipeline
- `turn_manager.py` round/turn events are used to tick down effect durations
- `combat_narrator.py` damage severity classification feeds into narrative generation
- `search_rules` queries monster stat blocks for encounter builder
- Archivist `Condition` model is superseded by `ActiveEffect` (but kept for backward compat)

## Technical Approach

### Data Models (models.py extensions)

```python
# New fields on Character:
active_effects: list[ActiveEffect] = Field(default_factory=list)
concentration: ConcentrationState | None = None
position: Position | None = None  # Only set during tactical combat

# New models:
class ActiveEffect(BaseModel):
    id: str
    name: str               # "Bless", "Prone", "Shield"
    source: str             # "spell:bless", "condition:prone", "item:ring_of_protection"
    modifiers: list[Modifier]  # [{stat: "attack_roll", value: "1d4"}, ...]
    duration_type: str      # "rounds", "minutes", "concentration", "permanent"
    duration_remaining: int | None  # Rounds/minutes left (None = permanent)
    grants_advantage: list[str]    # ["dexterity_save"]
    grants_disadvantage: list[str] # ["attack_roll"]
    immunities: list[str]          # ["frightened"]
    stackable: bool = False

class ConcentrationState(BaseModel):
    spell_name: str
    effect_ids: list[str]   # ActiveEffect IDs to remove on break
    started_round: int

class Position(BaseModel):
    x: int
    y: int
```

### Combat Pipeline (pipeline.py)

Single entry point: `resolve_attack(attacker, target, weapon/spell, storage)` → `CombatResult`

Steps:
1. Gather attacker stats + active effect modifiers (EffectsEngine)
2. Determine advantage/disadvantage from conditions
3. Roll attack (using existing `roll_dice` internally)
4. Compare vs effective AC (target base AC + effect modifiers)
5. On hit: roll damage + modifiers, apply resistance/vulnerability
6. Apply damage to target HP
7. If target is concentrating → trigger CON save → potentially break concentration
8. Return `CombatResult` with all details

### Encounter Builder (encounter_builder.py)

Uses 5e SRD XP threshold tables (hardcoded, they're small) + `search_rules(category="monster")` to find candidates. Outputs: XP budget, 3 suggested monster groups, difficulty rating.

### ASCII Maps (ascii_map.py)

Grid stored as 2D array of `Cell(terrain, occupant)`. Renderer outputs monospaced text with legend. Movement validation checks speed + difficult terrain. Opportunity attack detection on leaving threatened squares.

## Implementation Strategy

### Development Phases

**Phase 1 (P0 — Foundation):** Active Effects + Concentration
- Tasks 1-2: ActiveEffect model, EffectsEngine, SRD conditions, concentration tracking
- These are prerequisites for everything else

**Phase 2 (P0-P1 — Core Value):** Combat Pipeline + Encounter Builder
- Tasks 3-4: Single-call combat resolution, encounter balancing
- This is where the user experience improves dramatically

**Phase 3 (P1-P2 — Tactical Layer):** Positioning + AoE + ASCII Maps
- Tasks 5-6: Position tracking, AoE target calculation, ASCII renderer
- Optional enhancement for players who want tactical depth

**Phase 4 (Integration):** MCP Tools + Agent Wiring
- Task 7: Register new tools, connect to Arbiter/Narrator agents

### Risk Mitigation
- ActiveEffect model uses `default_factory=list` so existing campaigns load without migration
- `conditions: list[str]` is preserved alongside `active_effects` — legacy code still works
- Each phase is independently testable and shippable
- ASCII maps are fully optional (combat works without them)

### Testing Approach
- Unit tests for EffectsEngine (modifier calculation, stacking, expiration)
- Unit tests for combat pipeline (attack flow, crits, saves, resistance)
- Unit tests for encounter builder (XP budget, difficulty classification)
- Integration tests for full combat round (start → actions → turn advance → effects expire)
- Tests live in `tests/test_combat_*.py`

## Task Breakdown Preview

- [ ] Task 1: Active Effects System — Model, EffectsEngine, 14 SRD conditions, duration tracking, persistence
- [ ] Task 2: Concentration Tracking — ConcentrationState, single-spell enforcement, CON save on damage, effect cleanup
- [ ] Task 3: Combat Action Pipeline — Single-call attack/spell resolution with modifiers, advantage, crits, resistance
- [ ] Task 4: Encounter Builder — XP thresholds, monster selection from rulebooks, difficulty multipliers
- [ ] Task 5: Positioning & AoE Engine — Position model, AoE shapes (sphere/cube/cone/line), target calculation, relative fallback
- [ ] Task 6: ASCII Tactical Maps — Grid model, terrain types, ASCII renderer, movement validation, opportunity attacks
- [ ] Task 7: MCP Tools & Agent Integration — `combat_action`, `build_encounter`, `show_map` tools + Arbiter/Narrator wiring

## Dependencies

### Task Dependencies
```
Task 1 (Active Effects) ──► Task 2 (Concentration)
                         ──► Task 3 (Pipeline)
Task 4 (Encounter Builder)    [independent]
Task 5 (Positioning/AoE)  ──► Task 6 (ASCII Maps)
Task 7 (Tools/Integration) ◄── Tasks 3, 4, 5
```

### Parallelism Opportunities
- **Stream A:** Tasks 1 → 2 → 3 (effects chain)
- **Stream B:** Task 4 (encounter builder, fully independent)
- **Stream C:** Tasks 5 → 6 (positioning chain)
- **Task 7** runs after Streams A, B, C converge

### Internal Codebase Dependencies
- `models.py` — Extended with ActiveEffect, ConcentrationState, Position (additive)
- `storage.py` — No changes needed (Pydantic serialization handles new fields)
- `main.py` — 3 new MCP tools registered
- `claudmaster/turn_manager.py` — Hook for effect duration tick-down
- `claudmaster/agents/arbiter.py` — Uses pipeline for NPC attacks
- `claudmaster/combat_narrator.py` — Receives CombatResult for narration

### External Dependencies
- None (pure Python, no new packages)

## Success Criteria (Technical)

| Criteria | Target |
|----------|--------|
| Combat action resolution (excluding LLM) | < 2 seconds |
| ASCII map render (30x30) | < 500ms |
| All 14 SRD conditions defined with mechanics | 100% |
| Existing campaigns load without migration | Zero breakage |
| Test coverage for combat/ package | > 90% |
| Encounter builder suggestion time (50 monsters) | < 1 second |

## Estimated Effort

| Task | Size | Estimate |
|------|------|----------|
| 1. Active Effects System | L | 8-10h |
| 2. Concentration Tracking | S | 3-4h |
| 3. Combat Action Pipeline | L | 8-10h |
| 4. Encounter Builder | M | 5-6h |
| 5. Positioning & AoE | M | 5-7h |
| 6. ASCII Tactical Maps | M | 5-7h |
| 7. MCP Tools & Integration | M | 5-6h |
| **Total** | | **39-50h** |

**Critical path:** Tasks 1 → 3 → 7 (Active Effects → Pipeline → Tools)

## Tasks Created

- [ ] 132.md - Active Effects System (parallel: true) — L, 8-10h
- [ ] 133.md - Concentration Tracking (depends: 132) — S, 3-4h
- [ ] 134.md - Combat Action Pipeline (depends: 132) — L, 8-10h
- [ ] 135.md - Encounter Builder (parallel: true) — M, 5-6h
- [ ] 136.md - Positioning & AoE Engine (parallel: true) — M, 5-7h
- [ ] 137.md - ASCII Tactical Maps (depends: 136) — M, 5-7h
- [ ] 138.md - MCP Tools & Agent Integration (depends: 134, 135, 136) — M, 5-6h

Total tasks: 7
Parallel tasks: 3 (#132, #135, #136 can run simultaneously)
Sequential tasks: 4 (#133→after #132, #134→after #132, #137→after #136, #138→after all)
Estimated total effort: 39-50h
