---
name: storage-refactoring
description: Refactor monolithic JSON storage to split files, add TOON output support, and session transcription summarizer
status: backlog
created: 2026-02-01T23:46:59Z
---

# PRD: Storage Refactoring

## Executive Summary

This PRD defines a comprehensive refactoring of the gamemaster-mcp storage architecture to improve performance, reduce token consumption, and add intelligent session summarization capabilities.

**Key deliverables:**
1. **Split Storage Architecture** — Replace monolithic campaign JSON with directory-based split files
2. **TOON Output Format** — Add Token Oriented Object Notation support for 30-50% token reduction
3. **Session Transcription Summarizer** — New tool to convert game session recordings into structured notes

**Value proposition:** Significant reduction in token costs (up to 35,000 tokens saved per session summary), improved write performance, and enhanced scalability for large campaigns.

## Problem Statement

### Current State

The gamemaster-mcp stores all campaign data in a single monolithic JSON file:

```
data/campaigns/campaign-name.json  (~14 KB current, up to 1 MB+ for large campaigns)
```

### Problems

1. **Write Amplification:** Every small change (e.g., +1 HP) rewrites the entire file
2. **Token Waste:** Loading full campaign context when only partial data needed
3. **Scalability Issues:** Large campaigns = large files = slow operations
4. **Session Note Growth:** Session notes accumulate indefinitely in the monolith
5. **No Session Summarization:** DMs must manually create session notes from recordings

### Why Now?

- User plans to record and transcribe game sessions (2-3 hours each)
- Transcriptions generate 30,000-50,000 tokens of raw text
- Combined with campaign context loading, current architecture would consume ~90,000 tokens per session summary
- With proposed changes, this drops to ~55,000 tokens (35,000 token savings per session)

## User Stories

### US-1: DM Creating New Campaign

**As a** Dungeon Master
**I want** campaigns to automatically use the split file structure
**So that** I get better performance and scalability from day one

**Acceptance Criteria:**
- [ ] New campaign creates directory with split files
- [ ] characters.json, npcs.json, locations.json, etc. created separately
- [ ] sessions/ subdirectory created for session notes
- [ ] Existing monolithic campaigns continue to work (backward compatibility)

### US-2: DM Updating Character

**As a** Dungeon Master
**I want** character updates to only write the characters file
**So that** disk writes are faster and more efficient

**Acceptance Criteria:**
- [ ] Updating a character only writes characters.json
- [ ] Other files remain untouched
- [ ] Dirty tracking prevents unnecessary writes

### US-3: AI Agent Requesting Data

**As an** AI agent (LLM)
**I want** to receive data in TOON format
**So that** I consume fewer tokens and process data more accurately

**Acceptance Criteria:**
- [ ] Tools support optional `format` parameter ("json" or "toon")
- [ ] TOON output reduces tokens by 30-50%
- [ ] JSON remains the default for backward compatibility

### US-4: DM Summarizing Session Recording

**As a** Dungeon Master
**I want** to provide a session transcription and get an intelligent summary
**So that** I have structured session notes without manual work

**Acceptance Criteria:**
- [ ] Tool accepts transcription text or file path
- [ ] Filters out irrelevant chatter (food, breaks, off-topic)
- [ ] Extracts roleplay-significant moments
- [ ] Creates structured SessionNote with events, NPCs, quest updates
- [ ] Supports Italian language transcriptions
- [ ] Handles large transcriptions via chunking

### US-5: DM with Existing Campaign

**As a** Dungeon Master with an existing monolithic campaign
**I want** the option to migrate to the new structure
**So that** I can benefit from the improvements without starting over

**Acceptance Criteria:**
- [ ] Migration utility script available
- [ ] Old campaigns work without migration (backward compatible)
- [ ] Migration is optional, not forced

## Requirements

### Functional Requirements

#### FR-1: Split Storage Architecture

