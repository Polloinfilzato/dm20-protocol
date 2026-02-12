---
name: bilingual-terminology-resolver
status: completed
created: 2026-02-12T16:41:22Z
progress: 100%
updated: 2026-02-12T17:56:55Z
completed: 2026-02-12T17:56:55Z
prd: .claude/prds/bilingual-terminology-resolver.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/91
---

# Epic: Bilingual Terminology Resolver

## Overview

Build a bilingual Italian ↔ English terminology resolver for dm20-protocol that handles D&D code-switching — the natural tendency of Italian players to freely mix Italian and English terms (e.g., "Lancio Fireball", "check di Furtività", "vado di soppiatto"). The system resolves any variant to the canonical English game entity via O(1) dict lookup, and tracks the player's per-category language preferences so the AI DM can mirror their style.

## Architecture Decisions

### 1. No OutputAdapter — LLM handles output adaptation

The PRD proposes a regex-based `OutputAdapter` to substitute terms in DM responses. This is fragile (Italian gender agreement, verb conjugation) and unnecessary. Instead, the `StyleTracker`'s preferences are injected into the Claudmaster narrator agent's prompt as context hints (e.g., "Player prefers English for spells, Italian for skills"). The LLM naturally produces grammatically correct output with the right terminology.

**Result:** Removed 1 component (OutputAdapter), simplified architecture.

### 2. No separate RulebookTermExtractor — TermResolver does it

The TermResolver directly pulls content names from `RulebookManager` when sources are loaded. No need for a separate extractor class — it's a single method `index_from_rulebook()` on the resolver.

**Result:** Removed 1 class, merged into TermResolver.

### 3. No separate StaticDictionary — TermResolver loads YAML directly

The YAML loading logic is trivial (parse file, iterate entries, build lookup dict). No separate class needed.

**Result:** Removed 1 class, merged into TermResolver.

### 4. unicodedata for accent normalization

Use Python's `unicodedata.normalize('NFD', text)` + strip combining marks for accent-insensitive matching. No external dependencies. Handles "furtivita" = "furtività" transparently.

### 5. YAML for dictionary data

YAML is human-readable and diff-friendly. The dictionary file is meant to be curated manually, so readability matters more than performance. PyYAML is already a dependency.

## Technical Approach

### New Package Structure

```
src/dm20_protocol/terminology/
├── __init__.py        # Public API exports
├── models.py          # TermEntry Pydantic model
├── resolver.py        # TermResolver: YAML loading + rulebook indexing + O(1) lookup
├── style.py           # StyleTracker: per-category observation + preferences dict
└── data/
    └── core_terms.yaml  # ~500 curated IT↔EN term pairs
```

### TermEntry Model

```python
class TermEntry(BaseModel):
    canonical: str       # Canonical English key (e.g., "fireball")
    category: str        # spell, skill, condition, ability, combat, item, class, race, general
    en: str              # English display name (e.g., "Fireball")
    it_primary: str      # Primary Italian name (e.g., "Palla di Fuoco")
    it_variants: list[str]  # All Italian variants including colloquial
```

### TermResolver

```python
class TermResolver:
    _lookup: dict[str, TermEntry]   # normalized_variant → TermEntry

    def load_yaml(self, path: Path) -> None           # Load curated dictionary
    def index_from_rulebook(self, manager) -> None     # Auto-index from loaded sources
    def resolve(self, text: str) -> TermEntry | None   # O(1) lookup
    def resolve_in_text(self, text: str) -> list[tuple[str, TermEntry]]  # Find all terms in text
    def _normalize(self, text: str) -> str             # lowercase + strip accents + strip whitespace
```

### StyleTracker

```python
class StyleTracker:
    _observations: dict[str, dict[str, int]]  # category → {"en": count, "it": count}

    def observe(self, term: TermEntry, used_variant: str) -> None
    def preferred_language(self, category: str) -> str  # "en" or "it"
    def preferences_summary(self) -> dict[str, str]     # For injection into DM prompt
    def reset(self) -> None
```

### Integration with Claudmaster

The `player_action` flow becomes:
1. Player sends text
2. TermResolver scans text → finds known terms + their used variants
3. StyleTracker observes the variants used
4. Action is processed normally (game engine uses English canonical keys)
5. Before DM agent generates response, `StyleTracker.preferences_summary()` is injected into the narrator agent's prompt context
6. LLM generates response using the player's preferred terminology naturally

