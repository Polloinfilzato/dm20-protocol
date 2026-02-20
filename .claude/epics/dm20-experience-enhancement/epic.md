---
name: dm20-experience-enhancement
status: backlog
created: 2026-02-19T23:07:40Z
progress: 87%
prd: .claude/prds/dm20-experience-enhancement.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/168
---

# Epic: DM20 Experience Enhancement Suite

## Overview

Comprehensive enhancement of DM20 across three phases: (1) foundation improvements requiring no new dependencies (standalone rules, stable tokens, QR display, import report), (2) intelligent prefetch for latency reduction, and (3) voice interaction via free open-source TTS/STT engines. The approach maximizes reuse of existing infrastructure (WebSocket, RulebookManager, party-mode auth) while introducing new capabilities incrementally.

## Architecture Decisions

### Rules Engine: Global + Per-Campaign Dual Manager
- **Decision:** Create a global `RulebookManager` at server startup (5etools, 2024 default) that serves standalone queries. When a campaign is loaded, its own manager takes priority.
- **Rationale:** Minimal change — the existing `RulebookManager` class works as-is; we only change where/when it's instantiated and add a fallback chain in MCP tool handlers.
- **Pattern:** Strategy pattern — `manager = storage.rulebook_manager or global_rulebook_manager`

### Party Tokens: Deterministic ID-Based
- **Decision:** Token = character ID (the character name string). Comment out old `secrets.token_urlsafe()` generation.
- **Rationale:** LAN-only context makes cryptographic tokens unnecessary. Simplicity > security for this use case. Old code preserved as comments for future internet-facing mode.

### Prefetch: Context-Aware Cache + Tiered Model Inference
- **Decision:** Scenario A (simple prefetch) with tiered model cascade — main model pre-generates variants, Haiku selects and refines.
- **Rationale:** Covers the highest-value case (combat) with moderate effort. Tiered inference reduces refinement latency by 60-70% and token cost by 80%.
- **Pattern:** Observer pattern for game state monitoring, Strategy pattern for model tier selection.

### Voice: 3-Tier TTS Router with Hardware Detection
- **Decision:** Kokoro (speed, local) → Qwen3-TTS (quality, local/MLX) → Edge-TTS (fallback, cloud/free). Piper replaces Kokoro on Intel Macs.
- **Rationale:** All engines are free. Apple Silicon gets full local stack; Intel degrades gracefully to cloud. Zero monthly cost.
- **Technology:** mlx-audio for Apple Silicon inference, edge-tts Python library for cloud fallback, Web Speech API for browser STT.

### Interaction Modes: Orthogonal to Model Profiles
- **Decision:** Campaign stores `interaction_mode` (classic/narrated/immersive) separately from `model_profile` (quality/balanced/economy).
- **Rationale:** Two independent axes. Mixing them would create 9 profiles; separating them gives 3+3 choices with any combination.

## Technical Approach

### Backend Components

**Modified Existing:**
- `src/dm20_protocol/main.py` — MCP tool handlers for rules (fallback to global manager), `create_campaign()` (add `rules_version` and `interaction_mode` params), import result formatting
- `src/dm20_protocol/storage.py` — Global rulebook manager initialization, campaign manifest schema (version, interaction_mode)
- `src/dm20_protocol/party/auth.py` — TokenManager: deterministic token generation
- `src/dm20_protocol/party/server.py` — WebSocket audio message type, QR terminal output
- `src/dm20_protocol/importers/dndbeyond/mapper.py` — Enhanced result reporting

**New Modules:**
- `src/dm20_protocol/voice/` — Voice engine package
  - `router.py` — TTSRouter with 3-tier selection
  - `engines/` — Engine wrappers (kokoro, qwen3, edge_tts, piper)
  - `registry.py` — Voice registry management (per-campaign YAML)
  - `streaming.py` — WebSocket audio chunk delivery
  - `hardware.py` — Apple Silicon / Intel detection
