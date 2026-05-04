# dotnet-graph

A Roslyn-powered knowledge graph for .NET/C# codebases, exposed as a [FastMCP](https://github.com/jlowin/fastmcp) server for use with Claude Code.

Replaces regex-based C# parsing with full AST analysis via the .NET Roslyn compiler API, producing a structured SQLite database that Claude can query to understand your codebase.

## What it indexes

| Table | Contents |
|-------|----------|
| `projects` | .csproj files with domain/platform tags |
| `files` | .cs source files with namespace |
| `types` | class / interface / enum / record / struct |
| `methods` | public+protected method declarations (name, return type, params, async, override, line) |
| `properties` | public+protected property declarations |
| `relationships` | inherits / implements (resolved full names) |
| `usings` | using statements per file |
| `registrations` | MvvmCross/DI registrations (interface, impl, lifetime) |
| `endpoints` | HTTP calls (url pattern, method) |
| `xaml_views` | .xaml files mapped by x:Class |
| `config_keys` | flattened JSON config keys per environment |
| `features` | ViewModel-centric feature index |
| `constructor_injections` | constructor parameter types per class |
| `field_declarations` | private/protected fields (name, type) |
| `method_calls` | call edges: caller type+method → callee expr+method |

## Requirements

- Python 3.11+
- .NET SDK 8+ (for compiling the Roslyn analyzer on first run)

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

## Usage

### Build the knowledge graph

```bash
dotnet-graph build --root /path/to/your/solution
```

The DB is written to `.dotnet-graph/knowledge.db` inside the solution root by default. Override with `--db`:

```bash
dotnet-graph build --root /path/to/solution --db /custom/path/knowledge.db
```

On first run, the Roslyn analyzer is compiled and cached at `.dotnet-graph-cache/` inside the solution root.

### Start the MCP server

```bash
dotnet-graph serve --root /path/to/your/solution
```

### Wire into Claude Code (`.mcp.json`)

```json
{
  "mcpServers": {
    "dotnet-graph": {
      "type": "stdio",
      "command": "/path/to/.venv/bin/dotnet-graph",
      "args": ["serve", "--root", "/path/to/your/solution"]
    }
  }
}
```

## MCP tools

| Tool | Description |
|------|-------------|
| `find_type` | Find a type by name (exact or LIKE) |
| `get_type_members` | Get all methods, properties, fields, and injections for a type |
| `find_implementors` | Find all types that implement/inherit from a given type |
| `find_injectors` | Find classes that constructor-inject a given type |
| `get_method_calls` | Get all calls made by a specific method |
| `find_callers` | Find all callers of a given method across the codebase |
| `get_di_registrations` | List DI registrations matching a type name |
| `get_endpoints` | List HTTP endpoints matching a pattern |
| `get_features` | Browse the ViewModel-centric feature index |
| `search` | Keyword search across types, methods, and properties |
| `get_stats` | Row counts for all tables |
| `build_graph` | Trigger a full graph rebuild from within Claude |

## License

MIT
