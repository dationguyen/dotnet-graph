"""CLI entry point for dotnet-graph."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click


# ── Version check ──────────────────────────────────────────────────────────────

def _check_for_update() -> None:
    """Print a one-line nudge if a newer version is on PyPI (at most once per day)."""
    try:
        from dotnet_graph import __version__
        cache_file = Path.home() / ".cache" / "dotnet-graph" / "version_check.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        # Read cached result
        cached: dict = {}
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        today = datetime.now(timezone.utc).date().isoformat()
        if cached.get("checked_on") == today:
            latest = cached.get("latest", __version__)
        else:
            import urllib.request
            with urllib.request.urlopen(
                "https://pypi.org/pypi/dotnet-graph/json", timeout=2
            ) as resp:
                latest = json.loads(resp.read())["info"]["version"]
            cache_file.write_text(json.dumps({"checked_on": today, "latest": latest}), encoding="utf-8")

        from packaging.version import Version
        if Version(latest) > Version(__version__):
            click.echo(
                f"  Update available: {__version__} → {latest}  "
                f"Run: dotnet-graph update",
                err=True,
            )
    except Exception:
        pass  # never break the CLI over a version check


# ── Root auto-detection ────────────────────────────────────────────────────────

def _find_root() -> Path | None:
    """Walk up from CWD looking for a .sln or .csproj to use as solution root."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if any(parent.glob("*.sln")):
            return parent
        if any(p for p in parent.glob("*.csproj") if not any(
            part in ("obj", "bin") for part in p.parts
        )):
            return parent
    return None


def _resolve_root(root: Optional[str]) -> Path:
    """Return root as a resolved Path, auto-detecting from CWD when omitted."""
    if root:
        return Path(root).resolve()
    detected = _find_root()
    if detected is None:
        raise click.ClickException(
            "Could not find a .sln or .csproj file. "
            "Run this command from inside a .NET solution, or pass --root <path>."
        )
    return detected


def _db_for(root_path: Path, db: Optional[str]) -> Path:
    return Path(db).resolve() if db else root_path / ".dotnet-graph" / "knowledge.db"



# ── CLI group ──────────────────────────────────────────────────────────────────

@click.group()
@click.version_option()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Roslyn-powered knowledge graph for .NET/C# codebases."""
    if ctx.invoked_subcommand != "update":
        _check_for_update()


# ── build ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--root", default=None, type=click.Path(exists=True, file_okay=False),
              help="Solution root (auto-detected from CWD if omitted)")
@click.option("--db", default=None, type=click.Path(),
              help="Database path (default: <root>/.dotnet-graph/knowledge.db)")
@click.option("--full", "force_full", is_flag=True, default=False,
              help="Force a full rebuild instead of incremental")
def build(root: Optional[str], db: Optional[str], force_full: bool) -> None:
    """Build (or rebuild) the knowledge graph.

    By default runs an incremental build — only re-analyzes files whose
    content has changed since the last build. Use --full to force a complete
    rebuild from scratch.
    """
    from dotnet_graph.builder import build as _build

    root_path = _resolve_root(root)
    db_path = _db_for(root_path, db)
    mode = "full" if force_full else "incremental"
    click.echo(f"Building graph [{mode}] for {root_path} → {db_path}")
    _build(root_path, db_path, verbose=True, incremental=not force_full)


# ── serve ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--root", default=None, type=click.Path(exists=True, file_okay=False),
              help="Solution root (auto-detected from CWD if omitted)")
@click.option("--db", default=None, type=click.Path(), help="Database path")
@click.option("--transport", default="stdio", type=click.Choice(["stdio", "http"]),
              show_default=True, help="Transport protocol")
@click.option("--host", default="0.0.0.0", show_default=True, help="Bind host (HTTP/REST only)")
@click.option("--port", default=8000, show_default=True, type=int,
              help="MCP SSE port (HTTP transport only)")
@click.option("--api-port", default=None, type=int,
              help="Also start the REST API on this port")