- `src/dm20_protocol/prefetch/` — Prefetch engine package
  - `observer.py` — Game state context observer
  - `cache.py` — Prefetch variant cache with TTL
  - `engine.py` — Pre-generation + Haiku refinement pipeline

### Frontend Components

**Modified Existing:**
- `src/dm20_protocol/party/static/` — Player UI
  - Add audio playback (receive TTS via WebSocket, auto-play)
  - Add STT microphone button (Web Speech API)
  - Add "listening" indicator
  - Display player name alongside character name

### Infrastructure

- **New Python dependencies:** `mlx-audio`, `kokoro`, `edge-tts`, `piper-tts` (optional, extras group)
- **Dependency installation:** TTS engines as optional extras (`pip install dm20-protocol[voice]`) to keep base install light
- **Hardware detection:** Runtime check for Apple Silicon vs Intel determines available TTS tiers
- **No new servers:** TTS runs in-process; audio streamed over existing WebSocket

## Implementation Strategy

### Development Phases

**Phase 1: Foundation** (no new dependencies, immediate value)
- Tasks 1-3: Rules standalone, stable tokens, QR display, import report
- Low risk, high impact, can be released independently

**Phase 2: Prefetch** (LLM integration)
- Task 4: Prefetch engine with tiered model inference
- Medium risk (new pattern), medium-high impact on combat latency

**Phase 3: Voice** (new dependencies, new subsystem)
- Tasks 5-8: TTS engine, voice registry, audio streaming, STT, wizard
- Higher risk (hardware-dependent), highest impact on user experience
- Should be behind `interaction_mode` flag — Classic mode works without voice deps

### Risk Mitigation

1. **TTS model quality/compatibility:** Test Qwen3-TTS on M1/M2/M3/M4 early. If MLX performance is inadequate, Edge-TTS cloud is the fallback.
2. **Prefetch waste:** Start with conservative prefetch (combat only). Measure cache hit rate before expanding.
3. **Browser STT accuracy:** Web Speech API varies by browser. Test on Chrome iOS, Safari iOS, Chrome macOS.
4. **Dependency bloat:** Voice engines are optional extras. Base install unchanged.

### Testing Approach

- **Unit tests:** Each new module (voice engines, prefetch cache, token generation)
- **Integration tests:** Rules standalone queries, party-mode with stable tokens, TTS-to-WebSocket pipeline
- **Manual tests:** Voice quality assessment, STT accuracy, QR code readability across terminals

## Task Breakdown Preview

- [ ] **Task 1: Standalone Rules Access + Rules Version Selection** — Global RulebookManager, 5etools default, rules_version in create_campaign, MCP tool fallback chain
- [ ] **Task 2: Party-Mode Stable Tokens + QR Terminal Display** — Deterministic tokens (token=character ID), ASCII QR in terminal output, comment out old token generation
- [ ] **Task 3: Import Report Enhancement + Player Name in Party UI** — Structured import report with status/fields/warnings/suggestions, player_name display in party-mode UI
- [ ] **Task 4: Prefetch Engine** — Context observer, variant pre-generation, Haiku refinement, cache with TTL, combat-triggered activation, token usage tracking
- [ ] **Task 5: TTS Engine Core** — TTSRouter, hardware detection, engine wrappers (Kokoro/Qwen3-TTS/Edge-TTS/Piper), optional dependency installation
- [ ] **Task 6: Voice Registry + Audio Streaming** — Per-campaign voice config (YAML), NPC voice mapping, WebSocket audio chunk delivery, Opus encoding
- [ ] **Task 7: STT Integration + Player UI Voice Controls** — Web Speech API in player browser, microphone button, listening indicator, transcription via WebSocket
- [ ] **Task 8: Campaign Wizard Enhancement** — interaction_mode + rules_version in create_campaign, configure_claudmaster integration, mode switching mid-session

## Dependencies

### External Dependencies

