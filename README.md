# dotnet-graph

[![PyPI](https://img.shields.io/pypi/v/dotnet-graph)](https://pypi.org/project/dotnet-graph/)
[![Python](https://img.shields.io/pypi/pyversions/dotnet-graph)](https://pypi.org/project/dotnet-graph/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-dationguyen-FFDD00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/dationguyen)

Ask your AI coding tool *"who injects `AuthService`?"* or *"what calls `ValidateToken`?"* and get answers backed by real Roslyn AST analysis — not guesswork.

dotnet-graph indexes your .NET solution into a structured SQLite database and exposes it over MCP (for AI agents) or a REST API (for anything else). Works with Claude Code, Cursor, and any other MCP-compatible tool.

## Requirements

- Python 3.11+ — verify with `python --version`
- .NET SDK 8+ — verify with `dotnet --version`

## Install

```bash
pip install dotnet-graph
```

> **macOS with uv:** If `pip install` fails because uv intercepts it, use `uv tool install dotnet-graph` instead. This creates an isolated environment and puts `dotnet-graph` on your PATH.

## Setup

Run once from anywhere inside your .NET repo:

```bash
# Claude Code (default)
dotnet-graph install

# Cursor
dotnet-graph install --agent cursor

# Both at once
dotnet-graph install --agent all
```

This auto-detects your solution root and:

1. Builds the knowledge graph (SQLite DB at `.dotnet-graph/knowledge.db`)
2. Registers the MCP server with your AI coding tool
3. Patches the agent rules file with dotnet-graph tool instructions

| Agent | MCP config | Rules file |
|-------|-----------|------------|
| Claude Code | `.mcp.json` + `claude mcp add` | `CLAUDE.md` |
| Cursor | `.cursor/mcp.json` | `.cursorrules` + `AGENTS.md` |

Restart your AI coding tool and you're done.

> **Solution not at repo root?** Pass the path explicitly:
> ```bash
> dotnet-graph install --root /path/to/your/repo
> ```

> **Skip rules file patching:**
> ```bash
> dotnet-graph install --skip-claude-md
> ```

> Subsequent builds are incremental — only changed files are re-analyzed. Force a full rebuild with `dotnet-graph build --full`.

## MCP tools

```
find_type            → locate any class or interface
get_type_members     → methods, properties, fields, constructor injections
find_injectors       → who depends on this type (DI graph)
find_implementors    → subclasses and interface implementations
get_method_calls     → trace execution flow from a method
find_callers         → who calls this method across the codebase
get_di_registrations → MvvmCross / DI registration lifetimes
get_endpoints        → HTTP endpoints
get_features         → ViewModel-centric feature index
get_stats            → build metadata and row counts for the knowledge graph
search               → keyword search across everything
build_graph          → trigger an incremental or full rebuild from inside the agent
build_obsidian_vault → export the graph as an Obsidian vault for visual exploration
get_or_create_note   → get or create a persistent knowledge note for a type
update_note          → write the ## Notes section (purpose, behaviours, work log)
sync_note_structure  → refresh a note's structure after a graph rebuild
```

## Knowledge notes

AI agents can accumulate domain knowledge about types as they work, persisting it across sessions in `.dotnet-graph/notes/<Domain>/<Project>/<TypeName>.md`.

Each note has two parts:
- **Structure** — auto-generated from the graph (methods, DI, inheritance). Refreshed on demand via `sync_note_structure`.
- **Notes section** — maintained by the agent (purpose, business logic, gotchas, work log). Never overwritten.

Typical agent workflow:
1. Read or modify a source file
2. Call `get_or_create_note("TypeName")` — creates the note if new
3. Edit the `## Notes` section with purpose, key behaviours, and a work log entry
4. After a `build_graph`, call `sync_note_structure("TypeName")` to refresh structure without losing notes

## Keeping the graph up to date

Rebuilds are incremental by default — only changed files are re-analyzed.

**From the terminal:**
```bash
dotnet-graph build        # incremental
dotnet-graph build --full # full rebuild
```

**From inside the agent** — just ask it to run `build_graph`:
```
rebuild the graph
```

**Generate an Obsidian vault** for a visual map of your codebase:
```bash
dotnet-graph obsidian
```
Or ask your agent: *"export the graph to Obsidian"* — it calls `build_obsidian_vault` directly.

## Development

```bash
git clone https://github.com/dationguyen/dotnet-graph
cd dotnet-graph
uv sync --extra dev
uv run --with pytest --with httpx pytest tests/integration_test.py -v
```

Requires .NET SDK 8+ for the Roslyn analyzer.

---

**Docs**

- [CLI reference](docs/cli.md)
- [MCP tools](docs/mcp-tools.md)
- [REST API](docs/rest-api.md)
- [What gets indexed](docs/schema.md)
- [Architecture & internals](docs/architecture.md)
