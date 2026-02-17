---
description: Automatically process all pending player actions in the Party Mode queue.
allowed-tools: Bash, Read, mcp__dm20-protocol__get_game_state, mcp__dm20-protocol__get_character, mcp__dm20-protocol__get_npc, mcp__dm20-protocol__get_location, mcp__dm20-protocol__list_npcs, mcp__dm20-protocol__roll_dice, mcp__dm20-protocol__search_rules, mcp__dm20-protocol__get_spell_info, mcp__dm20-protocol__get_class_info, mcp__dm20-protocol__get_race_info, mcp__dm20-protocol__get_monster_info, mcp__dm20-protocol__update_character, mcp__dm20-protocol__bulk_update_characters, mcp__dm20-protocol__add_item_to_character, mcp__dm20-protocol__update_game_state, mcp__dm20-protocol__update_quest, mcp__dm20-protocol__add_event, mcp__dm20-protocol__create_npc, mcp__dm20-protocol__create_location, mcp__dm20-protocol__start_combat, mcp__dm20-protocol__player_action, mcp__dm20-protocol__configure_claudmaster
---

# Party Mode — Auto-Process Loop

Continuously poll the action queue and process all pending player actions.

## Usage
```
/dm:party-auto
```

## Prerequisites

### Check Server is Running

Run via `Bash`:

```bash
python3 -c "
from dm20_protocol.party.server import get_server_instance
srv = get_server_instance()
if srv is None:
    print('NOT_RUNNING')
else:
    print('RUNNING')
"
```

**If not running:** Tell the user:
```
Party Mode is not running. Start it with /dm:party-mode first.
```

## Instructions

### Auto-Processing Loop

Process actions in a loop until the queue is empty:

1. **Check queue** for pending actions
2. **If action available:** Process it using the exact same game loop as `/dm:party-next` (Steps 1-4)
3. **If queue empty:** Wait briefly, then check once more
4. **If still empty after second check:** Exit the loop

For each action, follow this flow:

#### Pop Action

```bash
python3 -c "
import json
from dm20_protocol.party.server import get_server_instance
srv = get_server_instance()
action = srv.action_queue.pop()
if action is None:
    print(json.dumps({'empty': True}))
else:
    pending = srv.action_queue.get_pending_count()
    print(json.dumps({'empty': False, 'action': action, 'remaining': pending}))
"
```

#### Process Each Action

For each action popped from the queue:

1. Display the action header:
```
--- Processing Action {N}/{total} ---
Player: {player_id} | Action ID: {action_id}
Action: "{action_text}"
---
```

2. Follow the **complete game loop** (same as `/dm:party-next` Step 3):
   - **CONTEXT** — `get_game_state`, `get_character` for the acting PC
   - **DECIDE** — Determine what happens
   - **EXECUTE** — Roll dice, apply mechanics
   - **PERSIST** — Update state via MCP tools
   - **NARRATE** — Describe the outcome

3. Push the response to the queue:
```bash
python3 -c "
import json, sys
from dm20_protocol.party.server import get_server_instance
srv = get_server_instance()
response_data = json.loads(sys.stdin.read())
response_id = srv.response_queue.push(response_data)
srv.action_queue.resolve(response_data.get('action_id', ''), response_data)
print(json.dumps({'response_id': response_id}))
" <<'RESPONSE_JSON'
{
  "action_id": "{action_id}",
  "narrative": "{narration_text}",
  "private": {},
  "dm_only": ""
}
RESPONSE_JSON
```

4. Check for more pending actions and repeat.

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

### Second Check (Polling)

After the queue first appears empty, wait 3 seconds and check once more to catch any actions submitted during processing:

```bash
python3 -c "
import time, json
from dm20_protocol.party.server import get_server_instance
time.sleep(3)
srv = get_server_instance()
if srv is None:
    print(json.dumps({'empty': True, 'server_stopped': True}))
else:
    action = srv.action_queue.pop()
    if action is None:
        print(json.dumps({'empty': True}))
    else:
        pending = srv.action_queue.get_pending_count()
        print(json.dumps({'empty': False, 'action': action, 'remaining': pending}))
"
```

If a new action arrived, process it and continue the loop. If still empty, exit.

## Important Rules

1. **Process each action fully** before moving to the next. No parallel processing.
2. **Every action gets narrated and broadcast.** Do not skip or batch actions.
3. **Order matters.** Actions are FIFO — process in the order players submitted them.
4. **Exit cleanly.** Do not poll indefinitely. Two empty checks = done.
5. **Escape JSON properly** when constructing response payloads.