def serve(root: Optional[str], db: Optional[str], transport: str,
          host: str, port: int, api_port: Optional[int]) -> None:
    """Start the MCP server.

    Use --transport stdio (default) for Claude Code / local agents that spawn
    the process directly. Use --transport http to expose an SSE endpoint that
    remote agents can connect to over the network.

    If no knowledge graph exists yet, a full build is triggered automatically
    before the server starts.
    """
    from dotnet_graph.main import serve as _serve

    root_str = str(_resolve_root(root)) if not db else root
    _serve(root=root_str, db=db, transport=transport, host=host, port=port, api_port=api_port)


# ── api ────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--root", default=None, type=click.Path(exists=True, file_okay=False),
              help="Solution root (auto-detected from CWD if omitted)")
@click.option("--db", default=None, type=click.Path(), help="Database path")
@click.option("--host", default="0.0.0.0", show_default=True, help="Bind host")
@click.option("--port", default=8001, show_default=True, type=int, help="Bind port")
def api(root: Optional[str], db: Optional[str], host: str, port: int) -> None:
    """Start the REST API server (standalone, without MCP).

    Exposes all query tools as HTTP endpoints with an OpenAPI spec at /docs.
    Useful for non-MCP agents (LangChain, curl, custom scripts).
    """
    import uvicorn
    from dotnet_graph.api import create_app

    root_path = _resolve_root(root) if not db else (Path(root).resolve() if root else None)
    db_path = _db_for(root_path, db) if root_path else (Path(db).resolve() if db else None)

    if db_path is None:
        raise click.ClickException("Provide --root or --db.")

    click.echo(f"REST API → http://{host}:{port}/docs")
    click.echo(f"OpenAPI  → http://{host}:{port}/openapi.json")
    app = create_app(db_path)
    uvicorn.run(app, host=host, port=port)


# ── list ───────────────────────────────────────────────────────────────────────

@cli.command("list")
def list_servers() -> None:
    """List all running dotnet-graph server instances."""
    from dotnet_graph.registry import list_instances

    instances = list_instances()
    if not instances:
        click.echo("No running dotnet-graph instances found.")
        return

    click.echo(f"\n{len(instances)} running instance(s):\n")
    for inst in instances:
        transport = inst.get("transport", "stdio")
        click.echo(f"  root     : {inst.get('root') or '—'}")
        click.echo(f"  db       : {inst.get('db_path') or '—'}")
        click.echo(f"  pid      : {inst.get('pid', '—')}")
        click.echo(f"  started  : {inst.get('started_at', '—')}")
        click.echo(f"  transport: {transport}")
        if transport == "http":
            click.echo(f"  url      : {inst.get('url', '—')}")
        click.echo("")


# ── status ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--root", default=None, type=click.Path(exists=True, file_okay=False),
              help="Solution root (auto-detected from CWD if omitted)")
@click.option("--db", default=None, type=click.Path(), help="Database path")
def status(root: Optional[str], db: Optional[str]) -> None:
    """Show graph statistics."""
    from dotnet_graph.db import open_db, count

    root_path = _resolve_root(root)
    db_path = _db_for(root_path, db)

    if not db_path.exists():
        raise click.ClickException(
            f"No graph found at {db_path}. Run `dotnet-graph build` first."
        )

    conn = open_db(db_path)
    tables = [
        "projects", "files", "types", "methods", "properties",
        "relationships", "registrations", "endpoints", "config_keys",
        "features", "constructor_injections", "field_declarations", "method_calls",
    ]
    click.echo(f"\nGraph: {db_path}  ({db_path.stat().st_size / 1024 / 1024:.1f} MB)\n")
    for t in tables:
        click.echo(f"  {t:<22}: {count(conn, t):>6,}")


# ── obsidian ───────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--root", default=None, type=click.Path(exists=True, file_okay=False),
              help="Solution root (auto-detected from CWD if omitted)")
@click.option("--db", default=None, type=click.Path(),
              help="Database path (default: <root>/.dotnet-graph/knowledge.db)")
