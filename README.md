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

### 3 Steps to Play D&D

You don't need to install anything beforehand. One command sets up everything:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Polloinfilzato/dm20-protocol/main/install.sh)
```

The installer asks a few questions (which MCP client you use, where to put your data), handles all dependencies automatically, and configures everything. When it's done:

```bash
cd ~/dm20    # go to your play directory
claude       # start Claude Code — the MCP server connects automatically
```

That's it. You're ready to play.

> **Using Claude Desktop instead?** Just restart it after installation — the MCP server is already configured.

The installer offers two modes. **Most users should pick "User"** — it's the default:

| | User (recommended) | Developer |
|---|---|---|
| **Who it's for** | Players who want to play D&D | Contributors who want to modify the code |
| **What it installs** | A single `dm20-protocol` command | Full source code repository |
| **Disk footprint** | Minimal (~50 MB) | Full dev environment (~200+ MB) |
| **Prerequisites** | None (auto-installed) | None (auto-installed) |
| **How to update** | `uv tool upgrade dm20-protocol` | `git pull && uv sync` |

> Running `bash install.sh` from inside an existing clone? The installer auto-detects it and switches to Developer mode.

**Supported platforms:** macOS (Apple Silicon & Intel), Linux (x86_64/arm64), Windows via WSL. See [Installer Details](docs/INSTALLER.md) for the full breakdown.

**Want to know what happens under the hood?** The [Installer Guide](docs/INSTALLER.md) covers the full architecture, every edge case we handle, and why we built it this way.

### Compatibility

This server implements the open [Model Context Protocol](https://modelcontextprotocol.io/) standard. It works with **any MCP-compatible client** — not just Claude.

| Platform / Client | Status |
|---|---|
| macOS + Claude Code | **Tested** (Intel & Apple Silicon) |
| macOS + Claude Desktop | **Tested** (Intel & Apple Silicon) |
| Linux + Claude Code | Supported, community testing welcome |
| Linux + Claude Desktop | Supported, community testing welcome |
| Windows (via WSL) | Supported, community testing welcome |
| Cursor, Windsurf, Cline, VS Code Copilot | Supported, community testing welcome |
| OpenAI Codex, Gemini CLI, Amazon Q | Supported, community testing welcome |

> We're confident in cross-platform support (the installer and server are designed for it), but we can only mark combinations as "Tested" once a contributor confirms them. If you try one of the untested combinations and it works (or doesn't), please [open an issue](https://github.com/Polloinfilzato/dm20-protocol/issues) — it helps everyone.

For detailed per-client setup instructions, config file locations, and platform-specific notes, see the **[MCP Client Setup Guide](docs/MCP_CLIENTS.md)**.

### Manual Install

<details>
<summary><strong>Option A: Install as a tool (simplest — no git clone needed)</strong></summary>

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv tool install "dm20-protocol @ git+https://github.com/Polloinfilzato/dm20-protocol.git"
```

Then add to your MCP client's config file (see [MCP Client Setup Guide](docs/MCP_CLIENTS.md) for your client's config path):

```json
{
  "mcpServers": {
    "dm20-protocol": {
      "command": "dm20-protocol",
      "env": {
        "DM20_STORAGE_DIR": "/path/to/your/data"
      }
    }
  }
}
```

> **Note:** Some clients (like Claude Desktop) don't inherit your shell PATH. Use the absolute path instead: `"command": "/Users/you/.local/bin/dm20-protocol"` (find it with `which dm20-protocol`).

On Linux, if `dm20-protocol` is not found after install, run `uv tool update-shell` or add `~/.local/bin` to your PATH manually.

</details>

<details>
<summary><strong>Option B: Clone the repository (for development)</strong></summary>

```bash
git clone https://github.com/Polloinfilzato/dm20-protocol.git
cd dm20-protocol
uv sync
```

Then add to your MCP client's config file (see [MCP Client Setup Guide](docs/MCP_CLIENTS.md) for your client's config path):

```json
{
  "mcpServers": {
    "dm20-protocol": {
      "command": "uv",
      "args": ["run", "python", "-m", "dm20_protocol"],
      "cwd": "/absolute/path/to/dm20-protocol",
      "env": {
        "DM20_STORAGE_DIR": "/path/to/your/data"
      }
    }
  }
}
```

> **Note:** Claude Desktop doesn't inherit your shell PATH. Use absolute paths for both `command` and `cwd`. Find `uv` with `which uv`.

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
| `/dm:profile [tier]` | Switch model quality: quality, balanced, economy |

### How It Works

The system uses a **dual-agent architecture** where two specialized LLM agents run in parallel on every player action:

- **Narrator** — Rich scene descriptions, NPC dialogue, atmospheric text
- **Arbiter** — Mechanical resolution, dice rolls, rule adjudication

A **DM Persona** (`.claude/dm-persona.md`) orchestrates the game loop: gather context, decide what happens, execute via tools, update state, narrate the outcome. A Python-side **Archivist** agent handles data retrieval and game state tracking without consuming LLM tokens.

**Model Profiles** let you trade quality vs token cost with a single command. All profiles use Opus with different effort levels — medium effort matches Sonnet quality with ~76% fewer output tokens:

| Profile | Model + Effort | CC Agents | Best for |
|---------|---------------|-----------|----------|
| `quality` | Opus, effort high | Opus | Boss fights, key story moments |
| `balanced` | Opus, effort medium | Opus | General play (default) |
| `economy` | Opus, effort low | Haiku | Stretching token budgets |

Switch mid-session with `/dm:profile economy` or via `configure_claudmaster(model_profile="quality")`. The profile updates both the Python-side config and the Claude Code agent files at once.

> **Note:** Model profiles and effort levels are a **Claude-specific feature**. The effort parameter is only supported on Anthropic's Opus models via the Claude API. If you're using dm20-protocol with a different MCP client or LLM backend, the effort setting will have no effect — the system still works, but you won't get the quality/cost scaling that effort provides. CC agent file updates (`.claude/agents/*.md`) are specific to Claude Code.

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
