---
name: dm20-experience-enhancement
description: Comprehensive enhancement suite for DM20 including standalone rules, improved imports, stable party tokens, prefetch optimization, and voice interaction modes
status: draft
created: 2026-02-20T14:00:00Z
---

# PRD: DM20 Experience Enhancement Suite

## Executive Summary

This PRD defines a comprehensive set of enhancements to the DM20 protocol, spanning rules accessibility, character management, party-mode stability, performance optimization, and voice-powered interaction. The goal is to transform DM20 from a text-only tool requiring campaign setup into a flexible, low-latency, optionally voice-enabled D&D experience.

**Key deliverables:**
1. **Standalone Rules Access** — Query rules, spells, monsters without creating a campaign, with 5etools as primary source and 2014/2024 rules version selection
2. **Import Report & Player Name** — Detailed post-import report from D&D Beyond and player name metadata on characters
3. **Stable Party Tokens** — Fixed token = character ID for persistent party-mode URLs
4. **QR Code Terminal Display** — Show QR codes directly in terminal output
5. **Intelligent Prefetch** — Tiered model system (heavy pre-generation + Haiku refinement) for reduced latency
6. **Voice Interaction Modes** — Classic (text), Narrated (TTS output), Immersive (TTS + STT) with free local/cloud TTS engines

**Value proposition:** Make DM20 immediately useful out of the box (rules without campaign), reduce friction in party mode (stable links), and enable a fully voice-powered D&D experience at zero additional cost through open-source TTS/STT engines.

## Problem Statement

### Current State

DM20 requires a campaign to be loaded before any rules queries work:

```python
# Current: Rules require a campaign
search_rules("fireball")  # ❌ "No campaign loaded. Use load_campaign first."

# User just wants to look up a spell — must create a campaign first
create_campaign("temp")
load_rulebook(source="5etools")
search_rules("fireball")  # ✅ Now it works
```

Party-mode tokens change on every server restart, breaking saved bookmarks:

```
# Session 1: Player gets link
http://192.168.1.10:8080/play?token=abc123

# Session 2: Server restarts, new token
http://192.168.1.10:8080/play?token=xyz789  # Old link broken!
```

All interaction is text-only — no voice output or voice input capability.

### Problems

1. **Rules Inaccessible Without Campaign:** New users cannot explore D&D rules immediately after installation
2. **No Rules Version Choice:** No way to specify 2014 vs 2024 D&D rules at campaign creation
3. **Opaque Import Results:** D&D Beyond import gives minimal feedback on what succeeded/failed
4. **Missing Player Name:** Characters don't track the real-world player name
5. **Volatile Party Links:** Token changes every restart, players must get new QR codes each session
6. **QR Codes Not Visible:** QR codes saved to files but not shown in terminal
7. **High Response Latency:** Every DM response requires a full LLM round-trip with no pre-computation
8. **Text-Only Experience:** No voice narration or voice input, reducing immersion

### Why Now?

- DM20's core systems (rulebooks, party-mode, Claudmaster) are stable and feature-complete
- Open-source TTS models (Qwen3-TTS, Kokoro) have reached production quality with Apple Silicon support (Jan 2026)
- Browser-native STT (Web Speech API) is mature and free
- Party-mode WebSocket infrastructure is already in place for audio streaming
- Users consistently report wanting voice and faster responses

### Target User Scenario

