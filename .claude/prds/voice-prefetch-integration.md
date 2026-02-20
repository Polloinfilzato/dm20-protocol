---
name: voice-prefetch-integration
description: Wire the existing TTS voice engine and prefetch engine into the live Party Mode flow — close the gap between built-but-unused infrastructure and a working narrated game session
status: draft
created: 2026-02-20T00:00:00Z
---

# PRD: Voice & Prefetch Integration

## Executive Summary

The DM20 Experience Enhancement epic (issues #172–#176) built two major subsystems —
a 3-tier TTS router (`dm20_protocol/voice/`) and a combat prefetch engine
(`dm20_protocol/prefetch/`) — but neither is wired into the live game loop.
This PRD closes that gap: install the missing voice dependencies, connect TTS to
`party_resolve_action`, and integrate `PrefetchEngine` into the combat turn cycle
so that narrated sessions and latency reduction work end-to-end.

**Key deliverables:**
1. **Voice Dependencies** — `edge-tts` (cloud fallback) and optional local engines
   (`kokoro`, `mlx-audio`) added to `pyproject.toml [voice]` extras and installed
2. **TTS Integration** — `_party_tts_speak` fully operational: initialises
   `TTSRouter` once at Party Mode startup, synthesises narrative after every
   `party_resolve_action`, streams audio to DM speakers (afplay) and to connected
   browser players via WebSocket
3. **Prefetch Integration** — `PrefetchEngine` instantiated at Party Mode startup
   using `AnthropicLLMClient` (already in `claudmaster/llm_client.py`); fires
   pre-generation on combat turn start, refines on resolution
4. **Smoke-Test Suite** — `tests/integration/test_voice_prefetch_integration.py`
   covering the full path from `party_resolve_action` call → TTS synthesis → audio
   delivery and from game-state change → prefetch trigger → resolve

**Value proposition:** Turn the existing ~3 000 lines of voice/prefetch code from
tested-but-idle infrastructure into a working narrated D&D session experience.

---

## Problem Statement

### Current State

```
# party_resolve_action already calls _party_tts_speak at line ~5050
_party_tts_speak(narrative, server)

# BUT _party_tts_speak silently fails because:
# 1. edge-tts is not installed → TTSRouter import succeeds but zero engines available
# 2. Even if installed: interaction_mode defaults to "classic" → early return
# 3. Even if mode is "narrated": TTSRouter is never pre-initialised, first call is cold

# PrefetchEngine never instantiated anywhere in main.py
grep -n "PrefetchEngine" src/dm20_protocol/main.py  # → 0 results
```

The gap exists because the epic's task decomposition built each subsystem in isolation
(correct for parallel development) but did not include an explicit integration task.

### Problems

1. **TTS Never Plays** — `edge-tts` and other voice packages not in `pyproject.toml`;
   `TTSRouter` finds zero available engines; all narration is silently skipped
2. **Cold Start Latency** — `TTSRouter` initialises on first call instead of at
   Party Mode startup; first synthesis blocks the response for 1–2 extra seconds
3. **Audio Not Streamed to Players** — `_party_tts_speak` plays audio only on the
   DM's Mac via `afplay`; browser players in Party Mode receive no audio signal
4. **Prefetch Never Fires** — `PrefetchEngine` is instantiated nowhere; combat
   narrative pre-generation never happens; tiered-latency benefit is zero
5. **No LLM Client Wired to Prefetch** — `PrefetchEngine` requires a `LLMClient`
   implementor; `AnthropicLLMClient` in `claudmaster/llm_client.py` matches the
   protocol but is never connected

### Why Now?

- All subsystem code is already written, reviewed, and tested (~3 000 lines, 181 tests)
- The only missing pieces are wiring calls (initialisation + integration hooks)
- Users expect narrated sessions after configuring `interaction_mode = "narrated"`
- Party Mode is the primary multi-player surface — audio streaming matters most there

### Target User Scenario

```
DM: /dm:profile → sets interaction_mode = "narrated"
DM: /dm:party-auto
   [Party Mode starts. TTSRouter initialises in background. Edge-TTS available.]

Player: "I attack the goblin with my longsword!"
DM AI processes the action:
   → prefetch engine had already pre-generated hit/miss/crit variants
   → selects "hit" variant, refines with actual dice roll via Haiku
   → party_resolve_action called with narrative text
   → _party_tts_speak synthesises audio in <300ms (edge-tts cloud)
   → afplay speaks narration on DM Mac speakers
   → WebSocket broadcasts audio chunks to all browser players
   → Players hear DM narration without reading the screen

Next turn:
   → PrefetchEngine observes game state: it's still combat, Theron's turn is next
   → Pre-generates hit/miss/crit variants for Theron's likely attack
   → When Theron acts, response is near-instant (<500ms vs 3-5s baseline)
```

---

## Architecture Overview

### Integration Points (New Wiring Only)

```
                    start_party_mode()
                          │
                          ├──▶ TTSRouter.initialize()          [NEW]
                          │    (background, non-blocking)
                          │
                          └──▶ PrefetchEngine(                 [NEW]
                               main_model=AnthropicLLMClient(haiku),
                               refinement_model=AnthropicLLMClient(haiku)
                               )

party_resolve_action(narrative)
          │
          ├──▶ server.response_queue.push(...)    [existing]
          │
          ├──▶ _party_tts_speak(narrative, server)  [existing hook, needs fix]
          │         │
          │         ├── mode check ("narrated" / "immersive")
          │         ├── TTSRouter.synthesize(text, context="narration")
          │         │       └── EdgeTTSEngine (Tier 3 fallback, always available)
          │         │           KokoroEngine  (Tier 1, Apple Silicon optional)
          │         │           Qwen3Engine   (Tier 2, Apple Silicon optional)
          │         ├── afplay audio on DM Mac          [existing]
          │         └── WebSocket broadcast to players  [NEW — FR-B3]
          │
          └──▶ prefetch_engine.on_state_change(game_state)  [NEW]
                    └── schedules pre_generate_combat_variants() as asyncio task

next_turn() / start_combat()
          └──▶ prefetch_engine.on_state_change(game_state)  [NEW]
```

### TTS Engine Tier Map (Apple Silicon Mac)

```
Context        Tier Selected    Engine           Latency
─────────────────────────────────────────────────────────
combat         speed            Kokoro 82M        <300ms   (optional, local)
narration      quality          Qwen3-TTS 0.6B    ~800ms   (optional, local MLX)
dialogue       quality          Qwen3-TTS 0.6B    ~800ms
any            fallback         Edge-TTS          ~350ms   (always, cloud/free)
```

### Prefetch Data Flow (Party Mode)

```
start_combat() or next_turn()
       │
       └──▶ PrefetchEngine.on_state_change(game_state)
                  │
                  └── observer detects: combat + player turn
                            │
                            └──▶ asyncio.create_task(
                                   pre_generate_combat_variants(
                                     player_turn=PlayerTurn(
                                       character_name, class, target, weapon
                                     )
                                   )
                                 )
                                   │
                                   ├── Haiku generates: hit variant
                                   ├── Haiku generates: miss variant
                                   └── Haiku generates: crit variant
                                             └──▶ PrefetchCache.store(turn_id, variants)

party_resolve_action()   ← player acts seconds later
       │
       └──▶ prefetch_engine.resolve_with_actual(turn_id, {outcome, roll, damage})
                  │
                  ├── cache HIT  → Haiku refines selected variant   (<500ms)
                  └── cache MISS → Haiku full generation             (1-2s)
```

---

## User Stories

### US-1: Hear DM Narration in Party Mode

**As a** player connected via browser in a Narrated session
**I want to** hear the DM's narrative spoken aloud after each action resolution
**So that** I can follow the story without staring at a screen

**Acceptance Criteria:**
- [ ] Setting `interaction_mode = "narrated"` via `/dm:profile` enables TTS output
- [ ] After `party_resolve_action`, DM hears narrative on Mac speakers within 1s
- [ ] Browser players receive audio chunks via WebSocket and auto-play them
- [ ] Audio plays consistently for every action in a 30-minute session
- [ ] If TTS fails (network down), text narrative still delivered normally

### US-2: Faster Combat Responses via Prefetch

**As a** DM running a combat encounter in Party Mode
**I want** narrative responses to appear near-instantly after dice rolls
**So that** the game pace doesn't break when the AI generates descriptions

**Acceptance Criteria:**
- [ ] On combat turn start, PrefetchEngine pre-generates hit/miss/crit variants in background
- [ ] `party_resolve_action` narrative latency reduced by ≥40% on cache hit
- [ ] If prefetch cache misses (unexpected action), full generation still works
- [ ] Prefetch does not delay or block the `party_resolve_action` response
- [ ] Session summary includes prefetch cache hit rate

### US-3: TTS Starts Ready, Not Cold

**As a** DM starting Party Mode
**I want** TTS to be already initialised when the first action resolves
**So that** the first narrative isn't slower than all the others

**Acceptance Criteria:**
- [ ] `start_party_mode` triggers `TTSRouter.initialize()` in the background
- [ ] First TTS call after the first action is warm (no cold-init delay)
- [ ] Initialization errors are logged but do not abort Party Mode startup

### US-4: Edge-TTS Available as Guaranteed Fallback

**As a** DM without Kokoro or Qwen3-TTS installed
**I want** at least the cloud fallback engine to work out-of-the-box
**So that** I can hear narration without installing large local models

**Acceptance Criteria:**
- [ ] `pip install dm20-protocol[voice]` installs `edge-tts` and makes TTS functional
- [ ] `pyproject.toml [voice]` extras group includes `edge-tts` (required) plus
  `kokoro`, `mlx-audio` (optional / Apple Silicon)
- [ ] `TTSRouter` reports "edge-tts available" in startup log
- [ ] Narration works end-to-end in a Party Mode session with only edge-tts installed

---

## Requirements

### Functional Requirements

#### A — Voice Dependency Packaging

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-A1 | Add `edge-tts` to `pyproject.toml` as `[voice]` optional dependency | Must |
| FR-A2 | Add `kokoro` and `mlx-audio` to `[voice]` extras (Apple Silicon, optional) | Should |
| FR-A3 | `TTSRouter.is_available()` returns True when at least edge-tts is installed | Must |
| FR-A4 | `dm20-protocol[voice]` installs successfully with `uv pip install` | Must |

#### B — TTS Wiring into Party Mode

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-B1 | `start_party_mode` initialises `TTSRouter` asynchronously on startup | Must |
| FR-B2 | Single `TTSRouter` instance stored on the server object (`server.tts_router`) | Must |
| FR-B3 | `_party_tts_speak` broadcasts encoded audio chunks to browser players via WebSocket | Must |
| FR-B4 | Audio message format: `{"type": "audio", "format": "mp3", "data": "<base64>"}` | Must |
| FR-B5 | `_party_tts_speak` uses `server.tts_router` if available; falls back to cold init | Should |
| FR-B6 | TTS context derived from narrative content: "combat" if combat-related, else "narration" | Should |
| FR-B7 | TTS failures logged at WARNING level; text delivery unaffected | Must |

#### C — Prefetch Wiring into Party Mode

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-C1 | `start_party_mode` instantiates `PrefetchEngine` with `AnthropicLLMClient` (haiku for both tiers) | Must |
| FR-C2 | Single `PrefetchEngine` stored on server object (`server.prefetch_engine`) | Must |
| FR-C3 | `party_resolve_action` calls `prefetch_engine.on_state_change(game_state)` after resolution | Must |
| FR-C4 | `next_turn` (combat) calls `prefetch_engine.on_state_change(game_state)` after advancing turn | Must |
| FR-C5 | `start_combat` calls `prefetch_engine.on_state_change(game_state)` after combat begins | Should |
| FR-C6 | `ANTHROPIC_API_KEY` env var used for `AnthropicLLMClient`; missing key disables prefetch with WARNING | Must |
| FR-C7 | Prefetch intensity defaults to "conservative" (only combat turns trigger pre-generation) | Must |
| FR-C8 | Session summary (`summarize_session`) includes `prefetch_engine.get_token_summary()` | Should |

#### D — Browser Audio Streaming

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-D1 | Party Mode WebSocket handler accepts `{"type": "audio", ...}` broadcast messages | Must |
| FR-D2 | Player browser auto-plays received audio via `<audio>` element or Web Audio API | Must |
| FR-D3 | Audio playback does not block the UI or player action submission | Must |
| FR-D4 | If no browser players connected, audio plays only on DM Mac (existing afplay) | Must |

### Non-Functional Requirements

| ID | Requirement | Target | Priority |
|----|-------------|--------|----------|
| NFR-1 | Time from `party_resolve_action` call to first audio byte (edge-tts) | < 500ms | Must |
| NFR-2 | Time from `party_resolve_action` call to first audio byte (kokoro) | < 350ms | Should |
| NFR-3 | TTS initialisation does not block Party Mode startup | 0ms (async) | Must |
| NFR-4 | Prefetch pre-generation does not block `party_resolve_action` response | 0ms (asyncio task) | Must |
| NFR-5 | Prefetch latency reduction on cache hit | ≥ 40% vs baseline | Should |
| NFR-6 | Memory added by `TTSRouter` with edge-tts only | < 50MB | Must |
| NFR-7 | Memory added by `PrefetchEngine` (cache + observer only) | < 10MB | Must |
| NFR-8 | No regressions in existing Party Mode tests | 100% pass rate | Must |

---

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| TTS plays in narrated Party Mode session | 100% of `party_resolve_action` calls | Manual: 10-action session |
| Browser players hear audio | Audio received in player UI | Browser devtools: WebSocket audio frames |
| edge-tts installs via `[voice]` extras | `uv pip install dm20-protocol[voice]` succeeds | CI / manual |
| Prefetch fires in combat | Observer triggers for every combat turn | Log: "Pre-generating combat variants" |
| Prefetch cache hit rate | ≥ 50% after 3+ combat turns | Session summary token report |
| Existing Party Mode tests pass | Zero regressions | `uv run pytest tests/test_party*` |

---

## Constraints and Assumptions

### Constraints

1. **`ANTHROPIC_API_KEY` Required for Prefetch** — Pre-generation calls Haiku via API; if the key
   is absent, prefetch is gracefully disabled (not a fatal error)
2. **edge-tts Requires Internet** — Cloud fallback needs connectivity; in offline scenarios
   only local engines (kokoro, qwen3) work; if none available, TTS is silently skipped
3. **afplay macOS Only** — Local DM audio playback is macOS-specific; browser audio streaming
   is cross-platform
4. **Party Mode WebSocket Protocol** — Audio messages added to existing WebSocket protocol;
   player UI JavaScript must handle `"type": "audio"` messages

### Assumptions

1. `ANTHROPIC_API_KEY` is set in the DM's environment (required for CC itself to run)
2. User has run `/dm:profile` and set `interaction_mode` to `"narrated"` or `"immersive"`
   before expecting TTS output
3. `claudmaster/llm_client.py:AnthropicLLMClient` satisfies `prefetch/engine.py:LLMClient`
   protocol (both have `async generate(prompt, max_tokens) -> str`)
4. Browser players are using Chrome or Safari (Web Audio API support)

---

## Out of Scope

1. **Kokoro / Qwen3-TTS model download** — Installing and testing local Apple Silicon engines;
   this PRD targets edge-tts as the guaranteed baseline
2. **Voice Registry per NPC** — NPC-specific voice configuration (built in `voice/registry.py`);
   this PRD wires the router for DM narration only
3. **STT (Speech-to-Text) from browser** — Web Speech API integration in player UI (issue #175
   built it but integration parity is separate work)
4. **Prefetch for exploration / NPC dialogue** — Only combat turns in scope; observer already
   supports these contexts but wiring is limited to combat for now
5. **Prefetch with non-Anthropic LLMs** — `AnthropicLLMClient` only; OpenAI/local adapters are
   future work

---

## Dependencies

### External Dependencies

| Dependency | Purpose | Version | License | Install Group |
|-----------|---------|---------|---------|---------------|
| `edge-tts` | Cloud TTS fallback (free, Microsoft) | ≥ 6.1 | GPL-3.0 | `[voice]` required |
| `kokoro` | Local speed-tier TTS (Apple Silicon) | ≥ 0.9 | Apache 2.0 | `[voice]` optional |
| `mlx-audio` | Apple Silicon inference backend | Latest | MIT | `[voice]` optional |
| `anthropic` | API client for prefetch LLM calls | ≥ 0.40 | MIT | `[claudmaster]` (existing) |

### Internal Dependencies

```
voice/router.py          ← already built (issue #173)
voice/engines/edge_tts.py ← already built (issue #173)
voice/hardware.py        ← already built (issue #173)
prefetch/engine.py       ← already built (issue #172)
prefetch/observer.py     ← already built (issue #172)
prefetch/cache.py        ← already built (issue #172)
claudmaster/llm_client.py:AnthropicLLMClient  ← existing, reused for prefetch

main.py: start_party_mode()     ← wiring point for init
main.py: party_resolve_action() ← wiring point for TTS + prefetch state update
main.py: next_turn()            ← wiring point for prefetch state update
main.py: _party_tts_speak()     ← existing function, needs WebSocket broadcast added
party/server.py (or equivalent) ← stores tts_router and prefetch_engine as attributes
```

### Implementation Order

```
Phase 1 — Dependencies (no code changes)
  1. Add edge-tts to pyproject.toml [voice]
  2. uv pip install "dm20-protocol[voice]"
  UNBLOCKS: all Phase 2 work

Phase 2 — TTS Wiring (parallel streams possible)
  Stream A: start_party_mode initialises TTSRouter on server object
  Stream B: _party_tts_speak uses server.tts_router + WebSocket broadcast
  Stream C: Player UI JS handles {"type": "audio"} WebSocket messages

Phase 3 — Prefetch Wiring (after Phase 1)
  Stream A: start_party_mode instantiates PrefetchEngine with AnthropicLLMClient
  Stream B: party_resolve_action + next_turn call on_state_change

Phase 4 — Integration Tests + Session Summary
  test_voice_prefetch_integration.py
  summarize_session includes prefetch token summary
```

---

## Technical Notes

### pyproject.toml Change

```toml
[project.optional-dependencies]
voice = [
    "edge-tts>=6.1",            # Cloud fallback, always available
    "kokoro>=0.9; sys_platform == 'darwin'",   # Local speed tier (optional)
    "mlx-audio; sys_platform == 'darwin'",     # Apple Silicon inference (optional)
]
```

### TTSRouter Init in start_party_mode

```python
# In start_party_mode(), after server object is created:
async def _init_tts(srv):
    try:
        from .voice import TTSRouter
        srv.tts_router = TTSRouter()
        await srv.tts_router.initialize()
        logger.info("TTSRouter ready: %s", srv.tts_router.get_status())
    except Exception as exc:
        logger.warning("TTSRouter init failed, TTS disabled: %s", exc)
        srv.tts_router = None

asyncio.get_event_loop().create_task(_init_tts(server))
```

### _party_tts_speak: WebSocket Broadcast

```python
# After afplay block, add:
if audio_data:
    import base64
    audio_msg = {
        "type": "audio",
        "format": "mp3",
        "data": base64.b64encode(audio_data).decode(),
    }
    try:
        server.broadcast(audio_msg)   # existing broadcast method
    except Exception as exc:
        logger.warning("Audio broadcast failed: %s", exc)
```

### PrefetchEngine Init in start_party_mode

```python
# In start_party_mode():
try:
    from .prefetch import PrefetchEngine
    from .claudmaster.llm_client import AnthropicLLMClient
    haiku = AnthropicLLMClient(model="claude-haiku-4-5-20251001")
    server.prefetch_engine = PrefetchEngine(
        main_model=haiku,
        refinement_model=haiku,
        intensity="conservative",
    )
    logger.info("PrefetchEngine ready (intensity=conservative)")
except Exception as exc:
    logger.warning("PrefetchEngine init failed, prefetch disabled: %s", exc)
    server.prefetch_engine = None
```

### Prefetch Hook in party_resolve_action

```python
# At end of party_resolve_action, after _party_tts_speak:
if getattr(server, "prefetch_engine", None):
    try:
        game_state = json.loads(get_game_state())
        server.prefetch_engine.on_state_change(game_state)
    except Exception as exc:
        logger.debug("Prefetch state update failed: %s", exc)
```

### Player UI Audio Handling (JavaScript)

```javascript
// In party-mode player UI — add to existing ws.onmessage handler:
if (msg.type === "audio") {
    const bytes = Uint8Array.from(atob(msg.data), c => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: "audio/mpeg" });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => URL.revokeObjectURL(url);
    audio.play().catch(() => {});  // Ignore autoplay policy errors silently
}
```

---

## References

- `src/dm20_protocol/voice/` — Built in issue #173 (TTS Engine Core)
- `src/dm20_protocol/prefetch/` — Built in issue #172 (Prefetch Engine)
- `src/dm20_protocol/claudmaster/llm_client.py` — `AnthropicLLMClient` for prefetch
- `src/dm20_protocol/main.py:4926` — `_party_tts_speak` (existing hook, needs completion)
- `src/dm20_protocol/main.py:5050` — `_party_tts_speak` call in `party_resolve_action`
- PRD: `dm20-experience-enhancement.md` — Parent epic that built the subsystems
- Edge-TTS: https://github.com/rany2/edge-tts
- Kokoro: https://huggingface.co/hexgrad/Kokoro-82M
