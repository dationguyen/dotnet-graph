"""Shared keyword search over the knowledge graph.

One implementation behind both the MCP `search` tool and the REST `/query/search`
endpoint. Uses the FTS5 trigram index (`search_fts`, built by builder.py) when it
exists and the query is long enough for trigrams; otherwise falls back to a plain
LIKE scan. Both paths return the same normalized shape:

    {"types":      [{name, kind, full_name, path, line}, ...],
     "methods":    [{name, type_name, return_type, path, line}, ...],
     "properties": [{name, type_name, prop_type, path, line}, ...]}
"""

from __future__ import annotations

import sqlite3

# Trigram queries shorter than 3 chars can't hit the index — use LIKE for those.
_MIN_TRIGRAM = 3


def _fts_ready(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='search_fts'"
    ).fetchone() is not None


def _as_phrase(query: str) -> str:
    """Quote the query as a single FTS5 phrase so trigram does a literal substring
    match and the user's input can't be read as FTS query syntax."""
    return '"' + query.replace('"', '""') + '"'


def _search_fts(conn: sqlite3.Connection, query: str, limit: int) -> dict:
    match = _as_phrase(query)

    def run(entity: str):
        return conn.execute(
            "SELECT name, full_name, kind, container, path, line "
            "FROM search_fts WHERE entity = ? AND search_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (entity, match, limit),
        ).fetchall()

    return {
        "types": [
            {"name": r["name"], "kind": r["kind"], "full_name": r["full_name"],
             "path": r["path"], "line": r["line"]}
            for r in run("type")
        ],
        "methods": [
            {"name": r["name"], "type_name": r["container"], "return_type": r["kind"],
             "path": r["path"], "line": r["line"]}
            for r in run("method")
        ],
        "properties": [
            {"name": r["name"], "type_name": r["container"], "prop_type": r["kind"],
             "path": r["path"], "line": r["line"]}
            for r in run("property")
        ],
    }


def _search_like(conn: sqlite3.Connection, query: str, limit: int) -> dict:
    pat = f"%{query}%"
    types = conn.execute(
        "SELECT t.name, t.kind, t.full_name, f.path, t.line "
        "FROM types t JOIN files f ON t.file_id = f.id "
        "WHERE t.name LIKE ? OR t.full_name LIKE ? LIMIT ?",
        (pat, pat, limit),
    ).fetchall()
    methods = conn.execute(
        "SELECT m.name, t.name AS type_name, m.return_type, f.path, m.line "
        "FROM methods m JOIN types t ON m.type_id = t.id JOIN files f ON m.file_id = f.id "
        "WHERE m.name LIKE ? LIMIT ?",
        (pat, limit),
    ).fetchall()
    props = conn.execute(
        "SELECT p.name, t.name AS type_name, p.type_name AS prop_type, f.path, p.line "
        "FROM properties p JOIN types t ON p.type_id = t.id JOIN files f ON p.file_id = f.id "
        "WHERE p.name LIKE ? LIMIT ?",
        (pat, limit),
    ).fetchall()
    return {
        "types": [
            {"name": r["name"], "kind": r["kind"], "full_name": r["full_name"],
             "path": r["path"], "line": r["line"]}
            for r in types
        ],
        "methods": [
            {"name": r["name"], "type_name": r["type_name"], "return_type": r["return_type"],
             "path": r["path"], "line": r["line"]}
            for r in methods
        ],
        "properties": [
            {"name": r["name"], "type_name": r["type_name"], "prop_type": r["prop_type"],
             "path": r["path"], "line": r["line"]}
            for r in props
        ],
    }


def search_graph(conn: sqlite3.Connection, query: str, limit: int = 10) -> dict:
    """Search types, methods, and properties by keyword. FTS5 trigram when
    available and the query is long enough; otherwise a LIKE substring scan."""
    q = query.strip()
    if q and len(q) >= _MIN_TRIGRAM and _fts_ready(conn):
        try:
            return _search_fts(conn, q, limit)
        except sqlite3.OperationalError:
            pass  # corrupt/missing index — degrade gracefully
    return _search_like(conn, query, limit)