@click.option("--vault", default=None, type=click.Path(),
              help="Output vault directory (default: <root>/.dotnet-graph/obsidian)")
def obsidian(root: Optional[str], db: Optional[str], vault: Optional[str]) -> None:
    """Generate an Obsidian vault from the knowledge graph."""
    from dotnet_graph.obsidian import build_vault

    root_path = _resolve_root(root)
    db_path = _db_for(root_path, db)
    vault_path = Path(vault).resolve() if vault else root_path / ".dotnet-graph" / "obsidian"

    if not db_path.exists():
        raise click.ClickException(
            f"No graph found at {db_path}. Run `dotnet-graph build` first."
        )

    click.echo(f"Generating Obsidian vault → {vault_path}")
    n = build_vault(db_path, vault_path, verbose=True)
    click.echo(f"Done: {n} notes written to {vault_path}")
    click.echo("Open that folder in Obsidian and switch to Graph View.")


# ── explore ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--root", default=None, type=click.Path(exists=True, file_okay=False),
              help="Solution root (auto-detected from CWD if omitted)")
@click.option("--db", default=None, type=click.Path(),
              help="Database path (default: <root>/.dotnet-graph/knowledge.db)")
@click.option("--out", default=None, type=click.Path(),
              help="Output directory (default: <root>/.dotnet-graph/explore)")
@click.option("--notes", default=None, type=click.Path(),
              help="Notes directory to source summaries from (default: <root>/.dotnet-graph/notes)")
@click.option("--open", "open_browser", is_flag=True, default=False,
              help="Open the dashboard in your browser when done")
def explore(root: Optional[str], db: Optional[str], out: Optional[str],
            notes: Optional[str], open_browser: bool) -> None:
    """Build the interactive 'explore' dashboard from the knowledge graph.

    Generates a self-contained web app (index.html + data.js) that maps the
    codebase by architectural layer, gives every type a plain-English summary,
    builds dependency-ordered guided tours, and lays domains out as a left-to-right
    flow. Reuses enriched knowledge notes for the best summaries. No server needed —
    just open the index.html.
    """
    from dotnet_graph.explore import build_dashboard

    root_path = _resolve_root(root)
    db_path = _db_for(root_path, db)
    out_path = Path(out).resolve() if out else root_path / ".dotnet-graph" / "explore"
    notes_path = Path(notes).resolve() if notes else root_path / ".dotnet-graph" / "notes"

    if not db_path.exists():
        raise click.ClickException(
            f"No graph found at {db_path}. Run `dotnet-graph build` first."
        )

    click.echo(f"Building explore dashboard → {out_path}")
    build_dashboard(db_path, out_path, notes_path, verbose=True)

    index = out_path / "index.html"
    if open_browser:
        import webbrowser
        webbrowser.open(index.as_uri())
    else:
        click.echo(f"Open in a browser: {index}")


# ── note ───────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("type_name")
@click.option("--root", default=None, type=click.Path(exists=True, file_okay=False),
              help="Solution root (auto-detected from CWD if omitted)")
@click.option("--db", default=None, type=click.Path(), help="Database path")
@click.option("--notes", default=None, type=click.Path(),
              help="Notes directory (default: <root>/.dotnet-graph/notes)")
def note(type_name: str, root: Optional[str], db: Optional[str], notes: Optional[str]) -> None:
    """Get or create an enriched knowledge note for a type.

    If the note already exists, prints its current content.
    If not, creates one from graph data with an empty Notes section.

    Notes live in .dotnet-graph/notes/<Domain>/<TypeName>.md and are
    maintained by AI agents as they read and modify the codebase.
    """
    from dotnet_graph.notes import get_or_create_note as _get_or_create

    root_path = _resolve_root(root)
    db_path = _db_for(root_path, db)
    notes_path = Path(notes).resolve() if notes else root_path / ".dotnet-graph" / "notes"

    if not db_path.exists():
        raise click.ClickException(
            f"No graph found at {db_path}. Run `dotnet-graph build` first."
        )

    result = _get_or_create(db_path, type_name, notes_path)

    if "error" in result:
        raise click.ClickException(result["error"])

    status = "Created" if result["created"] else "Found existing"
    click.echo(f"{status} note: {result['path']}\n")
    click.echo(result["content"])


