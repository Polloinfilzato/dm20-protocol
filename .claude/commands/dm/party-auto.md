---
description: Automatically process all pending player actions in the Party Mode queue.
allowed-tools: Read, mcp__dm20-protocol__party_pop_action, mcp__dm20-protocol__party_resolve_action, mcp__dm20-protocol__get_party_status, mcp__dm20-protocol__get_game_state, mcp__dm20-protocol__get_character, mcp__dm20-protocol__get_npc, mcp__dm20-protocol__get_location, mcp__dm20-protocol__list_npcs, mcp__dm20-protocol__roll_dice, mcp__dm20-protocol__search_rules, mcp__dm20-protocol__get_spell_info, mcp__dm20-protocol__get_class_info, mcp__dm20-protocol__get_race_info, mcp__dm20-protocol__get_monster_info, mcp__dm20-protocol__update_character, mcp__dm20-protocol__bulk_update_characters, mcp__dm20-protocol__add_item_to_character, mcp__dm20-protocol__update_game_state, mcp__dm20-protocol__update_quest, mcp__dm20-protocol__add_event, mcp__dm20-protocol__create_npc, mcp__dm20-protocol__create_location, mcp__dm20-protocol__start_combat, mcp__dm20-protocol__player_action, mcp__dm20-protocol__configure_claudmaster
---

# Party Mode — Persistent Auto-Process Loop

Run as a **persistent DM loop** that continuously listens for and processes
player actions until the user interrupts with Ctrl+C.

This is the primary way to run a Party Mode session. The DM starts this
once and it keeps running for the entire session.

## Usage
```
/dm:party-auto
```

## Prerequisites

Call `get_party_status` to verify the server is running.

**If not running:** Tell the user:
```
Party Mode is not running. Start it with /dm:party-mode first.
```

## Instructions

### Startup Banner

Display once at the beginning:

```
+--------------------------------------------------+
|       PARTY MODE: AUTO-DM ACTIVE                 |
+--------------------------------------------------+
| Listening for player actions...                   |
| Processing will continue until you press Ctrl+C.  |
| When done, use /dm:save to end the session.       |
+--------------------------------------------------+
```

### Persistent Processing Loop

This loop runs **indefinitely** until the user interrupts (Ctrl+C).
It NEVER exits on its own. This is the core design — the DM stays
active for the entire gaming session.

**Loop behavior:**

1. **Poll** — Call `party_pop_action`
2. **If action available:**
   a. Process it through the full game loop (see below)
   b. Display a brief status after resolving
   c. Immediately poll again (actions may have queued during processing)
3. **If queue empty:**
   a. Display a brief idle indicator: `Listening... (N actions processed so far)`
   b. Call `party_pop_action` again after a short pause
   c. **DO NOT EXIT.** Keep polling. The player may be typing their next action.

**Polling rhythm:**
- After processing an action: poll again immediately (more may be queued)
- On empty queue: poll again right away (the pause between API calls is natural)
- After 3 consecutive empty polls: show a brief "Listening..." status, then continue
- **NEVER stop polling.** NEVER exit the loop. NEVER say "no more actions".

#### Display Action Header

When an action is found:

```
--- Action #{N} | {player_id} ---
> "{action_text}"
```

Keep it brief — the player is waiting for a response.

#### Process Each Action as DM

Follow the **complete game loop**:

1. **CONTEXT** — `get_game_state`, `get_character` for the acting PC
2. **DECIDE** — What happens? Ability check? Combat? Pure narration?
3. **EXECUTE** — Roll dice, apply mechanics via MCP tools
4. **PERSIST** — Update state (`update_character`, `update_game_state`, etc.)
5. **NARRATE** — Describe the outcome in DM voice

#### Push Response

Call `party_resolve_action` with:
- `action_id`: the action_id from the pop
- `narrative`: the full narrative text
- `private_messages`: JSON for player-specific secrets (optional)
- `dm_notes`: DM-only notes (optional)

Then display:
```
Action resolved. Listening for next action...
```

And immediately loop back to poll for the next action.

## Important Rules

1. **NEVER EXIT THE LOOP.** This is the #1 rule. The loop runs until Ctrl+C.
   Do not exit after empty checks. Do not suggest running the command again.
   Do not display a "complete" banner. The session is NOT complete until the
   user decides it is.

2. **Process each action fully** before moving to the next. No parallel processing.

3. **Every action gets narrated and broadcast.** Do not skip or batch actions.

4. **Order matters.** Actions are FIFO — process in the order submitted.

5. **Stay in character as DM.** You are the Dungeon Master for the entire session.
   Maintain narrative continuity between actions.

6. **Keep responses flowing.** Players are on their phones waiting. Process quickly
   and narrate concisely but vividly.
