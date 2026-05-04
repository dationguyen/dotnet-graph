"""Smoke tests for all PR changes. Run with the project venv Python."""

import os
import sys
import json
import sqlite3
import tempfile
import hashlib
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
results = []


def check(name, fn):
    try:
        fn()
        print(f"  {PASS}  {name}")
        results.append((name, True, None))
    except Exception as e:
        print(f"  {FAIL}  {name}")
        print(f"       {type(e).__name__}: {e}")
        results.append((name, False, str(e)))


# ── 1. Imports ─────────────────────────────────────────────────────────────────
print("\n[1] Imports")

def _import_builder():
    from dotnet_graph.builder import (
        build, _hash_file, _compute_all_hashes, _load_stored_hashes,
        _delete_file_data, _store_hashes, _store_build_meta,
        _is_analyzable_cs, _ingest_xaml_and_config,
    )

def _import_db():
    from dotnet_graph.db import init_db, open_db, count, SCHEMA
    assert "file_hashes" in SCHEMA
    assert "build_meta" in SCHEMA

def _import_registry():
    from dotnet_graph.registry import register, deregister, list_instances, prune

def _import_api():
    from dotnet_graph.api import create_app, router
    from fastapi import FastAPI
    assert isinstance(create_app(Path("/tmp/fake.db")), FastAPI)

def _import_main():
    from dotnet_graph.main import serve, _start_api_server, _get_db

def _import_cli():
    from dotnet_graph.cli import cli
    cmd_names = [c.name for c in cli.commands.values()]
    assert "build" in cmd_names
    assert "serve" in cmd_names
    assert "api" in cmd_names
    assert "list" in cmd_names
    assert "install" in cmd_names
    assert "status" in cmd_names
    assert "obsidian" in cmd_names

check("builder — all new symbols importable", _import_builder)
check("db — file_hashes and build_meta in SCHEMA", _import_db)
check("registry — all symbols importable", _import_registry)
check("api — create_app returns FastAPI instance", _import_api)
check("main — _start_api_server importable", _import_main)
check("cli — all 7 commands registered (build,serve,api,list,install,status,obsidian)", _import_cli)


# ── 2. Database schema ─────────────────────────────────────────────────────────
print("\n[2] Database schema")

def _schema_file_hashes():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    try:
        from dotnet_graph.db import init_db
        conn = init_db(db)
        conn.execute("INSERT INTO file_hashes (path, sha256, analyzed_at) VALUES (?,?,?)",
                     ("foo/bar.cs", "abc123", "2026-01-01T00:00:00"))
        conn.commit()
        row = conn.execute("SELECT * FROM file_hashes WHERE path='foo/bar.cs'").fetchone()
        assert row["sha256"] == "abc123"
        conn.close()
    finally:
        db.unlink(missing_ok=True)

def _schema_build_meta():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    try:
        from dotnet_graph.db import init_db
        conn = init_db(db)
        conn.execute("INSERT INTO build_meta (key, value) VALUES (?,?)", ("last_built_at", "2026-01-01"))
        conn.commit()
        row = conn.execute("SELECT value FROM build_meta WHERE key='last_built_at'").fetchone()
        assert row[0] == "2026-01-01"
        conn.close()
    finally:
        db.unlink(missing_ok=True)

check("file_hashes table — insert and read", _schema_file_hashes)
check("build_meta table — insert and read", _schema_build_meta)


# ── 3. Write lock ──────────────────────────────────────────────────────────────
print("\n[3] Write lock")

def _lock_fails_fast():
    from filelock import FileLock
    with tempfile.TemporaryDirectory() as d:
        lock_path = Path(d) / "knowledge.lock"
        outer = FileLock(str(lock_path))
        outer.acquire()
        try:
            from dotnet_graph.builder import build
            # A second lock attempt on the same file should raise RuntimeError
            inner = FileLock(str(lock_path), timeout=0)
            try:
                inner.acquire()
                inner.release()
                raise AssertionError("Expected lock contention error")
            except Exception as e:
                assert "Timeout" in type(e).__name__ or "timeout" in str(e).lower() or "Lock" in type(e).__name__
        finally:
            outer.release()

check("write lock — second acquire raises Timeout immediately", _lock_fails_fast)


# ── 4. Incremental build helpers ───────────────────────────────────────────────
print("\n[4] Incremental build helpers")

def _hash_file_deterministic():
    from dotnet_graph.builder import _hash_file
    with tempfile.NamedTemporaryFile(suffix=".cs", delete=False, mode="w") as f:
        f.write("public class Foo {}")
        p = Path(f.name)
    try:
        h1 = _hash_file(p)
        h2 = _hash_file(p)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex
    finally:
        p.unlink()

