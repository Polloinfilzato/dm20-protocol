# Issue #121 Analysis: RAG Activation — ModuleKeeper Wiring + Library Vector Search

## Part A: ModuleKeeper Wiring

### Current State
- `ModuleKeeperAgent` at `agents/module_keeper.py` — fully implemented, not wired
- Public API: `get_npc_knowledge()`, `get_location_description()`, `check_encounter_trigger()`, `get_plot_context()`
- Requires `VectorStoreManager` + `ModuleStructure`
- `orchestrator.py` already routes EXPLORATION + QUESTION intents to MODULE_KEEPER (lines 532-540)
- **Only needs agent registration** in `session_tools.py` (resolve TODO at line 175)

### Files to Modify
| File | Change |
|------|--------|
| `session_tools.py` | Add imports, init VectorStoreManager + ModuleIndexer, register agent in `start_session()` and `resume_session()` |
| `orchestrator.py` | Verify routing — already implemented, no changes needed |

### Key Insight
Orchestrator routing is already done. The entire Part A is just about initializing and registering the agent.

---

## Part B: Library Vector Search

### Current State
- `LibrarySearch` in `library/search.py` — TF-IDF with keyword expansion and D&D synonyms
- `LibraryManager` in `library/manager.py` — uses `semantic_search` attribute
- `ask_books()` and `search_library()` in `main.py` call through manager
- `VectorStoreManager` supports arbitrary collections

### Strategy
Create `library/vector_search.py` with `VectorLibrarySearch` class:
- Same `search()` API as `LibrarySearch`
- Returns same `SearchResult` format
- Uses ChromaDB per-source collections: `library_{source_id}`
- `LibraryManager` chooses backend at init time

### Files to Create/Modify
| File | Change |
|------|--------|
| `library/vector_search.py` | **NEW** — VectorLibrarySearch class |
| `library/manager.py` | Backend selection in `__init__()`, vector indexing in `scan_library()` |
| `main.py` | No changes — works transparently |

---

## Part C: Graceful Degradation

### Current Issue
`vector_store.py` imports `chromadb` without try/except — **will crash** if not installed!

### Required Changes
| File | Change |
|------|--------|
| `vector_store.py` | Wrap chromadb import in try/except, set `HAS_CHROMADB` flag |
| `library/vector_search.py` | Try import VectorStoreManager with fallback |
| `library/manager.py` | Choose backend based on available deps |
| `session_tools.py` | Try/except around ModuleKeeper init |

---

## Implementation Order

1. **Phase 1** — Fix `vector_store.py` imports (graceful degradation)
2. **Phase 2** — Create `library/vector_search.py`
3. **Phase 3** — Update `library/manager.py` backend selection
4. **Phase 4** — Wire ModuleKeeper in `session_tools.py`
5. **Phase 5** — Tests for both RAG and fallback paths

## Parallel Streams
- **Stream A**: Parts A + C degradation in session_tools (session wiring)
- **Stream B**: Parts B + C degradation in library (vector search)
- **NOT parallel-safe** — both share `vector_store.py` changes

## Risk Areas
- `vector_store.py` missing try/except causes test_module_keeper.py import error (pre-existing)
- ModuleKeeper requires `ModuleStructure` which comes from adventure modules — may not exist for all campaigns
- Chunk size standardization between ModuleIndexer (500 chars) and library indexing
