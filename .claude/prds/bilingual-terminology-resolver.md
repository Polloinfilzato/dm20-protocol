---
name: bilingual-terminology-resolver
description: Bilingual D&D terminology resolver with code-switching support and style mirroring for Italian/English gameplay
status: backlog
created: 2026-02-12T16:08:15Z
---

# PRD: Bilingual Terminology Resolver

## Executive Summary

Build a bilingual terminology resolution system that enables seamless Italian ↔ English D&D gameplay in dm20-protocol. The system handles **code-switching** — the natural tendency of Italian players to mix Italian and English D&D terms mid-sentence (e.g., "Lancio *Fireball*" or "Vado in modalità *stealth*"). It resolves both variants to the same canonical game entity and adapts DM output to mirror the player's preferred language per term.

**Key deliverables:**

1. **Static bilingual dictionary** — Curated mapping of ~500 core D&D terms (spells, conditions, skills, abilities, item types, combat terms) with Italian translations, synonyms, and colloquial variants
2. **Auto-lookup from rulebooks** — Automatic extraction of term pairs from loaded rulebook content (spell names, monster names, class/race names) so the dictionary grows with available sources
3. **Input resolver** — O(1) lookup that normalizes any term variant (IT or EN, formal or colloquial) to a canonical English key usable by the game engine
4. **Style tracker** — Per-session observer that records which language variant the player uses for each term category, enabling the DM to mirror the player's natural style
5. **Output adapter** — Transforms DM output terminology to match the player's observed style preferences (e.g., if player says "Fireball" → DM says "Fireball"; if player says "Palla di Fuoco" → DM says "Palla di Fuoco")

**Value proposition:** Italian players can speak naturally — mixing languages as they do at real D&D tables — and the AI DM understands everything and responds in the player's own style, creating a fluid, immersive experience.

## Problem Statement

### Current State

dm20-protocol's game engine, rulebook data, and internal models are all in English. When an Italian player interacts with the AI DM:

- The system doesn't understand "Palla di Fuoco" as equivalent to "Fireball"
- The system doesn't recognize "furtività" as the Stealth skill
- The AI DM responds with English terminology regardless of how the player speaks
- There's no awareness that "Lancio Fireball" and "Lancio Palla di Fuoco" should trigger the same action

```
Current experience:
  Player: "Lancio Palla di Fuoco sui goblin"
  System: ❌ Cannot resolve "Palla di Fuoco" to any known spell

  Player: "Faccio un check di Furtività"
  System: ❌ "Furtività" not recognized as a skill

Desired experience:
  Player: "Lancio Palla di Fuoco sui goblin"
  System: ✅ Resolves to Fireball → full spell mechanics applied
  DM: "La tua Palla di Fuoco esplode tra i goblin..."

  Player: "I cast Fireball on the goblins"
  System: ✅ Resolves to Fireball → same mechanics
  DM: "Your Fireball explodes among the goblins..."
```

### The Code-Switching Problem

Italian D&D players don't speak pure Italian or pure English — they code-switch constantly based on habit, context, and personal preference:

| Pattern | Example | What Happens |
|---------|---------|-------------|
| English spell names | "Lancio **Fireball**" | Common — English names feel more iconic |
| Italian skill names | "Check di **Furtività**" | Common — skills feel natural in Italian |
| Mixed in one sentence | "Uso **Stealth** per avvicinarmi e poi lancio **Palla di Fuoco**" | Very common |
| Colloquial variants | "Vado in modalità **stealth**" vs "mi muovo di **soppiatto**" | Same concept, different words |

The system must handle ALL of these seamlessly, resolving them to the same canonical entity.

### Why Now?

- The Claudmaster AI DM system is being built — it needs to communicate naturally with Italian players
- The rulebook system now supports multiple sources (SRD, Open5e, 5etools), providing thousands of terms that need bilingual mapping
- Code-switching support is a core UX requirement, not a nice-to-have — without it, Italian players must artificially constrain their natural speech

### Target User

Italian-speaking D&D players using dm20-protocol's AI DM. The user:
- Speaks Italian as primary language but knows English D&D terminology
- Naturally mixes IT/EN terms without thinking about it
- Expects the DM to understand both languages and respond naturally
- May have preferences that vary by term category (e.g., English for spells, Italian for skills)

## User Stories

### US-1: Player Uses Italian Spell Name
**As a** Italian-speaking player,
**I want to** say "Lancio Palla di Fuoco" and have the system understand it as Fireball,
**So that** I can play naturally in my language.

**Acceptance Criteria:**
- "Palla di Fuoco" resolves to the canonical spell "Fireball"
- The spell's full mechanics (damage, range, components) are applied correctly
- The DM's response uses "Palla di Fuoco" (mirroring the player's choice)
- Lookup is O(1), not a fuzzy search or LLM call

