---
issue: 77
stream: fix-dm-commands
started: 2026-02-12T11:40:31Z
status: completed
---

# Stream 1: Fix /dm:action and /dm:combat Invocation

## Root Cause

`disable-model-invocation: true` in command frontmatter prevented the Skill tool from invoking these commands. When typed mid-session, Claude attempted Skill-tool invocation which was blocked.

## Fix Applied

Removed `disable-model-invocation: true` from all 4 DM commands for consistency:
- `.claude/commands/dm/action.md`
- `.claude/commands/dm/combat.md`
- `.claude/commands/dm/start.md`
- `.claude/commands/dm/save.md`

## Rationale

The `disable-model-invocation` flag is redundant because:
1. The DM persona and command instructions already define when each command should be used
2. The `allowed-tools` list in each command already scopes what tools are available during execution
3. The flag was causing failures when users typed `/dm:action` during a session and Claude attempted to process it via the Skill tool

## Files Modified

- `.claude/commands/dm/action.md`
- `.claude/commands/dm/combat.md`
- `.claude/commands/dm/start.md`
- `.claude/commands/dm/save.md`
