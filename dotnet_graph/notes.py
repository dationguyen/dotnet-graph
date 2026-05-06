"""Enriched knowledge notes for types — maintained by AI agents across sessions.

Notes live in .dotnet-graph/notes/<Domain>/<TypeName>.md alongside the
auto-generated obsidian vault. Each note has a structural section generated
from the graph plus a ## Notes section that AI agents fill in as they work.
"""

from __future__ import annotations

from pathlib import Path

from .db import open_db
from ._render import _safe_filename, _normalize_domain, _type_lines


_NOTES_SECTION_MARKER = "---\n\n## Notes"


def _domain_folder(domain: str | None, full_name: str) -> str:
    d = _normalize_domain(domain)
    if d:
        return d.split("/")[0].split("\\")[0].strip()
    return full_name.split(".")[0] if "." in full_name else "Other"


def _lookup_type(conn, type_name: str):
    """Return all matching type rows. Callers must handle 0 (not found) and >1 (ambiguous)."""
    return conn.execute("""
        SELECT t.id, t.name, t.full_name, t.kind, t.is_abstract, t.line,
               f.namespace, f.path AS file_path,
               p.name AS project_name, p.domain
        FROM types t
        LEFT JOIN files f ON t.file_id = f.id
        LEFT JOIN projects p ON t.project_id = p.id
        WHERE t.name = ? OR t.full_name = ? OR t.full_name LIKE ?
        ORDER BY length(t.full_name)
    """, (type_name, type_name, f"%.{type_name}")).fetchall()


def _ambiguous_error(type_name: str, rows) -> dict:
    candidates = "\n".join(f"  - {r['full_name']}" for r in rows)
    return {"error": f"'{type_name}' matches {len(rows)} types — use the full name:\n{candidates}"}


def note_path_for(full_name: str, domain: str | None, project: str | None, notes_dir: Path) -> Path:
    """Return the expected path for a type's note: notes/<Domain>/<Project>/<FullName>.md"""
    folder = _domain_folder(domain, full_name)
    proj = _safe_filename(project) if project else "Unknown"
    return notes_dir / folder / proj / f"{_safe_filename(full_name)}.md"


def _structure_lines(t, conn) -> list[str]:
    """Fetch per-type graph data and delegate rendering to _type_lines."""
    full_name = t["full_name"] or t["name"]

    seen: set = set()
    bases = []
    for r in conn.execute(
        "SELECT to_type, kind FROM relationships WHERE from_type = ?", (full_name,)
    ):
        key = (r["to_type"], r["kind"])
        if key not in seen:
            seen.add(key)
            bases.append((r["to_type"], r["kind"]))

    seen = set()
    injects = []
    for r in conn.execute("""
        SELECT ci.param_type, ci.param_name
        FROM constructor_injections ci
        JOIN types t ON ci.type_id = t.id
        WHERE t.full_name = ?
    """, (full_name,)):
        key = (r["param_type"], r["param_name"])
        if key not in seen:
            seen.add(key)
            injects.append((r["param_type"], r["param_name"]))

    injectors = [r["full_name"] for r in conn.execute("""
        SELECT DISTINCT t.full_name
        FROM constructor_injections ci
        JOIN types t ON ci.type_id = t.id
        WHERE ci.param_type = ? OR ci.param_type LIKE ?
        ORDER BY t.full_name
        LIMIT 20
    """, (full_name, f"%.{t['name']}"))]

    methods = conn.execute(
        "SELECT name, return_type, visibility, is_async, line FROM methods WHERE type_id = ? ORDER BY line",
        (t["id"],),
    ).fetchall()

    props = conn.execute(
        "SELECT name, type_name, visibility, line FROM properties WHERE type_id = ? ORDER BY line",
        (t["id"],),
    ).fetchall()

    return _type_lines(t, bases, injects, injectors, methods, props)


def get_or_create_note(db_path: Path, type_name: str, notes_dir: Path) -> dict:
    """Get an existing note or create one from graph data.

    Returns a dict with: path (str), content (str), created (bool).
    On error, returns: error (str).
    """
    conn = open_db(db_path)
    rows = _lookup_type(conn, type_name)

    if not rows:
        conn.close()
        return {"error": f"Type '{type_name}' not found in graph. Run build_graph first."}
    if len(rows) > 1:
        conn.close()
        return _ambiguous_error(type_name, rows)

    t = rows[0]
    full_name = t["full_name"] or t["name"]
    domain = _normalize_domain(t["domain"])
    note_path = note_path_for(full_name, domain, t["project_name"], notes_dir)

    if note_path.exists():
        conn.close()
        return {"path": str(note_path), "content": note_path.read_text(encoding="utf-8"), "created": False}

    structure = _structure_lines(t, conn)
    conn.close()

    content = "\n".join(structure)
    content += "---\n\n## Notes\n"
    content += "> _No notes yet — add purpose, business logic, gotchas, and work log here._\n"

    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text(content, encoding="utf-8")

    return {"path": str(note_path), "content": content, "created": True}


def sync_note_structure(db_path: Path, type_name: str, notes_dir: Path) -> dict:
    """Refresh the structural section of an existing note from current graph data.

    Preserves everything from ## Notes onwards. If the note doesn't exist yet,
    delegates to get_or_create_note. Returns a dict with: path, content,
    refreshed (bool) or created (bool). On error, returns: error (str).
    If the note exists but has no marker, returns refreshed=False unchanged.
    """
    conn = open_db(db_path)
    rows = _lookup_type(conn, type_name)

    if not rows:
        conn.close()
        return {"error": f"Type '{type_name}' not found in graph. Run build_graph first."}
    if len(rows) > 1:
        conn.close()
        return _ambiguous_error(type_name, rows)

    t = rows[0]
    full_name = t["full_name"] or t["name"]
    domain = _normalize_domain(t["domain"])
    note_path = note_path_for(full_name, domain, t["project_name"], notes_dir)

    if not note_path.exists():
        conn.close()
        return get_or_create_note(db_path, type_name, notes_dir)

    existing = note_path.read_text(encoding="utf-8")
    marker_idx = existing.find(_NOTES_SECTION_MARKER)

    if marker_idx == -1:
        conn.close()
        return {"path": str(note_path), "content": existing, "refreshed": False}

    notes_tail = existing[marker_idx + len(_NOTES_SECTION_MARKER):]
    structure = _structure_lines(t, conn)
    conn.close()

    content = "\n".join(structure) + _NOTES_SECTION_MARKER + notes_tail
    note_path.write_text(content, encoding="utf-8")
    return {"path": str(note_path), "content": content, "refreshed": True}
