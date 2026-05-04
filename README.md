# dotnet-graph

A Roslyn-powered knowledge graph for .NET/C# codebases, designed to be used as a shared code-indexing service by multiple AI agents simultaneously.

Replaces regex-based C# parsing with full AST analysis via the .NET Roslyn compiler API, producing a structured SQLite database that agents can query to understand your codebase — over MCP (stdio or SSE) or a plain REST API.

## What it indexes

| Table | Contents |
|-------|----------|
| `projects` | `.csproj` files with domain/platform tags |
| `files` | `.cs` source files with namespace |
| `types` | class / interface / enum / record / struct |
| `methods` | method declarations (name, return type, params, async, override, line) |
| `properties` | property declarations |
| `relationships` | inherits / implements (resolved to full names) |
| `usings` | using statements per file |
| `registrations` | MvvmCross/DI registrations (interface, impl, lifetime) |
| `endpoints` | HTTP call sites (url pattern, method) |
| `xaml_views` | `.xaml` files mapped by `x:Class` |
| `config_keys` | flattened JSON config keys per environment |
| `features` | ViewModel-centric feature index |
| `constructor_injections` | constructor parameter types per class |
| `field_declarations` | private/protected fields (name, type) |
| `method_calls` | call edges: caller type+method → callee expr+method |
| `file_hashes` | SHA-256 per `.cs` file for incremental rebuild |
| `build_meta` | last build timestamp, duration, file counts, tool version |

## Requirements

- Python 3.11+
- .NET SDK 8+ (the Roslyn analyzer is compiled and cached on first run)

## Installation

```bash
pip install dotnet-graph
```

Or from source:

```bash
git clone https://github.com/yourorg/dotnet-graph
cd dotnet-graph
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

---

## Quick start

### 1. Build the graph

```bash
dotnet-graph build --root /path/to/your/solution
```

The database is written to `<root>/.dotnet-graph/knowledge.db`. Subsequent runs are **incremental** — only changed, new, or deleted `.cs` files are re-analyzed. Force a full rebuild with `--full`:

```bash
dotnet-graph build --root /path/to/solution --full
```

### 2. Start the server

**For Claude Code / local stdio agents:**

```bash
dotnet-graph serve --root /path/to/solution
```

**For remote HTTP agents (SSE transport):**

```bash
dotnet-graph serve --root /path/to/solution --transport http --port 8000
```

**With REST API alongside MCP:**

```bash
dotnet-graph serve --root /path/to/solution --transport http --port 8000 --api-port 8001
```

### 3. Wire into Claude Code

Auto-generate the `.mcp.json` entry:

```bash
dotnet-graph install --root /path/to/solution
```

Or manually:

```json
{
  "mcpServers": {
    "dotnet-graph": {
      "type": "stdio",
      "command": "uvx",
      "args": ["dotnet-graph", "serve", "--root", "/path/to/solution"]
    }
  }
}
```

For an HTTP server already running:

```bash
dotnet-graph install --root /path/to/solution --transport http --port 8000
```

This writes a URL-based entry pointing to the SSE endpoint.

---

## Multi-agent usage

Each codebase gets its own server instance. Multiple agents can query the same instance concurrently (SQLite WAL mode handles concurrent reads). Concurrent build requests are serialized by a file lock — the second caller gets a clear error rather than a corrupted database.

### See what's running

```bash
dotnet-graph list
```

```
2 running instance(s):

  root     : /Users/dev/MyApp
  db       : /Users/dev/MyApp/.dotnet-graph/knowledge.db
  pid      : 12345
  started  : 2026-05-04T03:01:00+00:00
  transport: http
  url      : http://0.0.0.0:8000/sse

  root     : /Users/dev/OtherApp
  db       : /Users/dev/OtherApp/.dotnet-graph/knowledge.db
  pid      : 12399
  started  : 2026-05-04T03:05:00+00:00
  transport: stdio
