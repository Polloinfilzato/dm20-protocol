---
name: party-mode
description: Multi-player web relay enabling N human players to connect via browser to a shared D&D session with AI DM
status: backlog
created: 2026-02-17T16:39:56Z
---

# PRD: Party Mode — Multi-Player Web Relay

## Executive Summary

dm20-protocol currently supports only single-player sessions where one user interacts with the AI DM through Claude Code. **Party Mode** adds a lightweight web server that lets multiple human players connect from their own devices (phone, tablet, or PC) via browser — no software installation required.

The host runs dm20-protocol on their machine as usual. When Party Mode is activated, a web server starts on the local network. Each player scans a QR code to get a personal browser interface with: narrative feed, character sheet, action input, and private DM messages — all filtered by the existing permission and visibility systems.

**Key deliverables:**

1. **Web Server** — Starlette-based HTTP/WebSocket server embedded in dm20-protocol, activated via `/dm:party-mode` command
2. **Player Web UI** — Responsive browser interface for narrative, character sheet, action input, and private messages
3. **QR Authentication** — Per-player session tokens encoded as QR codes for frictionless access
4. **Action Queue** — JSONL-based queue bridging player browser inputs to the host's Claude Code DM session
5. **Real-Time Push** — WebSocket delivery of filtered game updates to each player's browser
6. **Combat Coordination** — Turn-based combat with active-player gating and optional simultaneous action mode

**Value proposition:** A group of friends can play D&D together with an AI DM. One person hosts, everyone else joins with their phone. Zero setup for players, zero extra cost for the host (Phase 2A), with a path to fully autonomous AI DM sessions (Phase 2B).

## Problem Statement

### Current State

```
Multi-player experience today:
├── Permission system (DM/PLAYER/OBSERVER)     ✅ Implemented, tested
├── Character ownership enforcement             ✅ Implemented, tested
├── Output filtering by role                    ✅ Implemented, tested
├── Private messaging and hidden rolls          ✅ Implemented, tested
├── PC tracking and session management          ✅ Implemented, tested
├── Split party handling                        ✅ Implemented, tested
├── Transport for multiple connections          ❌ Only stdio (single client)
├── Player-facing interface                     ❌ Only Claude Code CLI
├── Player authentication                       ❌ No mechanism exists
└── Action coordination for N players           ❌ No queue or turn gating
```

**The data model is ready. The transport and presentation layer is missing.**

### Pain Points

1. **No way for friends to connect** — The MCP server communicates via stdio to a single Claude Code session. Even though `PCRegistry` supports N players and `PermissionResolver` enforces per-player access, there is no mechanism for multiple humans to send input or receive output.

2. **Players can't see their own character** — Character sheets, inventory, spell slots, and HP are accessible only through MCP tools in the host's terminal. Players have no way to check their own stats.

3. **Private information has no private channel** — `PrivateInfoManager` can mark information as PRIVATE or DM_ONLY, but there is no separate output channel to deliver private content to the intended recipient without other players seeing it.

4. **Combat with multiple players is uncoordinated** — The turn manager tracks initiative order, but there is no interface telling each player "it's your turn" or collecting their combat actions.

### Scenario

```
Without Party Mode:
  Host: "Ok Thorin, what do you do?"
  Thorin's player: (walks over to the host's Mac) "I attack the orc"
  Host: (types it into Claude Code) "Thorin attacks the orc"
  Host: (reads response aloud) "You swing your axe..."
  Host: "Elara, your turn" (Elara walks over...)
  → Slow, no privacy, no personal view, one person does all the typing

With Party Mode:
  Host: /dm:party-mode
  → QR codes appear on screen
  Each player scans their QR → opens browser on their phone
  Thorin types "I attack the orc" on his phone → response appears on his screen
  Elara sees the public narrative but not Thorin's perception check result
  → Fast, private channels work, everyone has their own view
```

### Target Users

- **Host** — The person running dm20-protocol on their Mac/PC via Claude Code. Manages the campaign, starts Party Mode, optionally monitors the game.
- **Player** — A friend with a smartphone, tablet, or laptop. Joins via QR code, controls their character, reads narrative, submits actions.
- **Observer** — Someone who wants to watch the game without acting (read-only narrative feed).

## Architecture Overview

