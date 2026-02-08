# Example Campaign: Shadows of Shadowfen

A ready-to-explore example campaign that demonstrates how DM20 Protocol organizes D&D data.

## What's Inside

[`shadowfen-campaign.json`](shadowfen-campaign.json) contains a complete campaign after Session 1:

| Entity | Count | Details |
|--------|-------|---------|
| Player Characters | 2 | Elara Moonwhisper (High Elf Wizard 3), Thrain Stoneheart (Hill Dwarf Cleric 3) |
| NPCs | 3 | Quest giver, merchant, villain — each linked to a location |
| Locations | 2 | Starting village + dungeon, connected to each other |
| Quests | 1 | 5 objectives, 2 completed — shows partial progress tracking |
| Sessions | 1 | Full session note with events, combat, loot, XP |
| Game State | — | Current location, party level, active quests, funds |

## Data Structure Features Demonstrated

- **Cross-references between entities** — NPCs live in locations, quests reference NPC givers, session notes track which NPCs were encountered
- **Character sheets with equipment slots** — separate `inventory` (carried items) and `equipment` (worn/wielded gear with stat properties)
- **Spell slots with usage tracking** — `spell_slots` vs `spell_slots_used` shows mid-session resource management
- **Quest objective progress** — `objectives` and `completed_objectives` as separate lists for partial completion
- **NPC relationships** — bidirectional relationship maps connecting NPCs to each other and to PCs
- **Game state snapshot** — captures exactly where the campaign stands between sessions

## Story Hook

The cursed marshes of Shadowfen conceal a half-sunken temple where a former priestess, Lysara the Pale, raises undead from the swamp. Two villagers have vanished. The party has tracked the source to the Temple of Forgotten Names but hasn't entered yet. Session 2 begins at dawn.

## Loading This Example

To use this campaign in a running DM20 instance, ask your AI assistant:

```
Load the campaign from example/dnd/shadowfen-campaign.json
```

Or copy the file into your data directory:

```bash
cp example/dnd/shadowfen-campaign.json <your-data-dir>/campaigns/shadows-of-shadowfen.json
```

Then ask your AI to load it:

```
List campaigns and load "Shadows of Shadowfen"
```

Once loaded, try commands like:

```
Show me Elara's character sheet
What quests are active?
Describe Fenwatch Village
What happened in Session 1?
```