### US-2: Player Uses English Term in Italian Sentence
**As a** Italian-speaking player,
**I want to** say "Faccio un check di Stealth" and have it work the same as "Faccio un check di Furtività",
**So that** I can code-switch freely without the system breaking.

**Acceptance Criteria:**
- Both "Stealth" and "Furtività" resolve to the same Stealth skill
- The system doesn't require the player to be consistent
- No error or fallback when mixing languages

### US-3: DM Mirrors Player Style
**As a** player who prefers English spell names but Italian skill names,
**I want** the DM to respond using my preferred terms,
**So that** the conversation feels natural and consistent with my style.

**Acceptance Criteria:**
- Style tracker detects per-category language preferences over multiple interactions
- DM output adapts: "Il tuo Fireball infligge 28 danni" (not "La tua Palla di Fuoco")
- Preferences persist within a session
- Preferences can be overridden if the player switches style

### US-4: New Spell from Rulebook Auto-Mapped
**As a** DM who loaded the 5etools rulebook source,
**I want** newly loaded spell names to be automatically available in both languages,
**So that** I don't have to manually configure translations for every term.

**Acceptance Criteria:**
- When a rulebook source is loaded, spell/monster/class names are indexed for bilingual lookup
- Common terms have curated Italian translations from the static dictionary
- Less common terms fall back to the English name (no translation is better than a wrong translation)
- The auto-lookup supplements but never overrides the curated dictionary

### US-5: Colloquial Variants Understood
**As a** player who says "vado di soppiatto" instead of the formal "faccio un check di Furtività",
**I want** the system to understand colloquial Italian D&D expressions,
**So that** I don't have to use formal terminology.

**Acceptance Criteria:**
- Colloquial variants ("di soppiatto", "tiro salvezza", "punto ferita") are in the dictionary
- Multiple Italian variants can map to the same English canonical term
- The dictionary includes common informal D&D Italian terminology

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  Player Input                        │
│  "Lancio Fireball e poi mi muovo di soppiatto"       │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              TermResolver (Input)                     │
│                                                       │
│  ┌─────────────────┐    ┌──────────────────────────┐ │
│  │ Static Dict     │    │ Rulebook Auto-Index      │ │
│  │ ~500 curated    │    │ From loaded sources      │ │
│  │ IT↔EN pairs     │    │ (spell names, monsters)  │ │
│  │ + colloquial    │    │ Supplements static dict  │ │
│  └────────┬────────┘    └───────────┬──────────────┘ │
│           │     Merged into         │                 │
│           └──────┬──────────────────┘                 │
│                  ▼                                    │
│  ┌──────────────────────────────────┐                │
│  │ Lookup Table (O(1) dict)         │                │
│  │ "fireball" → Fireball            │                │
│  │ "palla di fuoco" → Fireball      │                │
│  │ "stealth" → Stealth              │                │
│  │ "furtività" → Stealth            │                │
│  │ "soppiatto" → Stealth            │                │
│  └──────────────────────────────────┘                │
└──────────────────────┬──────────────────────────────┘
                       │ canonical_key
                       ▼
┌──────────────────────────────────────────────────────┐
│              Game Engine                              │
│  (processes action using English canonical key)       │
└──────────────────────┬──────────────────────────────┘
                       │ result
                       ▼
