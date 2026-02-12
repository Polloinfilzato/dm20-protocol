---
description: Save the current D&D game session and pause. Creates session notes and a narrative stopping point.
allowed-tools: mcp__dm20-protocol__get_game_state, mcp__dm20-protocol__get_character, mcp__dm20-protocol__list_characters, mcp__dm20-protocol__get_events, mcp__dm20-protocol__list_quests, mcp__dm20-protocol__add_session_note, mcp__dm20-protocol__end_claudmaster_session, mcp__dm20-protocol__update_game_state, mcp__dm20-protocol__add_event
---

# DM Save

Save the current game session and pause.

## Usage
```
/dm:save
```

No arguments needed. Saves the current session state and provides a narrative stopping point.

## Prerequisites

A game session must be active. If not: "No active session — nothing to save."

## DM Persona

!`cat .claude/dm-persona.md`

## Instructions

### 1. Gather Session Data

Call in parallel:
- `get_game_state` — current location, session number, in-game date
- `list_characters` — all PCs and their current state
- `get_events` — events logged during this session
- `list_quests(status="active")` — current quest state

### 2. Generate Session Summary

From the events and game state, compose:
- **Summary**: 2-3 sentence overview of what happened this session
- **Key events**: list of significant moments
- **NPCs encountered**: names of NPCs the party interacted with
- **Quest updates**: any objectives completed or new quests accepted
- **Combat encounters**: brief summary of any fights

### 3. Save Session Note

```
add_session_note(
  session_number=N,
  summary="...",
  title="Session N: [evocative title]",
  events=["..."],
  npcs_encountered=["..."],
  quest_updates={"quest_name": "progress description"},
  combat_encounters=["..."],
  characters_present=["..."]
)
```

### 4. Log Session End Event

```
add_event(
  event_type="session",
  title="Session N End",
  description="Session saved. [brief state summary]",
  importance=2
)
```

### 5. Update Game State

```
update_game_state(
  notes="Session paused. [current situation in 1 sentence]"
)
```

### 6. End Claudmaster Session

```
end_claudmaster_session(
  session_id="...",
  mode="pause",
  summary_notes="[brief DM notes for next session]"
)
```

### 7. Narrative Closing

Deliver a closing narration as the DM:
- Write a natural pause point or atmospheric cliffhanger
- Use the DM persona's read-aloud formatting (blockquote italics)
- Make the player want to come back

Then confirm the save with a brief out-of-character summary:

```
---
**Session saved.**
- Session: N
- Location: [current location]
- In-game date: [date]
- PC status: [name] — [HP/max HP]
- Active quests: [count]

Resume with `/dm:start [campaign_name]`
```

## Error Handling

- **No active session:** "No active game session to save. Nothing to do."
- **Save fails:** Report the error, suggest the player try again or check storage.
- **No events this session:** Still save — note it was a short session.
