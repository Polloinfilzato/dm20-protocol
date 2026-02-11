---
name: pdf-rulebook-library
description: Shared library for third-party and homebrew PDF/Markdown rulebooks with intelligent content extraction and cross-campaign sharing
status: completed
created: 2026-02-02T15:30:00Z
---

# PRD: PDF Rulebook Library System

## Executive Summary

This PRD defines a shared rulebook library system that enables users to add third-party and homebrew content from PDF and Markdown files, making them available across all campaigns with intelligent on-demand content extraction.

**Key deliverables:**
1. **Shared Library** — Global folder for PDF/Markdown rulebooks accessible by all campaigns
2. **TOC Indexer** — Automatic table of contents extraction and content discovery
3. **On-Demand Extractor** — Extract specific content (classes, races, spells) only when needed
4. **Campaign Binding** — Per-campaign configuration of which content to use
5. **Smart Cache** — JSON cache of extracted content for fast access
6. **"Ask Your Books"** — Natural language queries across all available content

**Value proposition:** Transform the rulebook system from "official content only" to a comprehensive library that includes ALL the user's purchased and homebrew materials, making gamemaster-mcp the single source of truth for game rules.

## Problem Statement

### Current State

The rulebook system only supports:
- Official SRD content via API
- Custom JSON files manually created by the user

```python
# Current: Must manually create JSON for any non-SRD content
# User has "Tome of Heroes" PDF but cannot use it
load_rulebook(source="custom", path="tome_of_heroes.json")  # Does not exist
# User must manually type everything from the PDF into JSON format
```

### Problems

1. **Manual Data Entry:** Users must manually transcribe PDF content to JSON
2. **No PDF Support:** Cannot leverage purchased third-party books
3. **No Content Discovery:** User doesn't know what's in their PDFs without reading them
4. **Per-Campaign Isolation:** Custom content must be duplicated across campaigns
5. **Slow Lookup:** No way to quickly find "a class that does X" across materials
6. **Wasted Resources:** Same PDF parsed repeatedly if needed in multiple contexts

### Why Now?

- Rulebook system is stable and working with SRD/custom JSON
- Users are asking for third-party content support
- PDF extraction libraries (PyMuPDF, pdfplumber) are mature
- LLM capabilities make intelligent content extraction feasible
- Competitive advantage: Most tools don't support user's full library

### Target User Scenario

```
DM: "I bought 'Tome of Heroes' from Kobold Press. It has cool new classes.
     I want to use the 'Dragon Knight' class for an NPC in my campaign."

Current: Must manually read PDF, transcribe class to JSON, load as custom rulebook.
         Time: 30-60 minutes per class.

With this feature:
1. Drop PDF in library folder
2. System indexes TOC automatically
3. Ask "what classes are in Tome of Heroes?" -> instant answer
4. Say "extract Dragon Knight class" -> JSON created automatically
5. Use in any campaign immediately
```

## Architecture Overview

### Directory Structure

```
dnd_data/                           # Global data directory
|-- library/                        # SHARED LIBRARY (new!)
|   |-- pdfs/                       # User drops PDFs here
|   |   |-- Tome_of_Heroes.pdf
|   |   |-- Deep_Magic.pdf
|   |   +-- homebrew_classes.md
|   |-- index/                      # Auto-generated TOC indexes
|   |   |-- tome-of-heroes.index.json
|   |   +-- deep-magic.index.json
|   +-- extracted/                  # Extracted content cache
|       |-- tome-of-heroes/
|       |   |-- classes/
|       |   |   +-- dragon-knight.json
|       |   +-- races/
|       +-- deep-magic/
|           +-- spells/
|
+-- campaigns/
    +-- my_campaign/
        |-- campaign.json
        +-- rulebooks/
            |-- manifest.json           # Which SRD/custom rulebooks active
            +-- library-bindings.json   # Which library content enabled
```

### Library Bindings Example

```json
{
  "enabled_sources": ["tome-of-heroes", "deep-magic"],
  "enabled_content": {
    "tome-of-heroes": {
      "classes": ["dragon-knight"],
      "races": ["all"]
    }
  }
}
```

### Data Flow

```
USER ACTIONS
    |                    |                      |
    v                    v                      v
[Drop PDF]         [Query Content]       [Enable for Campaign]
    |                    |                      |
    v                    v                      v
TOC Indexer        Ask Your Books        Campaign Binder
(one-time)         Engine               (library-bindings)
    |                    |                      |
    v                    v                      v
index/*.json  <--- On-Demand    --->  extracted/*.json
(TOC cache)        Extractor          (content cache)
                       |
                       v
                  RulebookMgr
                  Integration
```

## User Stories

### US-1: Adding a PDF to the Library

**As a** Dungeon Master
**I want** to add a PDF rulebook to my library by dropping it in a folder
**So that** I can use its content in my campaigns without manual transcription

