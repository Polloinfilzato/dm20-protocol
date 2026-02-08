# DM20 Protocol

A comprehensive [Model Context Protocol](https://modelcontextprotocol.io/) server for managing AI-assisted Dungeons & Dragons campaigns, built with **FastMCP 2.9+**.

- **For Groups** — A toolkit to help run campaigns more effectively
- **For Solo Players** — A complete virtual D&D experience with AI as the DM
- **For Worldbuilders** — Tools to create rich, interconnected game worlds

> **Status:** Under active development. See [Roadmap](#roadmap) for what's next.

## Features

- **Campaign Management** — Create and switch between multiple campaigns
- **Character Sheets** — Full D&D 5e stats, inventory, spellcasting, progression
- **NPCs & Locations** — Rich world-building with relationships and connections
- **Quest Tracking** — Objectives, status, rewards, and branching paths
- **Combat System** — Initiative, turns, conditions, damage/healing
- **Session Notes** — Per-session summaries, XP, loot, attendance
- **Adventure Log** — Searchable timeline of all campaign events
- **Dice & Utilities** — Rolls, XP calculations, rules lookup
- **PDF Rulebook Library** — Import and query your own PDFs and homebrew content
- **50+ MCP Tools** — Full list in the [User Guide](docs/GUIDE.md)

## Prerequisites

| Requirement | Version | Check | Install |
|------------|---------|-------|---------|
| Python | 3.12+ | `python3 --version` | [python.org](https://python.org) |
| uv | latest | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| git | any | `git --version` | `xcode-select --install` (macOS) |

## Installation

This server implements the open [Model Context Protocol](https://modelcontextprotocol.io/) standard. It works with **any MCP-compatible client** — not just Claude. If your AI tool supports MCP, it can run this server.

**Tested with:** Claude Desktop, Claude Code, Cursor, VS Code (Copilot), Windsurf, Cline, OpenAI Codex, Gemini CLI.

### Quick Install

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Polloinfilzato/dm20-protocol/main/install.sh)
```

The interactive installer handles cloning, dependencies, MCP client configuration, and data directory setup. It detects your CPU architecture and warns about platform-specific limitations.

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
      "args": ["run", "dm20-protocol"],
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
      "args": ["run", "dm20-protocol"],
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
      "args": ["run", "dm20-protocol"],
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
        "args": ["run", "dm20-protocol"],
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

- **Command:** `uv run dm20-protocol`
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
Create a character named Elara, a High Elf Wizard with 16 INT
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

The AI will use DM20's tools automatically — no special syntax needed. Just describe what you want in plain English.

For the full list of 50+ tools and advanced usage, see the [User Guide](docs/GUIDE.md). For a complete example campaign, see [example/dnd/](example/dnd/example.md).

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
uv run dm20-protocol
```

## Roadmap

The next major feature is **Claudmaster** — an autonomous AI Dungeon Master powered by a multi-agent architecture:

- **Narrator Agent** — Scene descriptions, NPC dialogue, atmosphere
- **Archivist Agent** — Game state, rules lookup, combat management
- **Module Keeper Agent** — RAG-based adventure module content
- **Consistency Engine** — Fact tracking, contradiction detection

Play published adventures (Curse of Strahd, Lost Mines of Phandelver, etc.) with AI following the module plot while adapting to player choices. Supports solo play, group play, and DM assistant modes.

Based on [academic research](https://arxiv.org/html/2502.19519v2) showing multi-agent GM outperforms single-agent approaches.

**Status:** In development.

## Documentation

- [User Guide](docs/GUIDE.md) — System prompt, tools reference, data structure, PDF library
- [Storage Structure](docs/STORAGE_STRUCTURE.md) — How campaign data is organized on disk
- [Development Guide](docs/DEVELOPMENT.md) — Architecture, contributing, API details
- [Changelog](CHANGELOG.md) — Version history

## Credits

This project started as a fork of [gamemaster-mcp](https://github.com/study-flamingo/gamemaster-mcp) by **Joel Casimir**, who created the initial foundation for D&D campaign management via MCP.

| Component | Origin | Lines |
|-----------|--------|-------|
| Original code (v0.1.0 foundation) | Joel Casimir | ~3.9% |
| New code (library system, claudmaster, tools, tests) | DM20 Protocol contributors | ~96.1% |

The project has since been extensively rewritten and expanded with 50+ new tools, a PDF rulebook library system, the Claudmaster multi-agent architecture, and comprehensive test coverage.

## License

MIT License
