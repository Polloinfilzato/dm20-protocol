---
name: party-mode
status: completed
created: 2026-02-17T16:50:44Z
progress: 100%
prd: .claude/prds/party-mode.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/150
---

# Epic: Party Mode — Multi-Player Web Relay

## Overview

Build a lightweight web server inside dm20-protocol that lets N players connect via browser to a shared D&D session. The host activates Party Mode from Claude Code; players scan a QR code on their phone and get a personal game interface with narrative feed, character sheet, and action input — all filtered by the existing permission system.

The core challenge is **bridging two worlds**: the MCP stdio channel (host ↔ dm20-protocol) and HTTP/WebSocket channels (players ↔ web server), while keeping the existing single-player mode completely unaffected.

## Architecture Decisions

### AD-1: In-Process Web Server (not separate process)

The Starlette web server runs **inside the same Python process** as the MCP server, in a background thread. This means:

- The web server has direct access to `StorageManager`, `PermissionResolver`, `PCRegistry`, and all other in-memory objects
- No inter-process communication needed for reading game state (character sheets, narrative)
- The action queue can be an in-memory deque with JSONL persistence (not file-based IPC)
- The web server thread is started/stopped by the `/dm:party-mode` and `/dm:party-stop` slash commands

**Trade-off:** Tighter coupling to the MCP server process, but dramatically simpler implementation. If the MCP server restarts, the web server also restarts (acceptable for LAN sessions).

**Critical constraint:** The web server must use `asyncio` in its own event loop (Uvicorn runs its own loop in the background thread). It must **never** block the main thread where MCP stdio operates.

### AD-2: JSONL Queues as Bridge

The action queue and response queue use JSONL files in the campaign directory (`party/actions.jsonl`, `party/responses.jsonl`). This serves dual purpose:

- **In-memory deque** for fast access within the process
- **JSONL persistence** for crash recovery and debugging (human-readable log of all actions/responses)

The web server writes actions; Claude Code (via `/dm:party-next`) reads them. Claude Code writes responses; the web server reads and pushes them via WebSocket.

### AD-3: Vanilla Frontend (no build step)

The player UI is vanilla HTML + CSS + JavaScript served as static files from within the Python package (`src/dm20_protocol/party/static/`). No React, no Vue, no Node.js, no build step.

**Rationale:** The UI is intentionally simple (narrative feed + character sheet + text input). A framework would add complexity and dependencies with no proportional benefit. The WebSocket client is ~50 lines of JS.

### AD-4: Token-Based Auth (no sessions, no cookies)

Each player gets a random token at Party Mode startup. The token is passed as a URL query parameter (`?token=...`) and included in WebSocket messages. No cookies, no server-side sessions.

**Rationale:** Simplest auth model for a LAN game. Tokens are short-lived (session-scoped), easy to regenerate, and encode naturally into QR codes.

### AD-5: Leverage Existing Systems (don't rebuild)

The permission system, output filtering, PC tracking, private info, and turn management are **already implemented and tested**. The web server is a thin presentation layer that calls into these existing systems. No duplication of logic.

Key integration points:
- `PermissionResolver.check_permission(player_id, tool_name, target)` → validates every request
- `OutputFilter` → filters every response before WebSocket push
- `PCRegistry` → reads player list and character mappings
- `PrivateInfoManager.get_pending_messages(pc_id)` → delivers private DM messages
- `TurnManager` → reads combat state for turn gating

## Technical Approach

### Backend Components

```
src/dm20_protocol/party/
├── __init__.py
├── server.py          # Starlette app, routes, WebSocket handler
├── auth.py            # Token generation, validation, QR code creation
├── queue.py           # ActionQueue + ResponseQueue (in-memory + JSONL)
├── bridge.py          # Bridge between queue and existing dm20 systems
└── static/
    ├── index.html     # Player UI (single page)
    ├── style.css      # Mobile-first responsive styles
    └── app.js         # WebSocket client, DOM updates, action submission
```

#### `server.py` — Web Server Core
- Starlette application with routes:
  - `GET /play` → serves `index.html` (validates token in query param)
  - `POST /action` → receives player action, writes to queue
  - `GET /character/{player_id}` → returns character JSON (permission-checked)
  - `GET /status` → health check (for host monitoring)
  - `WS /ws` → WebSocket for real-time push (authenticated via token in first message)
- Background thread lifecycle: `start_party_server()` / `stop_party_server()`
- Connection manager: tracks connected WebSocket clients per player_id