@cli.command()
@click.argument("type_name")
@click.option("--root", default=None, type=click.Path(exists=True, file_okay=False),
              help="Solution root (auto-detected from CWD if omitted)")
@click.option("--db", default=None, type=click.Path(), help="Database path")
@click.option("--notes", default=None, type=click.Path(),
              help="Notes directory (default: <root>/.dotnet-graph/notes)")
def sync_note(type_name: str, root: Optional[str], db: Optional[str], notes: Optional[str]) -> None:
    """Refresh a note's structure from current graph data, preserving ## Notes.

    Re-generates Methods, Properties, Injections, and Inheritance sections from
    the live graph. The ## Notes section (purpose, business logic, work log) is
    never touched. Creates the note first if it doesn't exist yet.
    """
    from dotnet_graph.notes import sync_note_structure as _sync

    root_path = _resolve_root(root)
    db_path = _db_for(root_path, db)
    notes_path = Path(notes).resolve() if notes else root_path / ".dotnet-graph" / "notes"

    if not db_path.exists():
        raise click.ClickException(
            f"No graph found at {db_path}. Run `dotnet-graph build` first."
        )

    result = _sync(db_path, type_name, notes_path)

    if "error" in result:
        raise click.ClickException(result["error"])

    if result.get("created"):
        click.echo(f"Created note: {result['path']}\n")
    elif result.get("refreshed"):
        click.echo(f"Refreshed note: {result['path']}\n")
    else:
        click.echo(f"No standard marker found — returned unchanged: {result['path']}\n")
    click.echo(result["content"])


# ── configure-claude ──────────────────────────────────────────────────────────

_HOOK_MARKER = "dotnet-graph:"

_PRETOOLS_HOOK_GROUP: dict = {
    "matcher": "Grep|Glob",
    "hooks": [
        {
            "type": "command",
            "command": (
                """echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"REMINDER: If searching for a type, class, interface, or cross-module dependency — query via the dotnet-graph MCP tool FIRST. It is faster and uses fewer tokens than Grep/Glob."}}'"""
            ),
            "statusMessage": "dotnet-graph: nudging graph-first...",
        }
    ],
}

_POST_CS_HOOK_GROUP: dict = {
    "matcher": "Edit|Write",
    "hooks": [
        {
            "type": "command",
            "if": "Edit(*.cs)|Write(*.cs)",
            "command": (
                """echo '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"You just edited a .cs file — call get_or_create_note for the type you modified, then update_note with purpose, key behaviours, gotchas, and work log."}}'"""
            ),
            "statusMessage": "dotnet-graph: nudging knowledge note...",
        }
    ],
}

_SESSION_START_HOOK_GROUP: dict = {
    "matcher": "",
    "hooks": [
        {
            "type": "command",
            "command": (
                'DB=".dotnet-graph/knowledge.db"; '
                'if [ ! -f "$DB" ]; then '
                """echo '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"dotnet-graph knowledge.db is missing. Rebuild: uvx dotnet-graph build"}}'; """
                'else '
                'DB_MTIME=$(stat -f %m "$DB" 2>/dev/null); '
                'COMMIT_TIME=$(git log -1 --format=%ct 2>/dev/null); '
                'if [ -n "$DB_MTIME" ] && [ -n "$COMMIT_TIME" ] && [ "$DB_MTIME" -lt "$COMMIT_TIME" ]; then '
                'COMMIT=$(git rev-parse --short HEAD 2>/dev/null); '
                r'echo "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":\"dotnet-graph may be stale - db older than latest commit $COMMIT. Rebuild: uvx dotnet-graph build\"}}"; '
                """else echo '{"continue":true,"suppressOutput":true}'; fi; fi"""
            ),
            "statusMessage": "dotnet-graph: checking db freshness...",
            "timeout": 10,
        }
    ],
}