| Dependency | Required By | Install Method |
|-----------|------------|----------------|
| mlx-audio | Task 5 (TTS) | `pip install dm20-protocol[voice]` |
| kokoro | Task 5 (TTS) | `pip install dm20-protocol[voice]` |
| edge-tts | Task 5 (TTS) | `pip install dm20-protocol[voice]` |
| piper-tts | Task 5 (TTS, Intel) | `pip install dm20-protocol[voice]` |
| qrcode[pil] | Task 2 (QR) | Already in dependencies |

### Internal Task Dependencies

```
Task 1 (Rules)  ──────────────────────────────┐
Task 2 (Tokens + QR) ── no deps               │
Task 3 (Import + Player Name) ── no deps       │
                                               ▼
Task 4 (Prefetch) ── no strict deps    Task 8 (Wizard)
                                               ▲
Task 5 (TTS Core) ─────┐                      │
                        ├──→ Task 6 (Voice) ───┤
                        │                      │
                        └──→ Task 7 (STT) ─────┘
```

**Parallel streams:**
- Stream A: Task 1 → Task 8 (partial — rules_version)
- Stream B: Tasks 2 + 3 (independent, can run in parallel)
- Stream C: Task 4 (independent of all others)
- Stream D: Task 5 → Task 6 → Task 7 → Task 8 (voice pipeline, sequential)

## Success Criteria (Technical)

| Criterion | Target | Gate |
|-----------|--------|------|
| Rules work without campaign | All 5 rule tools return results | Phase 1 release |
| Stable token across restarts | Same URL validated after 10 restarts | Phase 1 release |
| Import report covers all fields | 100% of ImportResult fields displayed | Phase 1 release |
| Prefetch reduces combat latency | > 50% reduction measured | Phase 2 release |
| TTS generates audio on Apple Silicon | Qwen3-TTS produces valid audio | Phase 3 alpha |
| Audio streams to browser | Player receives and plays audio chunks | Phase 3 alpha |
| STT transcribes in browser | Spoken commands arrive as text via WS | Phase 3 beta |
| Full voice pipeline end-to-end | Speak → process → narrate → hear | Phase 3 release |

## Estimated Effort

| Task | Size | Est. Hours | Critical Path |
|------|------|-----------|---------------|
| 1. Standalone Rules + Version | M | 6-8h | Yes (blocks Task 8) |
| 2. Stable Tokens + QR Display | S | 3-4h | No |
| 3. Import Report + Player Name | S | 3-4h | No |
| 4. Prefetch Engine | L | 12-16h | No |
| 5. TTS Engine Core | L | 12-16h | Yes (blocks 6, 7) |
| 6. Voice Registry + Streaming | M | 6-8h | Yes (blocks 7) |
| 7. STT + Player UI | M | 6-8h | Yes (blocks 8) |
| 8. Campaign Wizard Enhancement | S | 4-6h | No |
| **Total** | | **52-70h** | |

**Critical path:** Task 1 → Task 8 (rules_version) AND Task 5 → 6 → 7 → 8 (voice pipeline)
**Maximum parallelism:** 4 streams (A+B+C+D) can execute simultaneously

## Tasks Created

- [ ] 167.md - Standalone Rules Access + Rules Version Selection (parallel: true, Size M, 6-8h)
- [ ] 168.md - Party-Mode Stable Tokens + QR Terminal Display (parallel: true, Size S, 3-4h)
- [ ] 169.md - Import Report Enhancement + Player Name in Party UI (parallel: true, Size S, 3-4h)
- [ ] 170.md - Prefetch Engine (parallel: true, Size L, 12-16h)
- [ ] 171.md - TTS Engine Core (parallel: true, Size L, 12-16h)
- [ ] 172.md - Voice Registry + Audio Streaming (parallel: false, depends: #171, Size M, 6-8h)
- [ ] 173.md - STT Integration + Player UI Voice Controls (parallel: false, depends: #172, Size M, 6-8h)
- [ ] 174.md - Campaign Wizard Enhancement (parallel: false, depends: #167 + #173, Size S, 4-6h)

Total tasks: 8
Parallel tasks: 5 (167, 168, 169, 170, 171)
Sequential tasks: 3 (172 → 173 → 174)
Estimated total effort: 52-70h