```
  ┌──────────────────────────── Host Machine ─────────────────────────────┐
  │                                                                       │
  │  ┌──────────────┐         ┌──────────────────┐     ┌───────────────┐ │
  │  │ Claude Code   │◄──MCP──►│ dm20-protocol    │◄────►│ Web Server   │ │
  │  │ (DM brain)    │         │ (state & rules)  │ API  │ (Party Mode) │ │
  │  └──────────────┘         └──────────────────┘     └──────┬────────┘ │
  │                                                           │          │
  └───────────────────────────────────────────────────────────┼──────────┘
  Phase 2A: Claude Code is the brain                          │ HTTP / WS
  Phase 2B: Claudmaster agent replaces Claude Code            │
                                            ┌─────────────────┼────────────┐
                                            │     Local Network (WiFi)     │
                                            │                              │
                                   ┌────────┼────────┐                     │
                                   │        │        │                     │
                             ┌─────┴───┐ ┌──┴─────┐ ┌┴────────┐          │
                             │Player 1 │ │Player 2│ │Player 3 │          │
                             │(browser)│ │(browser│ │(browser)│          │
                             └─────────┘ └────────┘ └─────────┘          │
                             └─────────────────────────────────────────────┘
```

### Data Flow: Player Action → Response

```
Phase 2A (Host-Driven):

  Player browser                Web Server              Action Queue        Claude Code (host)
  ─────────────                 ──────────              ────────────        ──────────────────
       │                             │                       │                     │
       │── POST /action {text} ─────►│                       │                     │
       │                             │── write action ──────►│                     │
       │◄─ "Queued" ────────────────│                       │                     │
       │                             │                       │                     │
       │                             │                       │◄── read action ─────│
       │                             │                       │                     │
       │                             │                       │──── process ────────│
       │                             │                       │    (game loop)      │
       │                             │                       │                     │
       │                             │◄── write response ────│                     │
       │                             │    (filtered per role) │                     │
       │                             │                       │                     │
       │◄─ WebSocket push ──────────│                       │                     │
       │   (player-specific view)    │                       │                     │
```

### Combat Data Flow

```
  Turn-Based Mode (default):

  Turn Manager says: "Thorin's turn (initiative 18)"
       │
       ├─► Thorin's browser: "IT'S YOUR TURN" + action input enabled
       ├─► Elara's browser:  "Waiting for Thorin..." + action input disabled
       └─► Vex's browser:    "Waiting for Thorin..." + action input disabled

  Thorin submits action → processed → results pushed to all → next turn

  Simultaneous Mode (optional, for group checks / surprise rounds):

  DM triggers simultaneous round
       │
       ├─► All browsers: "SUBMIT YOUR ACTION" + action input enabled + timer
       │
       ├── Thorin submits "I attack"
       ├── Elara submits "I cast Shield"
       └── Vex submits "I hide"

  Timer expires or all submitted → DM resolves in initiative order → results pushed
```

## User Stories

### US-1: Player Joins a Session

```
As a player invited to a D&D session,
I want to scan a QR code on my phone and immediately see the game,
So that I can start playing without installing anything or creating an account.

Acceptance Criteria:
- [ ] Player scans QR code → browser opens with game interface
- [ ] No app installation, account creation, or password required
- [ ] Interface loads in < 3 seconds on mobile
- [ ] Player sees their character name and basic stats on load
- [ ] Player sees the current narrative context (last N messages)
- [ ] Works on iOS Safari, Android Chrome, and desktop browsers
```

### US-2: Player Submits an Action

```
As a player during a game session,
I want to type my action on my phone and see the result,
So that I can participate in the game from my own device.

Acceptance Criteria:
- [ ] Text input field at bottom of screen (mobile-friendly)
- [ ] "Send" button or Enter key submits the action
- [ ] Visual feedback: "Queued" → "Processing..." → result appears
- [ ] Action appears in the player's narrative feed when resolved
- [ ] Other players see the public portion of the result
- [ ] Player's private info (perception checks, DM whispers) visible only to them
```

### US-3: Player Views Character Sheet