┌──────────────────────────────────────────────────────┐
│              StyleTracker + OutputAdapter             │
│                                                       │
│  ┌──────────────────────────────────┐                │
│  │ Per-Category Style Preferences   │                │
│  │ spells: "en" (player says        │                │
│  │         "Fireball" not           │                │
│  │         "Palla di Fuoco")        │                │
│  │ skills: "it" (player says        │                │
│  │         "Furtività" not          │                │
│  │         "Stealth")               │                │
│  └──────────────────────────────────┘                │
│                                                       │
│  Output: "Il tuo Fireball colpisce! Fai un tiro      │
│           di Furtività per nasconderti."              │
└──────────────────────────────────────────────────────┘
```

### Component Overview

| Component | Location | Role |
|-----------|----------|------|
| `TermEntry` | `terminology/models.py` | Data model for a bilingual term (canonical key, EN name, IT name, IT variants, category) |
| `StaticDictionary` | `terminology/dictionary.py` | Curated IT↔EN mappings loaded from YAML/JSON |
| `RulebookTermExtractor` | `terminology/extractor.py` | Extracts term pairs from loaded rulebook sources |
| `TermResolver` | `terminology/resolver.py` | Unified O(1) lookup merging static + auto terms |
| `StyleTracker` | `terminology/style.py` | Observes player language choices, tracks per-category preferences |
| `OutputAdapter` | `terminology/adapter.py` | Transforms DM output terms to match player style |
| Dictionary data | `terminology/data/core_terms.yaml` | Static bilingual dictionary file |

## Requirements

### Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1 | Static dictionary with ~500 curated D&D term pairs (IT↔EN) | Must |
| FR-2 | Dictionary covers: spells, skills, conditions, abilities, combat terms, item types, class/race names | Must |
| FR-3 | Multiple Italian variants per term (formal + colloquial) | Must |
| FR-4 | O(1) dict-based lookup for input resolution | Must |
| FR-5 | Auto-extraction of term pairs from loaded rulebook content | Must |
| FR-6 | Static dictionary takes priority over auto-extracted terms | Must |
| FR-7 | Style tracker records per-category language preference | Must |
| FR-8 | Output adapter transforms DM terminology to match player style | Must |
| FR-9 | Case-insensitive matching | Must |
| FR-10 | Accent-insensitive matching (e.g., "furtivita" = "furtività") | Should |
| FR-11 | Terms categorized (spell, skill, condition, ability, combat, item, class, race, general) | Must |
| FR-12 | Integration with Claudmaster player_action processing | Must |
| FR-13 | Extensible to other language pairs (FR, DE, ES, PT) in the future | Should |
| FR-14 | User can add custom term mappings | Could |
| FR-15 | Dictionary data stored as YAML for easy human editing | Should |

### Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | Term lookup latency | < 1ms (O(1) dict lookup) |
| NFR-2 | Dictionary load time | < 500ms |
| NFR-3 | Memory footprint (static dict) | < 5 MB |
| NFR-4 | Memory footprint (with auto-index) | < 20 MB |
| NFR-5 | No external API calls for term resolution | Strictly local |
| NFR-6 | No LLM calls for term resolution | Strictly in-memory |
| NFR-7 | Thread safety | Safe for concurrent access |
| NFR-8 | Graceful fallback for unknown terms | Pass through unchanged |

## Technical Details

### Static Dictionary Format (YAML)

```yaml
# terminology/data/core_terms.yaml
terms:
  - canonical: "Fireball"
    category: spell
    en: "Fireball"
    it:
      primary: "Palla di Fuoco"
      variants: ["palla di fuoco", "fireball"]

  - canonical: "Stealth"
    category: skill
    en: "Stealth"
    it:
      primary: "Furtività"
      variants: ["furtività", "stealth", "soppiatto", "di soppiatto"]

  - canonical: "hit_points"
    category: combat
    en: "Hit Points"
    it:
      primary: "Punti Ferita"
      variants: ["punti ferita", "PF", "HP", "punti vita"]

  - canonical: "saving_throw"
    category: combat
    en: "Saving Throw"
    it:
      primary: "Tiro Salvezza"
      variants: ["tiro salvezza", "TS", "save", "saving throw"]
```

### TermResolver Lookup Strategy

```python
class TermResolver:
    def __init__(self):
        self._lookup: dict[str, TermEntry] = {}
        # All variants (EN + IT + colloquial) map to the same TermEntry
        # Key is lowercase, stripped of accents

    def resolve(self, text: str) -> TermEntry | None:
        """O(1) lookup — returns TermEntry or None."""
        normalized = self._normalize(text)
        return self._lookup.get(normalized)

    def _normalize(self, text: str) -> str:
        """Lowercase, strip accents, strip extra whitespace."""
        ...
```

### StyleTracker Design

```python
class StyleTracker:
    """Tracks which language variant the player prefers per category."""

    def __init__(self):
        # category → {"en": count, "it": count}
        self._observations: dict[str, dict[str, int]] = {}

    def observe(self, term: TermEntry, used_variant: str) -> None:
        """Record that the player used this variant."""
        lang = "en" if used_variant == term.en else "it"
        self._observations[term.category][lang] += 1

    def preferred_language(self, category: str) -> str:
        """Returns 'en' or 'it' based on majority of observations."""
        ...