| ID | Requirement |
|----|-------------|
| FR-1.1 | Create campaign directory structure on new campaign creation |
| FR-1.2 | Save characters to dedicated characters.json file |
| FR-1.3 | Save NPCs to dedicated npcs.json file |
| FR-1.4 | Save locations to dedicated locations.json file |
| FR-1.5 | Save quests to dedicated quests.json file |
| FR-1.6 | Save encounters to dedicated encounters.json file |
| FR-1.7 | Save game state to dedicated game_state.json file |
| FR-1.8 | Save campaign metadata to campaign.json file |
| FR-1.9 | Create sessions/ subdirectory for session notes |
| FR-1.10 | Save each session to individual session-XXX.json file |
| FR-1.11 | Implement per-section dirty tracking |
| FR-1.12 | Detect and read legacy monolithic files |
| FR-1.13 | Provide optional migration utility |

#### FR-2: TOON Output Integration

| ID | Requirement |
|----|-------------|
| FR-2.1 | Add python-toon as project dependency |
| FR-2.2 | Create TOON encoder wrapper utility |
| FR-2.3 | Add `format` parameter to list_characters tool |
| FR-2.4 | Add `format` parameter to list_npcs tool |
| FR-2.5 | Add `format` parameter to list_locations tool |
| FR-2.6 | Add `format` parameter to list_quests tool |
| FR-2.7 | Add `format` parameter to get_campaign_info tool |
| FR-2.8 | Default format to "json" for backward compatibility |
| FR-2.9 | Fallback to JSON if TOON encoding fails |

#### FR-3: Session Transcription Summarizer

| ID | Requirement |
|----|-------------|
| FR-3.1 | Accept transcription as text string or file path |
| FR-3.2 | Accept session_number parameter |
| FR-3.3 | Accept language parameter (default: "it") |
| FR-3.4 | Accept detail_level parameter (brief/medium/detailed) |
| FR-3.5 | Load campaign context (characters, quests, locations) |
| FR-3.6 | Filter irrelevant content from transcription |
| FR-3.7 | Extract character decisions and actions |
| FR-3.8 | Extract NPC dialogues and revelations |
| FR-3.9 | Extract combat encounters and outcomes |
| FR-3.10 | Extract quest progress and discoveries |
| FR-3.11 | Generate structured SessionNote output |
| FR-3.12 | Save to sessions/session-XXX.json |
| FR-3.13 | Handle large transcriptions via chunking/map-reduce |
| FR-3.14 | Map speaker labels to character/player names |

### Non-Functional Requirements

#### NFR-1: Performance

| ID | Requirement |
|----|-------------|
| NFR-1.1 | Single-section write < 50ms for typical file sizes |
| NFR-1.2 | Campaign load time equivalent or better than monolithic |
| NFR-1.3 | TOON encoding overhead < 10ms per response |

#### NFR-2: Reliability

| ID | Requirement |
|----|-------------|
| NFR-2.1 | Atomic writes to prevent data corruption |
| NFR-2.2 | Validation on file load to detect corruption |
| NFR-2.3 | Graceful degradation if python-toon unavailable |

#### NFR-3: Compatibility

| ID | Requirement |
|----|-------------|
| NFR-3.1 | Read existing monolithic campaign files |
| NFR-3.2 | No breaking changes to existing tool interfaces |
| NFR-3.3 | JSON remains default output format |

#### NFR-4: Token Efficiency

| ID | Requirement |
|----|-------------|
| NFR-4.1 | TOON output achieves minimum 30% token reduction |
| NFR-4.2 | Session summarizer uses TOON for context loading |

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Token reduction (TOON) | ≥30% | Compare JSON vs TOON token counts |
| Write performance improvement | ≥50% | Measure write time for single-field update |
| Session summary token savings | ~35,000 tokens | Compare before/after implementation |
| Backward compatibility | 100% | All existing campaigns load without error |
| Test coverage | ≥80% | Unit tests for new functionality |

## Constraints & Assumptions

### Constraints

1. **Fork repository:** Changes must be pushed to fork remote, not origin
2. **Python version:** Must support Python 3.12+
3. **Dependency stability:** python-toon is a new library (may have bugs)
4. **Context limits:** LLM context windows limit transcription processing

### Assumptions

1. Users will create new campaigns to benefit from split storage
2. Existing campaigns may not be migrated (migration is optional)
3. Italian is the primary language for transcriptions
4. Transcriptions may or may not include speaker labels

