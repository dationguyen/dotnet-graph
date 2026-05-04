# dotnet-graph

[![PyPI](https://img.shields.io/pypi/v/dotnet-graph)](https://pypi.org/project/dotnet-graph/)
[![Python](https://img.shields.io/pypi/pyversions/dotnet-graph)](https://pypi.org/project/dotnet-graph/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Ask Claude Code *"who injects `AuthService`?"* or *"what calls `ValidateToken`?"* and get answers backed by real Roslyn AST analysis — not guesswork.

dotnet-graph indexes your .NET solution into a structured SQLite database and exposes it over MCP (for AI Agents) or a REST API (for anything else).

## Requirements

- Python 3.11+
- .NET SDK 8+

## Install

```bash
pip install dotnet-graph
```

Or run without installing via [uv](https://docs.astral.sh/uv/):

```bash
uvx dotnet-graph
```

## Setup

Run once from anywhere inside your .NET repo:

```bash
dotnet-graph install
```

This auto-detects your solution root, builds the knowledge graph, registers with Claude Code via `claude mcp add`, and writes `.mcp.json` as a fallback. Restart Claude Code and you're done.

> Subsequent builds are incremental — only changed files are re-analyzed. Force a full rebuild with `dotnet-graph build --full`.

## What you get in Claude Code

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
search               → keyword search across everything
build_graph          → trigger a rebuild from inside the agent
```

## Updating

```bash
dotnet-graph update
```

---

**Docs**

- [CLI reference](docs/cli.md)
- [MCP tools](docs/mcp-tools.md)
- [REST API](docs/rest-api.md)
- [What gets indexed](docs/schema.md)
- [Architecture & internals](docs/architecture.md)
