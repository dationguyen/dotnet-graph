"""Build orchestrator: compiles Roslyn analyzer, runs it, ingests results into SQLite."""

from __future__ import annotations

import bisect
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from .db import init_db, count

XAML_CLASS_PAT = re.compile(r'x:Class="([\w.]+)"')


# ── Analyzer binary management ─────────────────────────────────────────────────

def _cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "dotnet-graph"


def _ensure_analyzer(verbose: bool = False) -> list[str]:
    """Return the command list to invoke the Roslyn analyzer, compiling if needed."""
    src = Path(__file__).parent / "analyzer"
    out = _cache_dir() / "analyzer"
    stamp = out / ".stamp"

    needs_build = not stamp.exists()
    if not needs_build:
        stamp_mtime = stamp.stat().st_mtime
        needs_build = any(f.stat().st_mtime > stamp_mtime for f in src.rglob("*.cs"))

    if needs_build:
        out.mkdir(parents=True, exist_ok=True)
        if verbose:
            print("  Compiling Roslyn analyzer...")
        result = subprocess.run(
            ["dotnet", "publish", str(src), "-c", "Release", "-o", str(out),
             "--verbosity", "quiet", "--nologo"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Roslyn analyzer compilation failed:\n{result.stderr}")
        stamp.touch()
        if verbose:
            print("  Roslyn analyzer ready.")

    dll = out / "RoslynAnalyzer.dll"
    if not dll.exists():
        raise RuntimeError(f"Compiled binary not found: {dll}")
    return ["dotnet", str(dll)]


def _run_roslyn(root: Path, verbose: bool = False) -> list[dict]:
    cmd = _ensure_analyzer(verbose=verbose)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = f.name
    try:
        result = subprocess.run(
            [*cmd, "--root", str(root), "--output", tmp],
            capture_output=True, text=True, timeout=600,
        )
        if verbose and result.stderr:
            for line in result.stderr.strip().splitlines():
                print(f"  {line}")
        if result.returncode != 0:
            raise RuntimeError(f"Roslyn analyzer failed:\n{result.stderr}")
        with open(tmp, encoding="utf-8") as f:
            return json.load(f)
    finally:
        Path(tmp).unlink(missing_ok=True)


# ── Project discovery ──────────────────────────────────────────────────────────

def _infer_domain(rel_path: str) -> tuple[str, str]:
    parts = Path(rel_path).parts
    top = parts[0] if parts else ""
    domain = top if top not in (".", "") else "Core"

    p = rel_path.lower().replace(".", "").replace(" ", "").replace("-", "")
    if "android" in p:
        platform = "android"
    elif "ios" in p or "shareextension" in p:
        platform = "ios"
    elif "windows" in p or "maui" in p:
        platform = "windows"
    else:
        platform = "shared"
    return domain, platform


def _collect_projects(root: Path) -> list[dict]:
    projects = []
    for csproj in root.rglob("*.csproj"):
        parts = csproj.parts
        if any(p in ("obj", "bin") or p.startswith(".") for p in parts[len(root.parts):]):
            continue
        rel = str(csproj.relative_to(root))
        domain, platform = _infer_domain(rel)
        projects.append({
            "name": csproj.stem,
            "path": rel,
            "domain": domain,
            "platform": platform,
            "dir": csproj.parent,
        })
    return projects


# ── Ingest Roslyn JSON output ──────────────────────────────────────────────────

def _file_to_project(path: str, projects: list[dict]) -> dict | None:
    """Find the deepest project whose directory is a parent of the file path."""
    best = None
    best_len = -1
    for proj in projects:
        proj_prefix = str(proj["dir"]).rstrip("/\\")
        if path.startswith(proj_prefix) and len(proj_prefix) > best_len:
            best = proj
            best_len = len(proj_prefix)
    return best


def _ingest_roslyn(
    file_data_list: list[dict],
    root: Path,
    projects: list[dict],
    project_ids: dict[str, int],
    conn: sqlite3.Connection,
) -> None:
    cur = conn.cursor()

    def insert_types_recursive(
        type_list: list[dict],
        file_id: int,
        project_id: int,
        namespace: str | None,
    ) -> list[tuple[int, int, str]]:
        """Insert types and return [(line, type_id, full_name)] for method-call anchoring."""
        rows = []
        for t in type_list:
            name = t["name"]
            full_name = f"{namespace}.{name}" if namespace else name
            cur.execute(
                "INSERT INTO types (file_id, project_id, name, full_name, kind, is_abstract, is_partial, line) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (file_id, project_id, name, full_name,
                 t["kind"], int(t["is_abstract"]), int(t["is_partial"]), t["line"]),
            )
            type_id = cur.lastrowid
            rows.append((t["line"], type_id, full_name))

            for base in t.get("bases", []):
                kind = "implements" if base.startswith("I") and len(base) > 1 and base[1].isupper() else "inherits"
                cur.execute(
                    "INSERT INTO relationships (from_type, to_type, kind) VALUES (?,?,?)",
                    (full_name, base, kind),
                )

            for m in t.get("methods", []):
                cur.execute(
                    "INSERT INTO methods (file_id, type_id, project_id, name, return_type, parameters, "
                    "visibility, is_async, is_static, is_override, line) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (file_id, type_id, project_id, m["name"], m["return_type"], m["parameters"],
                     m["visibility"], int(m["is_async"]), int(m["is_static"]), int(m["is_override"]), m["line"]),
                )

            for p in t.get("properties", []):
                cur.execute(
                    "INSERT INTO properties (file_id, type_id, project_id, name, type_name, visibility, is_static, line) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (file_id, type_id, project_id, p["name"], p["type_name"],
                     p["visibility"], int(p["is_static"]), p["line"]),
                )

            for f in t.get("fields", []):
                cur.execute(
                    "INSERT INTO field_declarations "
                    "(file_id, type_id, project_id, name, type_name, visibility, is_readonly, is_static, line) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (file_id, type_id, project_id, f["name"], f["type_name"],
                     f["visibility"], int(f["is_readonly"]), int(f["is_static"]), f["line"]),
                )

            for c in t.get("constructors", []):
                for param in c.get("parameters", []):
                    cur.execute(
                        "INSERT INTO constructor_injections (file_id, type_id, project_id, param_type, param_name, line) "
                        "VALUES (?,?,?,?,?,?)",
                        (file_id, type_id, project_id, param["type"], param["name"], c["line"]),
                    )

            for reg in t.get("registrations", []):
                cur.execute(
                    "INSERT INTO registrations (file_id, project_id, interface_type, impl_type, lifetime, line) "
                    "VALUES (?,?,?,?,?,?)",
                    (file_id, project_id, reg.get("interface_type"), reg.get("impl_type"),
                     reg["lifetime"], reg["line"]),
                )

            for ep in t.get("endpoints", []):
                cur.execute(
                    "INSERT INTO endpoints (file_id, project_id, type_name, url_pattern, http_method, line) "
                    "VALUES (?,?,?,?,?,?)",
                    (file_id, project_id, full_name, ep["url_pattern"], ep["http_method"], ep["line"]),
                )

            for mc in t.get("method_calls", []):
                cur.execute(
                    "INSERT INTO method_calls (file_id, caller_type_id, caller_method, callee_expr, callee_method, line) "
                    "VALUES (?,?,?,?,?,?)",
                    (file_id, type_id, mc["caller_method"], mc["callee_expr"], mc["callee_method"], mc["line"]),
                )

            # Recurse into nested types
            nested = insert_types_recursive(t.get("nested_types", []), file_id, project_id, full_name)
            rows.extend(nested)

        return rows

    for file_data in file_data_list:
        rel_path = file_data["path"]
        namespace = file_data.get("namespace")

        proj = _file_to_project(str(root / rel_path), projects)
        project_id = project_ids.get(proj["path"]) if proj else None
        if project_id is None:
            continue

        cur.execute(
            "INSERT OR IGNORE INTO files (project_id, path, namespace) VALUES (?,?,?)",
            (project_id, rel_path, namespace),
        )
        cur.execute("SELECT id FROM files WHERE path=?", (rel_path,))
        file_id = cur.fetchone()[0]

        for ns in set(file_data.get("usings", [])):
            cur.execute("INSERT OR IGNORE INTO usings (file_id, namespace) VALUES (?,?)", (file_id, ns))

        insert_types_recursive(file_data.get("types", []), file_id, project_id, namespace)


