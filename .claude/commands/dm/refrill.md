---
description: Auto-save and refresh the session to free context window space.
allowed-tools: Skill, mcp__dm20-protocol__get_game_state, mcp__dm20-protocol__get_campaign_info
---

# DM Refrill

Auto-save the current session and provide instructions to refresh the context window.

## Instructions

1. Call `get_game_state()` to capture the current campaign name and session info.
2. Call `get_campaign_info()` to get the campaign name.
3. Invoke `/dm:save` using the Skill tool (`skill: "dm:save"`) to save the current session.
4. After save completes, output the following message to the user:

```
---
**Context refresh in progress.**

Session saved successfully. To free context window space, run these commands in order:

1. `/clear` — clears conversation context
2. `/dm:start {campaign_name}` — resumes your campaign

Or just copy-paste this after clearing:
`/dm:start {campaign_name}`

Your game state, characters, quests, and session notes are all safely persisted.
---
```

Replace `{campaign_name}` with the actual campaign name from the game state.
