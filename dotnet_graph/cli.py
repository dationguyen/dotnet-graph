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
def build(root: str, db: Optional[str]) -> None:
    """Build (or rebuild) the knowledge graph."""
    from dotnet_graph.builder import build as _build

    root_path = Path(root).resolve()
    db_path = Path(db).resolve() if db else root_path / ".dotnet-graph" / "knowledge.db"
    click.echo(f"Building graph for {root_path} → {db_path}")
    _build(root_path, db_path, verbose=True)


@cli.command()
@click.option("--root", default=None, type=click.Path(exists=True, file_okay=False), help="Solution root (infers --db)")
@click.option("--db", default=None, type=click.Path(), help="Database path")
def serve(root: Optional[str], db: Optional[str]) -> None:
    """Start the MCP server (stdio transport)."""
    from dotnet_graph.main import serve as _serve
    _serve(root=root, db=db)


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
@click.option("--root", default=".", type=click.Path(exists=True, file_okay=False), help="Project root to install into")
@click.option("--db", default=None, type=click.Path(), help="Database path override")
def install(root: str, db: Optional[str]) -> None:
    """Add dotnet-graph to .mcp.json in the project root."""
    import json

    root_path = Path(root).resolve()
    mcp_file = root_path / ".mcp.json"

    config = {}
    if mcp_file.exists():
        with open(mcp_file) as f:
            config = json.load(f)

    config.setdefault("mcpServers", {})

    args = ["dotnet-graph", "serve", "--root", str(root_path)]
    if db:
        args += ["--db", db]

    config["mcpServers"]["dotnet-graph"] = {
        "command": "uvx",
        "args": args,
        "type": "stdio",
    }

    with open(mcp_file, "w") as f:
        json.dump(config, f, indent=2)

    click.echo(f"Installed dotnet-graph MCP server in {mcp_file}")
    click.echo("Restart your AI coding tool to pick up the new config.")