**Acceptance Criteria:**
- [ ] Designated folder for PDF/MD files (`library/pdfs/`)
- [ ] Tool to scan library and index new files
- [ ] TOC extracted automatically from PDF structure
- [ ] Index stored as JSON for fast queries
- [ ] Handles PDFs without proper TOC (best-effort extraction)

### US-2: Discovering Content in My Library

**As a** Dungeon Master
**I want** to ask "what classes/races/spells are in my library?"
**So that** I know what options are available beyond the SRD

**Acceptance Criteria:**
- [ ] Query content across all indexed books
- [ ] Filter by content type (class, race, spell, monster, etc.)
- [ ] Filter by source book
- [ ] Show page numbers for reference
- [ ] Natural language query support ("find a tanky spellcaster class")

### US-3: Extracting Specific Content

**As a** Dungeon Master
**I want** to extract a specific class/race from a PDF
**So that** I can use it in character creation and validation

**Acceptance Criteria:**
- [ ] Extract content by name and type
- [ ] Convert to standard rulebook JSON format
- [ ] Cache extracted content for future use
- [ ] Handle extraction errors gracefully
- [ ] Support manual correction of extracted data

### US-4: Enabling Library Content for a Campaign

**As a** Dungeon Master
**I want** to specify which library content is available in my campaign
**So that** different campaigns can use different third-party books

**Acceptance Criteria:**
- [ ] Enable/disable entire source books per campaign
- [ ] Enable/disable specific content within a book
- [ ] Enabled content appears in `search_rules` results
- [ ] Character validation considers enabled library content
- [ ] Easy toggle without re-extraction

### US-5: Using Library Content in Character Creation

**As a** Dungeon Master
**I want** library classes/races to work like SRD content
**So that** I can create characters using third-party options

**Acceptance Criteria:**
- [ ] `create_character` accepts library classes/races
- [ ] `validate_character` checks against library content
- [ ] `get_class_info` returns library class details
- [ ] Level-up features available for library classes

### US-6: Natural Language Content Search

**As a** Dungeon Master
**I want** to ask questions like "find a class good for a dragon-themed character"
**So that** I can discover relevant content across all my books

**Acceptance Criteria:**
- [ ] Natural language query interface
- [ ] Searches across TOC, descriptions, and extracted content
- [ ] Returns relevant matches with source and page
- [ ] Offers to extract detailed content on request

## Requirements

### Functional Requirements

#### FR-1: Library Management

| ID | Requirement |
|----|-------------|
| FR-1.1 | Create global library directory structure |
| FR-1.2 | Implement `scan_library` tool to detect new files |
| FR-1.3 | Support PDF files (.pdf) |
| FR-1.4 | Support Markdown files (.md) |
| FR-1.5 | Generate unique source ID from filename |
| FR-1.6 | Track file modification dates to detect changes |
| FR-1.7 | Implement `list_library` tool to show all sources |

#### FR-2: TOC Indexing

| ID | Requirement |
|----|-------------|
| FR-2.1 | Extract TOC from PDF bookmarks/outlines |
| FR-2.2 | Fall back to heading detection if no TOC |
| FR-2.3 | Identify content types (Chapter: Classes, Chapter: Races, etc.) |
| FR-2.4 | Store page numbers for each entry |
| FR-2.5 | Create searchable index with keywords |
| FR-2.6 | Index Markdown files by headers |
| FR-2.7 | Re-index on file modification |

#### FR-3: Content Extraction

| ID | Requirement |
|----|-------------|
| FR-3.1 | Extract class definitions to standard JSON |
| FR-3.2 | Extract race definitions to standard JSON |
| FR-3.3 | Extract spell definitions to standard JSON |
| FR-3.4 | Extract monster stat blocks to standard JSON |
| FR-3.5 | Extract feat definitions to standard JSON |
| FR-3.6 | Extract item definitions to standard JSON |
| FR-3.7 | Extract subclass definitions to standard JSON |
| FR-3.8 | Handle multi-page content correctly |
| FR-3.9 | Preserve formatting (tables, lists) where relevant |
| FR-3.10 | Support LLM-assisted extraction for complex layouts |

#### FR-4: Campaign Binding

| ID | Requirement |
|----|-------------|
| FR-4.1 | Create `library-bindings.json` per campaign |
| FR-4.2 | Implement `enable_library_source` tool |
| FR-4.3 | Implement `disable_library_source` tool |
| FR-4.4 | Support enabling specific content types from a source |
| FR-4.5 | Support enabling specific items (e.g., just one class) |
| FR-4.6 | Integrate with RulebookManager query interface |

#### FR-5: Query Interface

