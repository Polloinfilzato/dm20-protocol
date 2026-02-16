---
issue: 118
stream: error-ux-hardening
agent: python-pro
started: 2026-02-15T03:29:25Z
status: completed
---

# Stream 1: Error UX Hardening

## Scope
Wrap all player-facing code paths with ErrorMessageFormatter

## Files
- src/dm20_protocol/claudmaster/tools/action_tools.py (modify)
- src/dm20_protocol/claudmaster/tools/session_tools.py (modify)
- src/dm20_protocol/claudmaster/recovery/error_messages.py (modify)
- tests/claudmaster/test_error_ux.py (new)
- tests/claudmaster/test_session_integration.py (fix assertions)

## Progress
- 17 new tests + 2 fixed pre-existing tests
- Commits: 247f252, 5cc4cda
- 1500 total tests passing
