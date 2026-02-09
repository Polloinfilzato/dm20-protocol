---
name: pdf-rulebook-library
status: completed
created: 2026-02-02T20:02:21Z
progress: 100%
prd: .claude/prds/pdf-rulebook-library.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/21
---

# Epic: PDF Rulebook Library System

## Overview

Implement a shared library system that allows users to add third-party and homebrew PDF/Markdown rulebooks, extract content on-demand, and use them across all campaigns. The system leverages the existing `RulebookSourceBase` architecture and `CustomSource` format for extracted content.

**Key Insight:** Instead of creating a new source type, we'll build a "PDF Library" layer that:
1. Indexes PDFs and extracts TOC
2. Extracts content to standard `CustomSource` JSON format
3. Loads extracted content through existing `CustomSource` infrastructure

This approach minimizes new code and maximizes reuse of the battle-tested rulebook system.

## Architecture Decisions

### AD-1: Extraction-to-CustomSource Pattern
**Decision:** Extract PDF content to JSON files in `CustomSource` format, then load via existing `CustomSource`.

**Rationale:**
- Reuses 100% of existing query/search infrastructure
- No changes needed to `RulebookManager` core
- Extracted content is editable/correctable by users
- Cache is human-readable and debuggable

### AD-2: Shared Library Directory
**Decision:** Global `dnd_data/library/` directory outside campaigns.

**Rationale:**
- Single location for all PDFs (no duplication)
- Extracted content shared across campaigns
- Campaign bindings control what's enabled per-campaign

### AD-3: On-Demand Extraction
**Decision:** Index TOC immediately, extract full content only when requested.

**Rationale:**
- Fast initial setup (just TOC scan)
- Avoids extracting unused content
- User controls what gets extracted

### AD-4: PyMuPDF for PDF Processing
**Decision:** Use PyMuPDF (fitz) as primary PDF library.

**Rationale:**
- Fast and memory-efficient
- Good TOC/bookmark extraction
- Active maintenance, permissive license
- pdfplumber as fallback for complex tables if needed

## Technical Approach

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    PDF Library System                        │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ LibraryIndex │  │ TOCExtractor │  │ ContentExtractor │  │
│  │ (scan/list)  │  │ (PDF→index)  │  │ (pages→JSON)     │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│         └────────────┬────┴────────────────────┘            │
│                      │                                      │
│              ┌───────▼───────┐                              │
│              │ LibraryManager│ (orchestration)              │
│              └───────┬───────┘                              │
└──────────────────────┼──────────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │  CustomSource   │ (existing, unchanged)
              └────────┬────────┘
                       │
              ┌────────▼────────┐
              │ RulebookManager │ (existing, unchanged)
              └─────────────────┘
```

### Directory Structure

```
dnd_data/
├── library/                          # NEW: Shared library
│   ├── pdfs/                         # User drops files here
│   │   ├── Tome_of_Heroes.pdf
│   │   └── homebrew.md
│   ├── index/                        # Auto-generated indexes
│   │   └── tome-of-heroes.index.json
│   └── extracted/                    # Extracted content (CustomSource format)
│       └── tome-of-heroes/
│           └── dragon-knight.json    # One file per extracted item
│
└── campaigns/
    └── my_campaign/
        └── rulebooks/
            └── library-bindings.json # NEW: What library content is enabled
