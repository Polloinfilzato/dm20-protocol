---
issue: 76
stream: dice-roll-labels
started: 2026-02-12T11:40:31Z
status: completed
---

# Stream 1: Dice Roll Context Labels

## Changes
- Added optional `label` parameter to `roll_dice` in main.py
- Updated DM persona to require labels on all rolls
- Label displays as prefix in roll output

## Files Modified
- src/dm20_protocol/main.py (roll_dice function)
- .claude/dm-persona.md (EXECUTE section, Combat Protocol)