```
DM: "I just installed DM20. I want to look up how Fireball works."
Current: Must create a campaign, load rulebooks, THEN query.
Enhanced: Just ask — get an instant answer from 5etools.

DM: "We're playing tonight. Let me start party mode."
Current: Share new QR codes every session (tokens change).
Enhanced: Same QR code works forever — players bookmark it once.

DM: "The fighter attacks the dragon. Roll to hit!"
Current: Text response in 3-5 seconds.
Enhanced (Narrated mode): DM's voice narrates the result in <1 second
         (pre-generated during player's think time).

Player (on phone): "I cast Shield as a reaction!"
Current: Must type the action.
Enhanced (Immersive mode): Speaks into phone, STT converts, DM processes.
```

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      DM20 Server                            │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Rules Engine  │  │ Party Mode   │  │  Claudmaster     │  │
│  │ (standalone + │  │ (stable      │  │  (prefetch +     │  │
│  │  per-campaign)│  │  tokens)     │  │   tiered model)  │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │             │
│  ┌──────┴─────────────────┴────────────────────┴─────────┐  │
│  │                  Voice Engine                          │  │
│  │  ┌─────────┐  ┌────────────┐  ┌───────────────────┐   │  │
│  │  │ TTS     │  │ TTS Router │  │ Audio Streaming   │   │  │
│  │  │ Registry│  │ (3 tiers)  │  │ (WebSocket)       │   │  │
│  │  └─────────┘  └────────────┘  └───────────────────┘   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                Prefetch Engine                        │   │
│  │  Context Observer → Prediction → Pre-generation      │   │
│  │  Heavy Model (pre-gen) → Haiku (select + refine)     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         │                    │
    ┌────┴────┐         ┌────┴────┐
    │ Players │         │ Players │
    │ (text)  │         │ (voice) │
    │ Browser │         │ Browser │
    │         │         │ STT+TTS │
    └─────────┘         └─────────┘
```

### Campaign Creation Wizard (Enhanced)

```
create_campaign("Dragon's Lair")
    │
    ├─ 1. Campaign name, setting, description
    │
    ├─ 2. Rules version: 2014 or 2024?
    │     └─ Determines which SRD/5etools data to load
    │
    ├─ 3. Interaction mode:
    │     ├─ Classic    — Text input, text output
    │     ├─ Narrated   — Text input, TTS + text output
    │     └─ Immersive  — STT input, TTS + text output
    │
    └─ 4. Model profile: Quality / Balanced / Economy
```

### TTS Architecture (3-Tier Router)

```
                    ┌─────────────┐
                    │ TTS Router  │
                    │ (context    │
                    │  aware)     │
                    └──────┬──────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
    ┌─────┴─────┐   ┌─────┴──────┐   ┌─────┴──────┐
    │  TIER 1   │   │  TIER 2    │   │  TIER 3    │
    │  Speed    │   │  Quality   │   │  Fallback  │
    ├───────────┤   ├────────────┤   ├────────────┤
    │ Kokoro    │   │ Qwen3-TTS  │   │ Edge-TTS   │
    │ 82M       │   │ 0.6B MLX   │   │ Cloud/Free │
    │ <300ms    │   │ ~500ms-1s  │   │ ~300ms     │
    │ Combat    │   │ DM + NPC   │   │ GPU busy   │
    │ Local     │   │ Local      │   │ Internet   │
    │ Free      │   │ Free       │   │ Free       │
    └───────────┘   └────────────┘   └────────────┘

    Hardware Detection at Startup:
    ┌─────────────────┐    ┌──────────────────┐
    │ Apple Silicon?  │    │ Intel Mac?       │
    │ Tier 1: Kokoro  │    │ Tier 1: Piper    │
    │ Tier 2: Qwen3   │    │ Tier 2: Edge-TTS │
    │ Tier 3: Edge    │    │ Tier 3: Edge-TTS │
    └─────────────────┘    └──────────────────┘
```

### Prefetch Engine Data Flow

```
Game State Observer
    │
    ├─ Combat started? ──→ Preload: monster stats, PC spells, action options
    │
    ├─ Player's turn? ──→ Pre-generate: 2-3 narrative variants
    │   │                  (hit/miss/critical) using main model
    │   │
    │   └─ Dice rolled ──→ Haiku selects correct variant
    │                      Haiku refines with actual values
    │                      Response in <500ms vs 3-5s
    │
    ├─ Exploration? ──→ Preload: current location NPCs, quests, items
    │
    └─ NPC dialogue? ──→ Pre-generate: 2-3 likely NPC responses
