# Hybrid Python Integration

This document describes the integration of Python-based deterministic operations into the MCP tool flow for the Claudmaster AI DM system.

## Overview

The Hybrid Python Integration allows deterministic operations (intent classification, data retrieval, consistency checks) to run locally in Python instead of consuming LLM tokens. This improves performance, reduces costs, and provides more reliable, reproducible results.

## Active Python Components

These Python components are **currently wired and operational** in the MCP tool flow:

### 1. Intent Classification (`Orchestrator.classify_intent()`)

- **Location:** `src/dm20_protocol/claudmaster/orchestrator.py`
- **Function:** Classifies player input into intent types (combat, roleplay, exploration, etc.)
- **Method:** Weighted pattern matching with multi-word phrase detection
- **Token Cost:** Zero - fully deterministic Python
- **When Used:** Before every player action in `player_action` MCP tool
- **Output:** Intent type, confidence score, matched patterns, ambiguity flag

**Integration Point:** `src/dm20_protocol/claudmaster/tools/action_tools.py`

```python
# Intent is classified BEFORE LLM processing
intent = orchestrator.classify_intent(action)
# Result included in response metadata
response_dict["_intent_classification"] = {
    "intent_type": intent.intent_type.value,
    "confidence": intent.confidence,
    "matched_patterns": intent.metadata.get("matched_patterns", []),
    "ambiguous": intent.metadata.get("ambiguous", False),
    "python_classified": True
}
```

### 2. Archivist Data Retrieval

- **Location:** `src/dm20_protocol/claudmaster/agents/archivist.py`
- **Function:** Queries character stats, HP, inventory, combat state, conditions
- **Methods Used:**
  - `get_character_stats()` - Full character snapshot
  - `get_character_hp()` - Current HP status with percentage
  - `get_inventory()` - Items and equipment
  - `get_combat_state()` - Initiative order, current turn, round number
  - `get_available_actions()` - Standard D&D combat actions
- **Caching:** 30-second TTL cache to reduce repeated queries
- **Token Cost:** Zero - pure Python data access
- **When Used:** Automatically routed by Orchestrator based on intent type

**Integration Point:** `src/dm20_protocol/claudmaster/tools/session_tools.py`

```python
# Registered when session starts
archivist = ArchivistAgent(
    campaign=campaign,
    rules_lookup_fn=None,  # RAG not yet wired
    cache_ttl=30.0
)
orchestrator.register_agent("archivist", archivist)
```

### 3. Consistency Engine (FactDatabase)

- **Location:** `src/dm20_protocol/claudmaster/consistency/fact_database.py`
- **Function:** Tracks narrative facts for consistency across sessions
- **Features:**
  - Fact storage with categories (event, location, NPC, item, quest, world)
  - Query by category, session, relevance score, tags
  - Fact linking and relationship tracking
  - JSON persistence to disk
- **Token Cost:** Zero - local storage and retrieval
- **When Used:** Session lifecycle (start, pause, resume, end)

**Integration Points:**

- **Session Start:** Initialize FactDatabase from campaign path
- **Session Pause/End:** Save facts to disk
- **Session Resume:** Load facts from disk

```python
# Lifecycle management
fact_db = FactDatabase(campaign_path)  # Auto-loads from disk
self._fact_databases[session_id] = fact_db
# On pause/end:
fact_db.save()
```

## Available But Unused Components

These Python components exist but are **not yet wired** into the MCP flow:

### 1. Narrator Agent (LLM-based)

- **Location:** `src/dm20_protocol/claudmaster/agents/narrator.py`
- **Function:** Generates narrative descriptions and NPC dialogue
- **Blocking Issue:** Requires LLM client implementation
- **Token Cost:** Would consume LLM tokens (not deterministic)
- **Planned Integration:** Phase 2 - once LLM client is wired

### 2. Module Keeper Agent (RAG-based)

- **Location:** `src/dm20_protocol/claudmaster/agents/module_keeper.py`
- **Function:** RAG-based retrieval of adventure module content (NPCs, locations, encounters)
- **Blocking Issue:** Requires vector store manager integration
- **Token Cost:** Zero for retrieval, but requires embedding setup
- **Planned Integration:** Phase 2 - once vector store is ready

**Methods Available:**