| ID | Requirement |
|----|-------------|
| FR-5.1 | Implement `search_library` tool |
| FR-5.2 | Search across all indexed sources |
| FR-5.3 | Filter by source, content type |
| FR-5.4 | Return source name, content name, page number |
| FR-5.5 | Implement `ask_books` natural language query |
| FR-5.6 | Support semantic search across descriptions |

#### FR-6: MCP Tools

| ID | Requirement |
|----|-------------|
| FR-6.1 | `scan_library` - Scan and index new PDF/MD files |
| FR-6.2 | `list_library` - List all sources in library |
| FR-6.3 | `get_library_toc` - Get TOC for a specific source |
| FR-6.4 | `search_library` - Search across all library content |
| FR-6.5 | `extract_content` - Extract specific content from source |
| FR-6.6 | `enable_library_source` - Enable source for campaign |
| FR-6.7 | `disable_library_source` - Disable source for campaign |
| FR-6.8 | `list_enabled_library` - Show what is enabled for campaign |
| FR-6.9 | `ask_books` - Natural language query across library |

### Non-Functional Requirements

#### NFR-1: Performance

| ID | Requirement |
|----|-------------|
| NFR-1.1 | TOC indexing < 10 seconds per PDF |
| NFR-1.2 | Library scan < 5 seconds for 20 files |
| NFR-1.3 | Search query < 500ms |
| NFR-1.4 | Content extraction < 30 seconds per item |
| NFR-1.5 | Cached content retrieval < 100ms |

#### NFR-2: Accuracy

| ID | Requirement |
|----|-------------|
| NFR-2.1 | TOC extraction >= 90% accurate for well-formatted PDFs |
| NFR-2.2 | Content extraction >= 80% accurate for standard layouts |
| NFR-2.3 | Support manual correction of extracted data |
| NFR-2.4 | Preserve original page references |

#### NFR-3: Usability

| ID | Requirement |
|----|-------------|
| NFR-3.1 | Zero-config: just drop PDF in folder |
| NFR-3.2 | Clear error messages for unsupported PDFs |
| NFR-3.3 | Progress indication for long operations |
| NFR-3.4 | Non-destructive: original PDFs never modified |

#### NFR-4: Storage

| ID | Requirement |
|----|-------------|
| NFR-4.1 | Index files < 1% of original PDF size |
| NFR-4.2 | Extracted content in compact JSON |
| NFR-4.3 | Support cleanup of unused extractions |

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| PDF support | Common formats | Test with 5+ real third-party PDFs |
| TOC accuracy | >= 90% | Manual review of index vs actual TOC |
| Extraction accuracy | >= 80% | Compare extracted JSON to source |
| Query performance | < 500ms | Measure p95 latency |
| User workflow | < 5 min | Time from PDF drop to using content |
| Cross-campaign | Works | Same extraction used in 2+ campaigns |

## Constraints and Assumptions

### Constraints

1. **No OCR:** Assumes PDFs have selectable text (not scanned images)
2. **Format Variance:** Third-party PDFs have inconsistent layouts
3. **Copyright:** System extracts for personal use; user responsible for licensing
4. **LLM Dependency:** Complex extraction may require LLM assistance
5. **Storage:** Large libraries may consume significant disk space

### Assumptions

1. Users have legally obtained PDF copies
2. Most third-party PDFs follow D&D 5e conventions
3. Users accept that extraction may not be 100% accurate
4. Markdown homebrew follows reasonable heading structure
5. Users will correct extraction errors when found

## Out of Scope

The following are explicitly NOT included in this PRD:

1. OCR for scanned/image-based PDFs
2. Automatic purchase/download of PDFs
3. DRM removal or circumvention
4. Sharing extracted content between users
5. Real-time PDF editing
6. Support for non-D&D 5e systems
7. Mobile app integration
8. Cloud storage of library

## Dependencies

### External Dependencies

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| PyMuPDF (fitz) | >=1.23 | PDF parsing and text extraction | Low |
| pdfplumber | >=0.10 | Table extraction from PDFs | Low |
| markdown | >=3.5 | Markdown parsing | Low |

### Internal Dependencies

```
PDF Rulebook Library (this PRD)
    +-- depends on -> Rulebook System (completed)
    +-- depends on -> RulebookManager (completed)
    +-- extends -> CustomSource (existing)
    +-- enhances -> search_rules (existing)
```

### Recommended Implementation Order

1. **Phase 1:** Library Structure and File Detection (FR-1)
2. **Phase 2:** TOC Indexing (FR-2)
3. **Phase 3:** Basic Search (FR-5.1-5.4)
4. **Phase 4:** Content Extraction - Classes (FR-3.1)
5. **Phase 5:** Content Extraction - Other Types (FR-3.2-3.7)
6. **Phase 6:** Campaign Binding (FR-4)
7. **Phase 7:** RulebookManager Integration
8. **Phase 8:** Natural Language Search (FR-5.5-5.6)
9. **Phase 9:** MCP Tools (FR-6)

