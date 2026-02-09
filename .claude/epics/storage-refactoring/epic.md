---
name: storage-refactoring
status: completed
created: 2026-02-01T23:49:05Z
progress: 100%
prd: .claude/prds/storage-refactoring.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/1
updated: 2026-02-09T02:09:06Z
---

# Epic: storage-refactoring

## Overview

Refactoring of the storage architecture from monolithic JSON file to directory-based structure with separate files per entity, adding TOON output format support for token reduction, and a new tool to summarize session transcriptions.

## Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| **Directory-based storage** | Each campaign becomes a directory with separate files per entity (characters.json, npcs.json, etc.) |
| **Lazy file writing** | Only "dirty" files are rewritten, reducing I/O by 50%+ |
| **Backward compatibility via detection** | The system automatically detects whether a campaign is monolithic or split and handles it accordingly |
| **TOON as output-only** | TOON is used only for MCP tool output, disk storage remains JSON |
| **Session summarizer as prompt template** | Uses campaign context + transcription to generate structured SessionNote |

## Technical Approach

### Storage Layer Changes

**New Directory Structure:**
```
data/campaigns/{campaign-name}/
├── campaign.json      # Metadata only (id, name, description, dm_name, setting)
├── characters.json    # All characters dict
├── npcs.json          # All NPCs dict
├── locations.json     # All locations dict
├── quests.json        # All quests dict
├── encounters.json    # All encounters dict
├── game_state.json    # Game state object
└── sessions/
    └── session-{NNN}.json  # Individual session files
```

**Per-Section Dirty Tracking:**
- Replace single `_campaign_hash` with per-file hashes
- Track which sections are modified
- Only save modified files on `_save_campaign()`

**Legacy Detection:**
- Check if `campaigns/{name}.json` (file) or `campaigns/{name}/` (directory) exists
- Load appropriately based on detection
- New campaigns always use split structure

### TOON Integration

**Dependency:** `python-toon >= 0.1.0`

**Implementation:**
- Add optional `format` parameter to list_* tools
- Default: "json" (backward compatible)
- When "toon": encode response with python-toon
- Graceful fallback to JSON if TOON encoding fails

**Affected Tools:**
- `list_characters`
- `list_npcs`
- `list_locations`
- `list_quests`
- `get_campaign_info`

### Session Summarizer Tool

**New Tool:** `summarize_session`

**Parameters:**
- `transcription: str` - Raw transcription text
- `session_number: int` - Session number
- `detail_level: str` - "brief" | "medium" | "detailed" (default: "medium")
- `speaker_map: dict[str, str]` - Optional mapping of speaker labels to character names

**Output:** Creates `SessionNote` and saves to `sessions/session-{NNN}.json`

**Implementation Strategy:**
- Load campaign context (characters, quests, locations) in TOON format
- Send transcription + context to LLM with structured prompt
- Parse response into `SessionNote` model
- For very long transcriptions (>50k tokens): chunk and use map-reduce pattern

## Implementation Strategy

### Phase 1: Split Storage (Foundation)
- Create `SplitStorageBackend` class
- Implement per-file save/load methods
- Add dirty tracking per section
- Add legacy detection and backward compatibility
- Migrate `storage.py` to use new backend

### Phase 2: TOON Output
- Add python-toon dependency
- Create TOON encoder utility
- Add format parameter to list tools
- Test token reduction

### Phase 3: Session Summarizer
- Create `summarize_session` tool
- Implement chunking for large transcriptions
- Add speaker mapping support

## Task Breakdown Preview

- [ ] **Task 1**: Implement split storage backend with per-file save/load and dirty tracking
- [ ] **Task 2**: Add legacy detection and backward compatibility for monolithic campaigns
- [ ] **Task 3**: Migrate storage.py to use split storage for new campaigns
- [ ] **Task 4**: Add python-toon dependency and create TOON encoder utility
- [ ] **Task 5**: Add format parameter to list tools with TOON output support
- [ ] **Task 6**: Implement summarize_session tool with chunking support
- [ ] **Task 7**: Add migration utility script (optional, for existing campaigns)
- [ ] **Task 8**: Write tests for split storage, TOON output, and session summarizer

## Dependencies

### External Dependencies

| Dependency | Purpose | Risk |
|------------|---------|------|
| python-toon ≥0.1.0 | TOON encoding | Medium - new library |

### Internal Dependencies

```
Task 3 (Migrate storage.py) → depends on → Task 1, Task 2
Task 5 (TOON tools) → depends on → Task 4
Task 6 (Session summarizer) → depends on → Task 3, Task 5
Task 7 (Migration utility) → depends on → Task 3
Task 8 (Tests) → depends on → All other tasks
```

## Success Criteria (Technical)

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Write performance | ≥50% faster | Single-field update write time |
| TOON token reduction | ≥30% | Compare JSON vs TOON token counts |
| Backward compatibility | 100% | Existing campaigns load without error |
| Test coverage | ≥80% | pytest --cov |

## Estimated Effort

| Phase | Complexity | Notes |
|-------|------------|-------|
| Split Storage | Medium | Core refactoring, most code changes |
| TOON Output | Low | Thin wrapper over library |
| Session Summarizer | Medium | Prompt engineering + chunking logic |
| Tests | Medium | Need comprehensive coverage |

**Total Tasks:** 8
**Critical Path:** Tasks 1 → 2 → 3 → 5 → 6

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| python-toon instability | Graceful fallback to JSON |
| Large transcription handling | Chunking with map-reduce |
| Migration errors | Migration is optional, legacy format always works |

## Tasks Created

- [ ] 3.md - Implement split storage backend (parallel: true)
- [ ] 4.md - Add legacy detection and backward compatibility (parallel: true)
- [ ] 5.md - Migrate storage.py to use split storage (parallel: false, depends: 3, 4)
- [ ] 6.md - Add python-toon dependency and TOON encoder (parallel: true)
- [ ] 7.md - Add format parameter to list tools (parallel: false, depends: 6)
- [ ] 8.md - Implement summarize_session tool (parallel: false, depends: 5, 7)
- [ ] 9.md - Add migration utility script (parallel: true, depends: 5)
- [ ] 10.md - Write comprehensive tests (parallel: false, depends: 5, 7, 8)

**Total tasks:** 8
**Parallel tasks:** 4 (Tasks 3, 4, 6, 9)
**Sequential tasks:** 4 (Tasks 5, 7, 8, 10)
**Estimated total effort:** 34-45 hours

### Dependency Graph

```
Phase 1 (Parallel):     [3] Split Backend    [4] Legacy Detection    [6] TOON Encoder
                              ↓                    ↓                       ↓
Phase 2:                      └────────[5] Migrate Storage────┐     [7] Format Param
                                            ↓                 ↓           ↓
Phase 3 (Parallel):                   [9] Migration      [8] Session Summarizer
                                                                    ↓
Phase 4:                                              [10] Comprehensive Tests
```
