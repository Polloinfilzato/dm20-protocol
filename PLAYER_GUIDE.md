# Player Guide: Solo D&D with dm20-protocol

dm20-protocol turns Claude Code into a complete Dungeon Master for D&D 5e. You describe what your character does in natural language, Claude handles everything else: narration, NPCs, rules, combat, dice.

Everything is controlled with **4 slash commands**:

| Command | What it does |
|---------|-------------|
| `/dm:start` | Begin or resume a session |
| `/dm:action` | Do something as your character |
| `/dm:combat` | Start or manage combat |
| `/dm:save` | Save session and pause |

---

## Quick Start: Your First Session

### Step 1 — Prepare the Campaign

Before playing, you need to set up campaign data. Ask Claude in plain language:

> *"Create a campaign called 'The Dark Valley'. Setting: a remote valley infested by undead. Create a character: Kael, level 1 human fighter with 16 Strength and 14 Constitution. Create a tavern as the starting location and a bartender NPC."*

Claude will use the MCP tools behind the scenes (`create_campaign`, `create_character`, `create_location`, `create_npc`) to set everything up.

### Step 2 — Start Playing

```
/dm:start The Dark Valley
```

Claude loads the campaign, activates the DM persona, and describes the opening scene. From that moment, you're IN the game.

### Step 3 — Play!

```
/dm:action I look at the notice board
/dm:action I ask the bartender if he has work for an adventurer
/dm:action I head north along the road
```

Claude handles everything: rolls dice when needed, roleplays NPCs, describes the environment, updates game state.

### Step 4 — Save When You Want

```
/dm:save
```

Saves everything and gives you a summary plus a narrative cliffhanger.

---

## Game Commands in Detail

### `/dm:start [campaign_name]`

Starts or resumes a game session.

**First session:** Claude describes the opening scene and introduces the world.

**Later sessions:** Claude delivers a "Previously..." recap based on saved session notes, then picks up exactly where you left off.

**Examples:**
```
/dm:start The Dark Valley       # load specific campaign
/dm:start                        # shows campaign list and asks which one
```

**What happens behind the scenes:**
1. Loads the campaign from the database
2. Retrieves characters, game state, active quests
3. Checks for a previous session to resume
4. Activates the DM persona (Claude becomes the Dungeon Master)
5. Presents the scene and waits for your first action

---

### `/dm:action <what you do>`

The main gameplay command. Describe what your character does and Claude resolves it.

**Examples:**
```
/dm:action I search the room for traps
/dm:action I try to convince the guard to let us pass
/dm:action I attack the goblin with my sword
/dm:action I open the door and look around
/dm:action I ask Berta what she knows about the goblins
```

**Tips for writing actions:** Write naturally, as if talking to a DM at a real table:
- **Exploration**: "I look", "I search", "I examine", "I move toward"
- **Social**: "I ask", "I try to convince", "I lie and say that"
- **Combat**: "I attack", "I cast a spell", "I hide"
- **Other**: "I rest", "I buy", "I use the item"

