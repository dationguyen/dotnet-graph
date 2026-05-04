"""Integration tests — runs the actual Roslyn build pipeline against a sample .NET solution.

Requires: dotnet SDK, project venv with dotnet-graph installed.
Run with: uv run --with pytest pytest tests/integration_test.py -v
"""

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURE = Path(__file__).parent / "fixtures" / "SampleSolution"


@pytest.fixture(scope="session")
def graph_db():
    from dotnet_graph.builder import build
    from dotnet_graph.db import open_db

    tmp_dir = tempfile.mkdtemp(prefix="dotnet-graph-test-")
    db_path = Path(tmp_dir) / "knowledge.db"
    build(FIXTURE, db_path, verbose=True, incremental=False)
    conn = open_db(db_path)

    yield conn, db_path

    conn.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── 1. Projects ────────────────────────────────────────────────────────────────

def test_projects_indexed(graph_db):
    conn, _ = graph_db
    rows = conn.execute("SELECT name FROM projects ORDER BY name").fetchall()
    names = [r["name"] for r in rows]
    assert "Core" in names
    assert "Api" in names


def test_projects_have_domain(graph_db):
    conn, _ = graph_db
    for r in conn.execute("SELECT name, domain FROM projects"):
        assert r["domain"], f"Project {r['name']} has no domain"


# ── 2. Types ───────────────────────────────────────────────────────────────────

EXPECTED_TYPES = [
    ("User", "class"),
    ("IUserRepository", "interface"),
    ("UserRepository", "class"),
    ("IUserService", "interface"),
    ("UserService", "class"),
    ("UserViewModel", "class"),
    ("UserController", "class"),
    ("AppSetup", "class"),
]


@pytest.mark.parametrize("name,kind", EXPECTED_TYPES)
def test_type_indexed(graph_db, name, kind):
    conn, _ = graph_db
    row = conn.execute("SELECT name, kind FROM types WHERE name=?", (name,)).fetchone()
    assert row, f"Type '{name}' not found in DB"
    assert row["kind"] == kind, f"Expected kind={kind}, got {row['kind']}"


# ── 3. Relationships ───────────────────────────────────────────────────────────

def test_userservice_implements_iuserservice(graph_db):
    conn, _ = graph_db
    row = conn.execute("""
        SELECT * FROM relationships
        WHERE from_type LIKE '%UserService' AND to_type LIKE '%IUserService'
        AND kind = 'implements'
    """).fetchone()
    assert row, "UserService → IUserService (implements) not found"


def test_userrepository_implements_iuserrepository(graph_db):
    conn, _ = graph_db
    row = conn.execute("""
        SELECT * FROM relationships
        WHERE from_type LIKE '%UserRepository' AND to_type LIKE '%IUserRepository'
        AND kind = 'implements'
    """).fetchone()
    assert row, "UserRepository → IUserRepository (implements) not found"


# ── 4. Constructor injections ──────────────────────────────────────────────────

@pytest.mark.parametrize("type_name,param_type", [
    ("UserService", "IUserRepository"),
    ("UserViewModel", "IUserService"),
    ("UserController", "IUserService"),
])
def test_constructor_injection(graph_db, type_name, param_type):
    conn, _ = graph_db
    row = conn.execute("""
        SELECT ci.param_type FROM constructor_injections ci
        JOIN types t ON ci.type_id = t.id
        WHERE t.name = ? AND ci.param_type LIKE ?
    """, (type_name, f"%{param_type}%")).fetchone()
    assert row, f"{type_name} does not show {param_type} injection"


# ── 5. Methods ─────────────────────────────────────────────────────────────────

def test_userservice_async_methods(graph_db):
    conn, _ = graph_db
    rows = conn.execute("""
        SELECT m.name, m.is_async FROM methods m
        JOIN types t ON m.type_id = t.id
        WHERE t.name = 'UserService'
    """).fetchall()
    names = {r["name"] for r in rows}
    assert {"GetUserAsync", "ListUsersAsync", "CreateUserAsync"}.issubset(names)
    for r in rows:
        if r["name"] in ("GetUserAsync", "ListUsersAsync", "CreateUserAsync"):
            assert r["is_async"], f"{r['name']} should be async"


def test_userrepository_methods(graph_db):
    conn, _ = graph_db
    rows = conn.execute("""
        SELECT m.name FROM methods m
        JOIN types t ON m.type_id = t.id
        WHERE t.name = 'UserRepository'
    """).fetchall()
    names = {r["name"] for r in rows}
    assert {"GetByIdAsync", "GetAllAsync", "SaveAsync"}.issubset(names), \
        f"Missing methods in UserRepository. Got: {names}"


# ── 6. Method call graph ───────────────────────────────────────────────────────

def test_userservice_calls_repository(graph_db):
    conn, _ = graph_db
    row = conn.execute("""
        SELECT mc.callee_method FROM method_calls mc
        JOIN types t ON mc.caller_type_id = t.id
        WHERE t.name = 'UserService' AND mc.caller_method = 'GetUserAsync'
        AND mc.callee_method = 'GetByIdAsync'
    """).fetchone()
    assert row, "UserService.GetUserAsync → _userRepository.GetByIdAsync call not tracked"


def test_userviewmodel_calls_service(graph_db):
    conn, _ = graph_db
    row = conn.execute("""
        SELECT mc.callee_method FROM method_calls mc
        JOIN types t ON mc.caller_type_id = t.id
        WHERE t.name = 'UserViewModel' AND mc.caller_method = 'LoadAsync'
        AND mc.callee_method = 'ListUsersAsync'
    """).fetchone()
    assert row, "UserViewModel.LoadAsync → _userService.ListUsersAsync call not tracked"


