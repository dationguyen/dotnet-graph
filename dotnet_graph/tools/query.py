"""MCP query tools for the dotnet-graph knowledge database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Callable


def register_query_tools(mcp, get_db: Callable[[], sqlite3.Connection]) -> None:
    """Register all read-only query tools on the FastMCP instance."""

    @mcp.tool()
    def find_type(name: str, exact: bool = False) -> str:
        """Find a C# type (class, interface, enum, record, struct) by name.

        Use exact=True for precise matches. Defaults to a LIKE search (case-insensitive).
        Returns location, kind, base types, and method count.
        """
        conn = get_db()
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

        if not rows:
            return f"No types found matching '{name}'."

        lines = [f"Found {len(rows)} type(s) matching `{name}`:\n"]
        for r in rows:
            flags = []
            if r["is_abstract"]: flags.append("abstract")
            if r["is_partial"]: flags.append("partial")
            flag_str = f" ({', '.join(flags)})" if flags else ""
            lines.append(f"**{r['name']}** `{r['kind']}`{flag_str}")
            lines.append(f"  full: `{r['full_name']}`")
            lines.append(f"  at: `{r['path']}:{r['line']}`  project: {r['project']} ({r['domain']})")

            bases = conn.execute(
                "SELECT to_type, kind FROM relationships WHERE from_type=?", (r["full_name"],)
            ).fetchall()
            if bases:
                lines.append(f"  bases: {', '.join(b['to_type'] for b in bases)}")
            lines.append("")
        return "\n".join(lines)

    @mcp.tool()
    def get_type_members(type_name: str) -> str:
        """Get all methods, properties, and constructor parameters for a type."""
        conn = get_db()
        t = conn.execute(
            "SELECT id, full_name, kind, line FROM types WHERE name=? OR full_name=? LIMIT 1",
            (type_name, type_name),
        ).fetchone()
        if not t:
            return f"Type `{type_name}` not found."

        out = [f"## {t['full_name']} (`{t['kind']}`)\n"]

        # Constructor injections
        ctors = conn.execute(
            "SELECT DISTINCT param_type, param_name FROM constructor_injections WHERE type_id=? ORDER BY line",
            (t["id"],),
        ).fetchall()
        if ctors:
            out.append("### Constructor Parameters")
            for c in ctors:
                out.append(f"- `{c['param_type']}` {c['param_name']}")
            out.append("")

        # Methods
        methods = conn.execute(
            "SELECT name, return_type, parameters, visibility, is_async, is_override, line "
            "FROM methods WHERE type_id=? ORDER BY line",
            (t["id"],),
        ).fetchall()
        if methods:
            out.append("### Methods")
            for m in methods:
                async_tag = "async " if m["is_async"] else ""
                override_tag = "override " if m["is_override"] else ""
                out.append(f"- `{m['visibility']} {async_tag}{override_tag}{m['return_type']} {m['name']}{m['parameters']}`  :{m['line']}")
            out.append("")

        # Properties
        props = conn.execute(
            "SELECT name, type_name, visibility, is_static, line FROM properties WHERE type_id=? ORDER BY line",
            (t["id"],),
        ).fetchall()
        if props:
            out.append("### Properties")
            for p in props:
                static_tag = "static " if p["is_static"] else ""
                out.append(f"- `{p['visibility']} {static_tag}{p['type_name']} {p['name']}`  :{p['line']}")
            out.append("")

        # Fields
        fields = conn.execute(
            "SELECT name, type_name, is_readonly FROM field_declarations WHERE type_id=? ORDER BY line",
            (t["id"],),
        ).fetchall()
        if fields:
            out.append("### Private/Protected Fields")
            for f in fields:
                ro = "readonly " if f["is_readonly"] else ""
                out.append(f"- `{ro}{f['type_name']} {f['name']}`")

        return "\n".join(out)

    @mcp.tool()
    def find_implementors(interface_name: str) -> str:
        """Find all types that implement or inherit from the given type."""
        conn = get_db()
        pat = f"%{interface_name}%"
        rows = conn.execute("""
            SELECT r.from_type, r.to_type, r.kind, f.path, t.line, p.name AS project
            FROM relationships r
            JOIN types t ON r.from_type = t.full_name
            JOIN files f ON t.file_id = f.id
            JOIN projects p ON t.project_id = p.id
            WHERE r.to_type LIKE ?
            ORDER BY r.from_type
        """, (pat,)).fetchall()

        if not rows:
            return f"No implementors found for `{interface_name}`."

        lines = [f"**{len(rows)}** type(s) implement/inherit `{interface_name}`:\n"]
        for r in rows:
            lines.append(f"- `{r['from_type']}` ({r['kind']} `{r['to_type']}`)")
            lines.append(f"  `{r['path']}:{r['line']}`  [{r['project']}]")
        return "\n".join(lines)

    @mcp.tool()
    def find_injectors(interface_name: str) -> str:
        """Find all classes that inject the given interface via constructor."""
        conn = get_db()
        pat = f"%{interface_name}%"
        rows = conn.execute("""
            SELECT t.name, t.full_name, ci.param_name, ci.param_type, f.path, ci.line, p.name AS project
            FROM constructor_injections ci
            JOIN types t ON ci.type_id = t.id
            JOIN files f ON ci.file_id = f.id
            JOIN projects p ON ci.project_id = p.id
            WHERE ci.param_type LIKE ?
            ORDER BY t.name
        """, (pat,)).fetchall()

        if not rows:
            return f"No classes inject `{interface_name}`."

        lines = [f"**{len(rows)}** class(es) inject `{interface_name}`:\n"]
        for r in rows:
            lines.append(f"- `{r['full_name']}` — param `{r['param_type']} {r['param_name']}`")
            lines.append(f"  `{r['path']}:{r['line']}`  [{r['project']}]")
        return "\n".join(lines)

    @mcp.tool()
    def get_method_calls(type_name: str, method_name: str) -> str:
        """Get all service/method calls made within a specific method."""
        conn = get_db()
        t = conn.execute(
            "SELECT id FROM types WHERE name=? OR full_name=? LIMIT 1", (type_name, type_name)
        ).fetchone()
        if not t:
            return f"Type `{type_name}` not found."

        rows = conn.execute(
            "SELECT callee_expr, callee_method, line FROM method_calls "
            "WHERE caller_type_id=? AND caller_method=? ORDER BY line",
            (t["id"], method_name),
        ).fetchall()

        if not rows:
            return f"No calls found in `{type_name}.{method_name}`."

        lines = [f"Calls in `{type_name}.{method_name}`:\n"]
        for r in rows:
            lines.append(f"- :{r['line']}  `{r['callee_expr']}.{r['callee_method']}()`")
        return "\n".join(lines)

    @mcp.tool()
    def find_callers(method_name: str) -> str:
        """Find all methods across the codebase that call the given method name."""
        conn = get_db()
        rows = conn.execute("""
            SELECT t.name AS caller_type, mc.caller_method, mc.callee_expr, f.path, mc.line
            FROM method_calls mc
            JOIN types t ON mc.caller_type_id = t.id
            JOIN files f ON mc.file_id = f.id
            WHERE mc.callee_method = ?
            ORDER BY t.name, mc.caller_method
            LIMIT 50
        """, (method_name,)).fetchall()

        if not rows:
            return f"No callers found for method `{method_name}`."

        lines = [f"**{len(rows)}** call site(s) for `{method_name}`:\n"]
        for r in rows:
            lines.append(f"- `{r['caller_type']}.{r['caller_method']}` via `{r['callee_expr']}.{method_name}()`")
            lines.append(f"  `{r['path']}:{r['line']}`")
        return "\n".join(lines)

    @mcp.tool()
    def get_di_registrations(name: str = "") -> str:
        """Get DI registrations. Filter by interface or implementation name (leave empty for all)."""
        conn = get_db()
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

        if not rows:
            return f"No DI registrations found matching '{name}'." if name else "No DI registrations found."

        lines = [f"**{len(rows)}** DI registration(s):\n"]
        for r in rows:
            iface = r["interface_type"] or "—"
            impl = r["impl_type"] or "—"
            lines.append(f"- `{iface}` → `{impl}`  [{r['lifetime']}]")
            lines.append(f"  `{r['path']}:{r['line']}`  [{r['project']}]")
        return "\n".join(lines)

    @mcp.tool()
    def get_endpoints() -> str:
        """List all HTTP endpoints found in the codebase."""
        conn = get_db()
        rows = conn.execute("""
            SELECT e.http_method, e.url_pattern, e.type_name, f.path, e.line, p.name AS project
            FROM endpoints e
            JOIN files f ON e.file_id = f.id
            JOIN projects p ON e.project_id = p.id
            ORDER BY e.http_method, e.url_pattern
        """).fetchall()

        if not rows:
            return "No HTTP endpoints found."

        lines = [f"**{len(rows)}** HTTP endpoint(s):\n"]
        for r in rows:
            lines.append(f"- `{r['http_method']}` `{r['url_pattern']}`")
            lines.append(f"  caller: `{r['type_name']}`  `{r['path']}:{r['line']}`")
        return "\n".join(lines)

    @mcp.tool()
    def get_features() -> str:
        """Get the ViewModel-centric feature index (one entry per feature domain area)."""
        conn = get_db()
        rows = conn.execute(
            "SELECT name, domain, viewmodel, service, project FROM features ORDER BY domain, name"
        ).fetchall()

        if not rows:
            return "No features indexed."

        lines = [f"**{len(rows)}** feature(s):\n"]
        cur_domain = None
        for r in rows:
            if r["domain"] != cur_domain:
                cur_domain = r["domain"]
                lines.append(f"\n### {cur_domain}")
            svc = f"  service: `{r['service']}`" if r["service"] else ""
            lines.append(f"- **{r['name']}** — `{r['viewmodel']}`{svc}  [{r['project']}]")
        return "\n".join(lines)

    @mcp.tool()
    def search(query: str) -> str:
        """Search types, methods, properties, and fields by keyword."""
        conn = get_db()
        pat = f"%{query}%"

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

        out = [f"Search results for `{query}`:\n"]

        if types:
            out.append("**Types**")
            for r in types:
                out.append(f"- `{r['name']}` ({r['kind']})  `{r['path']}:{r['line']}`")
            out.append("")

        if methods:
            out.append("**Methods**")
            for r in methods:
                out.append(f"- `{r['type_name']}.{r['name']}` → `{r['return_type']}`  `{r['path']}:{r['line']}`")
            out.append("")

        if props:
            out.append("**Properties**")
            for r in props:
                out.append(f"- `{r['type_name']}.{r['name']}` : `{r['prop_type']}`  `{r['path']}:{r['line']}`")

        if not types and not methods and not props:
            return f"Nothing found matching `{query}`."

        return "\n".join(out)

    @mcp.tool()
    def get_stats() -> str:
        """Show knowledge graph statistics (row counts per table)."""
        conn = get_db()
        tables = [
            "projects", "files", "types", "methods", "properties",
            "relationships", "registrations", "endpoints", "config_keys",
            "features", "constructor_injections", "field_declarations", "method_calls",
        ]
        lines = ["**Graph statistics:**\n"]
        for t in tables:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            lines.append(f"- {t:<22}: {n:>6,}")
        return "\n".join(lines)
