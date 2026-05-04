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


def _start_api_server(db_path: Path, host: str, port: int) -> None:
    import sys
    import threading
    import uvicorn
    from dotnet_graph.api import create_app

    api_app = create_app(db_path)
    config = uvicorn.Config(api_app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="rest-api")
    thread.start()
    print(f"REST API started on http://{host}:{port}/docs", file=sys.stderr)


def serve(
    root: Optional[str] = None,
    db: Optional[str] = None,
    transport: str = "stdio",
    host: str = "0.0.0.0",
    port: int = 8000,
    api_port: Optional[int] = None,
) -> None:
    import sys
    global _db_path

    if db:
        _db_path = Path(db).resolve()
    elif root:
        _db_path = Path(root).resolve() / ".claude" / ".dotnet-graph" / "knowledge.db"

    # Lazy build: if no DB exists yet, run a full build before starting.
    if _db_path is not None and not _db_path.exists():
        from dotnet_graph.builder import build as _build
        # DB lives at <root>/.claude/.dotnet-graph/knowledge.db → go up 3 levels
        root_path = Path(root).resolve() if root else _db_path.parent.parent.parent
        print(f"No knowledge graph found — building now for {root_path} ...", file=sys.stderr)
        _build(root_path, _db_path, verbose=True, incremental=False)

    db_path_str = str(_db_path) if _db_path else ""
    registry.register(root, db_path_str, transport, host, port)
    atexit.register(registry.deregister, db_path_str)

    if api_port is not None and _db_path is not None:
        _start_api_server(_db_path, host, api_port)

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        print(f"MCP server started on http://{host}:{port}/sse", file=sys.stderr)
        mcp.run(transport="sse", host=host, port=port)