Claude follows the **CONTEXT → DECIDE → EXECUTE → PERSIST → NARRATE** cycle:
1. Gathers context (where you are, who you are, what's around)
2. Decides if a dice roll, NPC reaction, or pure narration is needed
3. Rolls dice and applies rules
4. Updates game state (HP, position, quests)
5. Narrates the result — you only see the story, not the numbers

---

### `/dm:combat [situation]`

Starts a combat encounter or continues an active one.

**Examples:**
```
/dm:combat three goblins ambush us!
/dm:combat                            # if combat is already active, continues
```

**How combat works:**

1. Claude identifies all combatants and rolls initiative
2. Announces turn order
3. **Your turn**: tells you it's your turn and waits for your action
4. **Enemy turns**: decides tactically and resolves (enemies are intelligent!)
5. Repeats until combat ends
6. At the end: XP, loot, aftermath narration

**During combat**, just say what your character does:
- *"I attack the nearest goblin with my sword"*
- *"I cast Cure Wounds on myself"*
- *"I disengage and run toward the door"*

---

### `/dm:save`

Saves the session state and pauses the game.

```
/dm:save
```

**What gets saved:**
- Current position and world state
- Character HP and inventory
- Active quests and completed objectives
- Session summary and key events
- Notes for the next session

**Output:** A narrative cliffhanger + a technical summary with stats.

---

## Context Management (Important!)

Claude Code has a limited context window. During a game session it fills up quickly (narration, tool calls, dice rolls). When it reaches 50-60%, it's time to save and reload.

### The Save/Resume Flow

```
1. /dm:save                          ← saves everything to the backend
2. /clear                            ← clears Claude's context
3. /dm:start Campaign Name           ← reloads everything, delivers recap, resumes
```

**Where is data saved?** All data (campaign, characters, events, state) is persisted by the MCP server in its on-disk database. These are **not markdown files** — they are persistent data managed by the Python backend. When you run `/dm:start`, everything is reloaded from the database, even in a completely new conversation.

### When to Save/Resume?

| Situation | What to do |
|-----------|-----------|
| Context at 50-60% | `/dm:save` → `/clear` → `/dm:start` |
| Natural end of a scene | Good moment for `/dm:save` |
| Before a long combat | `/dm:save` for a fresh context |
| Want to continue tomorrow | `/dm:save` and close everything |
| Claude gets slow or repetitive | Context is probably full — save and reload |

### Alternatives

| Command | What it does | When to use |
|---------|-------------|-------------|
| `/clear` | Clears all context | After saving with `/dm:save` |
| `/compact` | Compresses old messages | For small gains without reloading |

**Rule of thumb:** `/compact` is fine for small gains. For long sessions, the **save → clear → start** flow is much more effective and also tests the persistence system!

---

## Preparing a Campaign

Before playing, you need to prepare data. You can do it in plain language — Claude understands and uses the right tools.

### Setup Checklist

- **Campaign**: name, description, setting
- **Character**: name, class, race, level, stats, equipment
- **Starting location**: a tavern, village, or city
- **At least 1 NPC**: someone to interact with
- **Starting quest**: something to do (optional but recommended)
- **Rulebook**: load the SRD with *"load the 2014 SRD rulebook"*

### Complete Setup Example

> *"Set up a campaign for me:*
> - *Name: 'The Dungeons of Zarak'*
> - *Setting: a port city with catacombs under the old quarter*
> - *My character: Lyra, level 1 elf wizard, 16 Intelligence, 14 Dexterity, 12 Constitution*
> - *NPC: Master Voss, a mysterious gnome antiquarian who knows about the catacombs*
> - *Location: Voss's shop, 'Curiosities & Antiquities'*
> - *Quest: explore the catacombs to find an ancient artifact*
> - *Also load the SRD"*

---

## Two Modes of Use

dm20-protocol can be used in **two different ways**:

### 1. Automatic DM (Solo Play)

Use the `/dm:*` commands and Claude becomes your full DM. It handles everything: narrative, NPCs, rules, combat. You are just the player.

This is the mode designed for solo play.

### 2. DM Assistant (You Are the DM)

If you're the DM for a group of players, you can use the MCP tools directly (without `/dm:*` commands) as an assistant:

- *"Roll 3d6+2"* → `roll_dice`
- *"How much HP does Thorin have?"* → `get_character`
- *"Everyone takes 8 damage"* → `bulk_update_characters`
- *"Add a note for session 5"* → `add_session_note`

In this case Claude doesn't act as the DM — it's just your management tool.

**Quick Reference (Assistant Mode):**

| I want to... | Tell Claude... |
|--------------|---------------|
| Create a campaign | *"Create a campaign called..."* |
| Create a PC | *"Create a character: name, class, race, level"* |
| View a PC | *"Show me the sheet for [name]"* |
| Apply damage | *"[Name] takes X damage"* |
| Damage everyone | *"Everyone takes X damage"* |
| Give an item | *"Give [name] a [item]"* |
| Create an NPC | *"Create NPC [name], [description]"* |
| Roll dice | *"Roll 1d20+5"* |
| Session notes | *"Save notes for session X: [summary]"* |
| Game state | *"What's the current game state?"* |

---

## Troubleshooting

**"Claude doesn't behave like a DM"**
Did you use `/dm:start`? Without that command, the DM persona is not activated.

**"Context filled up too quickly"**
Combat consumes a lot of context (many tool calls). Save before long combats and reload with fresh context.

**"It doesn't remember what happened before"**
If you used `/clear` without `/dm:save`, conversation data is lost. Backend data (HP, position, quests) always persists, but in-conversation narration does not. Always save before clearing!

**"Can't find the campaign"**
Check the exact name with *"show available campaigns"* or simply `/dm:start` without arguments.

**"Monsters don't have stat blocks"**
The SRD may not have all monsters. Ask Claude to use standard values or find a similar one.