- `get_npc_knowledge()` - NPC personality, goals, relationships
- `get_location_description()` - Location details with read-aloud text
- `check_encounter_trigger()` - Check if player actions trigger encounters
- `get_plot_context()` - Current chapter, objectives, foreshadowing

### 3. Rules Lookup (Archivist)

- **Location:** `src/dm20_protocol/claudmaster/agents/archivist.py` (line 776-841)
- **Function:** Search D&D rulebooks for relevant rules
- **Blocking Issue:** Requires vector store integration for rule embeddings
- **Token Cost:** Zero for retrieval (RAG-based)
- **Planned Integration:** Phase 2 - once vector store contains rulebook data

## Architecture: Deterministic vs LLM Operations

```
┌─────────────────────────────────────────────────────────┐
│                    player_action                        │
│                   (MCP Tool Entry)                       │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
       ┌──────────────────────┐
       │  classify_intent()   │  ◄─── Python (zero tokens)
       │   (Orchestrator)     │
       └──────────┬───────────┘
                  │
                  ▼
       ┌──────────────────────┐
       │   Orchestrator       │
       │  process_player_     │
       │     input()          │
       └──────────┬───────────┘
                  │
         ┌────────┴────────┐
         │                 │
         ▼                 ▼
  ┌─────────────┐   ┌─────────────┐
  │  Archivist  │   │  Narrator   │  ◄─── LLM (tokens)
  │   (Python)  │   │   (LLM)     │       (not yet wired)
  └─────────────┘   └─────────────┘
         │
         ▼
  ┌─────────────────────┐
  │ Data Retrieval      │  ◄─── Python (zero tokens)
  │ - Character stats   │
  │ - Combat state      │
  │ - HP/Inventory      │
  └─────────────────────┘
```

## Response Metadata

The `player_action` tool now includes intent classification metadata in every response:

```json
{
  "narrative": "...",
  "action_type": "combat",
  "state_changes": [...],
  "dice_rolls": [...],
  "_intent_classification": {
    "intent_type": "combat",
    "confidence": 0.9,
    "matched_patterns": ["attack", "cast spell"],
    "ambiguous": false,
    "python_classified": true,
    "alternative_intent": null,
    "score_gap": null
  }
}
```

The `_intent_classification` key is internal metadata that Claude (the DM) can use to decide how to respond, but is not part of the player-facing narrative.

## Benefits

1. **Performance:** Intent classification happens instantly without LLM latency
2. **Cost:** Zero tokens consumed for classification and data retrieval
3. **Reliability:** Deterministic pattern matching ensures reproducible results
4. **Debugging:** Clear logs showing Python operations vs LLM calls
5. **Caching:** Archivist caches frequently accessed data for 30 seconds

## Future Enhancements (Phase 2)

1. **Wire Narrator with LLM client** - Enable narrative generation
2. **Integrate Vector Store** - Enable Module Keeper RAG and rules lookup
3. **Consistency Agent** - Auto-detect contradictions and suggest resolutions
4. **Fact Tracking** - Auto-populate FactDatabase from agent observations
5. **Multi-agent Coordination** - Parallel agent execution with aggregation

## Testing

To verify hybrid integration is working:

1. **Check logs for Python operations:**
   ```
   [Hybrid Python] Intent classified: combat (confidence: 0.9)
   [Hybrid Python] Registered ArchivistAgent for data retrieval
   [Hybrid Python] Initialized FactDatabase at /path/to/campaign
   ```

2. **Inspect response metadata:**
   ```python
   response = await player_action(session_id, "I attack the orc")
   assert response["_intent_classification"]["python_classified"] == True
   ```

3. **Monitor token usage:**
   - Intent classification should consume 0 tokens
   - Data retrieval should consume 0 tokens
   - Only narrative generation consumes tokens (when Narrator is wired)

## Files Modified

- `src/dm20_protocol/claudmaster/tools/action_tools.py` - Intent classification wiring
- `src/dm20_protocol/claudmaster/tools/session_tools.py` - Agent registration and FactDatabase lifecycle
- `docs/hybrid-python-integration.md` - This documentation

## Related Documentation

- `src/dm20_protocol/claudmaster/orchestrator.py` - Intent classification implementation
- `src/dm20_protocol/claudmaster/agents/archivist.py` - Data retrieval methods
- `src/dm20_protocol/claudmaster/consistency/fact_database.py` - Fact persistence
- `README.md` - Claudmaster AI DM overview