```

### Voice Registry (Per-Campaign)

```json
{
  "dm_narrator": {
    "engine": "qwen3-tts",
    "voice_design": "A warm, deep male voice with authority",
    "language": "en"
  },
  "combat_narrator": {
    "engine": "kokoro",
    "voice": "af_heart",
    "language": "en"
  },
  "npc_defaults": {
    "male_human": {
      "engine": "qwen3-tts",
      "voice_design": "A middle-aged male voice, neutral tone"
    },
    "female_elf": {
      "engine": "qwen3-tts",
      "voice_design": "A young female voice, gentle and melodic"
    }
  },
  "npc_overrides": {
    "giuseppe_barkeep": {
      "engine": "qwen3-tts",
      "voice_design": "An Italian middle-aged man, warm and welcoming",
      "language": "it"
    }
  }
}
```

## User Stories

### US-1: Standalone Rules Query

**As a** new DM20 user
**I want to** look up D&D rules immediately after installation
**So that** I can use DM20 as a quick reference without creating a campaign

**Acceptance Criteria:**
- [ ] `search_rules("fireball")` works without any campaign loaded
- [ ] `get_spell_info("shield")` returns results from 5etools by default
- [ ] `get_monster_info("goblin")` works without campaign
- [ ] `get_class_info("wizard")` works without campaign
- [ ] Response includes source attribution (e.g., "Source: 5etools")
- [ ] Global rulebook manager initializes on server startup

### US-2: Rules Version Selection

**As a** DM creating a new campaign
**I want to** choose between 2014 and 2024 D&D rules
**So that** the system uses the correct version of rules for my game

**Acceptance Criteria:**
- [ ] `create_campaign()` includes `rules_version` parameter (2014 or 2024)
- [ ] Default is 2024 if not specified
- [ ] Selected version determines which SRD/5etools data is loaded
- [ ] Version is stored in campaign metadata and persisted
- [ ] Standalone rules mode uses 2024 by default (configurable)

### US-3: D&D Beyond Import Report

**As a** DM importing a character from D&D Beyond
**I want to** receive a clear, detailed report of what was imported
**So that** I know exactly what data is available and what's missing

**Acceptance Criteria:**
- [ ] Import returns status: `success` / `success_with_warnings` / `failed`
- [ ] Lists all fields successfully imported with counts
- [ ] Lists missing/unsupported fields with explanations
- [ ] Lists warnings (homebrew items, unknown classes, etc.)
- [ ] Report is formatted for easy reading (table or structured list)
- [ ] Includes actionable suggestions for missing data

### US-4: Player Name on Characters

**As a** DM
**I want to** associate a real-world player name with each character
**So that** the system can address players by name in party-mode and logs

**Acceptance Criteria:**
- [ ] `create_character()` accepts optional `player_name` parameter
- [ ] `import_from_dndbeyond()` already supports `player_name` (verify existing)
- [ ] Player name stored in character metadata
- [ ] Party-mode displays player name alongside character name
- [ ] Player name searchable via `list_characters()`

### US-5: Stable Party-Mode Tokens

**As a** player
**I want** my party-mode URL to remain the same across sessions
**So that** I can bookmark it and connect instantly every time

**Acceptance Criteria:**
- [ ] Token equals the character's unique identifier (character name/ID)
- [ ] Same character always gets the same URL
- [ ] Old random token generation is commented out (preserved for potential future use)
- [ ] QR codes generated once remain valid across server restarts
- [ ] OBSERVER token remains fixed as well
- [ ] Existing party-mode functionality (WebSocket, actions, permissions) unchanged

### US-6: QR Code Terminal Display

**As a** DM starting party-mode
**I want to** see QR codes directly in my terminal
**So that** players can scan them immediately without opening files

**Acceptance Criteria:**
- [ ] QR codes rendered as ASCII art in terminal output
- [ ] Each player's QR code shown with their character name
- [ ] QR codes still saved to files (existing behavior preserved)
- [ ] Works in standard terminal emulators (iTerm2, Terminal.app, etc.)
- [ ] Graceful fallback if terminal doesn't support Unicode block characters

### US-7: Intelligent Prefetch System

**As a** DM running a game session
**I want** the system to anticipate likely requests and prepare responses in advance
**So that** players experience minimal wait times

**Acceptance Criteria:**
- [ ] Combat start preloads: monster stat blocks, PC spell lists, action options
- [ ] Player turn pre-generates 2-3 narrative variants (hit/miss/critical)
- [ ] Main model (per profile) generates variants; Haiku selects and refines
- [ ] Actual response latency reduced by 50%+ compared to non-prefetch
- [ ] Prefetch activates automatically in combat (highest value context)
- [ ] Prefetch optionally activates in Narrated/Immersive modes for all contexts
- [ ] Cache invalidation when game state changes unexpectedly
- [ ] Prefetch does not interfere with normal request processing
- [ ] Token cost of prefetch tracked and reported in session summary

### US-8: Interaction Mode Selection

**As a** DM creating a campaign
**I want to** choose between text-only, narrated, or fully immersive voice modes
**So that** the game experience matches my group's preferences

**Acceptance Criteria:**
- [ ] Campaign creation includes `interaction_mode` parameter: classic, narrated, immersive
- [ ] Mode stored in campaign metadata and changeable mid-campaign
- [ ] Classic: all text (current behavior, no TTS/STT dependencies)
- [ ] Narrated: DM responses also delivered as TTS audio via WebSocket
- [ ] Immersive: Narrated + player STT input from browser
- [ ] Mode can be switched mid-session via `configure_claudmaster()`

### US-9: Text-to-Speech Output

**As a** player in a Narrated or Immersive session
**I want to** hear the DM's narration spoken aloud
**So that** the game feels more immersive and I don't have to read long text

**Acceptance Criteria:**
- [ ] TTS Router selects engine based on context (speed/quality/fallback tiers)
- [ ] Hardware detection at startup configures available tiers (Apple Silicon vs Intel)
- [ ] DM narrator has a consistent voice across the session
- [ ] NPCs have distinct voices based on voice registry
- [ ] Audio streamed via WebSocket to player browsers as Opus chunks
- [ ] Player browser auto-plays received audio
- [ ] Supports both English and Italian
- [ ] Voice registry persisted per campaign (JSON/YAML)
- [ ] Graceful degradation: if TTS fails, text still delivered normally

### US-10: Speech-to-Text Input

**As a** player using a phone in Immersive mode
**I want to** speak my actions instead of typing
**So that** I can play hands-free and more naturally

**Acceptance Criteria:**
- [ ] Player browser uses Web Speech API for STT (client-side, free)
- [ ] Transcribed text sent via existing WebSocket connection
- [ ] Server processes speech-transcribed text identically to typed text
- [ ] UI shows "listening" indicator when STT is active
- [ ] STT language matches campaign language (EN or IT)
- [ ] Works on Chrome, Safari (mobile and desktop)
- [ ] Graceful fallback: if STT unavailable, text input remains functional

## Requirements

### Functional Requirements

#### A — Standalone Rules Access

| ID | Requirement | Priority |
|----|------------|----------|
| FR-A1 | Global RulebookManager initialized on server startup (outside campaign context) | Must |
| FR-A2 | Rules MCP tools work without active campaign (search_rules, get_spell_info, get_monster_info, get_class_info, get_race_info) | Must |
| FR-A3 | 5etools loaded as default source for standalone queries | Must |
| FR-A4 | Response includes source attribution for every rule result | Should |
| FR-A5 | When campaign is active, campaign rulebook manager takes priority over global | Must |

#### A — Rules Version (2014/2024)

| ID | Requirement | Priority |
|----|------------|----------|
| FR-A6 | `create_campaign()` accepts `rules_version` parameter ("2014" or "2024") | Must |
| FR-A7 | Default rules version is "2024" | Must |
| FR-A8 | Version stored in campaign manifest and loaded on `load_campaign()` | Must |
| FR-A9 | Standalone mode defaults to 2024, configurable via `configure_claudmaster()` | Should |

#### B — Import Report

| ID | Requirement | Priority |
|----|------------|----------|
| FR-B1 | Import returns structured report with status, mapped fields, unmapped fields, warnings | Must |
| FR-B2 | Report formatted as readable table/list in MCP tool response | Must |
| FR-B3 | Warnings include actionable context (e.g., "Homebrew subclass 'X' not in SRD, imported as custom") | Should |

#### C — Player Name

| ID | Requirement | Priority |
|----|------------|----------|
| FR-C1 | `create_character()` accepts optional `player_name` field | Must |
| FR-C2 | Player name stored in character metadata JSON | Must |
| FR-C3 | Party-mode UI displays player name | Should |
| FR-C4 | `list_characters()` output includes player name | Should |

#### D — Stable Tokens

| ID | Requirement | Priority |
|----|------------|----------|
| FR-D1 | Token = character ID (deterministic, not random) | Must |
| FR-D2 | Old random token generation code commented out, not deleted | Must |
| FR-D3 | OBSERVER token is the fixed string "OBSERVER" | Must |
| FR-D4 | QR codes remain valid across server restarts | Must |

#### E — QR Code Display

| ID | Requirement | Priority |
|----|------------|----------|
| FR-E1 | QR codes rendered as ASCII/Unicode art in terminal | Must |
| FR-E2 | Each QR code labeled with character name and URL | Must |
| FR-E3 | File-based QR code saving preserved (existing behavior) | Must |
| FR-E4 | Fallback to URL-only output if terminal rendering fails | Should |

#### F — Prefetch System

| ID | Requirement | Priority |
|----|------------|----------|
| FR-F1 | Context observer monitors game state (combat, exploration, dialogue) | Must |
| FR-F2 | Combat triggers preload of relevant stat blocks, spells, and actions | Must |
| FR-F3 | Player turn triggers pre-generation of 2-3 narrative variants | Should |
| FR-F4 | Variant selection and refinement uses Haiku model (tiered inference) | Should |
| FR-F5 | Prefetch cache invalidated on unexpected state changes | Must |
| FR-F6 | Prefetch token usage tracked and included in session summary | Should |
| FR-F7 | Prefetch intensity configurable: off, conservative, aggressive | Should |

#### G — Voice Engine

| ID | Requirement | Priority |
|----|------------|----------|
| FR-G1 | TTS Router with 3 tiers: Speed (Kokoro), Quality (Qwen3-TTS), Fallback (Edge-TTS) | Must |
| FR-G2 | Hardware detection at startup determines available tiers | Must |
| FR-G3 | Apple Silicon: all 3 tiers local. Intel: Piper local + Edge-TTS cloud | Must |
| FR-G4 | Voice registry per campaign mapping characters to voice configurations | Must |
| FR-G5 | Qwen3-TTS voice design via text description for NPC voices | Should |
| FR-G6 | Qwen3-TTS voice cloning from reference audio (3s sample) | Could |
| FR-G7 | Audio streaming via WebSocket as Opus/PCM chunks | Must |
| FR-G8 | Player browser auto-plays TTS audio | Must |
| FR-G9 | STT via Web Speech API in player browser (client-side) | Must |
| FR-G10 | STT transcribed text sent via existing WebSocket | Must |
| FR-G11 | English and Italian language support for both TTS and STT | Must |
| FR-G12 | Campaign interaction mode stored in metadata (classic/narrated/immersive) | Must |
| FR-G13 | Interaction mode switchable mid-session | Should |

### Non-Functional Requirements

| ID | Requirement | Target | Priority |
|----|------------|--------|----------|
| NFR-1 | Standalone rules query response time | < 2s for first query, < 200ms cached | Must |
| NFR-2 | Party-mode token validation | O(1) lookup | Must |
| NFR-3 | TTS Tier 1 (Speed) latency | < 300ms | Must |
| NFR-4 | TTS Tier 2 (Quality) latency | < 1.5s | Must |
| NFR-5 | TTS Tier 3 (Fallback) latency | < 500ms | Should |
| NFR-6 | Prefetch cache hit rate in combat | > 60% | Should |
| NFR-7 | Prefetch wasted token ratio | < 3x useful output | Should |
| NFR-8 | STT recognition accuracy (English) | > 90% | Should |
| NFR-9 | TTS audio quality (Qwen3-TTS) | MOS > 4.0 | Should |
| NFR-10 | Memory usage (Qwen3-TTS 0.6B loaded) | < 4GB additional | Must |
| NFR-11 | Memory usage (Kokoro 82M loaded) | < 500MB additional | Must |
| NFR-12 | Voice registry load time | < 500ms | Should |
| NFR-13 | Zero-cost operation | TTS/STT must have $0/month option | Must |

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Rules accessible without campaign | 100% of rule tool types | Manual test: all 5 rule tools work standalone |
| Party-mode link stability | Same URL across 10+ restarts | Automated test: restart server, validate token |
| Prefetch latency reduction | > 50% reduction in combat | A/B test: same combat with/without prefetch |
| TTS voice consistency | Same NPC voice across session | Manual test: 10 utterances from same NPC |
| STT accuracy in gameplay | > 85% correct transcription | Manual test: 20 spoken commands |
| Monthly TTS cost | $0 (local engines) | Monitor: no external API charges |
| Import report completeness | All fields categorized | Test with 5 different DDB characters |

## Constraints and Assumptions

### Constraints

1. **Apple Silicon Required for Full TTS:** Qwen3-TTS (0.6B) via MLX requires M-series chip. Intel Macs fall back to Edge-TTS (cloud)
2. **16GB RAM Recommended:** Running Qwen3-TTS + Kokoro + DM20 needs ~16GB total RAM
3. **Internet for Edge-TTS:** Fallback tier requires internet connectivity
4. **Web Speech API Browser Support:** STT works in Chrome and Safari only (Firefox has limited support)
5. **LAN-Only Party Mode:** Current party-mode is LAN-only; token simplification is acceptable in this context
6. **No D&D Beyond Write-Back:** D&D Beyond has no public write API; reverse sync is not feasible

### Assumptions

1. Users have macOS (primary development platform) with either Apple Silicon or Intel
2. Most users will have 16GB+ RAM (standard on modern Macs)
3. 5etools data source remains available and maintained
4. Qwen3-TTS MLX implementation remains stable and performant
5. Web Speech API remains free and browser-supported
6. Edge-TTS (Microsoft) remains freely accessible
7. Players have modern smartphones with Chrome or Safari for party-mode

## Out of Scope

1. **D&D Beyond reverse sync** — No public write API exists (researched and confirmed)
2. **Internet-facing party mode** — Links remain LAN-only; HTTPS/public access is future work
3. **Custom voice model training** — Using existing voices/cloning only, not training new models
4. **Video/avatar generation** — Voice only, no visual character rendering
5. **Multi-language TTS beyond EN/IT** — English and Italian only for initial release
6. **Real-time voice chat between players** — Not a VoIP system; voice is player→DM→player only
7. **Foundry VTT integration** — Potential future feature, not in this scope
8. **Mobile app** — Players use mobile browser, not a native app

## Dependencies

### External Dependencies

| Dependency | Purpose | Version | License |
|-----------|---------|---------|---------|
| Qwen3-TTS | Quality TTS (Tier 2) | 0.6B | Apache 2.0 |
| mlx-audio | Apple Silicon TTS inference | Latest | MIT |
| Kokoro | Speed TTS (Tier 1) | 82M | Apache 2.0 |
| Piper | Speed TTS for Intel Macs | Latest | MIT |
| edge-tts | Fallback cloud TTS (Tier 3) | Latest | GPL-3.0 |
| qrcode | QR code generation (existing) | Latest | BSD |
| Web Speech API | Browser-native STT | N/A (browser) | N/A |
| 5etools | Rules data source | Latest | Community |

### Internal Dependencies

```
┌──────────────────┐
│ A: Standalone     │
│    Rules          │──────┐
└──────────────────┘      │
                          ▼
