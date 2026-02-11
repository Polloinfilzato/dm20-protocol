# Refactoring Plan: Storage Architecture

**Status:** APPROVED
**Author:** Claude (with Ema)
**Date:** 2026-02-02
**Version:** 2.0

---

## Executive Summary

This document defines the approved refactoring plan for gamemaster-mcp storage architecture:

1. **Split storage into multiple files** — Native behavior change, not migration
2. **TOON format for MCP output** — Keep JSON storage, convert to TOON on output
3. **Session Transcription Summarizer** — New tool for summarizing recorded sessions

---

## Approved Decisions

| Decision | Choice |
|----------|--------|
| **TOON Integration** | Output only (JSON storage, TOON on read) |
| **Split Files** | Yes — modify MCP core behavior |
| **Sessions Storage** | Separate file per session |
| **Migration** | Not required — new structure applies to new campaigns |

---

## Part 1: Current Architecture (Problem)

### Current Structure

```
data/
└── campaigns/
    └── campaign-name.json  ← MONOLITHIC FILE (all data)
```

### Problems

1. **Write Amplification:** Every small change rewrites entire file
2. **Token Waste:** Loading full context when only partial data needed
3. **Scalability:** Large campaigns = large files = slow operations
4. **Sessions Growth:** Session notes accumulate indefinitely in monolith

---

## Part 2: New Architecture (Solution)

### Target Structure

```
data/
├── campaigns/
│   └── campaign-name/                    # Directory per campaign
│       ├── campaign.json                 # Metadata only
│       ├── characters.json               # All characters
│       ├── npcs.json                     # All NPCs
│       ├── locations.json                # All locations
│       ├── quests.json                   # All quests
│       ├── encounters.json               # Combat encounters
│       ├── game_state.json               # Current state
│       └── sessions/                     # Sessions directory
│           ├── session-001.json          # Session 1
│           ├── session-002.json          # Session 2
│           └── ...
│
└── events/
    └── adventure_log.json                # Already separate (keep as-is)
```

### Key Principles

1. **Native behavior change:** New campaigns automatically use split structure
2. **Existing campaigns:** Can optionally be migrated via utility script
3. **Backward compatibility:** Keep ability to read old monolithic files
4. **Atomic writes:** Each section saved independently

---

## Part 3: TOON Integration

### Approach: Output Only

Store data in JSON, convert to TOON when returning to LLM.

```python
from toon import encode

class DnDStorage:
    def get_characters_toon(self) -> str:
        """Return characters in TOON format for token efficiency."""
        characters = self.list_characters_detailed()
        return encode([c.model_dump() for c in characters])
```

### Tool Enhancement

Add optional `format` parameter to relevant tools:

```python
@mcp_tool
def list_characters(format: str = "json") -> str:
    """List all characters. Format: 'json' or 'toon'."""
    characters = storage.list_characters_detailed()
    if format == "toon":
        return encode([c.model_dump() for c in characters])
    return json.dumps([c.model_dump() for c in characters])
```

### Expected Savings

| Scenario | JSON Tokens | TOON Tokens | Savings |
|----------|------------|-------------|---------|
| Current campaign | ~3,400 | ~1,700-2,400 | 30-50% |
| Large campaign | ~50,000 | ~25,000-35,000 | 30-50% |

---

## Part 4: Session Transcription Summarizer

### Use Case

DM records game sessions (2-3 hours), transcribes audio, needs intelligent summary.

### Workflow

```
🎙️ Game Session (2-3 hours audio)
        ↓
📝 Transcription (Whisper/other STT)
        ↓ (~30,000-50,000 tokens raw text)
🤖 MCP Tool: summarize_session
        ↓
📋 Structured SessionNote (saved to sessions/session-XXX.json)
```

### Tool Interface

```python
@mcp_tool
def summarize_session(
    transcript: str | Path,      # Raw transcription text or file path
    session_number: int,         # Session number to create
    language: str = "it",        # Transcription language
    detail_level: str = "medium" # brief | medium | detailed
) -> SessionNote:
    """
    Summarize a game session transcription into a structured note.

    Loads campaign context (characters, active quests, current location)
    to intelligently filter and extract relevant roleplay moments.

    Filters out:
    - Off-topic chatter
    - Bathroom breaks, food discussion
    - Dice rolling sounds, table talk

    Extracts:
    - Character decisions and actions
    - NPC dialogues and revelations
    - Combat encounters and outcomes
    - Quest progress and discoveries
    - World lore and plot developments
    """
```

### Output Structure

```json
{
  "session_number": 5,
  "title": "The Letter Revealed",
  "date": "2026-02-02T20:00:00Z",
  "summary": "The party opened the sealed letter at The Green Dragon...",
  "events": [
    "Rollo delivered the mysterious letter",
    "Aldric recognized the Dúnedain seal",
    "The Grey Stranger revealed himself as Mallorn"
  ],
  "characters_present": ["Aldric", "Bramble", "Elowen", "Durin"],
  "npcs_encountered": ["Rollo Goodbody", "Mallorn"],
  "quest_updates": {
    "The Sealed Letter": "Completed objective: Read the letter"
  },
  "combat_encounters": [],
  "loot_found": [],
  "experience_gained": 150,
  "notes": "Party decided to travel to Rivendell"
}
```

