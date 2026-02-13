# Player Guide: Solo D&D with dm20-protocol

dm20-protocol turns Claude Code into a complete Dungeon Master for D&D 5e. You describe what your character does in natural language; Claude handles everything else -- narration, NPCs, rules, combat, dice rolls, loot, and story progression.

Everything happens through **4 slash commands**:

| Command | What it does |
|---------|-------------|
| `/dm:start` | Begin or resume a session |
| `/dm:action` | Do something as your character |
| `/dm:combat` | Start or manage combat |
| `/dm:save` | Save session and pause |

---

## What is dm20-protocol?

dm20-protocol is an MCP (Model Context Protocol) server that gives Claude Code a full D&D 5e backend: campaign management, character sheets, rulebook data, dice rolling, combat tracking, session persistence, and more. When you run `/dm:start`, Claude transforms into an AI Dungeon Master and runs a solo adventure for you.

You are the player. Claude is the DM. There is no setup beyond creating a campaign, loading a rulebook, and making a character.

---

## Getting Started

### Step 1: Load Rulebooks

Before creating a character, load a rulebook so the system has access to class features, racial traits, spells, monsters, and equipment data. Ask Claude in plain language:

> *"Load the SRD 2014 rulebook"*

This calls `load_rulebook source="srd"` behind the scenes. You can load multiple sources for broader content:

| Source | What it contains | How to load |
|--------|-----------------|-------------|
| **SRD 2014** | Core 5e rules, 12 classes, 9 races, 300+ spells, 300+ monsters | *"Load the SRD 2014 rulebook"* |
| **SRD 2024** | Updated 2024 SRD revision | *"Load the SRD 2024 rulebook"* |
| **Open5e** | Community-curated OGL content from multiple publishers | *"Load the Open5e rulebook"* |
| **5etools** | Comprehensive 5e data including extended monster library | *"Load the 5etools rulebook"* |
| **Custom JSON** | Your own homebrew content in CustomSource format | *"Load custom rulebook from path/to/file.json"* |
| **PDF Library** | Scanned PDFs and Markdown files from your library folder | See [Multi-Source Rulebooks](#multi-source-rulebooks-srd-open5e-5etools-custompdf) |

You can stack multiple sources. Content from later-loaded sources supplements earlier ones.

### Step 2: Create Your Character

Once a rulebook is loaded, tell Claude to create your character. The system auto-populates saving throws, proficiencies, starting equipment, features, HP, spell slots, and more from the rulebook data.

#### Manual Ability Scores (default)

Set each score directly:

> *"Create a character: Kael, level 1 human fighter, 16 Strength, 14 Constitution, 12 Dexterity, 10 Wisdom, 8 Intelligence, 8 Charisma"*

#### Standard Array

Distribute the values **15, 14, 13, 12, 10, 8** across your six abilities:

> *"Create a character: Lyra, level 1 elf wizard, using Standard Array. Assign Intelligence 15, Dexterity 14, Constitution 13, Wisdom 12, Charisma 10, Strength 8"*

The system validates that your assignments use exactly the Standard Array values.

#### Point Buy

Spend **27 points** on ability scores between 8 and 15 (using PHB cost table):

| Score | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 |
|-------|---|---|----|----|----|----|----|----|
| Cost  | 0 | 1 | 2  | 3  | 4  | 5  | 7  | 9  |

> *"Create a character: Thorin, level 1 dwarf cleric, using Point Buy. Assign Wisdom 15, Constitution 14, Strength 13, Charisma 12, Dexterity 10, Intelligence 8"*

The system validates that your total cost is exactly 27 points.

#### What gets auto-populated

When a rulebook is loaded, the character builder automatically fills in:

- **Hit points** (max at level 1, average per PHB for higher levels)
- **Saving throw proficiencies** from your class
- **Skill proficiencies** from your class and background
- **Tool proficiencies** and **languages** from class, race, and background
- **Racial ability bonuses** applied on top of your base scores
- **Starting equipment** from your class and background
- **Class features** and **racial traits** up to your starting level
- **Spell slots** for spellcasting classes
- **Speed**, **proficiency bonus**, and **hit dice**

#### Optional fields

You can also specify:

- **Background**: `background: "Acolyte"` -- adds extra proficiencies, equipment, and a background feature
- **Subclass**: required if your starting level is at or above the subclass level (typically 3)
- **Subrace**: `subrace: "Hill Dwarf"` for races with subraces
- **Alignment**, **description**, **bio**: flavor text for your character

### Step 3: Set Up the World

Before starting, create the minimum world data:

- **Campaign**: a name, description, and setting
- **Starting location**: a tavern, village, dungeon entrance, or city
- **At least 1 NPC**: someone to interact with
- **Starting quest** (recommended): something to do

You can do all of this in a single natural-language request:

> *"Set up a campaign for me:*
> - *Name: 'The Dungeons of Zarak'*
> - *Setting: a port city with catacombs under the old quarter*
> - *My character: Lyra, level 1 elf wizard, Standard Array: INT 15, DEX 14, CON 13, WIS 12, CHA 10, STR 8, background Sage*
> - *NPC: Master Voss, a mysterious gnome antiquarian who knows about the catacombs*
> - *Location: Voss's shop, 'Curiosities and Antiquities'*
> - *Quest: explore the catacombs to find an ancient artifact*
> - *Load the SRD 2014 rulebook"*

Claude uses the MCP tools behind the scenes to create everything at once.

---

## Playing the Game

### Starting a Session (`/dm:start`)

```
/dm:start The Dungeons of Zarak
```

Claude loads the campaign, gathers all world state (characters, locations, NPCs, quests), activates the DM persona, and describes the opening scene. From that moment, you are in the game.

**First session**: Claude sets the scene with a vivid description and introduces the world.

**Later sessions**: Claude delivers a "Previously..." recap from saved session notes, then picks up exactly where you left off.

If you omit the campaign name, Claude lists available campaigns and asks you to choose:

```
/dm:start
```

**What happens behind the scenes:**
1. Loads the campaign and all associated data
2. Retrieves characters, game state, active quests
3. Checks for a previous session to resume (via session notes)
4. Activates the DM persona -- Claude *becomes* the Dungeon Master
5. Presents the scene and waits for your first action

### Taking Actions (`/dm:action`)

The core gameplay command. Describe what your character does and Claude resolves it.

```
/dm:action I search the room for traps
/dm:action I try to convince the guard to let us pass
/dm:action I attack the goblin with my sword
/dm:action I ask Berta what she knows about the missing merchant
/dm:action I cast Detect Magic and scan the altar
```

**Write naturally**, as if talking to a DM at a real table:

- **Exploration**: "I look around", "I search the chest", "I examine the inscription"
- **Social**: "I ask the innkeeper about rumors", "I intimidate the bandit", "I lie about my identity"
- **Combat**: "I attack with my longsword", "I cast Fireball", "I hide behind the pillar"
- **Other**: "I take a short rest", "I buy a healing potion", "I use my thieves' tools on the lock"

Claude follows the **CONTEXT -- DECIDE -- EXECUTE -- PERSIST -- NARRATE** cycle for every action:

1. **Context**: gathers your current location, stats, surroundings
2. **Decide**: determines if a dice roll, NPC reaction, or pure narration is needed
3. **Execute**: rolls dice, applies rules, resolves the outcome
4. **Persist**: updates game state (HP, position, quests, inventory) via backend tools
5. **Narrate**: describes the result as fiction -- you see the story, not the numbers

### Combat (`/dm:combat`)

Start a combat encounter by describing the situation:

```
/dm:combat Three goblins ambush us from the treeline!
```

If combat is already active, running `/dm:combat` without arguments continues it.

**How combat works:**

1. Claude identifies all combatants and rolls initiative for everyone
2. Announces turn order (highest initiative first)
3. **Your turn**: Claude tells you it is your turn and waits for your action
4. **Enemy turns**: Claude decides enemy actions tactically and resolves them
5. Repeats each round until combat ends
6. **Aftermath**: XP calculation, loot, and narrative transition back to exploration

**During combat**, describe your action on your turn:

- *"I attack the nearest goblin with my longsword"*
- *"I cast Cure Wounds on myself"*
- *"I disengage and run toward the door"*
- *"I use my bonus action to cast Healing Word on the downed ranger, then attack with my mace"*

Enemy tactics scale with the **difficulty** setting:

| Difficulty | Enemy behavior |
|------------|---------------|
| Easy | Enemies make mistakes, poor coordination |
| Normal | Solid tactics, reasonable self-preservation |
| Hard | Optimal targeting, terrain use, coordinated abilities |
| Deadly | Perfect tactics, no mercy, may target downed PCs |

### Saving Progress (`/dm:save`)

```
/dm:save
```

Saves the entire session state and provides a narrative stopping point.

**What gets saved:**
- Current location and world state
- Character HP, inventory, conditions
- Active quests and completed objectives
- Session summary and key events
- DM notes for the next session

**Output:** A narrative cliffhanger (making you want to come back) followed by a technical summary with session number, location, HP status, and active quest count.

---

## Character Management

### Level Up

When your character earns enough XP or the DM decides it is time, level up with:

> *"Level up Kael"*

This calls `level_up_character` which handles everything automatically:

- **HP increase**: average (PHB standard: hit die / 2 + 1 + CON mod) or rolled
- **New class features** added from the rulebook
- **Hit dice** updated to match new level
- **Proficiency bonus** updated if the level crosses a threshold (5, 9, 13, 17)
- **Spell slots** updated for spellcasting classes

#### Ability Score Improvement (ASI)

At ASI levels (4, 8, 12, 16, 19 -- plus extra levels for Fighters and Rogues), you can distribute +2 across your ability scores:

> *"Level up Kael with ASI: +2 Strength"*
> *"Level up Kael with ASI: +1 Strength, +1 Constitution"*

The total must be exactly 2. Each individual bonus must be 1 or 2. Scores cannot exceed 20.

#### Subclass Selection

At the subclass level (typically 3, varies by class), you choose a subclass:

> *"Level up Kael and choose Champion subclass"*

The system validates your subclass choice against the available options in the loaded rulebook.

#### HP Method

By default, HP increases use the PHB average (hit die / 2 + 1 + CON modifier). You can roll instead:

> *"Level up Kael and roll for HP"*

### Long Rest & Short Rest

#### Long Rest

A long rest (8 hours of downtime) restores your character:

> *"Kael takes a long rest"*

What happens:
- **HP restored** to maximum (can be disabled if the DM wants gritty resting rules)
- **Spell slots** fully restored (all used slots reset to 0)
- **Hit dice** partially restored (half your total level, minimum 1)
- **Death saves** reset to 0 successes / 0 failures
- **Temporary HP** removed

#### Short Rest

A short rest (1 hour of light activity) lets you spend hit dice to heal:

> *"Kael takes a short rest and spends 2 hit dice"*

What happens:
- For each hit die spent, the system rolls your hit die (e.g., 1d10 for a Fighter) and adds your CON modifier
- You heal for the total (minimum 1 HP per die)
- Your remaining hit dice count decreases accordingly

If you spend 0 hit dice, it is just a brief pause with no healing.

### Spell Slot Tracking

For spellcasting classes, the system tracks spell slots automatically:

- **Maximum slots** are set when you create the character or level up (based on class and level)
- **Used slots** are tracked as you cast spells during play
- **Long rest** restores all spell slots to their maximum

You can also manage prepared/known spells:

> *"Show Lyra's spell list"*
> *"Add Fireball to Lyra's known spells"*
> *"Remove Shield from Lyra's known spells"*

### Death Saves

When a PC drops to 0 HP, they are unconscious and start making death saving throws.

On each of their turns:
- The DM rolls 1d20
- **10 or higher**: one success
- **9 or lower**: one failure
- **Natural 20**: the PC wakes up with 1 HP (death saves reset)
- **Natural 1**: counts as **2 failures**

**Three successes** = stabilized (HP set to 1, death saves reset).
**Three failures** = death.

On Hard or Deadly difficulty, enemies may attack downed PCs. A melee attack on an unconscious character is an automatic critical hit, which counts as **2 failed death saves**.

### Inventory & Equipment

Items are managed through natural language during play:

- **Looting**: after combat, the DM adds found items to your inventory
- **Shopping**: *"I buy a healing potion from the shopkeeper"* -- the DM checks your gold and handles the transaction
- **Using items**: *"I drink the healing potion"* -- the DM resolves the effect and removes the item
- **Checking inventory**: *"What do I have in my pack?"* or ask Claude to call `get_character`

Each item tracks: name, type (weapon/armor/consumable/misc), quantity, value, weight, and description.

---

## Multi-Source Rulebooks (SRD, Open5e, 5etools, Custom/PDF)

dm20-protocol supports loading content from multiple sources simultaneously. This gives you access to a much wider range of classes, races, spells, and monsters than any single source provides.

### Loading Sources

```
"Load the SRD"                    → SRD 2014 (default)
"Load the 2024 SRD"              → SRD 2024
"Load Open5e"                     → Open5e community content
"Load 5etools"                    → 5etools data
"Load custom rulebook from X"     → Your own JSON files
```

### Searching Across Sources

Once loaded, you can search across all active rulebooks:

> *"Search for fire spells"*
> *"Look up the Adult Red Dragon stat block"*
> *"What ranger spells are available?"*
> *"Show me the Elf race details"*

These use `search_rules`, `get_spell_info`, `get_monster_info`, `get_class_info`, and `get_race_info` under the hood.

### PDF Library

If you have PDF or Markdown rulebooks, you can use the library system:

1. **Open the library folder**: *"Open the library folder"* -- this creates and opens `library/pdfs/` in your file manager
2. **Drop your files** into the folder (PDF or Markdown)
3. **Scan the library**: *"Scan the library"* -- indexes table of contents from all files
4. **Search your books**: *"Search my library for ranger subclasses"* or *"Ask my books about healing spells"*
5. **Enable for campaign**: *"Enable tome-of-heroes for this campaign"* -- makes content available during play
6. **Extract content**: *"Extract the Fighter class from tome-of-heroes"* -- converts PDF content into structured JSON for the rulebook system

### Managing Rulebooks

> *"List loaded rulebooks"* -- shows all active sources with content counts
> *"Unload the Open5e rulebook"* -- removes a source from the current campaign

---

## Playing in Italian (Bilingual Support)

dm20-protocol includes a bilingual terminology system designed for Italian-speaking players. You can freely mix Italian and English D&D terms during play, and the system understands both.

### How it works

The **Term Resolver** recognizes both Italian and English variants of D&D terms:

- *"Lancio Palla di Fuoco"* is understood as casting Fireball
- *"Tiro di Furtivita"* is understood as a Stealth check
- Accent-insensitive: *"furtivita"* matches *"Furtivita"*

### Adaptive language mirroring

The **Style Tracker** observes which language you prefer for different term categories (spells, skills, combat terms) and instructs the AI DM to mirror your style. If you consistently say "Palla di Fuoco" instead of "Fireball," the DM will respond using Italian spell names.

Categories tracked independently: spells, skills, combat terms, items, conditions, and more.

### What this means in practice

- You can write your actions in English, Italian, or a mix of both
- The DM adapts to your language preferences per category
- All backend data (character sheets, game state) uses canonical English names internally
- The narrative output mirrors whatever language you are using

---

## How the AI DM Works (Dual-Agent Architecture)

dm20-protocol uses a **dual-agent system** to deliver a richer DM experience than a single AI could provide alone.

### The Narrator Agent

- **Role**: generates evocative scene descriptions, NPC dialogue, and atmospheric text
- **Model**: Claude Haiku (fast, creative)
- **Temperature**: 0.8 (higher for more creative output)
- **Strengths**: vivid prose, distinct NPC voices, immersive atmosphere, pacing

### The Arbiter Agent (Archivist)

- **Role**: manages game state, tracks character stats, looks up rules, handles combat mechanics
- **Model**: Claude Sonnet (thorough, rules-focused)
- **Temperature**: 0.3 (lower for precise, consistent output)
- **Strengths**: accurate rule application, state tracking, combat resolution, HP/inventory management

### Why two agents?

A single LLM trying to be both creative storyteller and precise rules engine makes compromises in both directions. By splitting the responsibilities:

- The Narrator can focus purely on making the story compelling without worrying about rule accuracy
- The Arbiter can focus purely on correct game mechanics without worrying about prose quality
- Each agent uses the model size and temperature best suited to its role
- The result is a DM that is both a better storyteller and a more accurate rules engine

### Configurable Settings

You can tune the DM to your preferences:

> *"Configure the DM with dramatic narrative style and theatrical dialogue"*
> *"Set difficulty to hard"*
> *"Enable roll fudging for narrative purposes"*
> *"Set improvisation level to high"*

| Setting | Options | Default |
|---------|---------|---------|
| `narrative_style` | descriptive, concise, dramatic, cinematic | descriptive |
| `dialogue_style` | natural, theatrical, formal, casual | natural |
| `difficulty` | easy, normal, hard, deadly | normal |
| `fudge_rolls` | true / false | false |
| `improvisation_level` | none, low, medium, high, full (0-4) | medium |

Call `configure_claudmaster` with no arguments to view the current configuration.

---

## Two Modes of Use

dm20-protocol can be used in **two different ways**:

### 1. Solo Play (Automatic DM)

Use the `/dm:*` commands and Claude becomes your full DM. It handles everything: narrative, NPCs, rules, combat. You are just the player. This is the primary mode and the focus of this guide.

### 2. DM Assistant (You Are the DM)

If you are the DM for a group of players, you can use the MCP tools directly (without `/dm:*` commands) as a management assistant:

| I want to... | Tell Claude... |
|--------------|---------------|
| Create a campaign | *"Create a campaign called..."* |
| Create a PC | *"Create a character: name, class, race, level"* |
| View a character | *"Show me the sheet for Kael"* |
| Apply damage | *"Kael takes 8 damage"* |
| Damage everyone | *"Everyone takes 12 fire damage"* |
| Give an item | *"Give Kael a +1 longsword"* |
| Roll dice | *"Roll 3d6+2"* |
| Look up a spell | *"What does Fireball do?"* |
| Look up a monster | *"Show me the Goblin stat block"* |
| Session notes | *"Save notes for session 5: [summary]"* |
| Long rest | *"Kael takes a long rest"* |
| Short rest | *"Kael takes a short rest, spend 2 hit dice"* |
| Level up | *"Level up Kael"* |
| Calculate XP | *"Calculate XP for 4 players at level 3, 450 encounter XP"* |

In this mode, Claude does not act as the DM -- it is just your table management tool.

---

## Tips for Better Sessions

### Context Management

Claude Code has a limited context window. During a game session it fills up with narration, tool calls, and dice rolls. When it reaches 50-60%, it is time to save and reload.

**The Save/Resume Flow:**

```
1. /dm:save                    ← saves everything to the backend
2. /clear                      ← clears Claude's context window
3. /dm:start Campaign Name     ← reloads everything, delivers recap, resumes
```

All data (campaign, characters, events, state) is persisted by the MCP server in its on-disk database. When you run `/dm:start`, everything is reloaded even in a completely new conversation.

| Situation | What to do |
|-----------|-----------|
| Context at 50-60% | `/dm:save` then `/clear` then `/dm:start` |
| Natural end of a scene | Good moment for `/dm:save` |
| Before a long combat | `/dm:save` for fresh context |
| Want to continue tomorrow | `/dm:save` and close everything |
| Claude gets slow or repetitive | Context is probably full -- save and reload |

**Alternative:** `/compact` compresses old messages for small gains. For long sessions, the save-clear-start flow is much more effective.

### Writing Good Actions

- **Be specific**: *"I search the desk drawers for hidden compartments"* works better than *"I search"*
- **State your intent**: *"I want to sneak past the guards"* helps the DM choose the right mechanic
- **Include your approach**: *"I try to pick the lock using my thieves' tools"* gives context
- **One action at a time**: do one thing, see the result, then decide what to do next

### Getting the Most from the DM

- **Ask NPCs questions**: the AI DM can roleplay any NPC with distinct personality
- **Explore the environment**: describe what you examine and the DM will improvise details
- **Let combat emerge naturally**: sometimes `/dm:action I draw my sword and charge` is more immersive than `/dm:combat`
- **Try social solutions**: not every encounter needs to end in combat
- **Take rests at appropriate times**: the DM narrates rest scenes and they can lead to character moments

---

## Troubleshooting

**"Claude does not behave like a DM"**
Did you use `/dm:start`? Without that command, the DM persona is not activated. Claude is just a regular assistant until you start a session.

**"Context filled up too quickly"**
Combat consumes a lot of context (many tool calls per round). Save before long combats and reload with fresh context afterward. Use the save-clear-start flow described above.

**"It does not remember what happened before"**
If you used `/clear` without first running `/dm:save`, conversation-level narration is lost. Backend data (HP, position, quests, inventory) always persists, but the story context does not. **Always save before clearing.**

**"Cannot find the campaign"**
Check the exact name with *"show available campaigns"* or run `/dm:start` without arguments to see the list.

**"Character creation failed"**
Make sure a rulebook is loaded first. The character builder requires class and race definitions from a rulebook. Run *"Load the SRD"* and try again.

**"Level-up failed"**
Same as above -- level-up requires a loaded rulebook for class features and spell slot progression.

**"Monsters do not have stat blocks"**
The SRD only includes a subset of monsters. Try loading Open5e or 5etools for broader coverage, or ask Claude to use standard values for a similar creature.

**"Spells or features seem wrong"**
Check which rulebook is loaded. SRD 2014 and SRD 2024 have different class features. Use *"List loaded rulebooks"* to see what is active.

**"The DM is too easy / too hard"**
Adjust the difficulty setting: *"Set difficulty to hard"* or *"Set difficulty to easy"*. This affects DC thresholds, enemy tactics, and whether enemies target downed PCs.

**"I want the DM to be more dramatic / more concise"**
Configure the narrative style: *"Set narrative style to cinematic"* or *"Set narrative style to concise"*. You can also adjust dialogue style independently.