# ── XAML & JSON config (non-C# processing stays in Python) ────────────────────

def _process_xaml(path: Path, root: Path, project_id: int, conn: sqlite3.Connection) -> None:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return
    m = XAML_CLASS_PAT.search(text)
    if not m:
        return
    x_class = m.group(1)
    rel = str(path.relative_to(root))
    conn.execute(
        "INSERT OR IGNORE INTO xaml_views (project_id, path, x_class, view_name) VALUES (?,?,?,?)",
        (project_id, rel, x_class, x_class.split(".")[-1]),
    )


def _flatten_json(obj: dict, prefix: str = "") -> list[tuple[str, str]]:
    result = []
    for k, v in obj.items():
        key = f"{prefix}:{k}" if prefix else k
        if isinstance(v, dict):
            result.extend(_flatten_json(v, key))
        else:
            result.append((key, str(v)[:500] if v is not None else ""))
    return result


def _process_json_config(path: Path, root: Path, conn: sqlite3.Connection) -> None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except Exception:
        return
    name = path.name.lower()
    env = "Development" if "development" in name else "Production" if "production" in name else "shared"
    rel = str(path.relative_to(root))
    conn.executemany(
        "INSERT INTO config_keys (source_file, key_path, value, environment) VALUES (?,?,?,?)",
        [(rel, k, v, env) for k, v in _flatten_json(obj)],
    )