# ── 7. DI registrations ────────────────────────────────────────────────────────

def test_iuserservice_registration(graph_db):
    conn, _ = graph_db
    row = conn.execute("""
        SELECT interface_type, impl_type, lifetime FROM registrations
        WHERE interface_type LIKE '%IUserService%'
    """).fetchone()
    assert row, "IUserService registration not found"
    assert "UserService" in (row["impl_type"] or ""), \
        f"Expected UserService impl, got: {row['impl_type']}"
    assert row["lifetime"] == "transient", f"Expected transient, got: {row['lifetime']}"


def test_iuserrepository_registration(graph_db):
    conn, _ = graph_db
    row = conn.execute("""
        SELECT interface_type, impl_type, lifetime FROM registrations
        WHERE interface_type LIKE '%IUserRepository%'
    """).fetchone()
    assert row, "IUserRepository registration not found"
    assert row["lifetime"] == "singleton", f"Expected singleton, got: {row['lifetime']}"


# ── 8. Feature index ───────────────────────────────────────────────────────────

def test_user_feature_indexed(graph_db):
    conn, _ = graph_db
    row = conn.execute(
        "SELECT name, viewmodel, service FROM features WHERE name = 'User'"
    ).fetchone()
    assert row, "User feature not indexed (expected from UserViewModel)"
    assert "UserViewModel" in (row["viewmodel"] or ""), f"Wrong viewmodel: {row['viewmodel']}"
    assert row["service"] is not None, "User feature has no associated service"


# ── 9. Build metadata ──────────────────────────────────────────────────────────

def test_build_meta_populated(graph_db):
    conn, _ = graph_db
    meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM build_meta")}
    assert "last_built_at" in meta
    assert meta["build_mode"] == "full", f"Expected full, got {meta.get('build_mode')}"
    assert int(meta["files_analyzed"]) > 0
    assert float(meta["duration_seconds"]) > 0
    assert "tool_version" in meta


def test_file_hashes_populated(graph_db):
    conn, _ = graph_db
    count = conn.execute("SELECT COUNT(*) FROM file_hashes").fetchone()[0]
    assert count > 0, "file_hashes table is empty after full build"
    bad = conn.execute("SELECT path FROM file_hashes WHERE LENGTH(sha256) != 64").fetchone()
    assert not bad, f"Invalid SHA-256 hash for {bad}"


# ── 10. Incremental rebuild ────────────────────────────────────────────────────

def test_incremental_skips_unchanged(graph_db):
    from dotnet_graph.builder import build
    conn, db_path = graph_db
    build(FIXTURE, db_path, verbose=False, incremental=True)
    meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM build_meta")}
    assert int(meta["files_analyzed"]) == 0, \
        f"Expected 0 files analyzed (nothing changed), got {meta['files_analyzed']}"


def test_incremental_reanalyzes_changed_file(graph_db):
    from dotnet_graph.builder import build
    conn, db_path = graph_db
    user_service = FIXTURE / "Core" / "Services" / "UserService.cs"
    original = user_service.read_text()
    user_service.write_text(original + "\n// incremental test marker")
    try:
        build(FIXTURE, db_path, verbose=False, incremental=True)
        meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM build_meta")}
        assert int(meta["files_analyzed"]) == 1, \
            f"Expected 1 file re-analyzed, got {meta['files_analyzed']}"
        assert meta["build_mode"] == "incremental"
    finally:
        user_service.write_text(original)


def test_incremental_removes_deleted_file(graph_db):
    from dotnet_graph.builder import build
    conn, db_path = graph_db
    extra = FIXTURE / "Core" / "Services" / "TempService.cs"
    extra.write_text("""
namespace SampleSolution.Core.Services;
public class TempService { public void DoNothing() {} }
""")
    try:
        build(FIXTURE, db_path, verbose=False, incremental=True)
        row = conn.execute("SELECT name FROM types WHERE name='TempService'").fetchone()
        assert row, "TempService not indexed after being added"

        extra.unlink()
        build(FIXTURE, db_path, verbose=False, incremental=True)
        row = conn.execute("SELECT name FROM types WHERE name='TempService'").fetchone()
        assert not row, "TempService still in DB after file deleted"
    finally:
        if extra.exists():
            extra.unlink()


# ── 11. REST API ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def api_client(graph_db):
    from dotnet_graph.api import create_app
    from fastapi.testclient import TestClient
    _, db_path = graph_db
    return TestClient(create_app(db_path))


def test_api_find_userservice(api_client):
    resp = api_client.get("/query/types?name=UserService")
    assert resp.status_code == 200
    names = [r["name"] for r in resp.json()]
    assert "UserService" in names


def test_api_members_of_userservice(api_client):
    resp = api_client.get("/query/types/UserService/members")
    assert resp.status_code == 200
    data = resp.json()
    method_names = [m["name"] for m in data["methods"]]
    assert "GetUserAsync" in method_names
    assert "CreateUserAsync" in method_names
    ctor_types = [c["param_type"] for c in data["constructor_parameters"]]
    assert any("IUserRepository" in t for t in ctor_types)


def test_api_injectors_of_iuserservice(api_client):
    resp = api_client.get("/query/types/IUserService/injectors")
    assert resp.status_code == 200
    full_names = [r["full_name"] for r in resp.json()]
    assert any("UserViewModel" in n for n in full_names), \
        f"UserViewModel not in injectors: {full_names}"
    assert any("UserController" in n for n in full_names)


def test_api_di_registrations(api_client):
    resp = api_client.get("/query/di-registrations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
    lifetimes = {r["lifetime"] for r in data}
    assert "transient" in lifetimes
    assert "singleton" in lifetimes