def _hash_changes_on_edit():
    from dotnet_graph.builder import _hash_file
    with tempfile.NamedTemporaryFile(suffix=".cs", delete=False, mode="w") as f:
        f.write("public class Foo {}")
        p = Path(f.name)
    try:
        h1 = _hash_file(p)
        p.write_text("public class Bar {}")
        h2 = _hash_file(p)
        assert h1 != h2
    finally:
        p.unlink()

def _compute_all_hashes_filters_generated():
    from dotnet_graph.builder import _compute_all_hashes, _is_analyzable_cs
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # Normal file — should be hashed
        (root / "MyClass.cs").write_text("class A {}")
        # Generated files — should be excluded
        (root / "MyClass.g.cs").write_text("class B {}")
        (root / "MyView.designer.cs").write_text("class C {}")
        # obj/bin directories — should be excluded
        (root / "obj").mkdir()
        (root / "obj" / "Debug.cs").write_text("class D {}")

        hashes = _compute_all_hashes(root)
        assert "MyClass.cs" in hashes, f"expected MyClass.cs, got: {list(hashes)}"
        assert "MyClass.g.cs" not in hashes
        assert "MyView.designer.cs" not in hashes
        assert not any("obj" in k for k in hashes)

def _load_stored_hashes_empty_db():
    from dotnet_graph.builder import _load_stored_hashes
    from dotnet_graph.db import init_db
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    try:
        conn = init_db(db)
        result = _load_stored_hashes(conn)
        assert result == {}
        conn.close()
    finally:
        db.unlink(missing_ok=True)

def _delete_file_data_cascades():
    from dotnet_graph.builder import _delete_file_data
    from dotnet_graph.db import init_db
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    try:
        conn = init_db(db)
        # Insert a project, file, type, method
        conn.execute("INSERT INTO projects (name, path, domain, platform) VALUES (?,?,?,?)",
                     ("TestProj", "TestProj/TestProj.csproj", "Test", "shared"))
        pid = conn.execute("SELECT id FROM projects WHERE name='TestProj'").fetchone()[0]
        conn.execute("INSERT INTO files (project_id, path, namespace) VALUES (?,?,?)",
                     (pid, "TestProj/Foo.cs", "Test"))
        fid = conn.execute("SELECT id FROM files WHERE path='TestProj/Foo.cs'").fetchone()[0]
        conn.execute("INSERT INTO types (file_id, project_id, name, full_name, kind, line) VALUES (?,?,?,?,?,?)",
                     (fid, pid, "Foo", "Test.Foo", "class", 1))
        tid = conn.execute("SELECT id FROM types WHERE name='Foo'").fetchone()[0]
        conn.execute("INSERT INTO methods (file_id, type_id, project_id, name, return_type, parameters, visibility, is_async, is_static, is_override, line) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (fid, tid, pid, "DoThing", "void", "()", "public", 0, 0, 0, 5))
        conn.execute("INSERT INTO relationships (from_type, to_type, kind) VALUES (?,?,?)",
                     ("Test.Foo", "IFoo", "implements"))
        conn.commit()

        # Verify data exists
        assert conn.execute("SELECT COUNT(*) FROM types").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM methods").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0] == 1

        # Delete the file
        _delete_file_data(conn, ["TestProj/Foo.cs"])
        conn.commit()

        # Everything should be gone
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM types").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM methods").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0] == 0
        conn.close()
    finally:
        db.unlink(missing_ok=True)

def _store_build_meta_writes_all_keys():
    from dotnet_graph.builder import _store_build_meta
    from dotnet_graph.db import init_db
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    try:
        conn = init_db(db)
        _store_build_meta(conn, mode="full", files_analyzed=42, total_files=100, duration_s=3.7)
        conn.commit()
        meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM build_meta")}
        assert meta["build_mode"] == "full"
        assert meta["files_analyzed"] == "42"
        assert meta["total_files"] == "100"
        assert float(meta["duration_seconds"]) == 3.7
        assert "last_built_at" in meta
        assert "tool_version" in meta
        conn.close()
    finally:
        db.unlink(missing_ok=True)

check("_hash_file — deterministic SHA-256", _hash_file_deterministic)
check("_hash_file — changes when file content changes", _hash_changes_on_edit)
check("_compute_all_hashes — filters .g.cs, .designer.cs, obj/", _compute_all_hashes_filters_generated)
check("_load_stored_hashes — returns {} on fresh DB", _load_stored_hashes_empty_db)
check("_delete_file_data — cascades to types, methods, relationships", _delete_file_data_cascades)
check("_store_build_meta — writes all expected keys", _store_build_meta_writes_all_keys)


# ── 5. Registry ────────────────────────────────────────────────────────────────
print("\n[5] Instance registry")

