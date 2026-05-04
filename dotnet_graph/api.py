"""FastAPI REST wrapper — exposes the knowledge graph to non-MCP agents.

Start alongside the MCP server:
    dotnet-graph serve --transport http --port 8000 --api-port 8001

Or standalone:
    dotnet-graph api --root /path/to/solution --port 8001
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query

_db_path: Path | None = None
_conn: sqlite3.Connection | None = None
_conn_mtime: float = 0.0


def _set_db(path: Path) -> None:
    global _db_path
    _db_path = path


def _get_db() -> sqlite3.Connection:
    global _conn, _conn_mtime
    if _db_path is None or not _db_path.exists():
        raise HTTPException(
            status_code=503,
            detail="Knowledge graph not built. Run: dotnet-graph build --root <path>",
        )
    mtime = _db_path.stat().st_mtime
    if _conn is None or mtime != _conn_mtime:
        if _conn is not None:
            _conn.close()
        conn = sqlite3.connect(str(_db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _conn = conn
        _conn_mtime = mtime
    return _conn


router = APIRouter(prefix="/query", tags=["query"])


@router.get("/types", summary="Find types by name")
def find_types(
    name: str = Query(..., description="Type name to search (partial match by default)"),
    exact: bool = Query(False, description="Use exact match instead of LIKE"),
):
    """Find classes, interfaces, enums, records, and structs by name."""
    conn = _get_db()
    pat = name if exact else f"%{name}%"
    rows = conn.execute("""
        SELECT t.name, t.full_name, t.kind, t.is_abstract, t.is_partial, t.line,
               f.path, p.name AS project, p.domain
        FROM types t
        JOIN files f ON t.file_id = f.id
        JOIN projects p ON t.project_id = p.id
        WHERE t.name LIKE ?
        ORDER BY t.name
        LIMIT 30
    """, (pat,)).fetchall()
    return [dict(r) for r in rows]


@router.get("/types/{type_name}/members", summary="Get all members of a type")
def get_type_members(type_name: str):
    """Return methods, properties, fields, and constructor parameters for a type."""
    conn = _get_db()
    t = conn.execute(
        "SELECT id, full_name, kind, line FROM types WHERE name=? OR full_name=? LIMIT 1",
        (type_name, type_name),
    ).fetchone()
    if not t:
        raise HTTPException(status_code=404, detail=f"Type '{type_name}' not found")

    methods = conn.execute(
        "SELECT name, return_type, parameters, visibility, is_async, is_static, is_override, line "
        "FROM methods WHERE type_id=? ORDER BY line",
        (t["id"],),
    ).fetchall()
    props = conn.execute(
        "SELECT name, type_name, visibility, is_static, line "
        "FROM properties WHERE type_id=? ORDER BY line",
        (t["id"],),
    ).fetchall()
    fields = conn.execute(
        "SELECT name, type_name, visibility, is_readonly, is_static, line "
        "FROM field_declarations WHERE type_id=? ORDER BY line",
        (t["id"],),
    ).fetchall()
    ctors = conn.execute(
        "SELECT DISTINCT param_type, param_name, line "
        "FROM constructor_injections WHERE type_id=? ORDER BY line",
        (t["id"],),
    ).fetchall()

    return {
        "type": dict(t),
        "constructor_parameters": [dict(r) for r in ctors],
        "methods": [dict(r) for r in methods],
        "properties": [dict(r) for r in props],
        "fields": [dict(r) for r in fields],
    }


@router.get("/types/{type_name}/implementors", summary="Find implementors and subclasses")
def find_implementors(type_name: str):
    """Find all types that implement or inherit from the given type."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT r.from_type, r.to_type, r.kind, f.path, t.line, p.name AS project
        FROM relationships r
        JOIN types t ON r.from_type = t.full_name
        JOIN files f ON t.file_id = f.id
        JOIN projects p ON t.project_id = p.id
        WHERE r.to_type LIKE ?
        ORDER BY r.from_type
    """, (f"%{type_name}%",)).fetchall()
    return [dict(r) for r in rows]


@router.get("/types/{type_name}/injectors", summary="Find classes that inject this type")
def find_injectors(type_name: str):
    """Find all classes that constructor-inject the given interface or type."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT t.name, t.full_name, ci.param_name, ci.param_type, f.path, ci.line, p.name AS project
        FROM constructor_injections ci
        JOIN types t ON ci.type_id = t.id
        JOIN files f ON ci.file_id = f.id
        JOIN projects p ON ci.project_id = p.id
        WHERE ci.param_type LIKE ?
        ORDER BY t.name
    """, (f"%{type_name}%",)).fetchall()
    return [dict(r) for r in rows]


@router.get("/method-calls", summary="Get calls made within a method")
def get_method_calls(
    type_name: str = Query(..., description="The containing type name"),
    method: str = Query(..., description="The method name"),
):
    """List all service/method calls made inside a specific method."""
    conn = _get_db()
    t = conn.execute(
        "SELECT id FROM types WHERE name=? OR full_name=? LIMIT 1", (type_name, type_name)
    ).fetchone()
    if not t:
        raise HTTPException(status_code=404, detail=f"Type '{type_name}' not found")
    rows = conn.execute(
        "SELECT callee_expr, callee_method, line FROM method_calls "
        "WHERE caller_type_id=? AND caller_method=? ORDER BY line",
        (t["id"], method),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/callers", summary="Find all callers of a method")
def find_callers(method: str = Query(..., description="Method name to find callers for")):
    """Find all methods across the codebase that call the given method name."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT t.name AS caller_type, mc.caller_method, mc.callee_expr, f.path, mc.line
        FROM method_calls mc
        JOIN types t ON mc.caller_type_id = t.id
        JOIN files f ON mc.file_id = f.id
        WHERE mc.callee_method = ?
        ORDER BY t.name, mc.caller_method
        LIMIT 50
    """, (method,)).fetchall()
    return [dict(r) for r in rows]


@router.get("/di-registrations", summary="List DI registrations")
def get_di_registrations(
    name: str = Query("", description="Filter by interface or implementation name (empty = all)"),
):
    """Return DI registrations optionally filtered by type name."""
    conn = _get_db()
    pat = f"%{name}%" if name else "%"
    rows = conn.execute("""
        SELECT r.interface_type, r.impl_type, r.lifetime, f.path, r.line, p.name AS project
        FROM registrations r
        JOIN files f ON r.file_id = f.id
        JOIN projects p ON r.project_id = p.id
        WHERE r.interface_type LIKE ? OR r.impl_type LIKE ?
        ORDER BY r.interface_type
        LIMIT 100
    """, (pat, pat)).fetchall()
    return [dict(r) for r in rows]


@router.get("/endpoints", summary="List all HTTP endpoints")
def get_endpoints():
    """Return all HTTP endpoints (routes) found in the codebase."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT e.http_method, e.url_pattern, e.type_name, f.path, e.line, p.name AS project
        FROM endpoints e
        JOIN files f ON e.file_id = f.id
        JOIN projects p ON e.project_id = p.id
        ORDER BY e.http_method, e.url_pattern
    """).fetchall()
    return [dict(r) for r in rows]


@router.get("/features", summary="List ViewModel-centric features")
def get_features():
    """Return the feature index built from ViewModel classes."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT name, domain, viewmodel, service, project FROM features ORDER BY domain, name"
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/search", summary="Keyword search across the graph")
def search(q: str = Query(..., description="Keyword to search for")):
    """Search types, methods, and properties by keyword."""
    conn = _get_db()
    pat = f"%{q}%"
    types = conn.execute("""
        SELECT t.name, t.kind, t.full_name, f.path, t.line
        FROM types t JOIN files f ON t.file_id = f.id
        WHERE t.name LIKE ? OR t.full_name LIKE ?
        LIMIT 10
    """, (pat, pat)).fetchall()
    methods = conn.execute("""
        SELECT m.name, t.name AS type_name, f.path, m.line, m.return_type
        FROM methods m JOIN types t ON m.type_id = t.id JOIN files f ON m.file_id = f.id
        WHERE m.name LIKE ?
        LIMIT 10
    """, (pat,)).fetchall()
    props = conn.execute("""
        SELECT p.name, t.name AS type_name, f.path, p.line, p.type_name AS prop_type
        FROM properties p JOIN types t ON p.type_id = t.id JOIN files f ON p.file_id = f.id
        WHERE p.name LIKE ?
        LIMIT 10
    """, (pat,)).fetchall()
    return {
        "types": [dict(r) for r in types],
        "methods": [dict(r) for r in methods],
        "properties": [dict(r) for r in props],
    }


@router.get("/stats", summary="Graph statistics and build info")
def get_stats():
    """Return row counts for all tables and last build metadata."""
    conn = _get_db()
    tables = [
        "projects", "files", "types", "methods", "properties",
        "relationships", "registrations", "endpoints", "config_keys",
        "features", "constructor_injections", "field_declarations", "method_calls",
    ]
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    try:
        meta = {row[0]: row[1] for row in conn.execute("SELECT key, value FROM build_meta")}
    except Exception:
        meta = {}
    return {"build": meta, "counts": counts}


def create_app(db_path: Path) -> FastAPI:
    """Create and return the FastAPI application bound to the given database."""
    _set_db(db_path)
    app = FastAPI(
        title="dotnet-graph",
        description=(
            "REST API for querying the Roslyn-powered .NET/C# knowledge graph. "
            "Provides semantic search over types, methods, DI registrations, "
            "HTTP endpoints, constructor injections, and method call graphs. "
            "See `/docs` for the interactive OpenAPI explorer."
        ),
        version="0.1.0",
    )
    app.include_router(router)
    return app