```

### New Classes

1. **LibraryManager** (`src/gamemaster_mcp/library/manager.py`)
   - Orchestrates library operations
   - Manages index files and extracted content
   - Interfaces with RulebookManager for loading

2. **TOCExtractor** (`src/gamemaster_mcp/library/extractors/toc.py`)
   - Extracts table of contents from PDFs
   - Identifies content types (classes, races, spells, etc.)
   - Creates searchable index

3. **ContentExtractor** (`src/gamemaster_mcp/library/extractors/content.py`)
   - Extracts specific content from PDF pages
   - Converts to CustomSource JSON format
   - Handles different content types (class, race, spell, etc.)

4. **LibraryBindings** (`src/gamemaster_mcp/library/bindings.py`)
   - Per-campaign configuration of enabled library content
   - Loads/unloads extracted content as CustomSource

### MCP Tools (9 new tools)

| Tool | Purpose |
|------|---------|
| `scan_library` | Scan pdfs/ folder, index new files |
| `list_library` | List all sources in library |
| `get_library_toc` | Get TOC for a specific source |
| `search_library` | Search across all indexed content |
| `extract_content` | Extract specific content from PDF |
| `enable_library_source` | Enable source for current campaign |
| `disable_library_source` | Disable source for current campaign |
| `list_enabled_library` | Show enabled library content |
| `ask_books` | Natural language query (Phase 2) |

## Implementation Strategy

### Phase 1: Foundation (Tasks 1-3)
- Library directory structure and manager
- TOC extraction from PDFs
- Index persistence and search

### Phase 2: Extraction (Tasks 4-5)
- Content extraction for all types
- CustomSource JSON generation

### Phase 3: Integration (Tasks 6-7)
- Campaign bindings
- RulebookManager integration
- MCP tools

### Phase 4: Polish (Tasks 8-9)
- Markdown file support
- Natural language search (ask_books)

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| PDF layout variance | Start with well-structured PDFs, document limitations |
| Extraction accuracy | Manual correction support, clear error messages |
| Large PDFs slow | Async processing, progress indication |
| Storage growth | On-demand extraction, cleanup tools |

## Task Breakdown Preview

- [ ] **Task 1:** Library directory structure and LibraryManager base class
- [ ] **Task 2:** TOC extraction from PDFs (PyMuPDF)
- [ ] **Task 3:** Index persistence and search_library tool
- [ ] **Task 4:** Content extraction - classes and races
- [ ] **Task 5:** Content extraction - spells, monsters, feats, items
- [ ] **Task 6:** Campaign bindings and enable/disable tools
- [ ] **Task 7:** RulebookManager integration (load extracted as CustomSource)
- [ ] **Task 8:** Markdown file support
- [ ] **Task 9:** Natural language search (ask_books)

## Dependencies

### External Dependencies

| Package | Version | Purpose | Status |
|---------|---------|---------|--------|
| PyMuPDF | >=1.23 | PDF parsing | To add |
| pdfplumber | >=0.10 | Table extraction (optional) | To add |

### Internal Dependencies

- `RulebookSourceBase` - Existing, no changes needed
- `CustomSource` - Existing, no changes needed
- `RulebookManager` - Existing, minor integration point
- `DnDStorage` - Extend with library_dir property

## Success Criteria (Technical)

| Criteria | Target | Measurement |
|----------|--------|-------------|
| TOC extraction time | < 5s per PDF | Benchmark with 300-page PDF |
| Index search latency | < 200ms | Profile search_library |
| Content extraction | < 30s per item | Benchmark class extraction |
| Test coverage | >= 80% | pytest-cov report |
| Integration | Zero changes to existing sources | Code review |

## Estimated Effort

| Phase | Tasks | Estimate |
|-------|-------|----------|
| Foundation | 1-3 | 3-4 sessions |
| Extraction | 4-5 | 2-3 sessions |
| Integration | 6-7 | 2 sessions |
| Polish | 8-9 | 2 sessions |
| **Total** | 9 tasks | ~10 sessions |

**Critical Path:** Tasks 1→2→3→4→6→7 (core functionality)

## Technical Notes

### Index File Format

```json
{
  "source_id": "tome-of-heroes",
  "filename": "Tome_of_Heroes.pdf",
  "indexed_at": "2026-02-02T15:00:00Z",
  "file_hash": "sha256:abc123...",
  "total_pages": 350,
  "toc": [
    {
      "title": "Chapter 2: Classes",
      "page": 45,
      "type": "classes",
      "children": [
        {"title": "Dragon Knight", "page": 47, "type": "class"},
        {"title": "Spell Blade", "page": 62, "type": "class"}
      ]
    }
  ],
  "content_summary": {
    "classes": 8,
    "races": 15,
    "spells": 120
  }
}
```

### Extracted Content Format

Uses existing CustomSource schema:
```json
{
  "$schema": "gamemaster-mcp/rulebook-v1",
  "name": "Dragon Knight (Tome of Heroes)",
  "version": "extracted-2026-02-02",
  "source_pdf": "tome-of-heroes",
  "source_page": 47,
  "content": {
    "classes": [{
      "index": "dragon-knight",
      "name": "Dragon Knight",
      "hit_die": "d10",
      ...
    }]
  }
}
```

### Library Bindings Format

```json
{
  "campaign_id": "my_campaign",
  "updated_at": "2026-02-02T16:00:00Z",
  "enabled_sources": {
    "tome-of-heroes": {
      "enabled": true,
      "content": ["dragon-knight", "spell-blade"]
    }
  }
}
```

## Tasks Created

| # | File | Task | Parallel | Depends On |
|---|------|------|----------|------------|
| 22 | [22.md](22.md) | Library directory structure and LibraryManager base class | ✓ | - |
| 23 | [23.md](23.md) | TOC extraction from PDFs using PyMuPDF | ✗ | 22 |
| 24 | [24.md](24.md) | Index persistence and search_library MCP tool | ✗ | 22, 23 |
| 25 | [25.md](25.md) | Content extraction - classes and races | ✓ | 23, 24 |
| 26 | [26.md](26.md) | Content extraction - spells, monsters, feats, items | ✗ | 25 |
| 27 | [27.md](27.md) | Campaign bindings and enable/disable tools | ✓ | 24 |
| 28 | [28.md](28.md) | RulebookManager integration | ✗ | 25, 27 |
| 29 | [29.md](29.md) | Markdown file support | ✓ | 23, 25 |
| 30 | [30.md](30.md) | Natural language search (ask_books) | ✓ | 24, 28 |

**Total tasks:** 9
**Parallel tasks:** 5 (22, 25, 27, 29, 30)
**Sequential tasks:** 4 (23, 24, 26, 28)
**Estimated total effort:** 38-52 hours (~10 sessions)

### Dependency Graph

```
22 (Foundation)
 │
 ▼
23 (TOC Extraction)
 │
 ├──────────────┬────────────────┐
 ▼              ▼                ▼
24 (Index)     29 (Markdown)    ...
 │
 ├──────┬───────┐
 ▼      ▼       ▼
25     27      ...
 │      │
 ├──────┤
 ▼      │
26      │
 │      │
 └──┬───┘
    ▼
   28 (Integration)
    │
    ▼
   30 (ask_books)
```
