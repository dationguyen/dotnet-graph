"""FastMCP server entry point.

Run as: dotnet-graph serve [--root <path>] [--db <path>]
"""

from __future__ import annotations

import atexit
import sqlite3
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

from .db import open_db
from .tools import register_query_tools, register_build_tools
from . import registry

_db_path: Path | None = None
_conn: sqlite3.Connection | None = None
_conn_mtime: float = 0.0


def _get_db() -> sqlite3.Connection:
    global _conn, _conn_mtime
    if _db_path is None or not _db_path.exists():
        if _conn is not None:
            _conn.close()
            _conn = None
        raise RuntimeError(
            "No knowledge graph found. Run `dotnet-graph build --root <path>` first, "
            "or start the server with `--db <path>`."
        )
    current_mtime = _db_path.stat().st_mtime
    if _conn is None or current_mtime != _conn_mtime:
        if _conn is not None:
            _conn.close()
        _conn = open_db(_db_path)
        _conn_mtime = current_mtime
    return _conn


def _get_db_path() -> Path | None:
    return _db_path


mcp = FastMCP(
    "dotnet-graph",
    instructions=(
        "Roslyn-powered knowledge graph for .NET/C# codebases. "
        "Provides semantic search over types, methods, DI registrations, "
        "HTTP endpoints, constructor injections, and method call graphs. "
        "Use `find_type` to locate a class or interface, `get_type_members` for full member details, "
        "`find_injectors` to see who uses a service, and `get_method_calls` to trace execution flow."
    ),
)

register_query_tools(mcp, _get_db)
register_build_tools(mcp, _get_db_path)


def serve(
    root: Optional[str] = None,
    db: Optional[str] = None,
    transport: str = "stdio",
    host: str = "0.0.0.0",
    port: int = 8000,
) -> None:
    global _db_path

    if db:
        _db_path = Path(db).resolve()
    elif root:
        _db_path = Path(root).resolve() / ".dotnet-graph" / "knowledge.db"

    db_path_str = str(_db_path) if _db_path else ""
    registry.register(root, db_path_str, transport, host, port)
    atexit.register(registry.deregister, db_path_str)

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        import sys
        print(f"Starting MCP server on http://{host}:{port}/sse", file=sys.stderr)
        mcp.run(transport="sse", host=host, port=port)