┌──────────────────┐  ┌──────────────────┐
│ B: Import Report │  │ A2: Rules Version│
│ C: Player Name   │  │    (2014/2024)   │
└──────────────────┘  └──────────────────┘

┌──────────────────┐
│ D: Stable Tokens │
│ E: QR Terminal   │──── Independent (party-mode)
└──────────────────┘

┌──────────────────┐     ┌──────────────────┐
│ F: Prefetch      │────▶│ G: Voice Engine  │
│    Engine        │     │    (TTS/STT)     │
└──────────────────┘     └──────────────────┘
        │                         │
        └─────────┬───────────────┘
                  ▼
        ┌──────────────────┐
        │ Campaign Wizard  │
        │ (mode selection) │
        └──────────────────┘
```

### Recommended Implementation Order

**Phase 1: Foundation (no new dependencies)**
1. **A: Standalone Rules** — Global RulebookManager, 5etools default
2. **A2: Rules Version** — 2014/2024 parameter in campaign creation
3. **C: Player Name** — Add field to character model
4. **D: Stable Tokens** — Simplify token generation
5. **E: QR Terminal** — ASCII QR code rendering

**Phase 2: Import & Prefetch**
6. **B: Import Report** — Enhanced import result formatting
7. **F: Prefetch Engine** — Context observer, cache, tiered model

**Phase 3: Voice**
8. **G: TTS Engine** — TTS Router, voice registry, audio streaming
9. **G: STT Integration** — Web Speech API in player UI
10. **Campaign Wizard Update** — Interaction mode + rules version selection

## Technical Notes

### Standalone Rules: Global Manager Initialization

The key change is creating a `RulebookManager` instance at server startup, independent of any campaign:

```python
# In server initialization (before any campaign is loaded)
global_rulebook_manager = RulebookManager()
await global_rulebook_manager.load_source(FiveToolsSource(version="2024"))