```
As a player,
I want to check my character's HP, spells, inventory, and abilities on my device,
So that I can make informed decisions without asking the DM.

Acceptance Criteria:
- [ ] Expandable character summary always visible (HP, AC, level, conditions)
- [ ] Full character sheet accessible via tap/click (read-only)
- [ ] Shows: ability scores, skills, inventory, spell slots, features
- [ ] Updates in real-time when HP changes, items are used, etc.
- [ ] Only shows the player's own character (not other PCs)
```

### US-4: DM Sends Private Message

```
As the AI DM,
I want to send a private message to a specific player,
So that I can share secrets, perception results, or character-specific information.

Acceptance Criteria:
- [ ] Private messages appear in a dedicated section of the recipient's UI
- [ ] Other players cannot see private messages
- [ ] DM can send to one player or a subset of players
- [ ] Private messages are visually distinct from public narrative
- [ ] Hidden roll results (passive perception, insight) delivered as private messages
```

### US-5: Combat Turn Management

```
As a player in combat,
I want to know when it's my turn and what I can do,
So that combat flows smoothly with multiple players.

Acceptance Criteria:
- [ ] Active player sees "YOUR TURN" indicator with initiative order
- [ ] Active player's action input is enabled; others are disabled (turn-based mode)
- [ ] Initiative order visible to all players
- [ ] Combat stats visible: HP, AC, conditions, position
- [ ] DM can switch to simultaneous mode for group checks
- [ ] Turn timer optional (configurable timeout, default 5 min)
```

### US-6: Host Manages Party Mode

```
As the host running dm20-protocol,
I want simple commands to start, monitor, and stop Party Mode,
So that managing the web server doesn't distract from the game.

Acceptance Criteria:
- [ ] /dm:party-mode starts web server and generates QR codes
- [ ] /dm:party-status shows connected players and pending actions
- [ ] /dm:party-next processes the next queued action
- [ ] /dm:party-auto enables automatic action processing
- [ ] /dm:party-stop gracefully disconnects players and stops server
- [ ] /dm:party-kick <player> disconnects a specific player
- [ ] /dm:party-token <player> regenerates a player's access token
```

### US-7: Observer Watches the Game

```
As an observer (non-player),
I want to follow the game narrative in real-time,
So that I can enjoy the story without participating.

Acceptance Criteria:
- [ ] Observer role shows public narrative feed only
- [ ] No action input (read-only)
- [ ] No private messages or character sheets
- [ ] Can be used on a shared screen (TV) for group viewing
- [ ] Separate QR/token with OBSERVER role
```

## Functional Requirements

### Core Web Server

| ID | Requirement | Priority | Complexity |
|----|-------------|----------|------------|
| FR-01 | Starlette web server embedded in dm20-protocol, started via `/dm:party-mode` | P0 | M |
| FR-02 | HTTP endpoints: `/play` (player UI), `/action` (submit action), `/status` (health check) | P0 | M |
| FR-03 | WebSocket endpoint for real-time push to connected browsers | P0 | M |
| FR-04 | Graceful startup/shutdown without affecting the MCP server | P0 | S |
| FR-05 | Configurable port (default 8080) and bind address (default 0.0.0.0) | P1 | S |

### Authentication & Session

| ID | Requirement | Priority | Complexity |
|----|-------------|----------|------------|
| FR-06 | Per-player session token generated at Party Mode startup | P0 | S |
| FR-07 | Token ↔ player_id mapping using existing `PermissionResolver` | P0 | S |
| FR-08 | QR code generation (PNG) embedding URL + token | P0 | S |
| FR-09 | Token validation middleware on all endpoints | P0 | S |
| FR-10 | Token refresh command (`/dm:party-token <player>`) | P1 | S |
| FR-11 | OBSERVER token for read-only access | P1 | S |

### Action Queue & Processing

| ID | Requirement | Priority | Complexity |
|----|-------------|----------|------------|
| FR-12 | JSONL action queue in campaign directory (`party/actions.jsonl`) | P0 | S |
| FR-13 | Response queue with per-player visibility tags (`party/responses.jsonl`) | P0 | M |
| FR-14 | `/dm:party-next` command reads and processes next queued action | P0 | M |
| FR-15 | `/dm:party-auto` enables automatic action processing loop | P1 | L |
| FR-16 | Action status tracking: pending → processing → resolved | P0 | S |
| FR-17 | Response filtering through `PermissionResolver` + `OutputFilter` | P0 | M |

### Player Web UI