def _registry_register_deregister():
    from dotnet_graph import registry as reg
    import unittest.mock as mock

    # Redirect registry to a temp dir to avoid polluting ~/.dotnet-graph
    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        with mock.patch.object(reg, "_dir", return_value=tmp_dir):
            # Monkey-patch the path functions
            original_registry_path = reg._registry_path
            original_lock_path = reg._lock_path
            reg._registry_path = lambda: tmp_dir / "registry.json"
            reg._lock_path = lambda: tmp_dir / ".registry.lock"
            try:
                reg.register("/my/project", "/my/project/.dotnet-graph/knowledge.db", "stdio", "0.0.0.0", 8000)
                instances = reg.list_instances()
                assert len(instances) == 1
                assert instances[0]["root"] == "/my/project"
                assert instances[0]["transport"] == "stdio"
                assert instances[0]["pid"] == os.getpid()

                reg.deregister("/my/project/.dotnet-graph/knowledge.db")
                instances = reg.list_instances()
                assert len(instances) == 0
            finally:
                reg._registry_path = original_registry_path
                reg._lock_path = original_lock_path

def _registry_prunes_dead_pids():
    from dotnet_graph import registry as reg
    import unittest.mock as mock

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        reg_file = tmp_dir / "registry.json"
        lock_file = tmp_dir / ".registry.lock"

        original_registry_path = reg._registry_path
        original_lock_path = reg._lock_path
        reg._registry_path = lambda: reg_file
        reg._lock_path = lambda: lock_file
        try:
            # Write a dead-PID entry directly
            reg_file.write_text(json.dumps({
                "/fake/db": {
                    "root": "/fake",
                    "db_path": "/fake/db",
                    "transport": "stdio",
                    "pid": 999999999,  # definitely dead
                    "started_at": "2020-01-01T00:00:00",
                }
            }))
            instances = reg.list_instances()  # triggers prune
            assert len(instances) == 0
            # File should now be empty
            assert reg_file.read_text() == "{}"
        finally:
            reg._registry_path = original_registry_path
            reg._lock_path = original_lock_path

def _registry_http_entry_has_url():
    from dotnet_graph import registry as reg

    with tempfile.TemporaryDirectory() as d:
        tmp_dir = Path(d)
        reg_file = tmp_dir / "registry.json"
        lock_file = tmp_dir / ".registry.lock"

        original_registry_path = reg._registry_path
        original_lock_path = reg._lock_path
        reg._registry_path = lambda: reg_file
        reg._lock_path = lambda: lock_file
        try:
            reg.register("/proj", "/proj/knowledge.db", "http", "0.0.0.0", 9000)
            instances = reg.list_instances()
            assert instances[0]["url"] == "http://0.0.0.0:9000/sse"
            assert instances[0]["port"] == 9000
        finally:
            reg._registry_path = original_registry_path
            reg._lock_path = original_lock_path

check("registry — register + deregister round-trip", _registry_register_deregister)
check("registry — dead PIDs pruned on list_instances", _registry_prunes_dead_pids)
check("registry — HTTP entries include url field", _registry_http_entry_has_url)


# ── 6. REST API ────────────────────────────────────────────────────────────────
print("\n[6] REST API")

def _api_routes_registered():
    from dotnet_graph.api import create_app
    app = create_app(Path("/tmp/fake.db"))
    routes = {r.path for r in app.routes}
    expected = [
        "/query/types",
        "/query/types/{type_name}/members",
        "/query/types/{type_name}/implementors",
        "/query/types/{type_name}/injectors",
        "/query/method-calls",
        "/query/callers",
        "/query/di-registrations",
        "/query/endpoints",
        "/query/features",
        "/query/search",
        "/query/stats",
    ]
    for path in expected:
        assert path in routes, f"Missing route: {path}"

def _api_returns_503_no_db():
    from dotnet_graph.api import create_app, _set_db
    from fastapi.testclient import TestClient

    app = create_app(Path("/nonexistent/path/knowledge.db"))
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/query/types?name=Foo")
    assert resp.status_code == 503, f"Expected 503, got {resp.status_code}"

def _api_find_types_returns_json():
    from dotnet_graph.api import create_app, _set_db
    from dotnet_graph.db import init_db
    from fastapi.testclient import TestClient

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    try:
        conn = init_db(db)
        conn.execute("INSERT INTO projects (name,path,domain,platform) VALUES (?,?,?,?)",
                     ("P","P/P.csproj","D","shared"))
        pid = conn.execute("SELECT id FROM projects WHERE name='P'").fetchone()[0]
        conn.execute("INSERT INTO files (project_id,path,namespace) VALUES (?,?,?)",
                     (pid,"P/Auth.cs","P"))
        fid = conn.execute("SELECT id FROM files").fetchone()[0]
        conn.execute("INSERT INTO types (file_id,project_id,name,full_name,kind,line) VALUES (?,?,?,?,?,?)",
                     (fid,pid,"AuthService","P.AuthService","class",1))
        conn.commit()
        conn.close()

        app = create_app(db)
        client = TestClient(app)
        resp = client.get("/query/types?name=Auth")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "AuthService"
        assert data[0]["full_name"] == "P.AuthService"
    finally:
        db.unlink(missing_ok=True)

