---
issue: 68
stream: session-tool-fixes
agent: general-purpose
started: 2026-02-09T01:41:19Z
status: in_progress
---

# Stream A: Session Tool Fixes & player_action Registration

## Scope
Fix start_claudmaster_session, register player_action as MCP tool, fix active_quests in session state

## Files
- src/dm20_protocol/claudmaster/tools/session_tools.py
- src/dm20_protocol/claudmaster/tools/action_tools.py
- src/dm20_protocol/main.py (Claudmaster section only, lines 2200+)
- tests/ (new/existing test files)

## Progress
- Starting implementation