# In MCP tool handlers
def search_rules(query, ...):
    manager = storage.rulebook_manager or global_rulebook_manager
    return manager.search(query, ...)
```

### Stable Token Implementation

```python
# In TokenManager (auth.py)
class TokenManager:
    def generate_token(self, player_id: str) -> str:
        # NEW: Token = player_id (deterministic)
        token = player_id
        self._tokens[token] = player_id
        self._reverse_index[player_id] = token
        return token

        # OLD (commented out, preserved):
        # token = secrets.token_urlsafe(6)
        # self._tokens[token] = player_id
        # ...
```

### QR Code Terminal Rendering

```python
import qrcode

def render_qr_terminal(url: str, label: str) -> str:
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    # Returns Unicode block character art
    return f"\n{label}\n{qr.get_matrix_as_string()}\n{url}"
```

### TTS Router Logic

```python
class TTSRouter:
    def __init__(self):
        self.tiers = self._detect_hardware()

    def _detect_hardware(self) -> dict:
        if is_apple_silicon():
            return {
                "speed": KokoroEngine(),
                "quality": Qwen3TTSEngine(),
                "fallback": EdgeTTSEngine()
            }
        else:
            return {
                "speed": PiperEngine(),
                "quality": EdgeTTSEngine(),
                "fallback": EdgeTTSEngine()
            }

    async def synthesize(self, text: str, context: str, voice_config: dict) -> AudioChunk:
        if context == "combat" and len(text) < 100:
            engine = self.tiers["speed"]
        elif self.tiers["quality"].is_available():
            engine = self.tiers["quality"]
        else:
            engine = self.tiers["fallback"]

        return await engine.synthesize(text, voice_config)