| ID | Requirement | Priority | Complexity |
|----|-------------|----------|------------|
| FR-18 | Responsive HTML/CSS/JS interface (no build step, no Node.js) | P0 | L |
| FR-19 | Narrative feed with auto-scroll and WebSocket updates | P0 | M |
| FR-20 | Character summary bar (HP, AC, level, conditions) | P0 | M |
| FR-21 | Expandable full character sheet (read-only, from `get_character`) | P1 | M |
| FR-22 | Action text input with send button | P0 | S |
| FR-23 | Action status indicator (queued / processing / done) | P0 | S |
| FR-24 | Private message section (DM whispers) | P0 | M |
| FR-25 | Initiative order display during combat | P1 | S |
| FR-26 | Active turn indicator and input gating (turn-based combat) | P1 | M |
| FR-27 | Simultaneous action mode for group checks | P2 | M |

### Host Commands

| ID | Requirement | Priority | Complexity |
|----|-------------|----------|------------|
| FR-28 | `/dm:party-mode` — start server, generate tokens/QR | P0 | M |
| FR-29 | `/dm:party-stop` — stop server, disconnect players | P0 | S |
| FR-30 | `/dm:party-status` — show connections, queue, active players | P0 | S |
| FR-31 | `/dm:party-next` — process next action from queue | P0 | M |
| FR-32 | `/dm:party-auto` — auto-process loop | P1 | L |
| FR-33 | `/dm:party-kick <player>` — disconnect and invalidate token | P1 | S |
| FR-34 | `/dm:party-token <player>` — regenerate access token | P1 | S |

## Non-Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-01 | Player UI loads in < 3 seconds on mobile (LAN) | P0 |
| NFR-02 | WebSocket latency < 500ms on LAN | P0 |
| NFR-03 | Support 2-6 concurrent players (up to 12 max) | P0 |
| NFR-04 | Zero additional Python dependencies beyond `qrcode` | P1 |
| NFR-05 | Frontend: vanilla HTML/CSS/JS, no framework, no build step | P0 |
| NFR-06 | Web server must not block or interfere with MCP stdio transport | P0 |
| NFR-07 | Graceful handling of player disconnection and reconnection | P1 |
| NFR-08 | Action queue survives web server restart | P1 |
| NFR-09 | No credentials shared — tokens are the only auth mechanism | P0 |
| NFR-10 | Mobile-first responsive design (primary device is smartphone) | P0 |

## Success Criteria

