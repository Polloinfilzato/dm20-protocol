---
description: Switch model quality profile (quality/balanced/economy)
argument-hint: <quality|balanced|economy>
allowed-tools: mcp__dm20-protocol__configure_claudmaster, mcp__dm20-protocol__get_game_state
---

# Model Profile Switch

Switch the model quality tier for all Claudmaster agents and CC sub-agents at once.

**Note:** This feature is specific to Claude Code with Anthropic's Opus models. The effort parameter controls how much processing Opus puts into each response. Other MCP clients or LLM backends won't benefit from effort levels.

## Instructions

### If no argument is provided ($ARGUMENTS is empty)

1. Call `configure_claudmaster()` with no arguments to show the current config
2. Present the three profiles to the user:

| Profile | Model + Effort | CC Agents | Best for |
|---------|---------------|-----------|----------|
| **quality** | Opus, effort high | Opus | Boss fights, key story moments, maximum immersion |
| **balanced** | Opus, effort medium | Opus | General play, good balance of quality and cost |
| **economy** | Opus, effort low | Haiku | Stretching token budgets, fast responses, casual play |

3. Ask the user to run `/dm:profile <tier>` to switch

### If an argument is provided

1. Validate the argument is one of: quality, balanced, economy
2. Call `configure_claudmaster(model_profile="$ARGUMENTS")`
3. Show what changed:
   - Python-side config (model, effort level, temperatures, max_tokens)
   - CC agent files updated (narrator.md, combat-handler.md)
   - rules-lookup.md always stays on haiku
4. Instruct the user to run `/model <recommended>` to match the CC main model

### Tips to include

- "On Max plan, use **balanced** (Opus medium effort = Sonnet quality, ~76% fewer tokens) for everyday play, switch to **quality** for boss fights."
- "You can switch profiles mid-session -- changes take effect on the next action."
- "Individual settings can still be tweaked via `configure_claudmaster()` after applying a profile (profile will show as CUSTOM)."
