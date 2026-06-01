"""Build the interactive "explore" dashboard from the knowledge graph.

A second exporter alongside obsidian.py: instead of an Obsidian vault it emits a
self-contained web app (index.html + data.js) that presents the codebase the way
*Understand Anything* does — architectural layers, a plain-English summary on every
node, dependency-ordered guided tours, and a domain/business-flow view.

data.js is loaded via a <script> tag (assigns window.EXPLORE), so the dashboard
works straight off the filesystem with no server and no CORS issues.
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path

from .db import open_db
from ._render import _safe_filename, _normalize_domain
from .layers import classify_all, layer_legend, LAYER_IDS
from .summaries import load_note_purposes, summarize
from .tours import build_tours, build_type_index, _resolve

_ASSETS = Path(__file__).parent / "explore_assets"


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 1)
            return text[nl + 1:] if nl != -1 else ""
    return text


def _load_note_bodies(notes_dir: Path, stem_to_full: dict[str, str]) -> dict[str, str]:
    """Full note markdown (sans frontmatter) keyed by type full name."""
    bodies: dict[str, str] = {}
    if not notes_dir or not notes_dir.is_dir():
        return bodies
    for path in notes_dir.rglob("*.md"):
        full = stem_to_full.get(path.stem)
        if not full:
            continue
        try:
            bodies[full] = _strip_frontmatter(path.read_text(encoding="utf-8")).strip()
        except OSError:
            continue
    return bodies


def build_data(db_path: Path, notes_dir: Path) -> dict:
    """Assemble the full data payload for the dashboard."""
    conn = open_db(db_path)

    # ── projects ────────────────────────────────────────────────────────────
    projects: dict[int, dict] = {}
    for r in conn.execute("SELECT id, name, domain, platform FROM projects"):
        projects[r["id"]] = {
            "name": r["name"],
            "domain": _normalize_domain(r["domain"]) or "(none)",
            "platform": r["platform"],
        }

    # ── types ───────────────────────────────────────────────────────────────
    type_rows = conn.execute("""
        SELECT t.id, t.name, t.full_name, t.kind, t.is_abstract, t.line,
               t.project_id, f.namespace, f.path AS file
        FROM types t LEFT JOIN files f ON t.file_id = f.id
    """).fetchall()

    types = []
    by_id = {}
    full_names = []
    for r in type_rows:
        fn = r["full_name"] or r["name"]
        full_names.append(fn)
        d = {
            "id": r["id"], "full_name": fn, "name": r["name"], "kind": r["kind"],
            "namespace": r["namespace"], "is_abstract": bool(r["is_abstract"]),
            "line": r["line"], "file": r["file"],
            "project": projects.get(r["project_id"], {}).get("name"),
            "domain": projects.get(r["project_id"], {}).get("domain", "(none)"),
            "platform": projects.get(r["project_id"], {}).get("platform"),
        }
        types.append(d)
        by_id[r["id"]] = d

    internal = set(full_names)
    type_index = build_type_index(full_names)
    stem_to_full = {_safe_filename(fn): fn for fn in full_names}

    # ── relationships ─────────────────────────────────────────────────────────
    edges = []
    impl_count: dict[str, int] = defaultdict(int)
    external = set()
    seen_edge = set()
    for r in conn.execute("SELECT from_type, to_type, kind FROM relationships"):
        key = (r["from_type"], r["to_type"], r["kind"])
        if key in seen_edge:
            continue
        seen_edge.add(key)
        edges.append({"from": r["from_type"], "to": r["to_type"], "kind": r["kind"]})
        impl_count[r["to_type"]] += 1
        for t in (r["from_type"], r["to_type"]):
            if t not in internal:
                external.add(t)

    # ── members + injections ──────────────────────────────────────────────────
    def collect(query, fields):
        out: dict[int, list] = defaultdict(list)
        for r in conn.execute(query):
            out[r["type_id"]].append({k: r[k] for k in fields})
        return out

    methods = collect(
        "SELECT type_id, name, return_type, visibility, is_async, is_static, line FROM methods ORDER BY name",
        ["name", "return_type", "visibility", "is_async", "is_static", "line"])
    properties = collect(
        "SELECT type_id, name, type_name, visibility, line FROM properties ORDER BY name",
        ["name", "type_name", "visibility", "line"])
    fields = collect(
        "SELECT type_id, name, type_name, visibility, is_readonly, line FROM field_declarations ORDER BY name",
        ["name", "type_name", "visibility", "is_readonly", "line"])
    inj_rows = collect(
        "SELECT type_id, param_type, param_name, line FROM constructor_injections",
        ["param_type", "param_name", "line"])

    injections_by_type: dict[str, list[str]] = defaultdict(list)
    injector_count: dict[str, int] = defaultdict(int)
    for tid, rows in inj_rows.items():
        owner = by_id[tid]["full_name"]
        counted = set()
        for row in rows:
            injections_by_type[owner].append(row["param_type"])
            target = _resolve(row["param_type"], type_index)
            if target and target not in counted:
                counted.add(target)
                injector_count[target] += 1

    members = {}
    for tid, d in by_id.items():
        members[d["full_name"]] = {
            "methods": methods.get(tid, []),
            "properties": properties.get(tid, []),
            "fields": fields.get(tid, []),
            "injections": inj_rows.get(tid, []),
        }

    # ── layers ─────────────────────────────────────────────────────────────────
    endpoint_types = {r[0] for r in conn.execute("SELECT DISTINCT type_name FROM endpoints")}
    layer_of = classify_all(
        [{"full_name": t["full_name"], "name": t["name"], "kind": t["kind"],
          "namespace": t["namespace"]} for t in types],
        [{"from_type": e["from"], "to_type": e["to"], "kind": e["kind"]} for e in edges],
        endpoint_types,
    )

    # ── notes + summaries ───────────────────────────────────────────────────────
    note_purposes = load_note_purposes(notes_dir)
    note_bodies = _load_note_bodies(notes_dir, stem_to_full)

    # ── features ─────────────────────────────────────────────────────────────────
    features = [
        {"name": r["name"], "domain": _normalize_domain(r["domain"]),
         "viewmodel": r["viewmodel"], "service": r["service"], "project": r["project"]}
        for r in conn.execute("SELECT name, domain, viewmodel, service, project FROM features ORDER BY name")
    ]
    feature_by_vm = {f["viewmodel"]: f["name"] for f in features if f["viewmodel"]}

    # ── assemble nodes ───────────────────────────────────────────────────────────
    deg: dict[str, int] = defaultdict(int)
    for e in edges:
        deg[e["from"]] += 1
        deg[e["to"]] += 1

    nodes = []
    for t in types:
        fn = t["full_name"]
        layer = layer_of.get(fn, "other")
        summary, from_note = summarize(
            fn, t["name"], t["kind"], layer,
            note_purposes=note_purposes,
            injector_count=injector_count.get(fn, 0),
            impl_count=impl_count.get(fn, 0),
            feature=feature_by_vm.get(fn),
            is_abstract=t["is_abstract"],
        )
        nodes.append({
            "id": fn, "name": t["name"], "kind": t["kind"], "layer": layer,
            "domain": t["domain"], "project": t["project"], "platform": t["platform"],
            "file": t["file"], "line": t["line"], "abstract": t["is_abstract"],
            "summary": summary, "fromNote": from_note, "note": fn in note_bodies,
            "deg": deg.get(fn, 0),
            "injectors": injector_count.get(fn, 0),
            "impls": impl_count.get(fn, 0),
        })

    for ext in sorted(external):
        nodes.append({
            "id": ext, "name": ext.split(".")[-1], "kind": "external", "layer": "external",
            "domain": "(external)", "project": None, "platform": None,
            "summary": "External base type / framework dependency.",
            "fromNote": False, "note": False, "external": True,
            "deg": deg.get(ext, 0), "injectors": 0, "impls": impl_count.get(ext, 0),
        })

    # ── tours ─────────────────────────────────────────────────────────────────────
    tours = build_tours(features, types, injections_by_type, type_index)

    registrations = [
        {"interface": r["interface_type"], "impl": r["impl_type"], "lifetime": r["lifetime"],
         "project": projects.get(r["project_id"], {}).get("name")}
        for r in conn.execute(
            "SELECT interface_type, impl_type, lifetime, project_id FROM registrations ORDER BY interface_type")
    ]
    endpoints = [
        {"type": r["type_name"], "url": r["url_pattern"], "method": r["http_method"],
         "project": projects.get(r["project_id"], {}).get("name")}
        for r in conn.execute(
            "SELECT type_name, url_pattern, http_method, project_id FROM endpoints ORDER BY url_pattern")
    ]
    build_meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM build_meta")}
    conn.close()

    layer_dist = defaultdict(int)
    for lyr in layer_of.values():
        layer_dist[lyr] += 1

    return {
        "meta": {"generatedFrom": str(db_path), "buildMeta": build_meta},
        "layers": layer_legend(),
        "layerOrder": LAYER_IDS,
        "projects": list({p["name"]: p for p in projects.values()}.values()),
        "nodes": nodes,
        "edges": edges,
        "members": members,
        "notes": note_bodies,
        "registrations": registrations,
        "features": features,
        "endpoints": endpoints,
        "tours": tours,
        "stats": {
            "types": len(types), "edges": len(edges), "external": len(external),
            "notes": len(note_bodies), "summariesFromNotes": sum(1 for n in nodes if n.get("fromNote")),
            "registrations": len(registrations), "features": len(features),
            "endpoints": len(endpoints), "projects": len(projects), "tours": len(tours),
            "layerDist": dict(layer_dist),
        },
    }


def build_dashboard(db_path: Path, out_dir: Path, notes_dir: Path, verbose: bool = False) -> dict:
    """Write index.html + data.js to out_dir. Returns the stats dict."""
    data = build_data(db_path, notes_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (out_dir / "data.js").write_text("window.EXPLORE = " + payload + ";\n", encoding="utf-8")
    shutil.copy2(_ASSETS / "index.html", out_dir / "index.html")

    if verbose:
        s = data["stats"]
        print(f"  {s['types']} types · {s['edges']} edges · {s['tours']} tours · "
              f"{s['summariesFromNotes']}/{s['types']} summaries from notes")
        print(f"  Dashboard → {out_dir / 'index.html'}")
    return data["stats"]