```

### Prefetch Engine: Tiered Model Pattern

```python
class PrefetchEngine:
    async def pre_generate_combat_variants(self, game_state, player_turn):
        """Pre-generate narrative variants using main model."""
        prompts = self._build_variant_prompts(game_state, player_turn)
        # Use campaign's main model (Quality/Balanced/Economy profile)
        variants = await self.main_model.generate_batch(prompts)
        self.cache.store(player_turn.id, variants)

    async def resolve_with_actual(self, player_turn_id, actual_result):
        """Use Haiku to select and refine the best variant."""
        variants = self.cache.get(player_turn_id)
        if not variants:
            # Cache miss — generate normally
            return await self.main_model.generate(actual_result)

        # Haiku selects best variant and substitutes actual values
        refined = await self.haiku_model.select_and_refine(
            variants=variants,
            actual=actual_result
        )
        return refined
```

### Audio Streaming via WebSocket

```python
# Server-side: stream audio chunks to player
async def stream_tts_to_player(player_id, text, voice_config):
    audio_chunks = tts_router.synthesize_streaming(text, voice_config)
    async for chunk in audio_chunks:
        await connection_manager.send_to_player(player_id, {
            "type": "audio",
            "format": "opus",
            "data": base64.b64encode(chunk).decode(),
            "sequence": seq_num
        })