### Implementation Considerations

1. **Chunking:** Transcriptions may exceed context limits; use sliding window or map-reduce
2. **Speaker identification:** Map speaker labels to character/player names
3. **Language:** Primary support for Italian transcriptions
4. **Context loading:** Use TOON format to minimize token usage when loading campaign context

### Token Impact

| Scenario | Transcription | Campaign Context | TOTAL |
|----------|--------------|------------------|-------|
| JSON monolithic | 40K | 50K | **90K tokens** |
| TOON + split files | 40K | 15K | **55K tokens** |

**Savings: ~35,000 tokens per session summary**

---

## Part 5: Implementation Tasks

### Task Group A: Split Storage Architecture

| ID | Task | Description |
|----|------|-------------|
| A1 | Refactor DnDStorage class | Change save/load methods to use directory structure |
| A2 | Create campaign directory structure | On campaign creation, create directory with split files |
| A3 | Implement per-section save methods | _save_characters(), _save_npcs(), _save_locations(), etc. |
| A4 | Implement per-section load methods | _load_characters(), _load_npcs(), _load_locations(), etc. |
| A5 | Implement sessions directory | Save each session to sessions/session-XXX.json |
| A6 | Dirty tracking per section | Only save sections that changed |
| A7 | Backward compatibility | Detect and read old monolithic files |
| A8 | Migration utility | Optional script to convert old campaigns |
| A9 | Update tests | Adapt existing tests to new structure |
| A10 | Documentation | Update README and add architecture docs |

### Task Group B: TOON Output Integration

| ID | Task | Description |
|----|------|-------------|
| B1 | Add python-toon dependency | Add to pyproject.toml |
| B2 | Create TOON encoder wrapper | Utility module for JSON-to-TOON conversion |
| B3 | Add format parameter to tools | Add optional format="json"|"toon" to read tools |
| B4 | Benchmark token savings | Measure actual savings with real campaign data |
| B5 | Documentation | Document TOON usage in tools |

### Task Group C: Session Summarizer

| ID | Task | Description |
|----|------|-------------|
| C1 | Design summarize_session tool | Define interface and parameters |
| C2 | Implement transcription parser | Handle raw text and file input |
| C3 | Implement context loader | Load relevant campaign data efficiently |
| C4 | Implement filtering logic | Remove irrelevant content from transcription |
| C5 | Implement extraction logic | Identify roleplay-significant moments |
| C6 | Implement session note generation | Create structured SessionNote output |
| C7 | Handle large transcriptions | Chunking/map-reduce for long sessions |
| C8 | Speaker mapping | Map speaker labels to characters |
| C9 | Italian language support | Ensure proper handling of Italian text |
| C10 | Tests | Comprehensive tests with sample transcriptions |
| C11 | Documentation | Usage guide and examples |

---

## Part 6: Dependencies

### External Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| python-toon | >=0.1.0 | TOON encoding/decoding |

### Internal Dependencies

```
Task Group C (Summarizer)
    └── depends on → Task Group A (Split Storage)
    └── depends on → Task Group B (TOON Output)
```

---

## Part 7: Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Data inconsistency between files | Implement atomic writes, validation on load |
| python-toon library instability | Pin version, fallback to JSON if encoding fails |
| Large transcription exceeds context | Implement chunking with overlap |
| Migration breaks existing campaigns | Keep backward compatibility, migration is optional |

---

## Appendix A: File Format Examples

### campaign.json (metadata only)

```json
{
  "id": "4CZLRkTQ",
  "name": "L'Ombra sulla Terra di Mezzo",
  "description": "Una campagna epica...",
  "dm_name": "Ema",
  "setting": "# La Terra di Mezzo...",
  "created_at": "2026-02-01T05:06:09.201668",
  "updated_at": "2026-02-02T10:30:00.000000"
}
```

### characters.json

```json
{
  "Aldric": {
    "id": "TnVMGSJf",
    "name": "Aldric",
    "player_name": "Alessio",
    ...
  },
  "Bramble Tuckburrow": { ... }
}
```

### sessions/session-001.json

```json
{
  "id": "abc123",
  "session_number": 1,
  "date": "2026-02-01T20:00:00Z",
  "title": "A Gathering at The Green Dragon",
  "summary": "Four unlikely heroes meet at the famous inn...",
  "events": ["..."],
  "characters_present": ["Aldric", "Bramble", "Elowen", "Durin"],
  "experience_gained": 100,
  "notes": ""
}
```

---

## Appendix B: TOON Output Example

### JSON (characters list)

```json
[{"name":"Aldric","class":"Ranger","level":3,"hp":25},{"name":"Bramble","class":"Rogue","level":3,"hp":25}]
```

### TOON (same data)

```
[2]{name,class,level,hp}:
Aldric,Ranger,3,25
Bramble,Rogue,3,25
```

**Token reduction: ~40%**

---

## Appendix C: References

- [TOON Official Repository](https://github.com/toon-format/toon)
- [TOON Specification](https://github.com/toon-format/spec)
- [Python TOON SDK](https://github.com/xaviviro/python-toon)
- Video: Simone Rizzo - "TOON sta mandando in pensione JSON"
