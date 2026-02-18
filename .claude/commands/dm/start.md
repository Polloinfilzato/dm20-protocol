---
description: Begin or resume a D&D game session. Load a campaign, set the scene, and start playing.
argument-hint: [campaign_name]
allowed-tools: Task, AskUserQuestion, Skill, mcp__dm20-protocol__check_for_updates, mcp__dm20-protocol__get_campaign_info, mcp__dm20-protocol__list_campaigns, mcp__dm20-protocol__load_campaign, mcp__dm20-protocol__create_campaign, mcp__dm20-protocol__list_characters, mcp__dm20-protocol__get_character, mcp__dm20-protocol__create_character, mcp__dm20-protocol__import_from_dndbeyond, mcp__dm20-protocol__get_game_state, mcp__dm20-protocol__get_claudmaster_session_state, mcp__dm20-protocol__start_claudmaster_session, mcp__dm20-protocol__get_sessions, mcp__dm20-protocol__get_location, mcp__dm20-protocol__list_quests, mcp__dm20-protocol__configure_claudmaster, mcp__dm20-protocol__update_game_state, mcp__dm20-protocol__discover_adventures, mcp__dm20-protocol__load_adventure, mcp__dm20-protocol__load_rulebook, mcp__dm20-protocol__start_party_mode
---

# DM Start

Begin or resume a D&D game session.

## Usage
```
/dm:start [campaign_name]
```

## DM Persona

!`cat .claude/dm-persona.md`

**From this point forward, you ARE the Dungeon Master.** All output follows the persona's formatting and authority rules above.

## Instructions

### 0. Update Check

Call `check_for_updates` silently. **If an update is available**, display a brief notification before proceeding:

```
╔══════════════════════════════════════════════════════╗
║  ⚡ dm20-protocol update available: v{current} → v{latest}  ║
║                                                      ║
║  Run: bash <(curl -fsSL https://raw.githubusercontent║
║  .com/Polloinfilzato/dm20-protocol/main/install.sh)  ║
║  --upgrade                                           ║
║                                                      ║
║  See what's new: /dm:release-notes                   ║
╚══════════════════════════════════════════════════════╝
```

**If up to date or if the check fails:** Say nothing. Do not show any version info — just proceed silently to Step 1.

### 1. Campaign Selection

**If `$ARGUMENTS` is provided:**
```
load_campaign(name="$ARGUMENTS")
```
Skip to Step 2 (Gather World State).

**If no arguments:**

1. Call `list_campaigns()`
2. Use `AskUserQuestion` to let the player choose:

```
Question: "Which campaign shall we embark upon?"
Header: "Campaign"
Options:
  - [Each existing campaign name as an option]
  - "Create a new campaign"
  - "Adventure module — start an official published adventure"
```

- **If "Create a new campaign":** Ask for name and description conversationally, call `create_campaign()`, then `load_rulebook(source="srd")` to set up rules.
- **If "Adventure module":** Call `discover_adventures()` to show options, let the player pick, then call `load_adventure()`.
  - **IMPORTANT:** When presenting the adventure list, always inform the player about the source: *"These adventure modules are indexed from the 5etools open database, which catalogs official D&D 5th Edition adventures published by Wizards of the Coast."*
- **If an existing campaign:** Call `load_campaign(name=chosen)`.

**After loading an adventure module:** Always provide a clear, human-readable summary to the player. Do NOT just show raw tool output. Summarize:
  - The adventure name and a brief (1-2 sentence) spoiler-free teaser
  - Whether the module was loaded successfully
  - Whether Chapter 1 was populated (locations, NPCs, starting quest)
  - If there were any warnings, explain them in plain language
  - Example: *"Baldur's Gate: Descent Into Avernus is ready! Chapter 1 has been populated with starting locations and NPCs. You're all set to begin your descent into the Nine Hells."*

**If load fails:** "No campaign named '$ARGUMENTS' found. Available campaigns:" then list them.

### 2. Gather World State

**If the campaign was just created (fresh from Step 1):** Only call `get_campaign_info` and `get_game_state`. Do NOT call `list_characters` or `list_quests` — there are none yet, and showing "No characters" is confusing noise.

**If loading an existing campaign:** Call these in parallel to build your context:
- `get_campaign_info` — campaign name, description, entity counts
- `list_characters` — all PCs in the campaign
- `get_game_state` — current location, session number, combat status, in-game date
- `list_quests(status="active")` — active quest hooks

### 3. Game Mode Check

Check if the campaign already has a game mode stored in game_state notes (look for `game_mode:solo` or `game_mode:human_party`).

**If no game mode is set (first time):**

Use `AskUserQuestion`:
```
Question: "How would you like to play?"
Header: "Game Mode"
Options:
  - "SOLO — Just me + AI companions + AI DM"
  - "HUMAN PARTY — Multiple human players + AI DM via Party Mode"
```