def _hook_installed(event_hooks: list) -> bool:
    """Return True if any hook in the list already has our marker in statusMessage."""
    for group in event_hooks:
        for h in group.get("hooks", []):
            if h.get("statusMessage", "").startswith(_HOOK_MARKER):
                return True
    return False


def _claude_settings_path(root_path: Path, scope: str) -> Path:
    if scope == "user":
        return Path.home() / ".claude" / "settings.json"
    elif scope == "local":
        return root_path / ".claude" / "settings.local.json"
    else:
        return root_path / ".claude" / "settings.json"


def _install_skills(root_path: Path, dry_run: bool) -> list[str]:
    """Copy bundled Claude Code skills into <root>/.claude/skills/."""
    skills_src = Path(__file__).parent / "skills"
    skills_dst = root_path / ".claude" / "skills"
    msgs: list[str] = []

    for skill_file in sorted(skills_src.glob("*.md")):
        dest = skills_dst / skill_file.name
        if dest.exists():
            msgs.append(f"[=] {skill_file.name}: already installed — skipping")
        else:
            if not dry_run:
                skills_dst.mkdir(parents=True, exist_ok=True)
                shutil.copy2(skill_file, dest)
            verb = "would install" if dry_run else "installed"
            msgs.append(f"[+] {skill_file.name}: {verb}")

    return msgs


def _apply_claude_hooks(settings_path: Path, dry_run: bool) -> list[str]:
    config: dict = {}
    if settings_path.exists():
        try:
            config = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    config.setdefault("hooks", {})
    msgs: list[str] = []
    changed = False

    for event, hook_group in [
        ("PreToolUse", _PRETOOLS_HOOK_GROUP),
        ("PostToolUse", _POST_CS_HOOK_GROUP),
        ("SessionStart", _SESSION_START_HOOK_GROUP),
    ]:
        existing = config["hooks"].setdefault(event, [])
        if _hook_installed(existing):
            msgs.append(f"[=] {event}: already configured — skipping")
        else:
            if not dry_run:
                existing.append(hook_group)
                changed = True
            verb = "would add" if dry_run else "added"
            msgs.append(f"[+] {event}: {verb} dotnet-graph hook")

    if changed:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    return msgs


@cli.command("configure-claude")
@click.option("--root", default=None, type=click.Path(file_okay=False),
              help="Solution root (auto-detected from CWD; ignored for --scope user)")
@click.option("--scope", default="project",
              type=click.Choice(["project", "local", "user"]), show_default=True,
              help="project=<root>/.claude/settings.json (committed), "
                   "local=<root>/.claude/settings.local.json (git-ignored), "
                   "user=~/.claude/settings.json (all projects)")
@click.option("--dry-run", is_flag=True, default=False,
              help="Preview what would change without writing any files")
def configure_claude(root: Optional[str], scope: str, dry_run: bool) -> None:
    """Add Claude Code hooks that enforce dotnet-graph best practices.

    \b
    Installs three hooks into .claude/settings.json (or the scoped equivalent):
      PreToolUse   — nudges the AI to use dotnet-graph before falling back to Grep/Glob
      PostToolUse  — reminds the AI to call get_or_create_note after editing a .cs file
      SessionStart — warns when knowledge.db is missing or older than the latest commit

    \b
    Scopes:
      project  → <root>/.claude/settings.json        (committed, shared with the team)
      local    → <root>/.claude/settings.local.json  (git-ignored, personal overrides)
      user     → ~/.claude/settings.json             (applies to all your projects)

    \b
    Examples:
      dotnet-graph configure-claude                   # project scope (default)
      dotnet-graph configure-claude --scope local     # personal, not committed
      dotnet-graph configure-claude --scope user      # all projects globally
      dotnet-graph configure-claude --dry-run         # preview without writing
    """
    root_path = Path(root).resolve() if root else (
        Path.cwd() if scope == "user" else _resolve_root(None)
    )
    settings_path = _claude_settings_path(root_path, scope)

    action = "Would write" if dry_run else "Writing"
    click.echo(f"{action} hooks to: {settings_path}\n")

    msgs = _apply_claude_hooks(settings_path, dry_run)
    for msg in msgs:
        click.echo(f"  {msg}")

    if scope != "user":
        click.echo("")
        skill_msgs = _install_skills(root_path, dry_run)
        for msg in skill_msgs:
            click.echo(f"  {msg}")

    if not dry_run:
        click.echo("\nDone. Restart Claude Code to pick up the new hooks.")
    else:
        click.echo("\n(Dry run — no files written.)")


