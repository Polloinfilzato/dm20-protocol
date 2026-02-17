# Changelog

All notable changes to DM20 Protocol will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- D&D Beyond character import via URL or local JSON file
- New MCP tools: `import_from_dndbeyond`, `import_character_file`
- DDB-to-dm20 character mapping for identity, stats, inventory, spells, features
- Graceful degradation with warnings for partial imports
- **Output Filtering and Multi-User Session Coordination** — New `output_filter.py` module with `OutputFilter` class that wraps MCP tool responses and strips DM-only content based on the caller's role. `SessionCoordinator` manages session participants (join/leave/heartbeat), turn-based notifications ("It's [character]'s turn"), and DM-to-player private messaging. NPC responses automatically filter bio, notes, stats, and relationships for PLAYER/OBSERVER callers. Location responses combine discovery filter + permission filter (non-DM callers see only discovered features and no DM notes). `get_npc` and `get_location` MCP tools gain optional `player_id` parameter. New `send_private_message` MCP tool for DM-to-player private messages. `PCRegistry` extended with `join_session()`, `leave_session()`, and `heartbeat()` methods for participant tracking. Same tool call returns different content for DM vs PLAYER vs OBSERVER. 53 integration tests
- **Role-Based Permission System** — New `permissions.py` module with `PlayerRole` enum (DM, PLAYER, OBSERVER), `PermissionLevel` enum (ALLOWED, DENIED, CONDITIONAL), and `PermissionResolver` class for validating MCP tool calls against caller role and entity ownership. Permission matrix categorizes all MCP tools into read (all roles), character-modification (conditional on ownership for PLAYER), and DM-only sets. Entirely opt-in: when no `player_id` is provided, all calls operate in single-player DM mode with zero overhead. DM can grant/revoke temporary permissions with optional duration. `PCState` model extended with `role: PlayerRole` field. Sensitive character-modification tools (`update_character`, `add_item_to_character`, `equip_item`, `unequip_item`, `remove_item`, `use_spell_slot`, `add_spell`, `remove_spell`, `long_rest`, `short_rest`, `add_death_save`, `level_up_character`, `export_character_sheet`) now accept optional `player_id` parameter for permission enforcement. 83 unit tests covering every (role, tool) combination
- **Narrator Discovery Integration** — `DiscoveryContext` and `FeatureView` models structure what the party has discovered about a location's features. `build_discovery_context()` queries `DiscoveryTracker` to build narrator-ready context with appropriate description tiers (hidden/vague/full/complete) per feature. `format_discovery_prompt_section()` formats context into LLM prompt text with tier-specific instructions. Auto-glimpse on first visit sets location to GLIMPSED and reveals "obvious" features (first half of notable_features list). Undiscovered features produce deterministic sensory hints ("You notice a cold draft from the north wall...") instead of explicit descriptions. Perception/investigation check results call `discover_feature()` to upgrade discovery levels. `get_location` MCP tool gains `discovery_filter` parameter to filter notable features by discovery state. `filter_location_by_discovery()` helper for the MCP tool. Backward-compatible: untracked locations default to EXPLORED with all features visible. 42 integration tests
- **Party Knowledge System** — `PartyKnowledge` class provides a filtered view over `FactDatabase` for tracking what the adventuring party collectively knows. Facts are tagged with `party_known` in the FactDatabase (no data duplication). `KnowledgeRecord` tracks acquisition metadata (source, method, session, location). 8 acquisition methods: `told_by_npc`, `observed`, `investigated`, `read`, `overheard`, `deduced`, `magical`, `common_knowledge`. Querying by topic (content/tag/category match), source, or method. Bidirectional NPC integration: `NPCKnowledgeTracker.share_with_party()` flows NPC knowledge to party, `PartyKnowledge.share_with_npc()` flows party knowledge to NPCs. New `party_knowledge` MCP tool for querying party knowledge with optional topic, source, and method filters. JSON persistence to `party_knowledge.json`. 46 unit tests covering knowledge acquisition, querying, persistence, NPC bidirectional flow, and FactDatabase tag integration
- **Compendium Pack Import** — `PackImporter` class imports CompendiumPack JSON files into the current campaign with conflict resolution (skip, overwrite, rename). Features: preview/dry-run mode, selective import by entity type, ID regeneration (new UUIDs for all imported entities), and relationship re-linking (NPC locations, Location NPC lists, Quest givers, Encounter locations, Location connections updated after renames). `PackValidator` class validates pack schema (Pydantic model_validate), version compatibility (major version check), entity count consistency, and required field presence. 3 new MCP tools: `import_pack` (with conflict_mode, preview, entity_filter), `list_packs` (browse packs directory), `validate_pack` (check integrity without importing). 37 unit tests covering clean import, all 3 conflict modes, preview mode, selective import, relinking after rename, round-trip export/import, and edge cases
- **Compendium Pack Export** — New `compendium.py` module with `CompendiumPack` Pydantic model, `PackMetadata` for provenance tracking, and `PackSerializer` for extracting campaign entities into portable JSON pack files. Supports selective export by entity type (NPCs, locations, quests, encounters), location-based filtering, tag-based filtering, and full campaign backup (all entities + game state + sessions). Inter-entity relationships preserved. New `export_pack` MCP tool and `packs_dir` storage property. 33 unit tests
- **Combat Mechanics Automation** — Complete combat subsystem in `combat/` package (521 new tests):
  - **Active Effects System** — `EffectsEngine` manages buffs, debuffs, and conditions with stat modifiers, advantage/disadvantage grants, immunities, and duration tracking (rounds, minutes, concentration, permanent). All 14 SRD conditions (blinded, charmed, etc.) with pre-built effect definitions. Stacking rules and auto-expiry on turn/round boundaries
  - **Concentration Tracking** — `ConcentrationState` model tracks which spell a caster is concentrating on. Automatic CON save triggers on damage, with DC = max(10, damage/2). Breaking concentration removes all linked `ActiveEffect` instances. Prevents casting a second concentration spell without breaking the first
  - **Combat Action Pipeline** — `resolve_attack()` handles melee/ranged/spell attacks with advantage/disadvantage, AC comparison, damage rolls, and critical hits. `resolve_save_spell()` handles save-or-suck spells with DC, half damage on save, and effect application. Structured `CombatResult` output for consistent narration
  - **Encounter Builder** — XP budget calculator using DMG guidelines per party size and level. Monster selection from rulebook data with CR-appropriate filtering. Difficulty multipliers for encounter groups. Composition strategies (solo boss, elite + minions, swarm, mixed)
  - **Positioning & AoE Engine** — `Position` model for grid-based combat (5ft per square). Area-of-effect shape resolution for sphere, cube, cone, line, and cylinder. Target filtering within AoE areas. Relative positioning fallback when no grid is active
  - **ASCII Tactical Map** — `TacticalGrid` and `AsciiMapRenderer` generate text-based battle maps with character/monster positions, terrain markers, and AoE overlays. Movement validation with opportunity attack detection. Works in any terminal or chat interface
  - **5 New Combat MCP Tools** — `combat_action` (resolve attacks/spells), `build_encounter` (generate balanced encounters), `show_map` (render tactical map), `apply_effect` (add buff/debuff/condition), `remove_effect` (clear effects by name or ID)