| Metric | Target |
|--------|--------|
| Player onboarding time (QR scan → playing) | < 30 seconds |
| Actions per minute throughput (4 players) | ≥ 2 actions/min |
| Player devices supported | Any modern browser (iOS/Android/desktop) |
| Private info leakage | Zero (no player sees another's private data) |
| Host overhead vs single-player | Minimal (one extra command to start) |
| Web server stability | No crashes during a 3-hour session |

## Constraints & Assumptions

### Constraints

- **Single brain (Phase 2A)** — Claude Code on the host machine is the only DM brain. All actions are processed through the host's session. This means the host must be active for the game to progress.
- **LAN-only for MVP** — Remote play (via tunnel/ngrok) is an enhancement, not a launch requirement.
- **No persistent accounts** — Tokens are session-scoped. Players re-scan QR each session.
- **Text-only input** — No voice input, dice rolling UI, or map rendering in the MVP.
- **Starlette only** — The web server must use Starlette (already bundled with FastMCP). No FastAPI, Flask, or other frameworks.

### Assumptions

- Players have a device with a modern browser and WiFi access
- The host's machine can run both Claude Code and the web server simultaneously
- 2-6 players is the typical party size
- Most sessions happen in the same physical location (LAN scenario)
- The existing permission system correctly enforces all access rules

## Out of Scope

The following are explicitly **not** part of this PRD:

- **Phase 2B (Autonomous Claudmaster)** — Replacing the host's Claude Code with an autonomous Claude API agent. Documented in `docs/PARTY_MODE.md` for future reference.
- **Remote play via tunnel** — Exposing the web server to the internet (ngrok, Cloudflare Tunnel). Enhancement after MVP.
- **Voice input/output** — Speech-to-text or text-to-speech for player actions.
- **Visual maps or tokens** — Grid-based battle maps, token placement, or fog of war visualization.
- **Dice rolling UI** — Visual dice roller in the browser. Dice are rolled server-side via MCP tools.
- **Chat between players** — Player-to-player messaging. Players communicate verbally (same room) or via external chat.
- **Mobile app** — Native iOS/Android app. Browser-only for now.
- **Character editing** — Players view their character sheet but cannot edit it from the browser. Edits happen through MCP tools (DM-side).
- **mDNS/Bonjour discovery** — Automatic network discovery. Players use QR codes or typed URLs.

## Dependencies

### Existing Infrastructure (no changes needed)

| Component | Location | Used For |
|-----------|----------|----------|
| `PermissionResolver` | `src/dm20_protocol/permissions.py` | Token → role → access check |
| `PCRegistry` | `src/dm20_protocol/claudmaster/pc_tracking.py` | Player registration, session tracking |
| `PrivateInfoManager` | `src/dm20_protocol/claudmaster/private_info.py` | Private messages, hidden rolls |
| `OutputFilter` | `src/dm20_protocol/output_filter.py` | Response filtering by role |
| `TurnManager` | `src/dm20_protocol/claudmaster/turn_manager.py` | Combat initiative and turn tracking |
| `SplitPartyManager` | `src/dm20_protocol/claudmaster/split_party.py` | Split party scenarios |

### New Dependencies

| Package | Purpose | Size |
|---------|---------|------|
| `qrcode` | Generate QR code PNGs from tokens | Lightweight (~50KB) |
| Starlette | Web server + WebSocket | Already bundled with FastMCP |
| Uvicorn | ASGI server | Already bundled with FastMCP |

### External Dependencies

- **WiFi network** — All devices must be on the same LAN
- **Claude Code session** — Host must have an active Claude Code session (Phase 2A)

## Implementation Order

### Phase 2A — Host-Driven MVP

```
Step 1: Web Server Skeleton                               [P0, Size M]
  → Starlette app with /play, /action, /status routes
  → WebSocket endpoint for real-time push
  → Start/stop lifecycle tied to /dm:party-mode command
  → Runs in background thread, doesn't block MCP stdio

Step 2: Authentication & QR                               [P0, Size S]
  → Token generation (one per registered PC)
  → Token ↔ player_id mapping via PermissionResolver
  → QR code generation (qrcode package)
  → Token validation middleware

Step 3: Action Queue                                      [P0, Size M]
  → JSONL action queue (write from web server, read from Claude Code)
  → JSONL response queue (write from Claude Code, read from web server)
  → /dm:party-next reads and processes next action
  → Status tracking (pending → processing → resolved)

Step 4: Player Web UI                                     [P0, Size L]
  → Responsive HTML/CSS/JS (no framework, no build step)
  → Narrative feed with auto-scroll
  → Character summary (HP, AC, level)
  → Action input + send button
  → Private message display
  → Action status indicator

Step 5: Real-Time Integration                             [P0, Size M]
  → WebSocket push on new responses
  → Permission filtering on all outgoing data
  → Player connection/disconnection handling
  → Reconnection with message replay

Step 6: Combat Coordination                               [P1, Size M]
  → Initiative order display
  → Active turn indicator + input gating
  → Turn notification via WebSocket
  → Simultaneous action mode (P2)

Step 7: Host Commands & Polish                            [P1, Size M]
  → /dm:party-status, /dm:party-kick, /dm:party-token
  → /dm:party-auto (automatic processing loop)
  → Error handling, graceful degradation
  → Expandable full character sheet
```

### Phase 2B — Autonomous Claudmaster (Future)

Documented in `docs/PARTY_MODE.md`. Key additions:
- Claude API integration in web server
- Autonomous game loop (no host Claude Code needed)
- DM dashboard for monitoring
- Cost management (model tiering, token budgets)
- Fallback to Phase 2A when budget exhausted

## Related Documents

- **Architecture details**: `docs/PARTY_MODE.md`
- **Original multi-user requirements**: `.claude/prds/campaign-experience-enhancement.md` (US-4, US-5, FR-11 to FR-18)
- **Claudmaster multi-player**: `.claude/prds/claudmaster-ai-dm.md` (US-6, FR-8)
- **FastMCP transport docs**: `docs/FastMCP_2.9.0_docs.md`