# ── install ────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--root", default=None, type=click.Path(exists=True, file_okay=False),
              help="Solution root (auto-detected from CWD if omitted)")
@click.option("--db", default=None, type=click.Path(), help="Database path override")
@click.option("--transport", default="stdio", type=click.Choice(["stdio", "http"]),
              show_default=True, help="Transport protocol")
@click.option("--host", default="localhost", show_default=True,
              help="Server host (HTTP transport only)")
@click.option("--port", default=8000, show_default=True, type=int,
              help="Server port (HTTP transport only)")
@click.option("--scope", default="local",
              type=click.Choice(["project", "local", "user"]), show_default=True,
              help="Claude Code MCP scope: local=this project (git-ignored), "
                   "project=shared with team, user=all your projects")
@click.option("--agent", default="claude",
              type=click.Choice(["claude", "cursor", "all"]),
              show_default=True,
              help="AI coding tool to configure: claude, cursor, or all")
@click.option("--skip-build", is_flag=True, default=False,
              help="Skip building the knowledge graph")
@click.option("--skip-claude-md", is_flag=True, default=False,
              help="Skip patching rules files (CLAUDE.md, .cursorrules, AGENTS.md)")
def install(root: Optional[str], db: Optional[str], transport: str,
            host: str, port: int, scope: str, agent: str,
            skip_build: bool, skip_claude_md: bool) -> None:
    """Set up dotnet-graph for AI coding tools in one command.

    \b
    What this does:
      1. Auto-detects the solution root from your current directory
      2. Builds the knowledge graph (incremental if DB already exists)
      3. Registers the MCP server with your AI coding tool
      4. Installs Claude Code skills (.claude/skills/dotnet-*.md)
      5. Patches the agent rules file with dotnet-graph tool instructions

    \b
    Examples:
      dotnet-graph install                   # Claude Code (default)
      dotnet-graph install --agent cursor    # Cursor
      dotnet-graph install --agent all       # Claude Code + Cursor
      dotnet-graph install --scope user      # register globally in Claude Code
      dotnet-graph install --skip-build      # config only, skip the graph build
    """
    root_path = _resolve_root(root)
    db_path = _db_for(root_path, db)

    click.echo(f"Setting up dotnet-graph for {root_path} (agent: {agent})\n")

    # Step 1: Build
    if not skip_build:
        _do_build(root_path, db_path)
        click.echo("")

    # Step 2: MCP registration
    if agent in ("claude", "all"):
        claude = shutil.which("claude") if transport == "stdio" else None
        if claude:
            _try_claude_mcp_add(claude, root_path, db_path, scope)
        else:
            click.echo("[ ] Claude Code CLI not found — skipping claude mcp add")
        _write_mcp_json(root_path, db_path, transport, host, port)

    if agent in ("cursor", "all"):
        _write_cursor_mcp_json(root_path, db_path, transport, host, port)

    # Step 3: Skills
    if agent in ("claude", "all"):
        click.echo("")
        skill_msgs = _install_skills(root_path, dry_run=False)
        for msg in skill_msgs:
            click.echo(f"       {msg}")

    # Step 4: Rules files
    if not skip_claude_md:
        if agent in ("claude", "all"):
            _patch_rules_file(root_path / "CLAUDE.md")
        if agent in ("cursor", "all"):
            _patch_rules_file(root_path / ".cursorrules")
            _patch_rules_file(root_path / "AGENTS.md")

    click.echo("\nDone. Restart your AI coding tool to pick up the new config.")


