# dotnetgraph

Roslyn-powered knowledge graph for .NET/C# codebases. Indexes your solution into a structured SQLite database and exposes it over MCP (for Claude Code) or a REST API (for anything else).

## Requirements

- Python 3.11+
- .NET SDK 8+

## Install

```bash
pip install dotnetgraph
# or: uvx dotnetgraph install   (zero local install)
```

## Setup

Run once from anywhere inside your .NET repo:

```bash
dotnet-graph install
```

This auto-detects your solution root, builds the knowledge graph, registers with Claude Code via `claude mcp add`, and writes `.mcp.json` as a fallback. Restart Claude Code and you're done.

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

## Keeping the graph fresh

Subsequent builds are incremental — only changed files are re-analyzed:

```bash
dotnet-graph build          # incremental (default)
dotnet-graph build --full   # force full rebuild
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
