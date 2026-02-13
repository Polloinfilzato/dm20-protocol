---
name: docs-refresh
status: completed
created: 2026-02-13T00:57:49Z
progress: 100%
updated: 2026-02-13T14:30:00Z
completed: 2026-02-13T14:30:00Z
prd: .claude/prds/docs-refresh.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/107
---

# Epic: Documentation Refresh

## Overview

Comprehensive update of all user-facing documentation to reflect the current state of dm20-protocol after 10 completed epics. The documentation has fallen behind — major features (multi-source rulebooks, character builder, bilingual support, dual-agent architecture) are missing or outdated in README, CHANGELOG, PLAYER_GUIDE, GUIDE, ROADMAP, and DEVELOPMENT docs.

## Architecture Decisions

### 1. Panoramic + examples style (not API reference)
Documentation should explain features through practical workflow examples rather than exhaustive parameter listings. Users learn by seeing "here's how you create a character" not by reading parameter tables.

### 2. PLAYER_GUIDE.md as dedicated solo play guide
The existing PLAYER_GUIDE.md (266 lines) gets rewritten as a comprehensive guide covering the full solo play experience: rulebook loading → character creation → gameplay → combat → rest → level-up → save/resume.

### 3. Single [Unreleased] CHANGELOG entry
All changes since v0.2.0 go into one [Unreleased] section following Keep a Changelog format. No retroactive version splitting.

### 4. ROADMAP reflects reality + future direction
Mark everything completed as Done. Add forward-looking items based on natural next steps (PyPI distribution, module playtesting, narrative tuning).

### 5. Accuracy from source code
All tool names, parameters, and behaviors verified against actual source code — not from memory or epic descriptions.

## Technical Approach

### Files to Update

| File | Current State | Work Needed |
|------|--------------|-------------|
| `CHANGELOG.md` | Missing ~60% of features | Add all 10 epics to [Unreleased] |
| `README.md` | Missing multi-source, bilingual, builder, level-up | Update Features, Quick Start, Solo Play |
| `PLAYER_GUIDE.md` | Covers basic commands only | Full rewrite with new features |
| `docs/GUIDE.md` | Incomplete tools reference | Add all new tools + workflow examples |
| `docs/ROADMAP.md` | Shows done items as "Not started" | Full status update + future items |
| `docs/DEVELOPMENT.md` | Says "25+ tools", old models | Update architecture + models section |

### Information Sources for Accuracy

- `src/dm20_protocol/mcp/main.py` — all MCP tool definitions and parameters
- `src/dm20_protocol/mcp/tools/` — tool implementations
- `src/dm20_protocol/models.py` — Character v2 model fields
- `src/dm20_protocol/character_builder.py` — builder methods
- `src/dm20_protocol/level_up_engine.py` — level-up logic
- `src/dm20_protocol/rulebooks/sources/` — open5e.py, fivetools.py, srd.py, custom.py
- `src/dm20_protocol/library/` — LibraryManager, extractors
- `src/dm20_protocol/terminology/` — TermResolver, StyleTracker
- `src/dm20_protocol/claudmaster/` — agents, orchestrator, config
- `.claude/dm-persona.md` — DM persona
- `.claude/agents/` — sub-agent specs
- `.claude/epics/.archived/` — feature descriptions

## Implementation Strategy

### Parallel execution possible
Each file is independent — multiple can be updated simultaneously. The only dependency is the final cross-file consistency check.

### Verification
After updates, verify:
- All internal links work (`[text](path)` and `#anchor`)
- Tool names match actual code
- Feature counts are consistent across files
- Markdown renders correctly

## Task Breakdown Preview

- [ ] Task 1: CHANGELOG.md — Complete [Unreleased] with all 10 epics (S, 2h)
- [ ] Task 2: README.md — Update Features, Quick Start, Solo Play sections (S, 2h)
- [ ] Task 3: PLAYER_GUIDE.md — Full rewrite with character builder, multi-source, bilingual, rest, level-up (M, 3-4h)
- [ ] Task 4: docs/GUIDE.md — Updated tools reference with workflow examples (M, 4-5h)
- [ ] Task 5: docs/ROADMAP.md + docs/DEVELOPMENT.md — Status update + architecture refresh (S, 2-3h)
- [ ] Task 6: Cross-file consistency review + link verification (S, 1h)

## Tasks Created

- [ ] 106.md - CHANGELOG.md: Complete [Unreleased] with all 10 epics (parallel: true)
- [ ] 107.md - README.md: Update Features, Quick Start, Solo Play (parallel: true)
- [ ] 108.md - PLAYER_GUIDE.md: Full rewrite for solo play experience (parallel: true)
- [ ] 109.md - docs/GUIDE.md: Updated tools reference with workflow examples (parallel: true)
- [ ] 110.md - ROADMAP.md + DEVELOPMENT.md: Status update and architecture refresh (parallel: true)
- [ ] 111.md - Cross-file consistency review and link verification (parallel: false, depends on all above)

Total tasks: 6
Parallel tasks: 5 (#106-#110 can start simultaneously)
Sequential tasks: 1 (#111 after all others)
Estimated total effort: 14-17 hours

## Dependencies

- No code changes required
- All features already implemented and tested

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| Features documented | All 10 epics covered |
| Tools listed in GUIDE.md | All 50+ MCP tools |
| Internal links | Zero broken links |
| Cross-file consistency | Same names/counts everywhere |

## Estimated Effort

| Task | Size | Hours |
|------|------|-------|
| CHANGELOG.md | S | 2 |
| README.md | S | 2 |
| PLAYER_GUIDE.md | M | 3-4 |
| docs/GUIDE.md | M | 4-5 |
| ROADMAP + DEVELOPMENT | S | 2-3 |
| Consistency review | S | 1 |
| **Total** | **M** | **14-17** |