## Out of Scope

The following are explicitly **NOT** included in this PRD:

1. ❌ Automatic migration of existing campaigns (optional utility only)
2. ❌ Native TOON storage (JSON remains on disk, TOON output only)
3. ❌ Audio-to-text transcription (assumes transcription already done)
4. ❌ Real-time session recording integration
5. ❌ Multi-language transcription support beyond Italian
6. ❌ Web UI for session summarization
7. ❌ Breaking changes to existing MCP tool interfaces

## Dependencies

### External Dependencies

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| python-toon | ≥0.1.0 | TOON encoding/decoding | Medium - new library |
| pydantic | existing | Data models | Low |
| shortuuid | existing | ID generation | Low |

### Internal Dependencies

```
Session Summarizer (FR-3)
    └── depends on → Split Storage (FR-1)
    └── depends on → TOON Output (FR-2)
```

### Recommended Implementation Order

1. **Phase 1:** Split Storage Architecture (FR-1)
2. **Phase 2:** TOON Output Integration (FR-2)
3. **Phase 3:** Session Transcription Summarizer (FR-3)

*Note: Final prioritization to be determined during epic decomposition.*

## Technical Notes

### Target Directory Structure

```
data/
├── campaigns/
│   └── campaign-name/
│       ├── campaign.json
│       ├── characters.json
│       ├── npcs.json
│       ├── locations.json
│       ├── quests.json
│       ├── encounters.json
│       ├── game_state.json
│       └── sessions/
│           ├── session-001.json
│           ├── session-002.json
│           └── ...
└── events/
    └── adventure_log.json  (already separate, keep as-is)
```

### Session Note Output Structure

```json
{
  "session_number": 5,
  "title": "The Letter Revealed",
  "date": "2026-02-02T20:00:00Z",
  "summary": "The party opened the sealed letter...",
  "events": ["Event 1", "Event 2"],
  "characters_present": ["Aldric", "Bramble"],
  "npcs_encountered": ["Rollo Goodbody"],
  "quest_updates": {"Quest Name": "Progress description"},
  "combat_encounters": [],
  "loot_found": [],
  "experience_gained": 150,
  "notes": "Additional DM notes"
}
```

## References

- [TOON Official Repository](https://github.com/toon-format/toon)
- [TOON Specification](https://github.com/toon-format/spec)
- [Python TOON SDK](https://github.com/xaviviro/python-toon)
- Internal: `.claude/docs/REFACTORING_PLAN_STORAGE.md`

---

## Decision Log

### 2026-02-02: TOON Format Removed

**Decision:** Remove TOON output format support from the codebase.

**Context:** TOON (Token Oriented Object Notation) was implemented to reduce token usage for LLM output. The original goal was "30-50% token reduction."

**Analysis Results:**
After comparative testing, TOON did not deliver the promised benefits:

| Format | Characters | vs JSON formatted | vs JSON compact |
|--------|------------|-------------------|-----------------|
| JSON formatted | 1,406 | baseline | - |
| JSON compact | 841 | -40% | baseline |
| TOON | 1,048 | -25% | **+25% LARGER** |
| Markdown summary | 224 | -84% | -73% |

**Key Findings:**
1. TOON is ~25% **larger** than JSON compact (not smaller)
2. The "30% reduction" claim compared only to indented JSON (artificially inflated)
3. Markdown summaries are 4.7x more efficient than TOON
4. python-toon adds dependency complexity with minimal benefit

**Recommendation for Future Projects:**
Use TOON only when:
- You need human-readable config files with type safety
- You're replacing YAML (TOON is comparable)
- You have deeply nested structures with repeated type annotations

Do NOT use TOON when:
- Optimizing for LLM token consumption (use JSON compact or Markdown)
- Comparing against JSON compact (no benefit)
- Simplicity matters more than type safety

**Action Taken:**
- Removed `python-toon` dependency from `pyproject.toml`
- Deleted `src/gamemaster_mcp/toon_encoder.py`
- Removed `format` parameter from all MCP tools
- Replaced context encoding with `json.dumps(separators=(',', ':'))`
- Updated all related tests