## Technical Notes

### Index File Structure

```json
{
  "source_id": "tome-of-heroes",
  "filename": "Tome_of_Heroes.pdf",
  "indexed_at": "2026-02-02T15:00:00Z",
  "file_hash": "sha256:abc123...",
  "total_pages": 350,
  "toc": [
    {
      "title": "Chapter 1: Races",
      "page": 12,
      "type": "races",
      "children": [
        {"title": "Alseid", "page": 14, "type": "race"},
        {"title": "Bearfolk", "page": 18, "type": "race"}
      ]
    },
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
    "races": 15,
    "classes": 8,
    "subclasses": 24,
    "spells": 120,
    "monsters": 45
  },
  "keywords": ["kobold press", "midgard", "dragon", "fey", "shadow"]
}
```

### Library Bindings Structure

```json
{
  "campaign_id": "my_campaign",
  "updated_at": "2026-02-02T16:00:00Z",
  "enabled_sources": [
    {
      "source_id": "tome-of-heroes",
      "enabled": true,
      "content_filter": {
        "classes": ["dragon-knight", "spell-blade"],
        "races": "*",
        "spells": "*",
        "monsters": []
      }
    },
    {
      "source_id": "deep-magic",
      "enabled": true,
      "content_filter": {
        "spells": "*"
      }
    }
  ]
}
```

### Extraction Process Flow

```
User: "Extract Dragon Knight class from Tome of Heroes"
                    |
                    v
+-------------------------------------+
| 1. Look up in index                 |
|    -> "Dragon Knight" at page 47    |
+-------------------------------------+
                    |
                    v
+-------------------------------------+
| 2. Extract raw text from pages 47-61|
|    (until next class or chapter)    |
+-------------------------------------+
                    |
                    v
+-------------------------------------+
| 3. Parse into structured format     |
|    - Class name, hit die            |
|    - Features by level              |
|    - Subclasses                     |
|    - Equipment, proficiencies       |
+-------------------------------------+
                    |
                    v
+-------------------------------------+
| 4. Save to extracted/ cache         |
|    -> extracted/tome-of-heroes/     |
|       classes/dragon-knight.json    |
+-------------------------------------+
                    |
                    v
+-------------------------------------+
| 5. Return confirmation + summary    |
|    "Extracted: Dragon Knight        |
|     Level 1-20 features, 3 subclass"|
+-------------------------------------+
```

### "Ask Your Books" Query Examples

```
Query: "What options do I have for a melee spellcaster?"

Response:
Found 7 options across your library:

From SRD:
  - Eldritch Knight (Fighter subclass) - martial + wizard spells
  - Bladesinger (Wizard subclass) - melee combat focus

From Tome of Heroes (pages in parentheses):
  - Dragon Knight (p.47) - draconic warrior with breath weapon [Extract]
  - Spell Blade (p.62) - weapon and spell fusion [Extract]

From Deep Magic:
  - Battle Mage tradition (p.89) - wizard melee specialization [Extract]

From homebrew_classes.md:
  - Magus (custom) - full progression gish class [Already extracted]

Would you like me to extract any of these for detailed information?
```

## References

- PyMuPDF Documentation: https://pymupdf.readthedocs.io/
- pdfplumber GitHub: https://github.com/jsvine/pdfplumber
- Kobold Press: https://koboldpress.com/ (Common third-party publisher)
- DMsGuild: https://www.dmsguild.com/ (Homebrew marketplace)
- Existing Rulebook System PRD: ./rulebook-system.md

## Appendix A: Supported PDF Structures

### Well-Supported
- PDFs with proper bookmarks/outlines
- PDFs with consistent heading styles
- PDFs with selectable text
- PDFs following standard D&D layout conventions

### Partially Supported
- PDFs without bookmarks (uses heading detection)
- PDFs with complex multi-column layouts
- PDFs with embedded tables (best-effort extraction)

### Not Supported
- Scanned/image-only PDFs (no OCR)
- Encrypted/DRM-protected PDFs
- PDFs in non-Latin scripts (limited support)

## Appendix B: Content Type Detection Heuristics

| Content Type | Detection Keywords/Patterns |
|--------------|----------------------------|
| Class | "Hit Die:", "Proficiencies:", "Class Features", level table |
| Race | "Ability Score Increase:", "Size:", "Speed:", "Traits" |
| Spell | "Casting Time:", "Range:", "Components:", "Duration:" |
| Monster | "Armor Class:", "Hit Points:", "Challenge:", stat block format |
| Feat | "Prerequisite:", typically 1-2 paragraphs |
| Item | "Wondrous item", "Weapon", "Armor", rarity keywords |
| Subclass | Appears under class, "archetype", "tradition", "path" |