# ── Post-processing ────────────────────────────────────────────────────────────

def _resolve_relationships(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("SELECT name, full_name FROM types")
    name_map: dict[str, list[str]] = {}
    for name, full in cur.fetchall():
        name_map.setdefault(name, []).append(full)

    cur.execute("SELECT full_name, file_id FROM types")
    type_to_files: dict[str, set[int]] = {}
    for full, fid in cur.fetchall():
        type_to_files.setdefault(full, set()).add(fid)

    cur.execute("SELECT id, namespace, project_id FROM files")
    file_info: dict[int, tuple[str, int]] = {fid: (ns or "", pid) for fid, ns, pid in cur.fetchall()}

    cur.execute("SELECT file_id, namespace FROM usings")
    file_usings: dict[int, set[str]] = {}
    for fid, ns in cur.fetchall():
        file_usings.setdefault(fid, set()).add(ns)

    type_project = {full: file_info[fid][1] for full, fids in type_to_files.items()
                    for fid in fids if fid in file_info}

    def cns(full: str) -> str:
        return full.rsplit(".", 1)[0] if "." in full else ""

    def seg_prefix(a: str, b: str) -> int:
        count = 0
        for x, y in zip(a.split("."), b.split(".")):
            if x == y: count += 1
            else: break
        return count

    cur.execute("SELECT id, from_type, to_type FROM relationships WHERE to_type NOT LIKE '%.%'")
    updates = []
    for rel_id, from_type, to_type in cur.fetchall():
        candidates = name_map.get(to_type, [])
        if not candidates:
            continue
        if len(candidates) == 1:
            updates.append((candidates[0], rel_id))
            continue

        fids = type_to_files.get(from_type, set())
        from_nss = {file_info[f][0] for f in fids if f in file_info and file_info[f][0]}
        all_usings = set().union(*(file_usings.get(f, set()) for f in fids))
        from_proj = type_project.get(from_type)
        resolved = None

        s2 = [c for c in candidates if cns(c) in from_nss]
        if len(s2) == 1: resolved = s2[0]
        if not resolved:
            s3 = [c for c in candidates if cns(c) in all_usings]
            if len(s3) == 1: resolved = s3[0]
        if not resolved:
            s4 = [c for c in candidates if any(fn.startswith(cns(c) + ".") or fn == cns(c) for fn in from_nss)]
            if len(s4) == 1: resolved = s4[0]
        if not resolved:
            s5 = [c for c in candidates if type_project.get(c) == from_proj and from_proj is not None]
            if len(s5) == 1: resolved = s5[0]
        if not resolved:
            from_ns = next(iter(from_nss), "")
            if from_ns:
                scored = [(seg_prefix(cns(c), from_ns), c) for c in candidates]
                best = max(s for s, _ in scored)
                if best > 0:
                    bests = [c for s, c in scored if s == best]
                    if len(bests) == 1: resolved = bests[0]
        if resolved:
            updates.append((resolved, rel_id))

    if updates:
        cur.executemany("UPDATE relationships SET to_type = ? WHERE id = ?", updates)
    print(f"  Resolved {len(updates)} relationships.")


def _build_features(conn: sqlite3.Connection) -> None:
    rows = conn.execute("""
        SELECT t.name, t.full_name, p.domain, p.name
        FROM types t JOIN projects p ON t.project_id = p.id
        WHERE t.name LIKE '%ViewModel' AND t.kind = 'class'
    """).fetchall()
    for vm_name, full_name, domain, proj_name in rows:
        feature = vm_name.removesuffix("ViewModel")
        if not feature:
            continue
        svc = conn.execute(
            "SELECT full_name FROM types WHERE name IN (?,?,?) AND kind='class' LIMIT 1",
            (f"{feature}Service", f"{feature}ServiceAgent", f"{feature}Manager"),
        ).fetchone()
        conn.execute(
            "INSERT OR IGNORE INTO features (name, domain, viewmodel, service, project) VALUES (?,?,?,?,?)",
            (feature, domain, full_name, svc[0] if svc else None, proj_name),
        )
    print(f"  Built {len(rows)} features from ViewModels.")


# ── Main entry point ───────────────────────────────────────────────────────────

def build(root: Path, db_path: Path, verbose: bool = True) -> None:
    if db_path.exists():
        db_path.unlink()

    conn = init_db(db_path)

    # 1. Discover projects
    projects = _collect_projects(root)
    print(f"Found {len(projects)} projects.")

    cur = conn.cursor()
    project_ids: dict[str, int] = {}
    for proj in projects:
        cur.execute(
            "INSERT OR IGNORE INTO projects (name, path, domain, platform) VALUES (?,?,?,?)",
            (proj["name"], proj["path"], proj["domain"], proj["platform"]),
        )
        pid = cur.execute("SELECT id FROM projects WHERE path=?", (proj["path"],)).fetchone()[0]
        project_ids[proj["path"]] = pid
    conn.commit()

    # 2. Run Roslyn analyzer
    print("Running Roslyn analyzer...")
    file_data_list = _run_roslyn(root, verbose=verbose)
    print(f"  Roslyn analyzed {len(file_data_list)} files.")

    _ingest_roslyn(file_data_list, root, projects, project_ids, conn)
    conn.commit()
    print(f"  Ingested C# data.")

    # 3. XAML + config JSON
    xaml_count = 0
    for proj in projects:
        pid = project_ids[proj["path"]]
        for xf in proj["dir"].rglob("*.xaml"):
            if "obj" not in xf.parts and "bin" not in xf.parts:
                _process_xaml(xf, root, pid, conn)
                xaml_count += 1
    print(f"  Processed {xaml_count} XAML files.")

    json_count = 0
    for jf in root.rglob("appConfiguration*.json"):
        if "obj" not in jf.parts and "bin" not in jf.parts:
            _process_json_config(jf, root, conn)
            json_count += 1
    print(f"  Processed {json_count} config JSON files.")
    conn.commit()

    # 4. Post-processing
    print("Resolving relationships...")
    _resolve_relationships(conn)
    print("Building features index...")
    _build_features(conn)
    conn.commit()

    # 5. Summary
    tables = [
        "projects", "files", "types", "methods", "properties",
        "relationships", "usings", "xaml_views", "registrations",
        "endpoints", "config_keys", "features",
        "constructor_injections", "field_declarations", "method_calls",
    ]
    print("\nGraph complete:")
    for t in tables:
        print(f"  {t:<22}: {count(conn, t):>6,}")
    mb = db_path.stat().st_size / 1024 / 1024
    print(f"  DB: {db_path}  ({mb:.1f} MB)")
    conn.close()
