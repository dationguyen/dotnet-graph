"""FastMCP server entry point.

Run as: dotnet-graph serve [--root <path>] [--db <path>]
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

from .db import open_db
from .tools import register_query_tools, register_build_tools

_db_path: Path | None = None


def _get_db() -> sqlite3.Connection:
    if _db_path is None or not _db_path.exists():
        raise RuntimeError(
            "No knowledge graph found. Run `dotnet-graph build --root <path>` first, "
            "or start the server with `--db <path>`."
        )
    return open_db(_db_path)


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


def serve(root: Optional[str] = None, db: Optional[str] = None) -> None:
    global _db_path

    if db:
        _db_path = Path(db).resolve()
    elif root:
        _db_path = Path(root).resolve() / ".dotnet-graph" / "knowledge.db"

    mcp.run()
