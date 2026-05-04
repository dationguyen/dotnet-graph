"""Generate an Obsidian vault from the dotnet-graph knowledge database.

Each type becomes a markdown note with YAML frontmatter and WikiLinks for:
- Inheritance / interface implementation
- Constructor injections (what this type depends on)
- Injected-by (what types depend on this type)
- Methods and properties tables
"""

from __future__ import annotations

import re
from pathlib import Path

from .db import open_db


def _safe_filename(name: str) -> str:
    name = re.sub(r"<[^>]*>", "", name)
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return name.strip()


def _wikilink(full_name: str) -> str:
    short = full_name.split(".")[-1] if "." in full_name else full_name
    short = re.sub(r"<[^>]*>", "", short)
    safe_full = _safe_filename(full_name)
    if short == safe_full:
        return f"[[{short}]]"
    return f"[[{safe_full}|{short}]]"


def build_vault(db_path: Path, vault_path: Path, verbose: bool = False) -> int:
    """Build an Obsidian vault from knowledge.db. Returns notes written."""
    conn = open_db(db_path)
    vault_path.mkdir(parents=True, exist_ok=True)

    # ── Preload relationship maps (deduplicated) ───────────────────────────
    type_bases: dict[str, list[tuple[str, str]]] = {}
    _seen_bases: set[tuple[str, str, str]] = set()
    for row in conn.execute("SELECT from_type, to_type, kind FROM relationships"):
        key = (row["from_type"], row["to_type"], row["kind"])
        if key not in _seen_bases:
            _seen_bases.add(key)
            type_bases.setdefault(row["from_type"], []).append((row["to_type"], row["kind"]))

    type_injects: dict[str, list[tuple[str, str]]] = {}
    injected_by: dict[str, set[str]] = {}
    _seen_injects: set[tuple[str, str, str]] = set()
    for row in conn.execute("""
        SELECT t.full_name, ci.param_type, ci.param_name
        FROM constructor_injections ci
        JOIN types t ON ci.type_id = t.id
    """):
        key = (row["full_name"], row["param_type"], row["param_name"])
        if key not in _seen_injects:
            _seen_injects.add(key)
            type_injects.setdefault(row["full_name"], []).append((row["param_type"], row["param_name"]))
            injected_by.setdefault(row["param_type"], set()).add(row["full_name"])

    type_methods: dict[int, list] = {}
    for row in conn.execute(
        "SELECT type_id, name, return_type, visibility, is_async, parameters, line FROM methods"
    ):
        type_methods.setdefault(row["type_id"], []).append(row)

    type_props: dict[int, list] = {}
    for row in conn.execute(
        "SELECT type_id, name, type_name, visibility, line FROM properties"
    ):
        type_props.setdefault(row["type_id"], []).append(row)

    # ── Write one note per type ────────────────────────────────────────────
    types = conn.execute("""
        SELECT t.id, t.name, t.full_name, t.kind, t.is_abstract, t.line,
               f.namespace, f.path AS file_path,
               p.name AS project_name, p.domain
        FROM types t
        LEFT JOIN files f ON t.file_id = f.id
        LEFT JOIN projects p ON t.project_id = p.id
        ORDER BY t.full_name
    """).fetchall()

    written = 0
    for t in types:
        full_name = t["full_name"] or t["name"]
        note_path = vault_path / f"{_safe_filename(full_name)}.md"

        lines: list[str] = []

        # Frontmatter — skip domain if it looks like a path artifact
        domain = t["domain"]
        if domain and (domain.startswith(".") or "/" in domain or "\\" in domain):
            domain = None

        tags = [t["kind"] or "type"]
        if domain:
            tags.append(domain.lower().replace(" ", "-"))
        if t["name"].endswith("ViewModel"):
            tags.append("viewmodel")
        elif t["kind"] == "interface":
            tags.append("interface")

        lines += ["---"]
        lines += [f"kind: {t['kind'] or 'type'}"]
        if t["namespace"]:
            lines += [f"namespace: \"{t['namespace']}\""]
        if t["project_name"]:
            lines += [f"project: \"{t['project_name']}\""]
        if domain:
            lines += [f"domain: \"{domain}\""]
        lines += [f"tags: [{', '.join(tags)}]"]
        lines += ["---", ""]
        lines += [f"# {t['name']}", ""]

        if t["project_name"]:
            lines += [f"**Project:** {t['project_name']}  "]
        if t["namespace"]:
            lines += [f"**Namespace:** `{t['namespace']}`  "]
        if t["file_path"]:
            lines += [f"**File:** `{t['file_path']}`  "]
        lines += [""]

        # Inherits / Implements
        bases = type_bases.get(full_name, [])
        if bases:
            lines += ["## Inherits / Implements"]
            for to_type, kind in bases:
                lines += [f"- *{kind}* → {_wikilink(to_type)}"]
            lines += [""]

        # Constructor Injections
        injects = type_injects.get(full_name, [])
        if injects:
            lines += ["## Constructor Injections"]
            for param_type, param_name in injects:
                lines += [f"- `{param_name}` : {_wikilink(param_type)}"]
            lines += [""]

        # Injected By
        users = sorted(injected_by.get(full_name, set()))
        if users:
            lines += ["## Injected By"]
            for user in users[:20]:
                lines += [f"- {_wikilink(user)}"]
            if len(users) > 20:
                lines += [f"- *(and {len(users) - 20} more)*"]
            lines += [""]

        # Methods
        methods = type_methods.get(t["id"], [])
        if methods:
            lines += ["## Methods"]
            lines += ["| Name | Returns | Async | Visibility |"]
            lines += ["|------|---------|-------|------------|"]
            for m in sorted(methods, key=lambda x: x["line"] or 0):
                async_mark = "✓" if m["is_async"] else ""
                ret = m["return_type"] or ""
                vis = m["visibility"] or "public"
                lines += [f"| `{m['name']}` | `{ret}` | {async_mark} | {vis} |"]
            lines += [""]

        # Properties
        props = type_props.get(t["id"], [])
        if props:
            lines += ["## Properties"]
            for p in sorted(props, key=lambda x: x["line"] or 0):
                vis = p["visibility"] or "public"
                lines += [f"- `{p['name']}` : `{p['type_name']}` *({vis})*"]
            lines += [""]

        note_path.write_text("\n".join(lines), encoding="utf-8")
        written += 1
        if verbose and written % 200 == 0:
            print(f"  {written}/{len(types)} notes written...")

    conn.close()
    if verbose:
        print(f"Vault complete: {written} notes → {vault_path}")
    return written