Integration point: `claudmaster/tools/action_tools.py:player_action()` (lines ~350-400) and `claudmaster/agents/narrator.py`.

### Dictionary Coverage Plan

| Category | Count | Key Examples |
|----------|-------|-------------|
| Skills | 18 | Stealth/Furtività, Perception/Percezione |
| Abilities | 6 | Strength/Forza, Dexterity/Destrezza |
| Conditions | 15 | Poisoned/Avvelenato, Frightened/Spaventato |
| Combat | 30 | Initiative/Iniziativa, Saving Throw/Tiro Salvezza |
| Spell schools | 8 | Evocation/Evocazione |
| Core spells | 100 | Fireball/Palla di Fuoco, Cure Wounds/Cura Ferite |
| Core monsters | 100 | Dragon/Drago, Goblin/Goblin |
| Classes | 12 | Wizard/Mago, Rogue/Ladro |
| Races | 9 | Elf/Elfo, Dwarf/Nano |
| Items | 20 | Longsword/Spada Lunga, Shield/Scudo |
| General | 180+ | Adventure/Avventura, Dungeon/Dungeon |
| **Total** | **~500** | |

## Implementation Strategy

### Single phase, 5 sequential tasks

Tasks are sequential because each builds on the previous one. However, the dictionary curation (Task 2) can be done in parallel with Task 1 since it's pure data.

### Testing approach
- Unit tests: Each component tested independently with mock data
- Integration tests: Full flow from input text → resolved terms → style tracking
- E2E tests: player_action with bilingual input → DM response with correct terminology
- All tests in `tests/` directory following existing patterns

## Task Breakdown Preview

- [ ] Task 1: TermEntry model + TermResolver (YAML loading, normalization, O(1) lookup) + unit tests
- [ ] Task 2: Core terms dictionary (core_terms.yaml — ~500 curated IT↔EN pairs)
- [ ] Task 3: StyleTracker (per-category observation, preferences summary) + unit tests
- [ ] Task 4: Rulebook auto-indexing (TermResolver.index_from_rulebook + RulebookManager integration) + tests
- [ ] Task 5: Claudmaster integration (wire into player_action pipeline, inject style context into narrator) + E2E tests

## Dependencies

### Internal
- `RulebookManager` — source of auto-extractable term names (exists, read-only access)
- `claudmaster/tools/action_tools.py` — integration point for player_action
- `claudmaster/agents/narrator.py` — integration point for style-aware output
- PyYAML — already a dependency

### External
- None — fully offline, no external APIs

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| Static dictionary size | ≥ 500 curated term pairs |
| Term resolution accuracy | > 99% for known terms |
| Lookup latency | < 1ms per term (O(1) dict) |
| Accent-insensitive matching | Works for all accented Italian chars |
| Style tracking | Correct after 5+ observations per category |
| Unknown terms | Pass through unchanged (no errors) |
| Test coverage | > 80% for new code |
| Existing tests | Zero regressions |

## Estimated Effort

| Task | Size | Hours |
|------|------|-------|
| TermEntry + TermResolver | M | 3-4 |
| Core terms dictionary | M | 4-6 |
| StyleTracker | S | 2-3 |
| Rulebook auto-indexing | S | 2-3 |
| Claudmaster integration | M | 3-4 |
| **Total** | **M** | **14-20** |

**Parallelism:** Task 2 (data curation) can run in parallel with Task 1 (code). Tasks 3-5 are sequential.

## Tasks Created

- [ ] 89.md - TermEntry Model + TermResolver with YAML Loading and O(1) Lookup (parallel: true)
- [ ] 90.md - Core Terms Dictionary — ~500 Curated IT/EN Term Pairs (parallel: true)
- [ ] 91.md - StyleTracker — Per-Category Language Preference Tracking (parallel: false, depends: #89)
- [ ] 92.md - Rulebook Auto-Indexing — TermResolver Integration with RulebookManager (parallel: false, depends: #89, #90)
- [ ] 93.md - Claudmaster Integration — Wire Terminology into Player Action Pipeline (parallel: false, depends: #89, #90, #91, #92)

Total tasks: 5
Parallel tasks: 2 (#89 and #90 can run in parallel)
Sequential tasks: 3 (#91, #92, #93 are sequential)
Estimated total effort: 14-20 hours