```

### Integration with Claudmaster

The `player_action` tool processes natural language input. The TermResolver integrates at the pre-processing stage:

1. Player sends action text
2. **TermResolver scans** the text for known terms (both IT and EN variants)
3. For each recognized term, the **StyleTracker records** the language variant used
4. The action is processed by the game engine using **canonical English keys**
5. The DM agent generates a response
6. The **OutputAdapter transforms** terminology in the response to match the player's style

### Rulebook Auto-Extraction

When a rulebook source is loaded (SRD, Open5e, 5etools), the `RulebookTermExtractor` scans the content:

- **Spell names** → indexed as terms (EN name only, IT from static dict if available)
- **Monster names** → indexed
- **Class/Race names** → indexed
- **Skill/Ability names** → already in static dict
- **Condition names** → already in static dict

Auto-extracted terms are lower priority than static dictionary entries. If the static dict has a curated Italian translation for "Fireball", it takes precedence over any auto-extracted entry.

### Dictionary Coverage Plan (Phase 1: ~500 terms)

| Category | Count | Examples |
|----------|-------|---------|
| Skills (18) | 18 | Stealth/Furtività, Perception/Percezione, Athletics/Atletica |
| Abilities (6) | 6 | Strength/Forza, Dexterity/Destrezza, Constitution/Costituzione |
| Conditions (15) | 15 | Poisoned/Avvelenato, Frightened/Spaventato, Prone/Prono |
| Combat terms (30) | 30 | Initiative/Iniziativa, Saving Throw/Tiro Salvezza, Hit Points/Punti Ferita |
| Spell schools (8) | 8 | Evocation/Evocazione, Abjuration/Abiurazione |
| Core spells (100) | 100 | Fireball/Palla di Fuoco, Cure Wounds/Cura Ferite |
| Core monsters (100) | 100 | Goblin/Goblin, Dragon/Drago, Beholder/Beholder |
| Classes (12) | 12 | Wizard/Mago, Rogue/Ladro, Paladin/Paladino |
| Races (9) | 9 | Elf/Elfo, Dwarf/Nano, Human/Umano |
| Item types (20) | 20 | Longsword/Spada Lunga, Shield/Scudo, Potion/Pozione |
| General terms (180+) | 180+ | Adventure/Avventura, Dungeon/Dungeon, Quest/Missione |

## Success Criteria

| Metric | Target |
|--------|--------|
| Static dictionary size | ≥ 500 curated term pairs |
| Term resolution accuracy | > 99% for known terms |
| Lookup latency | < 1ms per term |
| Style tracking accuracy | > 90% correct style mirroring after 5+ observations |
| Code-switching handling | 100% — mixed IT/EN sentences resolve correctly |
| Fallback behavior | Unknown terms pass through unchanged (no errors) |
| Integration test coverage | > 80% |

## Constraints & Assumptions

### Constraints
- **Italian only in Phase 1** — Architecture should support multiple languages, but only Italian is implemented initially
- **No machine translation** — All Italian terms are curated or mapped from known sources, never auto-translated
- **No LLM calls** — Term resolution must be purely in-memory for performance
- **Dictionary maintenance** — Static dictionary requires manual curation for quality; this is intentional (quality over quantity)
- **Accent handling** — Must handle both accented ("furtività") and unaccented ("furtivita") input from keyboards

### Assumptions
- Italian players consistently use a mix of IT/EN terminology (validated by user feedback)
- The ~500 core terms cover >95% of typical gameplay terminology
- Per-category style tracking (not per-term) is sufficient granularity
- Players' language preferences are relatively stable within a session
- The Claudmaster DM agent can accept terminology hints in its output generation

## Out of Scope

- **Full Italian translation of DM narrative** — The DM already communicates in Italian; this system handles only terminology/game terms
- **Spell description translation** — Spell descriptions remain in English; only the term (name) is bilingual
- **Grammar-aware transformation** — The system maps terms, not full sentence structures (e.g., Italian gender agreement is not handled automatically)
- **Voice input/STT** — The system processes text input only
- **Machine learning for style detection** — Simple counting/majority is sufficient
- **Other languages beyond Italian** — Architecture supports it, but only Italian is built
- **User-facing dictionary editor UI** — Custom terms added via config file only

## Dependencies

### Internal
- `Claudmaster player_action` — Integration point for input processing
- `Claudmaster DM agents` — Integration point for output adaptation
- `RulebookManager` — Source of auto-extractable terms
- Loaded rulebook content (spells, monsters, classes, etc.)

### External
- None — Fully offline, no external APIs

## Implementation Order

```
Phase 1 — Core Dictionary & Resolution
  ├── Task 1: TermEntry model + StaticDictionary loader (YAML→dict)
  ├── Task 2: Curate core_terms.yaml (~500 terms)
  ├── Task 3: TermResolver with O(1) lookup + normalization
  └── Task 4: Unit tests for resolution (IT→EN, EN→EN, colloquial→EN)

Phase 2 — Style Tracking & Output
  ├── Task 5: StyleTracker (per-category observation + preference)
  ├── Task 6: OutputAdapter (term substitution in DM responses)
  └── Task 7: Integration tests (input→resolve→track→adapt→output)

Phase 3 — Auto-Extraction & Integration
  ├── Task 8: RulebookTermExtractor (extract from loaded sources)
  ├── Task 9: Integration with Claudmaster player_action pipeline
  └── Task 10: End-to-end tests with real gameplay scenarios
```

## Related Context

- Italian D&D community commonly uses a mix of English and Italian terminology
- Official Italian D&D translations exist (by Asmodee Italia) but players rarely use them consistently
- The system mirrors natural speech patterns observed at Italian D&D tables
