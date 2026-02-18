---
description: Process the next pending player action from the Party Mode queue.
allowed-tools: Read, mcp__dm20-protocol__party_pop_action, mcp__dm20-protocol__party_resolve_action, mcp__dm20-protocol__get_game_state, mcp__dm20-protocol__get_character, mcp__dm20-protocol__get_npc, mcp__dm20-protocol__get_location, mcp__dm20-protocol__list_npcs, mcp__dm20-protocol__roll_dice, mcp__dm20-protocol__search_rules, mcp__dm20-protocol__get_spell_info, mcp__dm20-protocol__get_class_info, mcp__dm20-protocol__get_race_info, mcp__dm20-protocol__get_monster_info, mcp__dm20-protocol__update_character, mcp__dm20-protocol__bulk_update_characters, mcp__dm20-protocol__add_item_to_character, mcp__dm20-protocol__update_game_state, mcp__dm20-protocol__update_quest, mcp__dm20-protocol__add_event, mcp__dm20-protocol__create_npc, mcp__dm20-protocol__create_location, mcp__dm20-protocol__start_combat, mcp__dm20-protocol__player_action, mcp__dm20-protocol__configure_claudmaster
---

# Party Mode — Process Next Action

Pop the next pending player action from the queue and process it through the game loop.

## Usage
```
/dm:party-next
```

## Instructions

### Step 1 — Pop Next Action

Call `party_pop_action` to get the next pending action.

**If queue is empty:** Tell the user:
```
+--------------------------------------------------+
|          NO PENDING ACTIONS                       |
+--------------------------------------------------+
| The action queue is empty. Waiting for players    |
| to submit actions via their browsers.             |
|                                                   |
| Run /dm:party-next again later, or use            |
| /dm:party-auto for automatic polling.             |
+--------------------------------------------------+
```
Then stop. Do not proceed further.

### Step 2 — Display Action Header

Display the action information:

```
+--------------------------------------------------+
|         PARTY MODE: PLAYER ACTION                 |
+--------------------------------------------------+
| Player:    {player_id}                            |
| Action ID: {action_id}                            |
| Submitted: {timestamp}                            |
| Remaining: {remaining} action(s) in queue         |
+--------------------------------------------------+
| Action: "{action_text}"                           |
+--------------------------------------------------+
```

### Step 3 — Process the Action as DM

Now process this action exactly like `/dm:action` would. You ARE the DM. Follow the complete game loop:

**3a. CONTEXT** — Gather what you need:
- Call `get_game_state` for current situation
- Call `get_character` for the acting PC's stats (use `{player_id}` as the character name)
- If the action involves a location or NPC, call `get_location` / `get_npc`
- If the action involves rules, call `search_rules` / `get_spell_info`

**3b. DECIDE** — What happens based on the action?
- Does it need an ability check? Set DC based on difficulty.
- Does it trigger combat? Initiate if so.
- Is it pure narration? Resolve it narratively.

**3c. EXECUTE** — Resolve it:
- Call `roll_dice` for any checks, attacks, saves
- Apply modifiers from character stats
- Compare results to DC or AC

**3d. PERSIST** — Update state BEFORE narrating:
- `update_character` for HP changes, conditions
- `add_item_to_character` for loot
- `update_game_state` for location changes, time
- `update_quest` for objective progress
- `add_event` for significant moments

**3e. NARRATE** — Describe the outcome in DM voice.

### Step 4 — Push Response to Queue

After narrating, call `party_resolve_action` with:
- `action_id`: the action_id from Step 1
- `narrative`: the full narrative text from Step 3e
- `private_messages`: JSON string for player-specific secret messages (optional)
- `dm_notes`: DM-only notes if relevant (optional)

### Step 5 — Confirm Broadcast

Display:
```
Response broadcast to connected players.
{remaining} action(s) remaining in queue.
```

If there are more actions pending, suggest:
```
Run /dm:party-next to process the next action, or /dm:party-auto for continuous processing.
```

## Important Rules

1. **Process exactly one action per invocation.** Pop one, resolve one, push one.
2. **The action comes from a specific player.** Always process it as that player's character acting.
3. **Push the response AFTER narrating.** The response queue triggers WebSocket broadcast automatically.
4. **Never skip the resolution.** Even trivial actions get narrated and broadcast.
