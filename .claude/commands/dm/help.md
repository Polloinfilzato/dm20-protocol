---
description: Show all available DM commands with descriptions.
---

# DM Commands Help

Display an overview of all available `/dm` commands.

## Instructions

Show the following command reference to the user:

---

## 🎲 DM Commands

Commands for playing D&D with the AI Dungeon Master.

| Command | Description |
|---------|-------------|
| `/dm:start [campaign]` | Begin or resume a game session. Loads campaign, sets the scene, activates DM persona. |
| `/dm:action <description>` | Process a player action through the game loop. The core gameplay command. |
| `/dm:combat [situation]` | Initiate or manage a combat encounter with initiative and turn tracking. |
| `/dm:save` | Save session state and pause. Creates session notes with a narrative stopping point. |
| `/dm:help` | Show this help overview. |

### Quick Start

1. **First time?** Create a campaign and character using the MCP tools, then run `/dm:start`
2. **Returning?** Just run `/dm:start [campaign_name]` to resume where you left off
3. **During play:** Use `/dm:action` for any character action, or just type naturally — the DM will respond
4. **Combat:** Use `/dm:combat` to start an encounter, or let it happen naturally through roleplay
5. **Done for now?** Run `/dm:save` to save progress

### Tips

- The DM handles all rules, dice rolls, and NPC decisions automatically
- You can describe actions in natural language: "I search the room for traps"
- Context management: when the conversation gets long, `/dm:save` then `/clear` then `/dm:start` to reload fresh
- Check your character with the `get_character` MCP tool anytime
