# dotnet-graph

[![PyPI](https://img.shields.io/pypi/v/dotnet-graph)](https://pypi.org/project/dotnet-graph/)
[![Python](https://img.shields.io/pypi/pyversions/dotnet-graph)](https://pypi.org/project/dotnet-graph/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Ask Claude Code *"who injects `AuthService`?"* or *"what calls `ValidateToken`?"* and get answers backed by real Roslyn AST analysis — not guesswork.

dotnet-graph indexes your .NET solution into a structured SQLite database and exposes it over MCP (for AI Agents) or a REST API (for anything else).

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
dotnet-graph install
```

This auto-detects your solution root and:

1. Builds the knowledge graph (SQLite DB at `.dotnet-graph/knowledge.db`)
2. Registers with Claude Code via `claude mcp add`
3. Writes `.mcp.json` as a fallback for other MCP clients
4. Patches `CLAUDE.md` with dotnet-graph tool instructions so Claude knows how to use it

Restart Claude Code and you're done.

> **Solution not at repo root?** Pass the path explicitly:
> ```bash
> dotnet-graph install --root /path/to/your/repo
> ```

> **Skip CLAUDE.md patching:**
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
```

## Keeping the graph up to date

Rebuilds are incremental by default — only changed files are re-analyzed.

**From the terminal:**
```bash
dotnet-graph build        # incremental
dotnet-graph build --full # full rebuild
```

**From inside the agent** — just ask Claude to run `build_graph`:
```
rebuild the graph
```

**Generate an Obsidian vault** for a visual map of your codebase:
```bash
dotnet-graph obsidian
```
Or ask Claude: *"export the graph to Obsidian"* — it calls `build_obsidian_vault` directly.

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