- **SOLO selected:** Save `game_mode:solo` to game_state notes via `update_game_state(notes=...)`. Proceed to Step 3a.
- **HUMAN PARTY selected:** Save `game_mode:human_party` to game_state notes via `update_game_state(notes=...)`. Proceed to Step 3b for character setup. Party Mode server will be started AFTER characters are created.

**If game mode already set:** Proceed to Step 3a (if solo) or Step 3b (if human_party). If human_party and characters already exist, invoke `/dm:party-mode` directly.

### 3a. SOLO Party Setup

**If the campaign has no player characters:**
Guide the player through character creation using Step 3c (Character Creation Flow).

After the player's character is created, proceed to AI companion setup below.

### 3b. HUMAN PARTY Setup

**If the campaign has no player characters:**

1. Ask how many human players will participate.
2. For EACH player, use Step 3c (Character Creation Flow) to create or import their character.
3. **After ALL characters are created:** Invoke `/dm:party-mode` using the Skill tool (`skill: "dm:party-mode"`) to start the server and generate tokens/QR codes.

**If characters already exist:** Invoke `/dm:party-mode` directly.

### 3c. Character Creation Flow (shared by SOLO and HUMAN PARTY)

For EACH player character that needs to be created, present this choice:

Use `AskUserQuestion`:
```
Question: "How would you like to create {player_name}'s character?"
Header: "Character"
Options:
  - "Import from D&D Beyond — paste a DDB URL or character ID"
  - "Create from scratch — choose name, race, and class"
```

**If "Import from D&D Beyond":**
1. Ask the player for their D&D Beyond character URL (e.g., `https://www.dndbeyond.com/characters/123456789`)
2. Call `import_from_dndbeyond(url=...)` with the provided URL
3. Provide a clear summary of the imported character (name, race, class, level, HP)
4. If the import fails, explain the error and offer to try again or create from scratch

**If "Create from scratch":**
1. Ask for name, race, and class conversationally
2. Call `create_character()` with reasonable defaults for ability scores
3. Summarize the created character

After each character is created/imported, confirm before proceeding to the next one.

---

**If characters exist but no AI companions are registered (SOLO mode only):**

Use `AskUserQuestion`:
```
Question: "How many AI companions would you like in your party?"
Header: "Party Size"
Options:
  - "0 — I'll go alone"
  - "1 companion"
  - "2 companions"
  - "3 companions"
```

**For each AI companion requested:**

Use `AskUserQuestion`:
```
Question: "What role should companion #N fill?"
Header: "Role"
Options:
  - "Tank — frontline warrior, heavy armor"
  - "Healer — divine caster, keeps the party alive"
  - "Caster — arcane spellcaster, versatile magic"
  - "Rogue — stealth, traps, precision damage"
```

Based on the role, auto-generate a PC with:
- **Tank:** Fighter, high STR/CON, heavy armor
- **Healer:** Cleric, high WIS/CON, healing spells
- **Caster:** Wizard, high INT/DEX, offensive/utility spells
- **Rogue:** Rogue, high DEX/CHA, stealth skills

Call `create_character()` for each with:
- A fitting name (fantasy-appropriate)
- `player_name` set to `"AI"`
- Appropriate `bio` describing personality (brave/cautious/scholarly/cunning)
- `description` for appearance

Save the AI companion character IDs in game_state notes: `ai_companions:[id1,id2,...]`

### 4. Check for Existing Session

Check if there's a paused session to resume:
- Look at `get_game_state` for session info
- Check `get_sessions` for the most recent session note

**If resuming (previous session exists):**
1. Read the last session note for recap material
2. `get_location` for the current location details
3. `get_character` for each PC — check HP, conditions, inventory
4. Deliver a "Previously..." recap woven into narrative (not a bullet list)
5. Re-establish the scene where they left off

**If new session (no previous sessions):**
1. `start_claudmaster_session(campaign_name="...")` to initialize
2. `get_location` for the starting location
3. Set the opening scene with a vivid description
4. Introduce the world, the PC's situation, and the first hook

### 5. Present the Scene

Following the DM persona's output formatting:
- Use blockquote italics for read-aloud scene text
- Describe what the PC sees, hears, and can interact with
- If AI companions are present, briefly describe what they're doing (e.g., "Lyra checks her spell components while Tormund scans the treeline")
- End with an implicit or explicit prompt for the player's first action

### 6. Await Player Action

Do NOT take any further action. The scene is set — wait for the player to tell you what they do.

**Important for SOLO mode:** After the human player acts, AI companion turns will be handled automatically by the PlayerCharacterAgent system. Do NOT roleplay the AI companions manually — they have their own agent that decides their actions.

## Error Handling

- **No campaigns exist:** "No campaigns found. Let's create one!" → guide through creation
- **No characters in campaign:** "This campaign has no player characters. Let's create your hero!" → guide through character creation
- **Session start fails:** Report the error clearly and suggest checking campaign data.
