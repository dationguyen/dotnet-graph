"""CLI entry point for dotnet-graph."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click


@click.group()
@click.version_option()
def cli() -> None:
    """Roslyn-powered knowledge graph for .NET/C# codebases."""


@cli.command()
@click.option("--root", required=True, type=click.Path(exists=True, file_okay=False), help="Solution root directory")
@click.option("--db", default=None, type=click.Path(), help="Database path (default: <root>/.dotnet-graph/knowledge.db)")
@click.option("--full", "force_full", is_flag=True, default=False, help="Force a full rebuild instead of incremental")
def build(root: str, db: Optional[str], force_full: bool) -> None:
    """Build (or rebuild) the knowledge graph.

    By default runs an incremental build — only re-analyzes files whose
    content has changed since the last build. Use --full to force a complete
    rebuild from scratch.
    """
    from dotnet_graph.builder import build as _build

    root_path = Path(root).resolve()
    db_path = Path(db).resolve() if db else root_path / ".dotnet-graph" / "knowledge.db"
    mode = "full" if force_full else "incremental"
    click.echo(f"Building graph [{mode}] for {root_path} → {db_path}")
    _build(root_path, db_path, verbose=True, incremental=not force_full)


@cli.command()
@click.option("--root", default=None, type=click.Path(exists=True, file_okay=False), help="Solution root (infers --db)")
@click.option("--db", default=None, type=click.Path(), help="Database path")
@click.option("--transport", default="stdio", type=click.Choice(["stdio", "http"]), show_default=True, help="Transport protocol")
@click.option("--host", default="0.0.0.0", show_default=True, help="Bind host (HTTP transport only)")
@click.option("--port", default=8000, show_default=True, type=int, help="Bind port (HTTP transport only)")
def serve(root: Optional[str], db: Optional[str], transport: str, host: str, port: int) -> None:
    """Start the MCP server.

    Use --transport stdio (default) for Claude Code / local agents that spawn
    the process directly. Use --transport http to expose an SSE endpoint that
    remote agents can connect to over the network.
    """
    from dotnet_graph.main import serve as _serve
    _serve(root=root, db=db, transport=transport, host=host, port=port)


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


@cli.command()
@click.option("--root", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--db", default=None, type=click.Path())
def status(root: str, db: Optional[str]) -> None:
    """Show graph statistics."""
    from dotnet_graph.db import open_db, count

    root_path = Path(root).resolve()
    db_path = Path(db).resolve() if db else root_path / ".dotnet-graph" / "knowledge.db"

    if not db_path.exists():
        click.echo(f"No graph found at {db_path}. Run `dotnet-graph build --root {root}` first.")
        return

    conn = open_db(db_path)
    tables = [
        "projects", "files", "types", "methods", "properties",
        "relationships", "registrations", "endpoints", "config_keys",
        "features", "constructor_injections", "field_declarations", "method_calls",
    ]
    click.echo(f"\nGraph: {db_path}  ({db_path.stat().st_size / 1024 / 1024:.1f} MB)\n")
    for t in tables:
        click.echo(f"  {t:<22}: {count(conn, t):>6,}")


@cli.command()
@click.option("--root", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--db", default=None, type=click.Path(), help="Database path (default: <root>/.dotnet-graph/knowledge.db)")
@click.option("--vault", default=None, type=click.Path(), help="Output vault directory (default: <root>/.dotnet-graph/obsidian)")
def obsidian(root: str, db: Optional[str], vault: Optional[str]) -> None:
    """Generate an Obsidian vault from the knowledge graph."""
    from dotnet_graph.obsidian import build_vault

    root_path = Path(root).resolve()
    db_path = Path(db).resolve() if db else root_path / ".dotnet-graph" / "knowledge.db"
    vault_path = Path(vault).resolve() if vault else root_path / ".dotnet-graph" / "obsidian"

    if not db_path.exists():
        click.echo(f"No graph found at {db_path}. Run `dotnet-graph build --root {root}` first.")
        return

    click.echo(f"Generating Obsidian vault → {vault_path}")
    n = build_vault(db_path, vault_path, verbose=True)
    click.echo(f"Done: {n} notes written to {vault_path}")
    click.echo("Open that folder in Obsidian and switch to Graph View.")


@cli.command()
@click.option("--root", default=".", type=click.Path(exists=True, file_okay=False), help="Project root to install into")
@click.option("--db", default=None, type=click.Path(), help="Database path override")
@click.option("--transport", default="stdio", type=click.Choice(["stdio", "http"]), show_default=True, help="Transport used by the running server")
@click.option("--host", default="localhost", show_default=True, help="Server host (HTTP transport only)")
@click.option("--port", default=8000, show_default=True, type=int, help="Server port (HTTP transport only)")
def install(root: str, db: Optional[str], transport: str, host: str, port: int) -> None:
    """Add dotnet-graph to .mcp.json in the project root.

    For stdio (default): registers a subprocess entry that your AI tool spawns.
    For http: registers the SSE URL of an already-running HTTP server instance.
    """
    import json

    root_path = Path(root).resolve()
    mcp_file = root_path / ".mcp.json"

    config = {}
    if mcp_file.exists():
        with open(mcp_file) as f:
            config = json.load(f)

    config.setdefault("mcpServers", {})

    if transport == "http":
        config["mcpServers"]["dotnet-graph"] = {
            "url": f"http://{host}:{port}/sse",
            "type": "sse",
        }
        click.echo(f"Installed dotnet-graph (HTTP/SSE) in {mcp_file}")
        click.echo(f"Make sure the server is running: dotnet-graph serve --root {root_path} --transport http --port {port}")
    else:
        args = ["dotnet-graph", "serve", "--root", str(root_path)]
        if db:
            args += ["--db", db]
        config["mcpServers"]["dotnet-graph"] = {
            "command": "uvx",
            "args": args,
            "type": "stdio",
        }
        click.echo(f"Installed dotnet-graph (stdio) in {mcp_file}")

    with open(mcp_file, "w") as f:
        json.dump(config, f, indent=2)

    click.echo("Restart your AI coding tool to pick up the new config.")
