# Gamemaster MCP

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
bash <(curl -fsSL https://raw.githubusercontent.com/Polloinfilzato/gamemaster-mcp/main/install.sh)
```

The interactive installer handles cloning, dependencies, MCP client configuration, and data directory setup. It detects your CPU architecture and warns about platform-specific limitations.

### Manual Install

Clone and install dependencies (same for all clients):

```bash
git clone https://github.com/Polloinfilzato/gamemaster-mcp.git
cd gamemaster-mcp
uv sync
```

Then configure your client:

<details>
<summary><strong>Claude Desktop</strong></summary>

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "gamemaster-mcp": {
      "command": "/absolute/path/to/uv",
      "args": ["run", "gamemaster-mcp"],
      "cwd": "/absolute/path/to/gamemaster-mcp",
      "env": {
        "GAMEMASTER_STORAGE_DIR": "/absolute/path/to/your/data"
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
    "gamemaster-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "gamemaster-mcp"],
      "cwd": "/path/to/gamemaster-mcp",
      "env": {
        "GAMEMASTER_STORAGE_DIR": "/path/to/your/data"
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
    "gamemaster-mcp": {
      "command": "uv",
      "args": ["run", "gamemaster-mcp"],
      "cwd": "/path/to/gamemaster-mcp",
      "env": {
        "GAMEMASTER_STORAGE_DIR": "/path/to/your/data"
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
      "gamemaster-mcp": {
        "command": "uv",
        "args": ["run", "gamemaster-mcp"],
        "cwd": "/path/to/gamemaster-mcp",
        "env": {
          "GAMEMASTER_STORAGE_DIR": "/path/to/your/data"
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

- **Command:** `uv run gamemaster-mcp`
- **Working directory:** The cloned repository root
- **Environment:** `GAMEMASTER_STORAGE_DIR` — path where campaign data is stored (defaults to `./data`)

Refer to your client's documentation for where to add MCP server entries. The transport is **stdio** (the default for most clients).

</details>

## Optional: RAG Dependencies

For semantic search capabilities (vector-based library queries via `ask_books`):

```bash
uv sync --extra rag
```

> **Note:** RAG dependencies (`chromadb`, `onnxruntime`) are not available on **macOS Intel (x86_64)**. The server works fine without them — only the `ask_books` tool requires RAG. All other library tools use keyword search.

## Development

```bash
git clone https://github.com/Polloinfilzato/gamemaster-mcp.git
cd gamemaster-mcp
uv sync --group dev
```

Run tests:

```bash
uv run pytest tests/
```

Run the server locally:

```bash
uv run gamemaster-mcp
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

## License

MIT License