# Client-side (JavaScript in player UI)
ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "audio") {
        audioQueue.push(base64ToArrayBuffer(msg.data));
        playNextChunk();
    }
};
```

### Voice Registry Schema

```yaml
# {campaign_dir}/voice_registry.yaml
version: 1
default_language: en
dm_voice:
  engine: qwen3-tts
  voice_design: "A warm, deep male voice with authority, like a seasoned storyteller"
  language: en

combat_voice:
  engine: kokoro
  voice: af_heart
  language: en

npc_defaults:
  male_human:
    engine: qwen3-tts
    voice_design: "A middle-aged male voice, neutral and calm"
  female_human:
    engine: qwen3-tts
    voice_design: "A middle-aged female voice, clear and friendly"
  male_dwarf:
    engine: qwen3-tts
    voice_design: "A deep, gruff male voice with a slight accent"
  female_elf:
    engine: qwen3-tts
    voice_design: "A young, melodic female voice, ethereal quality"

npc_overrides:
  # Character-specific voice overrides
  giuseppe_barkeep:
    engine: qwen3-tts
    voice_design: "Un uomo italiano di mezza età, voce calda e accogliente"
    language: it
  ancient_dragon:
    engine: qwen3-tts
    voice_design: "A deep, rumbling voice that echoes with ancient power"
    language: en
