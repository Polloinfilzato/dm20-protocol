---
description: Auto-save and refresh the session to free context window space.
allowed-tools: Skill, Write, mcp__dm20-protocol__get_game_state, mcp__dm20-protocol__get_campaign_info
---

# DM Refrill

Autonomous session save and context refresh. Saves the full session, creates a recovery checkpoint, and prepares for automatic campaign resume after compaction.

## Usage
```
/dm:refrill
```

No arguments needed.

## Instructions

### 1. Gather State

Call in parallel:
- `get_game_state()` — current session info, location, notes
- `get_campaign_info()` — active campaign name

If no active session: "No active session — nothing to refresh."

### 2. Save Session

Invoke `/dm:save` using the Skill tool:
```
skill: "dm:save"
```

Wait for save to complete before proceeding.

### 3. Create Recovery Checkpoint

Write the campaign name to `.claude/last-campaign.txt` using the Write tool:
```
Write(".claude/last-campaign.txt", campaign_name)
```

This file is read by the SessionStart hook after compaction to auto-resume.

### 4. Trigger Compaction

After save and checkpoint are confirmed, output ONLY this message — nothing else:

```
---
✅ **Session saved. Checkpoint created.**

Digita **`/compact`** per completare il refresh.
La campagna ripartirà automaticamente dopo la compattazione.
---
```

**CRITICAL RULES:**
- Do NOT list manual steps or additional commands
- Do NOT tell the user to run `/dm:start` — the SessionStart hook handles auto-resume
- Do NOT add explanations or caveats — keep the output minimal
- The ONLY manual action the user needs is typing `/compact`
