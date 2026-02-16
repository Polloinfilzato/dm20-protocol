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
  - "Show me the commands" → Command reference table (Step 3)
  - "I want to start playing" → Tell them to run /dm:start
```

### Step 2: Onboarding for New Users

Present the following information conversationally:

**What is dm20-protocol?**
An AI-powered Dungeon Master for D&D 5e. It manages campaigns, characters, combat, and narration — all from your terminal. You play, the AI handles everything behind the DM screen.

**Game Modes:**

| Mode | Description | Status |
|------|-------------|--------|
| **SOLO** | You + AI companions + AI DM. The AI controls companion PCs autonomously — you can suggest actions but they decide for themselves. | Available |
| **HUMAN PARTY** | Multiple human players + AI DM. Everyone connects and plays together. | Coming soon |

**What you need to start:**
1. A **campaign** — create one or load a pre-made adventure module
2. A **character** — your PC in the world
3. Optionally: **AI companions** for SOLO mode (set up during `/dm:start`)

**Quick start path:**
Run `/dm:start` and the system will guide you through campaign selection, character creation, and game mode setup interactively.

Then show the command reference from Step 3.

End with: **"Ready to play? Run `/dm:start` to begin your adventure!"**

### Step 3: Command Reference

Show the following table:

## 🎲 DM Commands

Commands for playing D&D with the AI Dungeon Master.

| Command | Description |
|---------|-------------|
| `/dm:start [campaign]` | Begin or resume a game session. Loads campaign, sets the scene, activates DM persona. |
| `/dm:action <description>` | Process a player action through the game loop. The core gameplay command. |
| `/dm:combat [situation]` | Initiate or manage a combat encounter with initiative and turn tracking. |
| `/dm:save` | Save session state and pause. Creates session notes with a narrative stopping point. |
| `/dm:campaigns [action]` | Manage campaigns: list, load, create, delete with interactive menus. |
| `/dm:profile [tier]` | Switch model quality tier: quality, balanced, economy. Trade quality vs token cost. |
| `/dm:install-rag` | Install RAG dependencies (ChromaDB + sentence-transformers) for vector search. ~2GB download. |
| `/dm:help` | Show this help overview. |

### Tips

- The DM handles all rules, dice rolls, and NPC decisions automatically
- You can describe actions in natural language: "I search the room for traps"
- Context management: when the conversation gets long, `/dm:save` then `/clear` then `/dm:start` to reload fresh
- Check your character with the `get_character` MCP tool anytime
- In SOLO mode, AI companions act on their own — you can suggest actions to them but they make their own decisions
