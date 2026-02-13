# DM20 Protocol

A comprehensive [Model Context Protocol](https://modelcontextprotocol.io/) server for managing AI-assisted Dungeons & Dragons campaigns, built with **FastMCP 2.9+**.

- **For Groups** — A toolkit to help run campaigns more effectively
- **For Solo Players** — A complete virtual D&D experience with AI as the DM
- **For Worldbuilders** — Tools to create rich, interconnected game worlds

> **Status:** Under active development. See [Roadmap](#roadmap) for what's next.

## Features

- **Campaign Management** — Create and switch between multiple campaigns
- **Character Builder** — Auto-populated characters from loaded rulebooks (Standard Array, Point Buy, Manual)
- **Level-Up & Progression** — Automatic HP, class features, spell slots, ASI/feats on level-up
- **Character Sheets** — Full D&D 5e stats, inventory, spellcasting, death saves
- **Rest & Recovery** — Long rest, short rest with hit dice, spell slot management, death saves
- **NPCs & Locations** — Rich world-building with relationships and connections
- **Quest Tracking** — Objectives, status, rewards, and branching paths
- **Combat System** — Initiative, turns, conditions, damage/healing
- **Multi-Source Rulebooks** — Load rules from SRD, Open5e, 5etools, or custom JSON
- **PDF Rulebook Library** — Import and query your own PDFs and homebrew content
- **Bilingual Play** — Italian/English D&D terminology resolution (500+ terms)
- **Session Notes** — Per-session summaries, XP, loot, attendance
- **Adventure Log** — Searchable timeline of all campaign events
- **Dice & Utilities** — Rolls, XP calculations, rules lookup
- **66 MCP Tools** — Full list in the [User Guide](docs/GUIDE.md)

## Installation

This server implements the open [Model Context Protocol](https://modelcontextprotocol.io/) standard. It works with **any MCP-compatible client** — not just Claude. If your AI tool supports MCP, it can run this server.

**Tested with:** Claude Desktop, Claude Code, Cursor, VS Code (Copilot), Windsurf, Cline, OpenAI Codex, Gemini CLI.

### Quick Install (Recommended)

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Polloinfilzato/dm20-protocol/main/install.sh)
```

The interactive installer is designed to get you running **with zero prior setup**. It handles everything from prerequisites to MCP client configuration in a single command.

**What the installer does for you:**

| Step | What happens |
|------|--------------|
| **Platform detection** | Identifies your OS (macOS, Linux, WSL) and CPU architecture |
| **Dependency resolution** | Detects missing tools and offers to install them automatically |
| **Homebrew** (macOS) | If not installed, explains what it is and offers one-click setup |
| **uv** | Auto-installs via Homebrew (macOS) or official installer (Linux) |
| **Python 3.12** | Auto-installs via `uv python install` — no system Python needed |
| **git** | Auto-installs via Homebrew (macOS) or system package manager (Linux) |
| **Repository clone** | Clones the repo or updates an existing copy |
| **iCloud Drive protection** | Detects iCloud-synced directories and shields `.venv` from sync corruption |
| **Virtual environment** | Creates `.venv` and installs all Python dependencies |
| **MCP client config** | Writes the JSON config for Claude Desktop, Claude Code, or both |
| **Data directory** | Sets up campaign storage in your preferred location |
| **Verification** | Smoke-tests the server to confirm everything works |

**Supported platforms:**

| Platform | Status | Notes |
|----------|--------|-------|
| **macOS** (Apple Silicon) | Full support | Homebrew integration for all dependencies |
| **macOS** (Intel) | Full support | RAG/semantic search unavailable (onnxruntime limitation) |
| **Linux** (x86_64 / arm64) | Full support | Auto-detects apt, dnf, pacman, zypper, apk |
| **Windows** (via WSL) | Full support | WSL is detected as Linux — everything works |
| **Windows** (native) | Not supported | Use WSL instead |

> **You don't need to install anything beforehand.** The only requirement is `curl` and `bash`, which you already have if you're running the command above. The installer takes care of the rest, asking permission before each step.

### Manual Install

Clone and install dependencies (same for all clients):

```bash
git clone https://github.com/Polloinfilzato/dm20-protocol.git
cd dm20-protocol
uv sync
```

Then configure your client:

<details>
<summary><strong>Claude Desktop</strong></summary>

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "dm20-protocol": {
      "command": "/absolute/path/to/uv",
      "args": ["run", "python", "-m", "dm20_protocol"],
      "cwd": "/absolute/path/to/dm20-protocol",
      "env": {
        "DM20_STORAGE_DIR": "/absolute/path/to/your/data"
      }
    }
  }
}
```

> **Important:** Claude Desktop does not inherit your shell PATH. Use the absolute path to `uv` (find it with `which uv`).

</details>

<details>
<summary><strong>Claude Code</strong></summary>

Add to `~/.claude/mcp.json` (global) or `.mcp.json` (project-level):

```json
{
  "mcpServers": {
    "dm20-protocol": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "python", "-m", "dm20_protocol"],
      "cwd": "/path/to/dm20-protocol",
      "env": {
        "DM20_STORAGE_DIR": "/path/to/your/data"
      }
    }
  }
}
```

</details>

<details>
<summary><strong>Cursor / Windsurf / Cline</strong></summary>

These editors have built-in MCP support. Add the server through their MCP settings UI, or edit the config file directly:

- **Cursor:** `~/.cursor/mcp.json`
- **Windsurf:** `~/.codeium/windsurf/mcp_config.json`
- **Cline:** VS Code settings → Cline → MCP Servers

```json
{
  "mcpServers": {
    "dm20-protocol": {
      "command": "uv",
      "args": ["run", "python", "-m", "dm20_protocol"],
      "cwd": "/path/to/dm20-protocol",
      "env": {
        "DM20_STORAGE_DIR": "/path/to/your/data"
      }
    }
  }
}
```

</details>

<details>
<summary><strong>VS Code + GitHub Copilot</strong></summary>

Add to your VS Code `settings.json` or `.vscode/mcp.json`:

```json
{
  "mcp": {
    "servers": {
      "dm20-protocol": {
        "command": "uv",
        "args": ["run", "python", "-m", "dm20_protocol"],
        "cwd": "/path/to/dm20-protocol",
        "env": {
          "DM20_STORAGE_DIR": "/path/to/your/data"
        }
      }
    }
  }
}
```

Requires Copilot Chat in **Agent Mode** (VS Code 1.99+).

</details>

<details>
<summary><strong>Other MCP Clients (Codex, Gemini CLI, etc.)</strong></summary>

Any MCP-compatible client can use this server. The key configuration:

- **Command:** `uv run python -m dm20_protocol`
- **Working directory:** The cloned repository root
- **Environment:** `DM20_STORAGE_DIR` — path where campaign data is stored
  - **Default:** `./data` relative to the repository root (created automatically on first run)
  - **Recommended:** use an absolute path like `~/dm20-data` to keep campaign data separate from the repo, making backups and updates easier

Refer to your client's documentation for where to add MCP server entries. The transport is **stdio** (the default for most clients).

</details>

## Quick Start

Once your MCP client is configured, try these natural language commands to get started:

```
Create a new campaign called "The Lost Kingdom"
```

```
Load the D&D 5e rules: load_rulebook source=srd
```

```
Create a level 3 High Elf Wizard named Lyra with Standard Array
```

```
Create a location called "Silverdale", a peaceful village surrounded by ancient forests
```

```
Create an NPC named Marta, an elderly herbalist who lives in Silverdale
```

```
Create a quest called "The Missing Amulet" given by Marta
```

The AI will use DM20's tools automatically — no special syntax needed. Just describe what you want in plain English. With a rulebook loaded, the Character Builder auto-populates HP, proficiencies, features, equipment, and spell slots from official rules.

For the full list of 66 tools and advanced usage, see the [User Guide](docs/GUIDE.md). For a complete example campaign, see [example/dnd/](example/dnd/example.md).

## Optional: RAG Dependencies

For semantic search capabilities (vector-based library queries via `ask_books`):

```bash
uv sync --extra rag
```

> **Note:** RAG dependencies (`chromadb`, `onnxruntime`) are not available on **macOS Intel (x86_64)**. The server works fine without them — only the `ask_books` tool requires RAG. All other library tools use keyword search.

## Development

```bash
git clone https://github.com/Polloinfilzato/dm20-protocol.git
cd dm20-protocol
uv sync --group dev
```

Run tests:

```bash
uv run pytest tests/
```

Run the server locally:

```bash
uv run python -m dm20_protocol
```

## Solo Play — AI Dungeon Master

DM20 Protocol includes a complete **AI Dungeon Master** system for solo D&D play. Claude becomes your DM — narrating the world, roleplaying NPCs, running combat, and tracking all game state automatically.

### Game Commands

| Command | What it does |
|---------|-------------|
| `/dm:start [campaign]` | Begin or resume a game session |
| `/dm:action I search the room` | Process any player action |
| `/dm:combat goblins ambush us!` | Start or manage combat |
| `/dm:save` | Save session and pause |

### How It Works

The system uses a **dual-agent architecture** where two specialized LLM agents run in parallel on every player action:

- **Narrator** (Haiku — fast, creative) — Rich scene descriptions, NPC dialogue, atmospheric text
- **Arbiter** (Sonnet — thorough, rules-focused) — Mechanical resolution, dice rolls, rule adjudication

A **DM Persona** (`.claude/dm-persona.md`) orchestrates the game loop: gather context, decide what happens, execute via tools, update state, narrate the outcome. A Python-side **Archivist** agent handles data retrieval and game state tracking without consuming LLM tokens.

Based on [academic research](https://arxiv.org/html/2502.19519v2) showing multi-agent GM outperforms single-agent approaches. Built on the Claudmaster architecture with session persistence, difficulty scaling, and configurable narrative style.

See the **[Player Guide](PLAYER_GUIDE.md)** for how to play, or the **[Roadmap](ROADMAP.md)** for what's next.

## Documentation

- [Player Guide](PLAYER_GUIDE.md) — How to play solo D&D with the AI DM
- [User Guide](docs/GUIDE.md) — System prompt, tools reference, data structure, PDF library
- [Storage Structure](docs/STORAGE_STRUCTURE.md) — How campaign data is organized on disk
- [Development Guide](docs/DEVELOPMENT.md) — Architecture, contributing, API details
- [Roadmap](ROADMAP.md) — What's implemented, what's next
- [Changelog](CHANGELOG.md) — Version history

## Credits

This project started as a fork of [gamemaster-mcp](https://github.com/study-flamingo/gamemaster-mcp) by **Joel Casimir**, who created the initial foundation for D&D campaign management via MCP.

| Component | Origin | Lines |
|-----------|--------|-------|
| Original code (v0.1.0 foundation) | Joel Casimir | ~3.9% |
| New code (library system, claudmaster, tools, tests) | DM20 Protocol contributors | ~96.1% |

The project has since been extensively rewritten and expanded with 66 MCP tools, a multi-source rulebook system, a PDF library, the Claudmaster dual-agent AI DM, and comprehensive test coverage.

## License

MIT License
