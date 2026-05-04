"""CLI entry point for dotnet-graph."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

import click


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
    return Path(db).resolve() if db else root_path / ".claude" / ".dotnet-graph" / "knowledge.db"


# ── CLI group ──────────────────────────────────────────────────────────────────

@click.group()
@click.version_option()
def cli() -> None:
    """Roslyn-powered knowledge graph for .NET/C# codebases."""


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
@click.option("--scope", default="project",
              type=click.Choice(["project", "local", "user"]), show_default=True,
              help="Claude Code MCP scope: project=.claude/settings.json, "
                   "local=git-ignored, user=~/.claude.json")
@click.option("--skip-build", is_flag=True, default=False,
              help="Skip building the knowledge graph")
def install(root: Optional[str], db: Optional[str], transport: str,
            host: str, port: int, scope: str, skip_build: bool) -> None:
    """Set up dotnet-graph for AI coding tools in one command.

    \b
    What this does:
      1. Auto-detects the solution root from your current directory
      2. Builds the knowledge graph (incremental if DB already exists)
      3. Registers with Claude Code via `claude mcp add` (if available)
      4. Writes .mcp.json as a fallback for other MCP-compatible tools

    \b
    Examples:
      dotnet-graph install                  # run from anywhere in your .NET repo
      dotnet-graph install --scope user     # register globally in Claude Code
      dotnet-graph install --skip-build     # config only, skip the graph build
    """
    root_path = _resolve_root(root)
    db_path = _db_for(root_path, db)

    click.echo(f"Setting up dotnet-graph for {root_path}\n")

    # Step 1: Build
    if not skip_build:
        _do_build(root_path, db_path)
        click.echo("")

    # Step 2: Claude Code native registration
    if transport == "stdio":
        _try_claude_mcp_add(root_path, scope)

    # Step 3: .mcp.json fallback
    _write_mcp_json(root_path, transport, host, port)

    click.echo("\nDone. Restart your AI coding tool to pick up the new config.")


def _do_build(root_path: Path, db_path: Path) -> None:
    from dotnet_graph.builder import build as _build

    incremental = db_path.exists()
    mode = "incremental" if incremental else "full"
    click.echo(f"[1/3] Building knowledge graph [{mode}] ...")
    _build(root_path, db_path, verbose=True, incremental=incremental)


def _try_claude_mcp_add(root_path: Path, scope: str) -> bool:
    """Run `claude mcp add` and return True on success."""
    claude = shutil.which("claude")
    if not claude:
        click.echo("[2/3] Claude Code CLI not found — skipping claude mcp add")
        return False

    cmd = [
        claude, "mcp", "add", "dotnet-graph",
        "-s", scope,
        "--",
        "uvx", "dotnet-graph", "serve", "--root", str(root_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        click.echo(f"[2/3] Registered with Claude Code (scope: {scope})")
        return True
    else:
        click.echo(
            f"[2/3] claude mcp add failed ({result.stderr.strip() or 'unknown error'}) "
            "— falling back to .mcp.json only",
            err=True,
        )
        return False


def _write_mcp_json(root_path: Path, transport: str, host: str, port: int) -> None:
    import json

    mcp_file = root_path / ".mcp.json"
    config: dict = {}
    if mcp_file.exists():
        try:
            config = json.loads(mcp_file.read_text())
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
            "args": ["dotnet-graph", "serve", "--root", str(root_path)],
            "type": "stdio",
        }
        click.echo(f"[3/3] Wrote {mcp_file}")

    mcp_file.write_text(json.dumps(config, indent=2))