- **Bidirectional Character Sheet Sync** — New `sheets/` package generates beautiful Markdown character sheets with YAML frontmatter from Character JSON data. Players can edit sheets in any Markdown editor (Obsidian-friendly); changes are parsed, diffed, and classified by editability tier (`player_free` auto-applied, `player_approval` queued for DM, `dm_only` silently rejected). File watcher (`watchdog`) monitors `campaigns/{name}/sheets/` with 500ms debounce and feedback loop prevention. 4 new MCP tools: `export_character_sheet`, `sync_all_sheets`, `check_sheet_changes`, `approve_sheet_change`. Storage callback system enables reactive sheet regeneration on character save/delete/rename

### Changed
- **RAG: replaced sentence-transformers with ONNX embeddings** — The `[rag]` extra no longer depends on `sentence-transformers` (and transitively `torch`). Embeddings now use ChromaDB's built-in `DefaultEmbeddingFunction` (ONNX-based, same `all-MiniLM-L6-v2` model). This fixes installation failures on Python 3.13+/3.14 and macOS Intel (x86_64) where torch has no compatible wheels, and reduces the RAG install size from ~2GB to ~200MB
- **Installer: Python fallback chain** — Both user and developer install modes now auto-retry with Python 3.12 (via `uv --python 3.12`) when dependency resolution fails with the default Python. If RAG dependencies specifically fail, the installer gracefully falls back to base install (TF-IDF search) instead of aborting. Upgrade mode also includes the Python 3.12 fallback