```

### Import Report Format

```
╔══════════════════════════════════════════════════╗
║  D&D Beyond Import Report                        ║
║  Character: Thorin Ironforge                      ║
║  Status: ✅ SUCCESS WITH WARNINGS                 ║
╠══════════════════════════════════════════════════╣
║                                                   ║
║  ✅ Imported Successfully (12 fields):            ║
║  ├─ Identity: name, race, class (Fighter 8)      ║
║  ├─ Abilities: STR 18, DEX 14, CON 16...        ║
║  ├─ Combat: HP 76/76, AC 18, Speed 25ft         ║
║  ├─ Proficiencies: 6 skills, 3 saves            ║
║  ├─ Inventory: 14 items                          ║
║  ├─ Equipment: Longsword, Chain Mail, Shield     ║
║  └─ Currency: 150 gp, 20 sp                     ║
║                                                   ║
║  ⚠️  Warnings (3):                               ║
║  ├─ Homebrew feat "Iron Will" imported as custom ║
║  ├─ Magic item "Flame Tongue" stats estimated    ║
║  └─ Subclass "Echo Knight" not in SRD           ║
║                                                   ║
║  ❌ Not Imported (2):                             ║
║  ├─ Character portrait (not supported)           ║
║  └─ Campaign notes (DDB-specific)                ║
║                                                   ║
║  💡 Suggestions:                                  ║
║  ├─ Load Explorer's Guide to Wildemount for      ║
║  │  Echo Knight subclass support                 ║
║  └─ Use add_item to manually set Flame Tongue    ║
║     properties                                   ║
╚══════════════════════════════════════════════════╝
```

## References

- [Qwen3-TTS (Alibaba)](https://github.com/QwenLM/Qwen3-TTS) — Primary TTS engine
- [mlx-audio](https://github.com/Blaizzy/mlx-audio) — Apple Silicon inference
- [Kokoro TTS](https://huggingface.co/hexgrad/Kokoro-82M) — Speed tier TTS
- [Piper TTS](https://github.com/rhasspy/piper) — Intel Mac fallback
- [Edge-TTS](https://github.com/rany2/edge-tts) — Free cloud TTS
- [Web Speech API (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API) — Browser STT
- [D&D Beyond Character Service API](https://character-service.dndbeyond.com) — Read-only import
- [5etools](https://5e.tools) — Primary rules data source
