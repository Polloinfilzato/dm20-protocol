---
description: Interactive onboarding and command reference for dm20-protocol.
allowed-tools: AskUserQuestion
---

# DM Help — Onboarding & Command Reference

Guide new users through dm20-protocol or show the command reference to experienced users.

## Instructions

### Step 1: Quick Assessment

Use `AskUserQuestion` to determine the user's experience level:

```
Question: "Welcome to dm20-protocol! How can I help you?"
Header: "Experience"
Options:
  - "I'm new here" → Full onboarding flow (Step 2)
  - "Show me the commands" → Command reference (Step 3)
  - "I want to start playing" → Tell them to run /dm:start
```

### Step 2: Onboarding for New Users

Present the following information conversationally:

**What is dm20-protocol?**
An AI-powered Dungeon Master for D&D 5e. It manages campaigns, characters, combat, and narration — all from your terminal. You play, the AI handles everything behind the DM screen.

**Game Modes:**

| Mode | Description |
|------|-------------|
| **SOLO** | You + AI companions + AI DM. The AI controls companion PCs autonomously — you can suggest actions but they decide for themselves. |
| **HUMAN PARTY** | Multiple human players + AI DM. Players connect via their phone/browser using QR codes. The DM processes actions from a shared queue. |

**What you need to start:**
1. A **campaign** — create one or load a published adventure module (e.g., Descent Into Avernus, Curse of Strahd)
2. A **character** — create from scratch with the guided wizard, or import directly from D&D Beyond
3. Optionally: **AI companions** for SOLO mode, or **Party Mode** for HUMAN PARTY

**Quick start path:**
Run `/dm:start` and the wizard will guide you through everything: campaign selection, adventure module loading, character creation (with D&D Beyond import option), and game mode setup.

Then show the command reference from Step 3.

End with: **"Ready to play? Run `/dm:start` to begin your adventure!"**

### Step 3: Command Reference

Show the following tables organized by category:

## Core Gameplay

The essential commands for playing D&D.

| Command | Description |
|---------|-------------|
| `/dm:start [campaign]` | Begin or resume a game session. Interactive wizard for campaign, characters, and game mode. |
| `/dm:action <description>` | Process a player action through the game loop. The core gameplay command. |
| `/dm:combat [situation]` | Initiate or manage a combat encounter with initiative, tactics, and turn tracking. |
| `/dm:save` | Save session state and create session notes with a narrative stopping point. |
| `/dm:campaigns [action]` | Manage campaigns: list, load, create, or delete. |

## Party Mode (Multiplayer)

Commands for running multi-player sessions. Players connect via phone/browser with QR codes.

| Command | Description |
|---------|-------------|
| `/dm:party-mode [port]` | Start the Party Mode web server. Generates QR codes and URLs for each player. |
| `/dm:party-status` | Show server info, connected players, and action queue stats. |
| `/dm:party-next` | Pop and process the next pending player action from the queue. |
| `/dm:party-auto` | Automatically process all pending actions in the queue, one by one. |
| `/dm:party-kick <player>` | Kick a player, revoke their token, and disconnect them. |
| `/dm:party-token <player>` | Generate a new token and QR code for a player (invalidates old). |
| `/dm:party-stop` | Shut down the Party Mode server and disconnect all players. |

## Utility

| Command | Description |
|---------|-------------|
| `/dm:profile <tier>` | Switch model quality: `quality`, `balanced`, or `economy`. |
| `/dm:release-notes` | Show installed version, latest version, and what's new. |
| `/dm:install-rag` | Install RAG dependencies (ChromaDB + ONNX embeddings) for vector search on PDF rulebooks. |
| `/dm:help` | This help overview. |

### Tips

- **Natural language actions:** Describe what you do in plain language — "I search the room for traps", "I try to persuade the guard"
- **Context management:** When the conversation gets long, `/dm:save` → `/clear` → `/dm:start` to reload with a fresh context
- **Character info:** Use the `get_character` MCP tool anytime to check your stats, HP, inventory
- **D&D Beyond import:** During character creation, you can paste a D&D Beyond URL to import a character directly
- **Adventure modules:** `/dm:start` offers published adventures from 5etools — choose "Adventure module" during setup
- **SOLO companions:** AI companions act on their own — you can suggest actions but they make their own decisions
- **Party Mode flow:** Start with `/dm:party-mode`, share QR codes, then use `/dm:party-next` or `/dm:party-auto` to process player actions
- **Stay updated:** `/dm:release-notes` shows what's new; the system notifies you automatically when an update is available