#### `auth.py` — Authentication
- `generate_tokens(pc_registry)` → creates one token per registered PC + one OBSERVER token
- `validate_token(token)` → returns `player_id` or `None`
- `generate_qr(url, token)` → creates QR code PNG using `qrcode` package
- `refresh_token(player_id)` → invalidates old token, generates new one
- Token format: 8-char alphanumeric (`secrets.token_urlsafe(6)`)

#### `queue.py` — Action & Response Queues
- `ActionQueue`: thread-safe deque + JSONL file
  - `push(player_id, text)` → adds action with status `pending`
  - `pop()` → returns next pending action, sets status to `processing`
  - `resolve(action_id, response)` → marks action as `resolved`, writes to response queue
- `ResponseQueue`: append-only, read by WebSocket push loop
  - `push(response)` → adds response with visibility tags
  - `get_for_player(player_id, since)` → returns filtered responses since timestamp

#### `bridge.py` — Integration Bridge
- `process_action(action)` → called by `/dm:party-next`; constructs the input for Claude Code's game loop
- `format_response(raw_response, player_ids)` → applies `OutputFilter` to create per-player views
- `get_character_view(player_id)` → calls `get_character` with permission check
- `get_combat_state(player_id)` → reads turn manager state, determines if it's this player's turn

### Frontend Components

Single-page application (`index.html` + `style.css` + `app.js`):

- **Narrative feed** — scrollable div, new messages appended via WebSocket
- **Private messages** — separate collapsible section, visually distinct (different background color)
- **Character bar** — sticky header with HP/AC/level/conditions, tap to expand full sheet
- **Action input** — fixed bottom bar with text input + send button (mobile keyboard friendly)
- **Status indicators** — action status (queued/processing/done), connection status (connected/disconnected)
- **Combat overlay** — when in combat: initiative order, "YOUR TURN" banner, turn timer

### Slash Commands

New Claude Code slash commands (`.claude/commands/dm/`):

| Command | Implementation |
|---------|---------------|
| `/dm:party-mode` | Start Starlette server in background thread, generate tokens/QR, display connection info |
| `/dm:party-stop` | Send disconnect to all WebSocket clients, stop server thread |
| `/dm:party-next` | Read next action from queue, present to Claude for processing, write response to queue |
| `/dm:party-auto` | Loop: watch action queue, auto-present each action to Claude, stop on command |
| `/dm:party-status` | Read connection manager + queue state, display summary |
| `/dm:party-kick` | Invalidate token, close WebSocket, remove from connection manager |
| `/dm:party-token` | Call `refresh_token()`, generate new QR, display |

## Implementation Strategy

### Development Phases

The implementation is ordered so that each task produces a testable increment:

1. **Foundation** (Task 1) → web server starts, serves a page, accepts WebSocket connections
2. **Data flow** (Tasks 2-3 in parallel) → actions flow in, responses flow out, UI renders them
3. **Integration** (Task 4) → WebSocket push connects queues to browsers with permission filtering
4. **UX layer** (Tasks 5-6 in parallel) → host commands and combat coordination
5. **Validation** (Task 7) → end-to-end testing with multiple simulated players

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Background thread blocks MCP stdio | Use `asyncio.run_in_executor` for any blocking calls; stress test with concurrent MCP + HTTP traffic |
| WebSocket drops on mobile (screen sleep) | Auto-reconnect in JS client with message replay from last-seen timestamp |
| Permission bypass via direct API calls | Token validation middleware on every endpoint; integration tests for all permission boundaries |
| JSONL queue grows unbounded | Rotate queue files per session; archive resolved actions |
| QR code not scannable on some phones | Also display plain URL as fallback text |

### Testing Approach

- **Unit tests** — `auth.py` (token generation/validation), `queue.py` (thread safety, JSONL persistence)
- **Integration tests** — WebSocket connection, action submission, response filtering by role
- **Permission tests** — Player A cannot see Player B's private messages; OBSERVER cannot submit actions
- **Concurrency tests** — Multiple simultaneous WebSocket connections; actions submitted while queue is being read
- **Manual playtest** — Host + 2-3 phones on same WiFi; real game session

## Task Breakdown Preview

7 tasks, ordered by dependency:

- [ ] **Task 1: Web Server Core + Authentication** — Starlette app, routes, WebSocket, tokens, QR generation, background thread lifecycle [P0, Size L, foundational]
- [ ] **Task 2: Action Queue and Response Pipeline** — JSONL queues, action status tracking, response filtering via PermissionResolver/OutputFilter [P0, Size M, depends on Task 1]
- [ ] **Task 3: Player Web UI** — HTML/CSS/JS frontend, narrative feed, character sheet, action input, private messages, mobile-first [P0, Size L, depends on Task 1]
- [ ] **Task 4: WebSocket Real-Time Push** — Wire response queue to WebSocket broadcast, per-player filtering, connection/disconnection handling, reconnection with replay [P0, Size M, depends on Tasks 1-3]
- [ ] **Task 5: Host Slash Commands** — /dm:party-mode, /dm:party-stop, /dm:party-next, /dm:party-auto, /dm:party-status, /dm:party-kick, /dm:party-token [P0, Size M, depends on Tasks 1-2]
- [ ] **Task 6: Combat Turn Coordination** — Initiative display, active turn indicator, input gating, simultaneous action mode [P1, Size M, depends on Tasks 3-4]
- [ ] **Task 7: End-to-End Integration Testing** — Multi-player simulation, permission boundary tests, concurrency tests, 3-hour stability test [P0, Size M, depends on all]

### Parallelism Analysis

```
                Task 1 (Server + Auth)
                    │
           ┌────────┼────────┐
           ▼        ▼        ▼
        Task 2   Task 3   Task 5*
        (Queue)  (UI)     (Commands)
           │        │        │
           └────┬───┘        │
                ▼            │
             Task 4          │
             (WebSocket)     │
                │            │
           ┌────┴────┐      │
           ▼         ▼      │
        Task 6    Task 7◄───┘
        (Combat)  (Testing)

  * Task 5 can start after Tasks 1+2 are done
  * Tasks 2, 3 can run in parallel
  * Tasks 5, 6 can run in parallel (after their deps)
```

**Optimal streams:**
- Stream A: Task 1 → Task 2 → Task 4 → Task 7
- Stream B: (after Task 1) Task 3 → Task 6
- Stream C: (after Tasks 1+2) Task 5

## Dependencies

### Internal (existing, no changes needed)

| System | Used By | How |
|--------|---------|-----|
| `PermissionResolver` | auth.py, bridge.py | `check_permission()` for every request |
| `PCRegistry` | auth.py | `get_all_active()` to generate tokens per PC |
| `PrivateInfoManager` | bridge.py | `get_pending_messages()` for private DM messages |
| `OutputFilter` | bridge.py | Filter responses before WebSocket push |
| `TurnManager` | bridge.py | Read combat state for turn gating |
| `StorageManager` | bridge.py | `get_character()` for character sheet endpoint |

### External (new)

| Package | Version | Purpose |
|---------|---------|---------|
| `qrcode[pil]` | >=7.0 | QR code PNG generation (Pillow for image rendering) |

Note: Starlette + Uvicorn are already included as transitive dependencies of `fastmcp>=2.9.0`.

## Success Criteria (Technical)

| Criteria | Target | How to Verify |
|----------|--------|---------------|
| Server startup time | < 2s | Time from `/dm:party-mode` to "ready" |
| UI load time (LAN) | < 3s | Lighthouse audit on mobile |
| WebSocket latency | < 500ms | Ping/pong measurement |
| Concurrent connections | 12 stable | Load test with 12 WebSocket clients |
| Permission correctness | 100% | Automated tests: no cross-player data leakage |
| MCP interference | Zero | Run MCP tool calls while web server is active |
| Queue throughput | > 10 actions/sec | Stress test with rapid submissions |
| Session stability | 3+ hours | Soak test with simulated activity |

## Estimated Effort

| Task | Size | Est. Hours |
|------|------|------------|
| Task 1: Web Server + Auth | L | 10-12h |
| Task 2: Action Queue + Response Pipeline | M | 6-8h |
| Task 3: Player Web UI | L | 10-12h |
| Task 4: WebSocket Real-Time Push | M | 6-8h |
| Task 5: Host Slash Commands | M | 6-8h |
| Task 6: Combat Turn Coordination | M | 6-8h |
| Task 7: E2E Integration Testing | M | 6-8h |
| **Total** | | **50-64h** |

**Critical path:** Task 1 → Task 2 → Task 4 → Task 7 = ~28-36h
**With parallelism (2 streams):** ~36-44h elapsed

## Tasks Created

- [ ] 149.md - Web Server Core + Authentication (parallel: false — foundational)
- [ ] 150.md - Action Queue and Response Pipeline (parallel: true — with #151)
- [ ] 151.md - Player Web UI (parallel: true — with #150)
- [ ] 152.md - WebSocket Real-Time Push (parallel: false — needs #149-151)
- [ ] 153.md - Host Slash Commands (parallel: true — with #154)
- [ ] 154.md - Combat Turn Coordination (parallel: true — with #153)
- [ ] 155.md - End-to-End Integration Testing (parallel: false — needs all)

Total tasks: 7
Parallel tasks: 4 (#150, #151, #153, #154)
Sequential tasks: 3 (#149, #152, #155)
Estimated total effort: 50-64h
