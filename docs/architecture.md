# Architecture & Internals

## How it works

```
.cs / .xaml / .json files
        │
        ▼
  Roslyn Analyzer (C#)          ← compiled once, cached in ~/.cache/dotnet-graph/
        │  AST-level analysis
        ▼
     JSON output
        │
        ▼
  Python ingest layer
        │  writes to SQLite
        ▼
  knowledge.db (WAL mode)
        │
   ┌────┴────┐
   │         │
MCP server  REST API
(stdio/SSE) (FastAPI)
   │         │
Claude    LangChain
Code      / curl
```

## Incremental builds

Every `.cs` file is SHA-256 hashed before analysis. On subsequent builds:

1. Load stored hashes from `file_hashes` table
2. Compare against current hashes on disk
3. Delete stale data for changed or deleted files
4. Run Roslyn only on changed/new files (passed via `--files-list`)
5. Store updated hashes

Result: a large solution re-analyzes only the files you touched, typically completing in under a second.

Force a full rebuild anytime: `dotnet-graph build --full`

## Concurrent access

SQLite runs in **WAL mode** — multiple agents can read simultaneously without blocking each other. Writes (builds) are serialized by a `filelock` on `<db>.lock`. A second build attempt fails immediately with a clear error rather than waiting or corrupting the database.

## Instance registry

Each running server registers itself to `~/.dotnet-graph/registry.json` on startup (via `atexit`, deregisters on clean shutdown). `dotnet-graph list` reads this file, prunes any entries whose process is no longer alive, and prints the rest.

## DB location

| Install path | DB location |
|-------------|-------------|
| Via `claude mcp add` (Claude Code) | `<root>/.claude/.dotnet-graph/knowledge.db` |
| Via `.mcp.json` (other tools) | `<root>/.dotnet-graph/knowledge.db` |
| Manual `--db` override | wherever you say |

## Roslyn analyzer

The analyzer is a standalone C# console app (`dotnet_graph/analyzer/`) compiled with `dotnet publish` on first run and cached in `~/.cache/dotnet-graph/analyzer/`. It is recompiled automatically if any source file is newer than the cache stamp.

The analyzer uses **syntax-only parsing** (`CSharpSyntaxTree.ParseText`) — no compilation or project loading needed. This makes it fast and dependency-free, but means it works on file-by-file ASTs rather than a fully resolved semantic model.

## Releasing

```bash
hatch version patch        # or minor / major
git add pyproject.toml
git commit -m "chore: bump to $(hatch version)"
git tag v$(hatch version)
git push && git push --tags
```

GitHub Actions builds the wheel, publishes to PyPI via OIDC trusted publisher, and creates a GitHub Release automatically.
