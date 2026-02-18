---
description: Automatically process all pending player actions in the Party Mode queue.
allowed-tools: Read, mcp__dm20-protocol__party_pop_action, mcp__dm20-protocol__party_resolve_action, mcp__dm20-protocol__get_party_status, mcp__dm20-protocol__get_game_state, mcp__dm20-protocol__get_character, mcp__dm20-protocol__get_npc, mcp__dm20-protocol__get_location, mcp__dm20-protocol__list_npcs, mcp__dm20-protocol__roll_dice, mcp__dm20-protocol__search_rules, mcp__dm20-protocol__get_spell_info, mcp__dm20-protocol__get_class_info, mcp__dm20-protocol__get_race_info, mcp__dm20-protocol__get_monster_info, mcp__dm20-protocol__update_character, mcp__dm20-protocol__bulk_update_characters, mcp__dm20-protocol__add_item_to_character, mcp__dm20-protocol__update_game_state, mcp__dm20-protocol__update_quest, mcp__dm20-protocol__add_event, mcp__dm20-protocol__create_npc, mcp__dm20-protocol__create_location, mcp__dm20-protocol__start_combat, mcp__dm20-protocol__player_action, mcp__dm20-protocol__configure_claudmaster
---

# Party Mode — Auto-Process Loop

Continuously poll the action queue and process all pending player actions.

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

### Auto-Processing Loop

Process actions in a loop until the queue is empty:

1. **Pop action** using `party_pop_action`
2. **If action available:** Process it using the game loop (see below)
3. **If queue empty:** Wait ~3 seconds, then call `party_pop_action` once more
4. **If still empty after second check:** Exit the loop

For each action, follow this flow:

#### Display Action Header

```
--- Processing Action {N}/{total} ---
Player: {player_id} | Action ID: {action_id}
Action: "{action_text}"
---
```

#### Process Each Action as DM

Follow the **complete game loop** (same as `/dm:party-next`):

1. **CONTEXT** — `get_game_state`, `get_character` for the acting PC
2. **DECIDE** — Determine what happens (ability check? combat? pure narration?)
3. **EXECUTE** — Roll dice, apply mechanics via MCP tools
4. **PERSIST** — Update state (`update_character`, `update_game_state`, etc.)
5. **NARRATE** — Describe the outcome in DM voice

#### Push Response

Call `party_resolve_action` with:
- `action_id`: the action_id from the pop
- `narrative`: the full narrative text
- `private_messages`: JSON for player-specific secrets (optional)
- `dm_notes`: DM-only notes (optional)

Then check for more pending actions and repeat.

### Loop Termination

When no more actions are pending after two consecutive checks:

```
+--------------------------------------------------+
|         AUTO-PROCESS COMPLETE                     |
+--------------------------------------------------+
| Actions processed: {count}                        |
| Queue status:      empty                          |
+--------------------------------------------------+
| Waiting for new player actions.                   |
| Run /dm:party-auto again, or use /dm:party-next   |
| for one-at-a-time processing.                     |
+--------------------------------------------------+
```

## Important Rules

1. **Process each action fully** before moving to the next. No parallel processing.
2. **Every action gets narrated and broadcast.** Do not skip or batch actions.
3. **Order matters.** Actions are FIFO — process in the order players submitted them.
4. **Exit cleanly.** Do not poll indefinitely. Two empty checks = done.