```

Each instance registers itself to `~/.dotnet-graph/registry.json` on startup and deregisters on clean shutdown. Dead instances (process no longer running) are pruned automatically.

---

## REST API

For non-MCP agents (LangChain, curl, custom scripts), start the REST API server:

```bash
dotnet-graph api --root /path/to/solution --port 8001
```

Interactive OpenAPI explorer: `http://localhost:8001/docs`  
Machine-readable spec: `http://localhost:8001/openapi.json`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/query/types?name=&exact=` | Find types by name |
| GET | `/query/types/{name}/members` | Get methods, properties, fields, constructor params |
| GET | `/query/types/{name}/implementors` | Find implementors and subclasses |
| GET | `/query/types/{name}/injectors` | Find classes that inject this type |
| GET | `/query/method-calls?type=&method=` | Get calls made within a method |
| GET | `/query/callers?method=` | Find all callers of a method |
| GET | `/query/di-registrations?name=` | List DI registrations |
| GET | `/query/endpoints` | List HTTP endpoints |
| GET | `/query/features` | Browse ViewModel-centric feature index |
| GET | `/query/search?q=` | Keyword search across types, methods, properties |
| GET | `/query/stats` | Build info + row counts for all tables |

All endpoints return structured JSON. Example:

```bash
curl http://localhost:8001/query/types?name=AuthService
curl http://localhost:8001/query/types/AuthService/injectors
curl http://localhost:8001/query/search?q=ValidateToken
```

---

## MCP tools

When using Claude Code or another MCP-compatible agent, the following tools are available:

| Tool | Description |
|------|-------------|
| `find_type` | Find a type by name (exact or LIKE) |
| `get_type_members` | Get all methods, properties, fields, and injections for a type |
| `find_implementors` | Find all types that implement/inherit from a given type |
| `find_injectors` | Find classes that constructor-inject a given type |
| `get_method_calls` | Get all calls made by a specific method |
| `find_callers` | Find all callers of a given method across the codebase |
| `get_di_registrations` | List DI registrations matching a type name |
| `get_endpoints` | List all HTTP endpoints found in the codebase |
| `get_features` | Browse the ViewModel-centric feature index |
| `search` | Keyword search across types, methods, and properties |
| `get_stats` | Build info and row counts for all tables |
| `build_graph` | Trigger a graph rebuild from within the agent |
| `build_obsidian_vault` | Generate an Obsidian vault for graph visualization |

---

## CLI reference

```
dotnet-graph build   --root <path> [--db <path>] [--full]
dotnet-graph serve   --root <path> [--transport stdio|http] [--port N] [--api-port N]
dotnet-graph api     --root <path> [--port N] [--host <host>]
dotnet-graph list
dotnet-graph install --root <path> [--transport stdio|http] [--port N]
dotnet-graph status  --root <path>
dotnet-graph obsidian --root <path> [--vault <path>]
```

| Command | Description |
|---------|-------------|
| `build` | Build or incrementally update the knowledge graph |
| `serve` | Start the MCP server (stdio or HTTP/SSE) |
| `api` | Start the standalone REST API server |
| `list` | Show all running server instances |
| `install` | Add dotnet-graph to `.mcp.json` in the project root |
| `status` | Show graph statistics |
| `obsidian` | Generate an Obsidian vault for visual exploration |

---

## Architecture

```
.cs files
    └─► Roslyn analyzer (C#, compiled once)
            └─► JSON output
                    └─► SQLite database (.dotnet-graph/knowledge.db)
                                │
                    ┌───────────┴───────────┐
                    │                       │
              MCP server               REST API
          (stdio or SSE)           (FastAPI + uvicorn)
                    │                       │
          Claude Code / agents    LangChain / curl / agents
```

- **Incremental builds**: SHA-256 hashes per file; Roslyn only analyzes changed files via `--files-list`
- **Concurrent reads**: SQLite WAL mode; multiple agents can query simultaneously
- **Write safety**: `filelock` serializes builds; second caller fails fast with a clear error
- **Instance discovery**: `~/.dotnet-graph/registry.json` tracks all running servers; dead entries auto-pruned

## License

MIT
