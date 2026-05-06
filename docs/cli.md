# CLI Reference

All commands auto-detect the solution root by walking up from your current directory looking for a `.sln` or `.csproj` file. Pass `--root` to override.

---

## install

Set up dotnet-graph for AI coding tools in one command.

```bash
dotnet-graph install [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--root` | auto-detected | Solution root |
| `--scope project\|local\|user` | `project` | Claude Code MCP scope |
| `--transport stdio\|http` | `stdio` | Transport protocol |
| `--port` | `8000` | Port (HTTP only) |
| `--skip-build` | off | Skip building the graph |
| `--skip-claude-md` | off | Skip patching CLAUDE.md |

**What it does:**
1. Detects solution root from CWD
2. Builds the knowledge graph — DB always at `<root>/.dotnet-graph/knowledge.db`
3. Registers with Claude Code via `claude mcp add` if the CLI is present
4. Writes `.mcp.json` as a fallback for other MCP clients
5. Patches `CLAUDE.md` with dotnet-graph tool instructions so Claude knows how to use it

**Scopes for Claude Code:**

| Scope | File | When to use |
|-------|------|-------------|
| `project` | `.claude/settings.json` | Shared with team (commit it) |
| `local` | `.claude/settings.local.json` | Personal, git-ignored |
| `user` | `~/.claude.json` | All your projects |

---

## configure-claude

Add Claude Code hooks that enforce dotnet-graph best practices.

```bash
dotnet-graph configure-claude [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--root` | auto-detected | Solution root (ignored for `--scope user`) |
| `--scope project\|local\|user` | `project` | Where to write the settings file |
| `--dry-run` | off | Preview changes without writing |

**What it installs:**

| Hook | Trigger | Effect |
|------|---------|--------|
| `PreToolUse` | `Grep` or `Glob` call | Reminds the AI to query dotnet-graph first |
| `PostToolUse` | Edit or Write to a `.cs` file | Reminds the AI to call `get_or_create_note` and `update_note` |
| `SessionStart` | Session opens | Warns if `knowledge.db` is missing or older than the latest commit |

**Scopes:**

| Scope | File | When to use |
|-------|------|-------------|
| `project` | `<root>/.claude/settings.json` | Shared with team (commit it) |
| `local` | `<root>/.claude/settings.local.json` | Personal, git-ignored |
| `user` | `~/.claude/settings.json` | All your projects |

The command is **idempotent** — re-running it skips hooks that are already installed.

**Why a separate command and not part of `install`?**

`install` wires up the MCP server and patches rules files — things every user needs. Hook configuration touches Claude Code's settings outside the project boundary, so it's an explicit opt-in step rather than a default.

---

## build

Build or incrementally update the knowledge graph.

```bash
dotnet-graph build [--root <path>] [--full]
```

- Default: incremental — only re-analyzes changed, new, or deleted `.cs` files
- `--full`: wipes and rebuilds from scratch
- DB written to `<root>/.dotnet-graph/knowledge.db` by default

---

## serve

Start the MCP server.

```bash
dotnet-graph serve [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--root` | auto-detected | Solution root |
| `--db` | `<root>/.dotnet-graph/knowledge.db` | Database path |
| `--transport stdio\|http` | `stdio` | Transport |
| `--port` | `8000` | MCP SSE port (HTTP only) |
| `--api-port` | — | Also start REST API on this port |

If no DB exists, a full build runs automatically before the server starts.

**stdio** (default) — Claude Code spawns the process directly:
```bash
dotnet-graph serve --root /path/to/solution
```

**HTTP/SSE** — remote agents connect over the network:
```bash
dotnet-graph serve --root /path/to/solution --transport http --port 8000
```

**MCP + REST API together:**
```bash
dotnet-graph serve --transport http --port 8000 --api-port 8001
```

---

## api

Start the standalone REST API server (no MCP).

```bash
dotnet-graph api [--root <path>] [--port 8001]
```

- OpenAPI explorer: `http://localhost:8001/docs`
- Spec: `http://localhost:8001/openapi.json`

See [REST API docs](rest-api.md) for all endpoints.

---

## status

Show graph statistics for a solution.

```bash
dotnet-graph status [--root <path>]
```

Prints row counts for every table and the DB file size.

---

## list

Show all running dotnet-graph server instances.

```bash
dotnet-graph list
```

Instances register themselves on startup and deregister on shutdown. Dead processes are pruned automatically.

---

## update

Upgrade dotnet-graph to the latest version on PyPI.

```bash
dotnet-graph update
```

Detects uvx vs pip install and runs the right command.

---

## obsidian

Generate an Obsidian vault from the knowledge graph for visual exploration.

```bash
dotnet-graph obsidian [--root <path>] [--vault <output-dir>]
```

Output defaults to `<root>/.dotnet-graph/obsidian`. Open the folder in Obsidian and switch to Graph View.
