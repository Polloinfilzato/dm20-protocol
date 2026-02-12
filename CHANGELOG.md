# Changelog

All notable changes to DM20 Protocol will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Inventory Management** — Three new MCP tools: `equip_item` (move item from inventory to equipment slot with auto-unequip), `unequip_item` (move equipped item back to inventory), `remove_item` (delete item with partial quantity support). Item lookup supports case-insensitive name and ID matching.
- **Level-Up Engine** — New `LevelUpEngine` module handles character progression with `level_up_character` MCP tool. Supports average and roll HP methods, class feature addition from rulebook data, spell slot progression for full/half/third casters, ASI at standard levels (with Fighter/Rogue extras), subclass selection at class-specific levels, and hit dice tracking. Returns structured `LevelUpResult` with summary of all changes.
- **Character Builder** — New `CharacterBuilder` module auto-populates characters from rulebook data (class, race, background). Supports Standard Array, Point Buy, and manual ability score methods. Calculates HP, assigns saving throws, proficiencies, starting equipment, spell slots, racial traits, class features, and languages automatically. Enhanced `create_character` MCP tool with `subclass`, `subrace`, `ability_method`, and `ability_assignments` parameters.
- **Character Model v2** — Extended Character model with `experience_points`, `speed`, `conditions`, `tool_proficiencies`, `hit_dice_type`, and structured `Feature` model (name, source, description, level_gained). Proficiency bonus is now auto-calculated from class level. Full backward compatibility with v1 characters via Pydantic defaults.
- **DM Persona system** — `.claude/dm-persona.md` defines Claude's behavior as a full D&D 5e Dungeon Master with structured game loop (CONTEXT → DECIDE → EXECUTE → PERSIST → NARRATE), combat protocol, session management, output formatting rules, and authority guidelines
- **Specialist sub-agents** — Three Claude Code agent files in `.claude/agents/`:
  - `narrator.md` — Scene descriptions, atmospheric text, NPC dialogue (sonnet model)
  - `combat-handler.md` — Combat management with advanced enemy tactics (sonnet model)
  - `rules-lookup.md` — Fast rules reference and stat blocks (haiku model)
- **Game slash commands** — Four player-facing commands in `.claude/commands/dm/`:
  - `/dm:start [campaign]` — Begin or resume a game session
  - `/dm:action <description>` — Process a player action through the game loop
  - `/dm:combat [situation]` — Initiate or manage combat encounters
  - `/dm:save` — Save session state with narrative cliffhanger
- **Hybrid Python integration** — Intent classification and data retrieval wired into tool flow, leveraging existing Orchestrator/Archivist for deterministic operations
- **Player guide** — `GUIDA_DM.md` rewritten with practical gameplay instructions, context management guide, and troubleshooting

### Fixed
- `start_claudmaster_session` — Now properly integrates with `DnDStorage` to load campaigns by name instead of returning hardcoded error
- `player_action` tool — Registered as `@mcp.tool` in `main.py` (existed but was not exposed via MCP)
- Tool output enrichment — Key tools (`get_character`, `get_npc`, `get_game_state`) now return comprehensive data for AI DM consumption including inventory details, NPC relationships, and combat state

## [0.2.0] - 2026-02-08

### Changed
- **Project renamed** from `gamemaster-mcp` to `dm20-protocol`
- Python package: `gamemaster_mcp` → `dm20_protocol`
- Environment variable: `GAMEMASTER_STORAGE_DIR` → `DM20_STORAGE_DIR`
- Entry point: `gamemaster-mcp` → `dm20-protocol`
- Repository moved to `Polloinfilzato/dm20-protocol`

## [0.1.1] - 2025-02-01

### Added
- `delete_character` tool to remove characters from campaigns
- Character lookup now supports searching by player name in addition to character name and ID
- `bulk_update_characters` tool for applying changes to multiple characters at once (e.g., area damage)
- CHANGELOG.md to track project changes

### Fixed
- Character lookup returning `None` when found by ID

### Changed
- Updated README.md to document `delete_character` tool

## [0.1.0] - 2024-12-01

### Added
- Initial release of Gamemaster MCP
- **Campaign Management**
  - `create_campaign` - Create a new D&D campaign
  - `get_campaign_info` - Get current campaign information
  - `list_campaigns` - List all available campaigns
  - `load_campaign` - Switch to a different campaign
- **Character Management**
  - `create_character` - Create a new player character with full D&D 5e stats
  - `get_character` - Get character sheet details
  - `update_character` - Update character properties (name, stats, HP, etc.)
  - `add_item_to_character` - Add items to inventory
  - `list_characters` - List all characters
  - Ability scores with automatic modifier calculation
  - Hit points, armor class, and combat stats
  - Inventory and equipment management
  - Spellcasting support
- **NPC Management**
  - `create_npc` - Create a new NPC
  - `get_npc` - Get NPC details
  - `list_npcs` - List all NPCs
  - Public descriptions and private bios for DM secrets
  - Attitude tracking (friendly, neutral, hostile, unknown)
- **Location Management**
  - `create_location` - Create a new location
  - `get_location` - Get location details
  - `list_locations` - List all locations
  - Support for various location types (city, town, village, dungeon, etc.)
  - Population, government, and notable features tracking
- **Quest Management**
  - `create_quest` - Create a new quest
  - `update_quest` - Update quest status or objectives
  - `list_quests` - List quests with optional status filter
  - Quest status tracking (active, completed, failed, on_hold)
  - Individual objective completion
- **Combat Management**
  - `start_combat` - Initialize combat with initiative order
  - `end_combat` - End combat encounter
  - `next_turn` - Advance to next participant's turn
  - Automatic initiative sorting
- **Game State Tracking**
  - `update_game_state` - Update current game state
  - `get_game_state` - Get current game state
  - Current location and session tracking
  - Party level and funds
  - In-game date tracking
  - Combat status
- **Session Management**
  - `add_session_note` - Add session notes and summary
  - `get_sessions` - Get all session notes
  - Experience and treasure tracking
  - Character attendance
- **Adventure Log**
  - `add_event` - Add event to adventure log
  - `get_events` - Get events with filtering and search
  - Event types: combat, roleplay, exploration, quest, character, world, session
  - Importance ratings (1-5)
  - Searchable and filterable
- **Utility Tools**
  - `roll_dice` - Roll dice with D&D notation (e.g., "1d20", "3d6+2")
  - `calculate_experience` - Calculate XP distribution for encounters
  - Advantage/disadvantage support for d20 rolls

[Unreleased]: https://github.com/Polloinfilzato/dm20-protocol/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Polloinfilzato/dm20-protocol/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/Polloinfilzato/dm20-protocol/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Polloinfilzato/dm20-protocol/releases/tag/v0.1.0