def _api_stats_includes_build_meta():
    from dotnet_graph.api import create_app
    from dotnet_graph.db import init_db
    from dotnet_graph.builder import _store_build_meta
    from fastapi.testclient import TestClient

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    try:
        conn = init_db(db)
        _store_build_meta(conn, mode="full", files_analyzed=10, total_files=10, duration_s=1.5)
        conn.commit()
        conn.close()

        app = create_app(db)
        client = TestClient(app)
        resp = client.get("/query/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "build" in data
        assert "counts" in data
        assert data["build"]["build_mode"] == "full"
        assert "types" in data["counts"]
    finally:
        db.unlink(missing_ok=True)

def _api_search_returns_typed_sections():
    from dotnet_graph.api import create_app
    from dotnet_graph.db import init_db
    from fastapi.testclient import TestClient

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    try:
        conn = init_db(db)
        conn.commit()
        conn.close()

        app = create_app(db)
        client = TestClient(app)
        resp = client.get("/query/search?q=Foo")
        assert resp.status_code == 200
        data = resp.json()
        assert "types" in data
        assert "methods" in data
        assert "properties" in data
    finally:
        db.unlink(missing_ok=True)

def _api_404_on_missing_type():
    from dotnet_graph.api import create_app
    from dotnet_graph.db import init_db
    from fastapi.testclient import TestClient

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Path(f.name)
    try:
        conn = init_db(db)
        conn.commit()
        conn.close()

        app = create_app(db)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/query/types/NonExistentType/members")
        assert resp.status_code == 404
    finally:
        db.unlink(missing_ok=True)

def _api_openapi_spec_accessible():
    from dotnet_graph.api import create_app
    from fastapi.testclient import TestClient
    app = create_app(Path("/tmp/fake.db"))
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["title"] == "dotnet-graph"
    assert "/query/types" in spec["paths"]

check("api — all 11 routes registered", _api_routes_registered)
check("api — GET /query/types returns 503 when DB missing", _api_returns_503_no_db)
check("api — GET /query/types returns JSON array from real DB", _api_find_types_returns_json)
check("api — GET /query/stats includes build_meta", _api_stats_includes_build_meta)
check("api — GET /query/search returns {types, methods, properties}", _api_search_returns_typed_sections)
check("api — GET /query/types/{name}/members returns 404 for unknown type", _api_404_on_missing_type)
check("api — GET /openapi.json returns valid spec with all paths", _api_openapi_spec_accessible)


# ── 7. CLI structure ───────────────────────────────────────────────────────────
print("\n[7] CLI options")

def _cli_build_has_full_flag():
    from click.testing import CliRunner
    from dotnet_graph.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["build", "--help"])
    assert "--full" in result.output

def _cli_serve_has_transport_and_api_port():
    from click.testing import CliRunner
    from dotnet_graph.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["serve", "--help"])
    assert "--transport" in result.output
    assert "--api-port" in result.output
    assert "--port" in result.output

def _cli_install_has_transport():
    from click.testing import CliRunner
    from dotnet_graph.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["install", "--help"])
    assert "--transport" in result.output

def _cli_api_command_exists():
    from click.testing import CliRunner
    from dotnet_graph.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["api", "--help"])
    assert result.exit_code == 0
    assert "--port" in result.output

def _cli_list_command_exists():
    from click.testing import CliRunner
    from dotnet_graph.cli import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["list", "--help"])
    assert result.exit_code == 0

check("cli build — has --full flag", _cli_build_has_full_flag)
check("cli serve — has --transport, --port, --api-port", _cli_serve_has_transport_and_api_port)
check("cli install — has --transport flag", _cli_install_has_transport)
check("cli api — command exists with --port", _cli_api_command_exists)
check("cli list — command exists", _cli_list_command_exists)


# ── Summary ────────────────────────────────────────────────────────────────────
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total = len(results)

print(f"\n{'─'*50}")
print(f"  {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} failed)")
    print("\nFailed tests:")
    for name, ok, err in results:
        if not ok:
            print(f"  ✗ {name}")
            print(f"    {err}")
else:
    print("  — all good")
print()

sys.exit(0 if failed == 0 else 1)