### Fixed
- **Installer: missing slash commands in User mode** — `do_create_play_dir()` now creates `.claude/commands/dm/` with all 6 `/dm:*` command files and `.claude/dm-persona.md`. Previously these were only available in Developer mode (inside the git clone), causing `/dm:start`, `/dm:action`, etc. to be missing after User installation
- **Installer: agent templates fallback** — Agent templates are now downloaded from GitHub when the Python package walk-up approach fails (which is always in `uv tool install` mode). Previously fell through to minimal 3-line templates missing all instructions

### Added
- **Installer `--upgrade` flag** — `bash install.sh --upgrade` upgrades both the Python package (`uv tool upgrade`) and the `.claude/` config files (slash commands, DM persona, agent templates) in one command. Auto-detects the play directory (current dir, `~/dm20`, or `DM20_STORAGE_DIR`); prompts if multiple found; shows clear instructions if none found. Creates timestamped backups before overwriting. Works from local clone or remote (`bash <(curl ...) --upgrade`)
- **Model Quality Profiles with Effort Levels** — Switchable `quality` (Opus, effort high), `balanced` (Opus, effort medium — default), and `economy` (Opus, effort low for Python API + Haiku for CC agents) presets that update all model settings and CC agent files at once via `configure_claudmaster(model_profile=...)` or the `/dm:profile` slash command. Opus effort parameter (`output_config`) controls output verbosity: medium effort matches Sonnet quality with ~76% fewer output tokens (Anthropic SWE-bench data). Individual field changes auto-set profile to "custom". Installer now includes profile selection during setup with `DM20_AGENTS_DIR` env var for agent file resolution
- **Dual-Mode Installer** — `install.sh` now offers two modes: **User** (zero-friction `uv tool install` with minimal footprint — no git clone, no virtualenv) and **Developer** (full repository clone for contributors). Auto-detects mode when run from inside an existing clone. User mode creates a lightweight play directory (`~/dm20`) with config and data, Developer mode always installs into a `dm20-protocol/` subdirectory of the chosen parent. Installer version bumped to 0.3.0
- **MCP Client Setup Guide** — New `docs/MCP_CLIENTS.md` with per-client configuration instructions for 13 MCP clients (Claude Code/Desktop, Cursor, Windsurf, Cline, VS Code Copilot, Continue, OpenAI Codex, Gemini CLI, Amazon Q, JetBrains, Zed, Visual Studio). Includes compatibility matrix with honest testing labels and a call for community test reports
- **Installer Guide** — New `docs/INSTALLER.md` documenting the dual-mode architecture, per-OS installation behavior (macOS, Linux, WSL, Windows), prerequisite resolution, MCP config generation, and every edge case the installer handles
- **Rulebook System** — `RulebookManager` with multi-source support and unified query interface. `SRDSource` adapter fetches D&D 5e SRD data (2014 and 2024 versions) via the 5e-srd-api with file-based caching. `CustomSource` adapter loads local JSON/YAML homebrew rulebooks. 9 MCP tools: `load_rulebook`, `list_rulebooks`, `unload_rulebook`, `search_rules`, `get_class_info`, `get_race_info`, `get_spell_info`, `get_monster_info`, `validate_character_rules`
- **PDF Rulebook Library** — Import third-party PDFs and Markdown rulebooks into a shared library. Automatic TOC extraction via PyMuPDF, on-demand content extraction to `CustomSource` JSON format, campaign-scoped enable/disable via library bindings, and TF-IDF semantic search with D&D synonym expansion. 10 MCP tools: `open_library_folder`, `scan_library`, `list_library`, `get_library_toc`, `search_library`, `extract_content`, `enable_library_source`, `disable_library_source`, `list_enabled_library`, `ask_books`
- **Multi-Source Rulebook** — Two additional rulebook adapters: `Open5eSource` (REST API with auto-pagination and local caching) and `FiveToolsSource` (GitHub JSON data with custom markup conversion). Extended `load_rulebook` tool to accept `"open5e"` and `"5etools"` source types
- **Bilingual Terminology Resolver** — Italian-to-English D&D term resolution for bilingual play sessions. ~500 curated term pairs in `core_terms.yaml` covering spells, skills, conditions, classes, races, and items. `TermResolver` with O(1) dict lookup, accent-insensitive matching via `unicodedata` normalization, and automatic rulebook indexing. `StyleTracker` observes per-category language preferences and injects style hints into narrator prompts
- **Claudmaster AI DM Engine** — Multi-agent architecture for autonomous D&D game mastering. Orchestrator coordinates Narrator (scene descriptions, NPC dialogue), Archivist (game state, rules, combat), and Module Keeper (RAG on PDF adventure modules via ChromaDB vector store) agents. Includes consistency engine (fact tracking, NPC knowledge state, contradiction detection, timeline consistency), 5-level improvisation control system, companion NPC system with AI combat tactics, multi-player support with split party handling, session continuity with auto-save and recap generation, and performance optimization (caching, parallel execution, context optimizer). 5 MCP tools: `configure_claudmaster`, `start_claudmaster_session`, `end_claudmaster_session`, `get_claudmaster_session_state`, `player_action`
- **Dual-Agent Response Architecture** — Parallel Narrator (fast) + Arbiter (reasoned) agents for responsive gameplay. `LLMClient` protocol for model-agnostic agent calls. Graceful degradation to single-agent mode on failure
- **Session Transcription Summarizer** — `summarize_session` MCP tool generates structured `SessionNote` from raw session transcriptions or file paths. Leverages campaign context (characters, NPCs, locations, quests) to enrich summaries. Automatic chunking with overlap for large transcriptions (>200k characters)
- **Extended update_character** — Now supports `experience_points`, `speed` scalar fields and list add/remove operations for `conditions`, `skill_proficiencies`, `tool_proficiencies`, `saving_throw_proficiencies`, `languages`, and `features_and_traits`. List params accept JSON arrays or comma-separated strings. Ability score updates now correctly modify the abilities dict.
- **Spell Management Tools** — `use_spell_slot` (decrement available slots with validation), `add_spell` (add to spells_known with duplicate detection), `remove_spell` (remove by name or ID).
- **Rest Mechanics** — `long_rest` (reset spell slots, restore half hit dice, clear death saves, optionally restore HP to max), `short_rest` (spend hit dice for healing with CON modifier, minimum 1 HP per die).
- **Death Save Tracking** — `add_death_save` tool tracks successes/failures. Auto-stabilizes at 3 successes (HP → 1, removes unconscious condition) or reports death at 3 failures.
- **Inventory Management** — Three new MCP tools: `equip_item` (move item from inventory to equipment slot with auto-unequip), `unequip_item` (move equipped item back to inventory), `remove_item` (delete item with partial quantity support). Item lookup supports case-insensitive name and ID matching.
- **Level-Up Engine** — New `LevelUpEngine` module handles character progression with `level_up_character` MCP tool. Supports average and roll HP methods, class feature addition from rulebook data, spell slot progression for full/half/third casters, ASI at standard levels (with Fighter/Rogue extras), subclass selection at class-specific levels, and hit dice tracking. Returns structured `LevelUpResult` with summary of all changes.
- **Character Builder** — New `CharacterBuilder` module auto-populates characters from rulebook data (class, race, background). Supports Standard Array, Point Buy, and manual ability score methods. Calculates HP, assigns saving throws, proficiencies, starting equipment, spell slots, racial traits, class features, and languages automatically. Enhanced `create_character` MCP tool with `subclass`, `subrace`, `ability_method`, and `ability_assignments` parameters.
- **Character Model v2** — Extended Character model with `experience_points`, `speed`, `conditions`, `tool_proficiencies`, `hit_dice_type`, and structured `Feature` model (name, source, description, level_gained). Proficiency bonus is now auto-calculated from class level. Full backward compatibility with v1 characters via Pydantic defaults.
- **Character v2 E2E Tests** — Comprehensive end-to-end test suite (`test_character_v2_e2e.py`, 23 tests) covering Fighter/Ranger/Wizard lifecycle, inventory cycle, rest mechanics, death saves, backward compatibility with v1 characters, ability score methods (Standard Array, Point Buy, Manual), and performance benchmarks.
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
- **Dice roll context labels** — `roll_dice` tool now accepts an optional `label` parameter for contextual roll descriptions (e.g., "Goblin Archer 2 attack vs Aldric")
- **`/dm:help` command** — Help overview listing all available `/dm` commands with descriptions and usage examples

### Changed
- **Storage system** — Refactored storage backend to split-storage architecture with per-campaign directory structure and separate files for characters, NPCs, locations, quests, and game state

### Fixed
- **DnDStorage.save()** — Added public `save()` method (was missing despite being called by inventory/level-up tools)
- `start_claudmaster_session` — Now properly integrates with `DnDStorage` to load campaigns by name instead of returning hardcoded error
- `player_action` tool — Registered as `@mcp.tool` in `main.py` (existed but was not exposed via MCP)
- Tool output enrichment — Key tools (`get_character`, `get_npc`, `get_game_state`) now return comprehensive data for AI DM consumption including inventory details, NPC relationships, and combat state
- `/dm:action` and `/dm:combat` slash commands — Fixed broken mid-session command invocation

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