def _do_build(root_path: Path, db_path: Path) -> None:
    from dotnet_graph.builder import build as _build

    incremental = db_path.exists()
    mode = "incremental" if incremental else "full"
    click.echo(f"[1/3] Building knowledge graph [{mode}] ...")
    _build(root_path, db_path, verbose=True, incremental=incremental)


def _try_claude_mcp_add(claude: str, root_path: Path, db_path: Path, scope: str) -> bool:
    """Run `claude mcp add` and return True on success."""
    cmd = [
        claude, "mcp", "add",
        "-s", scope,
        "dotnet-graph",
        "--",
        "uvx", "dotnet-graph", "serve", "--root", str(root_path), "--db", str(db_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        click.echo(f"[2/3] Registered with Claude Code (scope: {scope}, db: {db_path})")
        return True
    else:
        click.echo(
            f"[2/3] claude mcp add failed ({result.stderr.strip() or 'unknown error'}) "
            "— falling back to .mcp.json only",
            err=True,
        )
        return False


def _write_mcp_json(root_path: Path, db_path: Path, transport: str, host: str, port: int) -> None:
    import json

    mcp_file = root_path / ".mcp.json"
    config: dict = {}
    if mcp_file.exists():
        try:
            config = json.loads(mcp_file.read_text(encoding="utf-8"))
        except Exception:
            config = {}

    config.setdefault("mcpServers", {})

    if transport == "http":
        config["mcpServers"]["dotnet-graph"] = {
            "url": f"http://{host}:{port}/sse",
            "type": "sse",
        }
        click.echo(f"[3/3] Wrote {mcp_file} (HTTP/SSE → {host}:{port})")
        click.echo(f"      Start the server: dotnet-graph serve --transport http --port {port}")
    else:
        config["mcpServers"]["dotnet-graph"] = {
            "command": "uvx",
            "args": ["dotnet-graph", "serve", "--root", str(root_path), "--db", str(db_path)],
            "type": "stdio",
        }
        click.echo(f"[3/3] Wrote {mcp_file} (db: {db_path})")

    mcp_file.write_text(json.dumps(config, indent=2), encoding="utf-8")


_CLAUDE_MD_MARKER = "<!-- dotnet-graph -->"

_CLAUDE_MD_SECTION = """\
<!-- dotnet-graph -->
## Code Knowledge Graph

A Roslyn-powered knowledge graph lives at `.dotnet-graph/knowledge.db`, built by the `dotnet-graph` tool.

**IMPORTANT: Always use the `dotnet-graph` MCP tools first** before falling back to `Grep`/`Glob` when answering questions about:
- Where a class/interface/service is defined
- What methods or properties a type has
- What implements or inherits from a type
- Which module owns a piece of functionality
- Cross-module dependencies
- How a service is registered (DI lifetime)
- Who injects a service (constructor injection)
- What a method calls, or what calls a given method

The `dotnet-graph` MCP server is configured in `.mcp.json` (or `.cursor/mcp.json` for Cursor). If unavailable, fall back to `Grep` but note it to the user.

### Tool selection

| Task | Tool |
|------|------|
| Find a type by name | `find_type` |
| All members, fields, constructor params | `get_type_members` |
| Who implements an interface | `find_implementors` |
| Who injects a service | `find_injectors` |
| What a method calls | `get_method_calls` |
| Who calls a method | `find_callers` |
| DI registrations | `get_di_registrations` |
| HTTP endpoints | `get_endpoints` |
| ViewModel feature index | `get_features` |
| Keyword search across types/methods | `search` |
| Graph stats / health check | `get_stats` |
| Generate Obsidian vault | `build_obsidian_vault` |
| Get/create enriched knowledge note | `get_or_create_note` |
| Write the ## Notes section of a note | `update_note` |
| Refresh note structure after graph rebuild | `sync_note_structure` |
| Rebuild the graph | `build_graph` |

### Workflow

1. `find_type` — locate a class or interface
2. `get_type_members` — full member details (methods, properties, fields, constructor params)
3. `find_injectors` — who uses a service
4. `get_method_calls` — trace execution flow within a method
5. `find_callers` — all callers of a method across the codebase
6. Fall back to `Grep` only if the graph doesn't have what you need.

### Knowledge Notes

Enriched notes live in `.dotnet-graph/notes/<Domain>/<TypeName>.md` and persist across sessions.

**When to use `get_or_create_note`:**
- After reading a source file — record the type's purpose and key behaviours
- After making a change — add a work log entry with the ticket and what changed
- When you discover something non-obvious — gotchas, invariants, business rules

**Workflow:**
1. Call `get_or_create_note("TypeName")` — creates the note if it doesn't exist yet
2. Call `update_note("TypeName", "<notes content>")` to write purpose, behaviours, and work log
3. After running `build_graph`, call `sync_note_structure("TypeName")` to refresh Methods/Properties/Injections while keeping your notes intact
4. Notes are never overwritten by `build_graph` or `build_obsidian_vault`

**Note format:**
```
## Notes
### Purpose
What this type does in business terms.

### Key Behaviours
- Notable patterns, invariants, gotchas

### Work Log
- **SMA-XXXX** (YYYY-MM-DD): what changed and why
```
"""


def _write_cursor_mcp_json(root_path: Path, db_path: Path, transport: str, host: str, port: int) -> None:
    import json

    cursor_dir = root_path / ".cursor"
    cursor_dir.mkdir(exist_ok=True)
    mcp_file = cursor_dir / "mcp.json"

    config: dict = {}
    if mcp_file.exists():
        try:
            config = json.loads(mcp_file.read_text(encoding="utf-8"))
        except Exception:
            config = {}

    config.setdefault("mcpServers", {})

    if transport == "http":
        config["mcpServers"]["dotnet-graph"] = {
            "url": f"http://{host}:{port}/sse",
            "type": "sse",
        }
        click.echo(f"[ ] Wrote {mcp_file} (HTTP/SSE → {host}:{port})")
    else:
        config["mcpServers"]["dotnet-graph"] = {
            "command": "uvx",
            "args": ["dotnet-graph", "serve", "--root", str(root_path), "--db", str(db_path)],
        }
        click.echo(f"[ ] Wrote {mcp_file} (db: {db_path})")

    mcp_file.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _patch_rules_file(path: Path) -> None:
    name = path.name
    if path.exists():
        content = path.read_text(encoding="utf-8")
        if _CLAUDE_MD_MARKER in content:
            click.echo(f"[ ] {name} already contains dotnet-graph instructions — skipping")
            return
        path.write_text(content.rstrip("\n") + "\n\n" + _CLAUDE_MD_SECTION, encoding="utf-8")
        click.echo(f"[ ] Appended dotnet-graph instructions to {path}")
    else:
        path.write_text(_CLAUDE_MD_SECTION, encoding="utf-8")
        click.echo(f"[ ] Created {path} with dotnet-graph instructions")


# ── update ─────────────────────────────────────────────────────────────────────

@cli.command()
def update() -> None:
    """Upgrade dotnet-graph to the latest version on PyPI.

    Detects whether you installed via uvx or pip and runs the right command.
    """
    from dotnet_graph import __version__

    # Detect install method: if the executable lives inside a uv tool dir, use uvx.
    exe = Path(sys.executable)
    is_uvx = "uv" in str(exe) or shutil.which("uvx") is not None and (
        ".local/share/uv" in str(exe) or "uv/tools" in str(exe)
    )

    if is_uvx and shutil.which("uvx"):
        click.echo(f"Current version: {__version__}")
        click.echo("Upgrading via uvx ...")
        result = subprocess.run(["uv", "tool", "upgrade", "dotnet-graph"])
        if result.returncode != 0:
            raise SystemExit(result.returncode)
    else:
        click.echo(f"Current version: {__version__}")
        click.echo("Upgrading via pip ...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "dotnet-graph"]
        )
        if result.returncode != 0:
            raise SystemExit(result.returncode)

    click.echo("Done. Run `dotnet-graph --version` to confirm.")
