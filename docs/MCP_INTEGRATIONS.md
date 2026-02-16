# MCP Server Integrations Roadmap

Tracking potential MCP server integrations that could enhance dm20-protocol through FastMCP's native composition capabilities (`mount()`, `import_server()`, `create_proxy()`).

> **Integration Pattern:** Each server would be mounted as an optional dependency, namespaced to avoid tool conflicts. Users install only what they need.

---

## Integration Architecture

```
dm20-protocol (main server)
├── [MOUNT] knowledge-graph       ← World memory & relationships
├── [MOUNT] chroma-mcp            ← Enhanced RAG for PDF rulebooks
├── [MOUNT] foundryvtt-mcp        ← VTT bridge (optional)
├── [MOUNT] image-gen-mcp         ← Image generation (optional)
├── [MOUNT] mcp-tts               ← Voice narration (optional)
│
├── campaign/     (native tools)
├── combat/       (native tools)
├── library/      (native tools)
└── claudmaster/  (native tools)
```

---

## TIER 1 — High Value, Direct Impact

### 1. Knowledge Graph Memory

| Field | Details |
|-------|---------|
| **Purpose** | Persistent semantic memory for game world relationships |
| **Repository** | [modelcontextprotocol/servers/memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) |
| **Alternatives** | [MemoryMesh](https://github.com/CheMiguel23/MemoryMesh) (structured schemas) · [Memento MCP](https://github.com/gannonh/memento-mcp) (semantic retrieval + temporal awareness) |
| **Language** | TypeScript (official) / Python (community forks) |
| **Priority** | **P0** |
| **Status** | Not started |

**Why it matters:**
- Track NPC relationships ("the merchant knows the bandit")
- Remember narrative facts across sessions
- Feed the Claudmaster Consistency Engine with structured relational data
- Complements `storage.py` — doesn't replace it, enriches it

**Integration notes:**
- Official server is TypeScript — would need `create_proxy()` with stdio transport
- Python alternatives (memento-mcp) could use direct `mount()`
- Storage format: line-delimited JSON (compatible with dm20's JSON-based storage)

---

### 2. ChromaDB MCP Server

| Field | Details |
|-------|---------|
| **Purpose** | Vector database tools for enhanced RAG on PDF rulebooks |
| **Repository** | [chroma-core/chroma-mcp](https://github.com/chroma-core/chroma-mcp) |
| **Language** | Python |
| **Priority** | **P0** |
| **Status** | Not started |

**Why it matters:**
- dm20-protocol already has `chromadb` as optional dependency for RAG
- This server exposes collection management and semantic queries as explicit MCP tools
- Significant upgrade to the `library/search.py` system
- LLM can directly create, query, and manage vector collections

**Integration notes:**
- Natural fit — same language (Python), same dependency
- Could `mount()` directly with namespace `rag`
- Shares the `chromadb` dependency already in `pyproject.toml[rag]`

---

### 3. FoundryVTT MCP

| Field | Details |
|-------|---------|
| **Purpose** | Bridge between dm20-protocol and FoundryVTT virtual tabletop |
| **Repository** | [laurigates/foundryvtt-mcp](https://github.com/laurigates/foundryvtt-mcp) |
| **Language** | TypeScript |
| **Priority** | **P1** |
| **Status** | Not started |

**Why it matters:**
- FoundryVTT is the most popular VTT platform
- Sync dm20 characters ↔ FoundryVTT actors
- Run combat with real maps and tokens
- dm20-protocol becomes the "AI brain" behind a FoundryVTT session

**Integration notes:**
- TypeScript → requires `create_proxy()` with stdio transport
- Requires user to have FoundryVTT running — strictly optional dependency
- API key / connection config needed

---

## TIER 2 — Medium-High Value, Experience Boost

### 4. Image Generation MCP

| Field | Details |
|-------|---------|
| **Purpose** | Generate character portraits, battle maps, scene illustrations |
| **Options** | [sarthakkimtani/mcp-image-gen](https://github.com/sarthakkimtani/mcp-image-gen) (Together AI, Python) · [spartanz51/imagegen-mcp](https://github.com/spartanz51/imagegen-mcp) (OpenAI, editing) · [lansespirit/image-gen-mcp](https://github.com/lansespirit/image-gen-mcp) (multi-provider) |
| **Language** | Python / TypeScript (varies) |
| **Priority** | **P1** |
| **Status** | Not started |

**Why it matters:**
- Narrator Agent generates a portrait while describing an NPC
- Battle maps generated on the fly
- Transforms text-only sessions into visual experiences

**Integration notes:**
- Requires external API key (OpenAI, Together AI, etc.)
- Python options available → direct `mount()` possible
- Should be behind a feature flag / optional install

---

### 5. Text-to-Speech MCP

| Field | Details |
|-------|---------|
| **Purpose** | Voice narration for Claudmaster sessions |
| **Options** | [blacktop/mcp-tts](https://github.com/blacktop/mcp-tts) (multi-backend: macOS, ElevenLabs, OpenAI, Google) · [Kvadratni/speech-mcp](https://github.com/Kvadratni/speech-mcp) (54+ voices, multi-character dialogues) |
| **Language** | Go / Python |
| **Priority** | **P2** |
| **Status** | Not started |

**Why it matters:**
- Different voices for different NPCs
- Atmospheric narration from the Narrator Agent
- Transforms Claudmaster into an audio-immersive experience

**Integration notes:**
- `blacktop/mcp-tts` includes free macOS `say` backend (no API key needed)
- Premium backends (ElevenLabs, OpenAI) require API keys
- `speech-mcp` uses Kokoro TTS (local, free) — best for zero-config experience

---

### 6. Mapbox MCP

| Field | Details |
|-------|---------|
| **Purpose** | Geographic maps for worldbuilding inspiration |
| **Repository** | [mapbox/mcp-server](https://github.com/mapbox/mcp-server) |
| **Language** | TypeScript |
| **Priority** | **P2** |
| **Status** | Not started |

**Why it matters:**
- Generate realistic terrain as worldbuilding reference
- Feed the Location system with geographic data
- Useful for hex-crawl and exploration campaigns

**Integration notes:**
- Requires Mapbox API key (free tier available)
- TypeScript → `create_proxy()` needed

---

## TIER 3 — Nice to Have, Future Expansions

### 7. RPG Content Generator

| Field | Details |
|-------|---------|
| **Purpose** | Procedural generation of campaigns, regions, NPCs |
| **Repository** | [guyroyse/rpg-generator-mcp-server](https://github.com/guyroyse/rpg-generator-mcp-server) |
| **Priority** | **P3** |
| **Status** | Not started |

**Notes:** Useful but dm20 could implement this internally with higher quality and tighter integration.

---

### 8. Audio/Sound Effects

| Field | Details |
|-------|---------|
| **Purpose** | Ambient sounds and combat effects |
| **Repository** | [peerjakobsen/audiogen-mcp](https://github.com/peerjakobsen/audiogen-mcp) (Meta AudioGen) |
| **Priority** | **P3** |
| **Status** | Not started |

**Notes:** Complementary to TTS. Adds atmosphere to combat and exploration scenes.

---

### 9. Mnehmos RPG MCP (Spatial Combat)

| Field | Details |
|-------|---------|
| **Purpose** | Advanced spatial combat system with 3D visualization |
| **Repository** | [Mnehmos/rpg-mcp-servers](https://github.com/mnehmos/rpg-mcp-servers) |
| **Priority** | **P3** |
| **Status** | Not started |

**Notes:** Already a reference project for dm20-protocol. Could inspire or integrate with the combat system. ASCII-based spatial rendering.

---

## Technical Implementation Notes

### FastMCP Composition APIs

```python
# Pattern 1: Direct mount (Python servers)
mcp.mount(sub_server, namespace="memory")

# Pattern 2: Static import (frozen copy)
mcp.import_server(sub_server, namespace="rag")

# Pattern 3: Proxy (TypeScript/remote servers)
from fastmcp.server import create_proxy
proxy = create_proxy("./node_modules/.bin/memory-server", name="Memory")
mcp.mount(proxy, namespace="memory")
```

### Optional Dependencies Strategy

```toml
# pyproject.toml
[project.optional-dependencies]
memory = ["memento-mcp>=1.0"]
rag = ["chromadb>=0.4.0", "sentence-transformers>=2.2.0", "chroma-mcp>=0.1"]
tts = ["speech-mcp>=1.0"]
images = ["mcp-image-gen>=0.1"]
all = ["dm20-protocol[memory,rag,tts,images]"]
```

### Context Window Budget

| Component | Estimated Tools | Notes |
|-----------|----------------|-------|
| dm20-protocol (native) | ~66 | Current baseline |
| Knowledge Graph | ~5-8 | create/read/update/delete entities + relations |
| ChromaDB | ~6-10 | create/query/manage collections |
| Image Gen | ~2-3 | generate/edit image |
| TTS | ~3-5 | speak/narrate/list_voices |
| **Total with all** | **~85-92** | Monitor LLM tool selection accuracy |

> **Warning:** Beyond ~80-100 tools, LLM accuracy in selecting the right tool can degrade. Consider lazy-loading or feature flags to keep active tool count manageable.

---

## References

- [FastMCP Composition Docs](https://gofastmcp.com/servers/providers/mounting)
- [FastMCP Proxy Docs](https://www.jlowin.dev/blog/fastmcp-proxy)
- [Awesome MCP Servers (curated list)](https://github.com/punkpeye/awesome-mcp-servers)
- [Official MCP Servers](https://github.com/modelcontextprotocol/servers)
- [MCP Awesome Directory (1200+)](https://mcp-awesome.com/)
