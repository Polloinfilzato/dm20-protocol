---
name: docs-refresh
description: Comprehensive documentation refresh to cover all features from 10 completed epics
status: backlog
created: 2026-02-13T00:57:49Z
---

# PRD: Documentation Refresh

## Executive Summary

dm20-protocol has grown from a basic MCP server (v0.1.0) to a full-featured D&D campaign management + AI DM system across 10 completed epics. The documentation has not kept pace — major features like multi-source rulebooks, bilingual terminology, character builder, level-up engine, and dual-agent architecture are either missing or barely mentioned in user-facing docs.

### Key Deliverables

1. **CHANGELOG.md** — Complete [Unreleased] section with all features from 10 epics
2. **README.md** — Updated Features section, Quick Start examples reflecting new capabilities
3. **PLAYER_GUIDE.md** — Full rewrite covering character builder, multi-source rules, bilingual play, rest mechanics
4. **docs/GUIDE.md** — Panoramic tools reference with practical workflow examples
5. **docs/ROADMAP.md** — Updated with completed milestones + future direction
6. **docs/DEVELOPMENT.md** — Updated architecture, models, 50+ tools count

## Problem Statement

A new user visiting the GitHub repo today sees:
- README Features list that doesn't mention Open5e, 5etools, character builder, bilingual support, or dual-agent architecture
- CHANGELOG [Unreleased] covering only ~40% of actual changes
- ROADMAP showing features as "Not started" that are fully implemented
- PLAYER_GUIDE that doesn't explain character creation with auto-population, level-up, or rest mechanics
- GUIDE.md with system prompt recommendations but incomplete tools reference
- DEVELOPMENT.md saying "25+ tools" when there are 50+

The gap between what the system CAN do and what the documentation SAYS it can do is significant.

## Scope

### In Scope

- Update all 6 documentation files listed above
- Ensure consistency across all docs (same feature names, same tool names)
- Add practical examples and workflow descriptions
- Document all MCP tools added since v0.2.0
- Update completed milestones and add future direction to roadmap

### Out of Scope

- API/code-level documentation (docstrings, type annotations)
- Tutorial videos or interactive guides
- Localized documentation (Italian version)
- New documentation files beyond those listed

## User Stories

### US1: New visitor discovers the project
**As a** D&D player browsing GitHub for MCP servers,
**I want** the README to clearly show all capabilities,
**So that** I understand what dm20-protocol offers before installing.

**Acceptance Criteria:**
- README Features list mentions all major capability areas
- Quick Start shows character creation with auto-population
- Solo Play section explains dual-agent architecture benefit

### US2: Player wants to start solo play
**As a** player who installed dm20-protocol,
**I want** a comprehensive player guide,
**So that** I know how to create characters, load rulebooks, and start playing.

**Acceptance Criteria:**
- PLAYER_GUIDE covers: rulebook loading, character creation (3 ability methods), starting a session, combat, rest, level-up
- Mentions bilingual support for Italian players
- Includes troubleshooting section

### US3: Developer wants to contribute
**As a** developer exploring the codebase,
**I want** accurate architecture docs,
**So that** I understand the project structure and can contribute.

**Acceptance Criteria:**
- DEVELOPMENT.md reflects actual project structure with 50+ tools
- Data models section includes Character v2 fields
- Architecture section mentions dual-agent, terminology resolver, multi-source

### US4: User wants to know what changed
**As a** returning user updating dm20-protocol,
**I want** a complete changelog,
**So that** I know what new features and fixes are available.

**Acceptance Criteria:**
- CHANGELOG [Unreleased] lists all features from epics: storage-refactoring, rulebook-system, pdf-rulebook-library, multi-source-rulebook, claudmaster-ai-dm, dm-persona-gameloop, dm-improvements, system-evolution, character-model-v2, bilingual-terminology-resolver
- Follows Keep a Changelog format (Added, Changed, Fixed)

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | CHANGELOG.md [Unreleased] covers all 10 epics in Keep a Changelog format | Must |
| FR2 | README.md Features list mentions all major capabilities | Must |
| FR3 | README.md Quick Start includes character builder example | Should |
| FR4 | PLAYER_GUIDE.md rewritten with full gameplay workflow | Must |
| FR5 | docs/GUIDE.md tools reference updated with all new tools | Must |
| FR6 | docs/GUIDE.md includes workflow examples (character creation, solo play, combat) | Must |
| FR7 | docs/ROADMAP.md completed milestones updated | Must |
| FR8 | docs/ROADMAP.md future direction section added | Should |
| FR9 | docs/DEVELOPMENT.md architecture section updated | Should |
| FR10 | docs/DEVELOPMENT.md data models section updated for Character v2 | Should |
| FR11 | Cross-file consistency (tool names, feature names, counts) | Must |

## Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NF1 | All documentation in English (repo rule) |
| NF2 | Markdown renders correctly on GitHub |
| NF3 | No broken internal links between docs |
| NF4 | File sizes reasonable (no single file > 1000 lines) |

## Dependencies

- No code changes required
- All features already implemented and tested
- Tool names and parameters can be verified from source code

## Implementation Notes

### Information Sources

To write accurate documentation, reference:
- `src/dm20_protocol/mcp/main.py` — all MCP tool definitions
- `src/dm20_protocol/mcp/tools/` — tool implementation details
- `src/dm20_protocol/models.py` — Character v2 model
- `src/dm20_protocol/character_builder.py` — builder logic
- `src/dm20_protocol/level_up_engine.py` — level-up logic
- `src/dm20_protocol/rulebooks/` — rulebook system
- `src/dm20_protocol/library/` — PDF library system
- `src/dm20_protocol/terminology/` — bilingual resolver
- `src/dm20_protocol/claudmaster/` — AI DM system
- `.claude/dm-persona.md` — DM persona instructions
- `.claude/agents/` — sub-agent definitions
- `.claude/commands/dm/` — slash commands
- `.claude/epics/.archived/` — epic descriptions for feature summaries

### Estimated Task Breakdown

| Task | Files | Size |
|------|-------|------|
| CHANGELOG.md update | 1 file | S (2h) |
| README.md update | 1 file | S (2h) |
| PLAYER_GUIDE.md rewrite | 1 file | M (3-4h) |
| docs/GUIDE.md update | 1 file | M (4-5h) |
| docs/ROADMAP.md update | 1 file | S (1-2h) |
| docs/DEVELOPMENT.md update | 1 file | S (2h) |
| Cross-file review & consistency | all | S (1h) |
| **Total** | **6 files** | **15-18h** |
