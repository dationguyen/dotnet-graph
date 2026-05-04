"""Integration tests — runs the actual Roslyn build pipeline against a sample .NET solution.

Requires: dotnet SDK, project venv with dotnet-graph installed.
Run with: .venv/bin/python tests/integration_test.py
"""

import sys
import shutil
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
results = []

FIXTURE = Path(__file__).parent / "fixtures" / "SampleSolution"


def check(name, fn):
    try:
        fn()
        print(f"  {PASS}  {name}")
        results.append((name, True, None))
    except Exception as e:
        print(f"  {FAIL}  {name}")
        print(f"       {type(e).__name__}: {e}")
        results.append((name, False, str(e)))


# ── Setup: build against the sample solution ───────────────────────────────────

print("\n[setup] Building graph against SampleSolution fixture...")
print(f"  root: {FIXTURE}")

# Use a temp DB so we don't pollute the fixture directory
_tmp_dir = tempfile.mkdtemp(prefix="dotnet-graph-test-")
DB = Path(_tmp_dir) / "knowledge.db"

try:
    from dotnet_graph.builder import build
    t0 = time.monotonic()
    build(FIXTURE, DB, verbose=True, incremental=False)
    build_duration = time.monotonic() - t0
    print(f"  Full build completed in {build_duration:.1f}s\n")
    BUILD_OK = True
except Exception as e:
    print(f"  {FAIL} Build failed: {e}")
    BUILD_OK = False

if not BUILD_OK:
    print("\nCannot run integration tests without a successful build.")
    sys.exit(1)

from dotnet_graph.db import open_db
conn = open_db(DB)


# ── 1. Projects indexed ────────────────────────────────────────────────────────
print("[1] Projects")

def _two_projects_found():
    rows = conn.execute("SELECT name FROM projects ORDER BY name").fetchall()
    names = [r["name"] for r in rows]
    assert "Core" in names, f"Core project missing. Got: {names}"
    assert "Api" in names, f"Api project missing. Got: {names}"

def _projects_have_domain():
    rows = conn.execute("SELECT name, domain FROM projects").fetchall()
    for r in rows:
        assert r["domain"], f"Project {r['name']} has no domain"

check("2 projects indexed (Core, Api)", _two_projects_found)
check("all projects have a domain tag", _projects_have_domain)


# ── 2. Types indexed ───────────────────────────────────────────────────────────
print("\n[2] Types")

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

def _check_type(name, kind):
    def _fn():
        row = conn.execute(
            "SELECT name, kind FROM types WHERE name=?", (name,)
        ).fetchone()
        assert row, f"Type '{name}' not found in DB"
        assert row["kind"] == kind, f"Expected kind={kind}, got {row['kind']}"
    return _fn

for type_name, type_kind in EXPECTED_TYPES:
    check(f"type '{type_name}' indexed as {type_kind}", _check_type(type_name, type_kind))


# ── 3. Relationships ───────────────────────────────────────────────────────────
print("\n[3] Relationships")

def _userservice_implements_iuserservice():
    row = conn.execute("""
        SELECT * FROM relationships
        WHERE from_type LIKE '%UserService' AND to_type LIKE '%IUserService'
        AND kind = 'implements'
    """).fetchone()
    assert row, "UserService → IUserService (implements) not found"

def _userrepository_implements_iuserrepository():
    row = conn.execute("""
        SELECT * FROM relationships
        WHERE from_type LIKE '%UserRepository' AND to_type LIKE '%IUserRepository'
        AND kind = 'implements'
    """).fetchone()
    assert row, "UserRepository → IUserRepository (implements) not found"

check("UserService implements IUserService", _userservice_implements_iuserservice)
check("UserRepository implements IUserRepository", _userrepository_implements_iuserrepository)


# ── 4. Constructor injections ──────────────────────────────────────────────────
print("\n[4] Constructor injections (DI)")

def _userservice_injects_iuserrepository():
    row = conn.execute("""
        SELECT ci.param_type FROM constructor_injections ci
        JOIN types t ON ci.type_id = t.id
        WHERE t.name = 'UserService' AND ci.param_type LIKE '%IUserRepository%'
    """).fetchone()
    assert row, "UserService does not show IUserRepository injection"

def _userviewmodel_injects_iuserservice():
    row = conn.execute("""
        SELECT ci.param_type FROM constructor_injections ci
        JOIN types t ON ci.type_id = t.id
        WHERE t.name = 'UserViewModel' AND ci.param_type LIKE '%IUserService%'
    """).fetchone()
    assert row, "UserViewModel does not show IUserService injection"

def _usercontroller_injects_iuserservice():
    row = conn.execute("""
        SELECT ci.param_type FROM constructor_injections ci
        JOIN types t ON ci.type_id = t.id
        WHERE t.name = 'UserController' AND ci.param_type LIKE '%IUserService%'
    """).fetchone()
    assert row, "UserController does not show IUserService injection"

check("UserService injects IUserRepository", _userservice_injects_iuserrepository)
check("UserViewModel injects IUserService", _userviewmodel_injects_iuserservice)
check("UserController injects IUserService", _usercontroller_injects_iuserservice)


# ── 5. Methods ─────────────────────────────────────────────────────────────────
print("\n[5] Methods")

def _userservice_has_async_methods():
    rows = conn.execute("""
        SELECT m.name, m.is_async FROM methods m
        JOIN types t ON m.type_id = t.id
        WHERE t.name = 'UserService'
    """).fetchall()
    names = {r["name"] for r in rows}
    assert "GetUserAsync" in names, f"GetUserAsync missing from UserService. Got: {names}"
    assert "ListUsersAsync" in names
    assert "CreateUserAsync" in names
    for r in rows:
        if r["name"] in ("GetUserAsync", "ListUsersAsync", "CreateUserAsync"):
            assert r["is_async"], f"{r['name']} should be async"

def _userrepository_has_three_methods():
    rows = conn.execute("""
        SELECT m.name FROM methods m
        JOIN types t ON m.type_id = t.id
        WHERE t.name = 'UserRepository'
    """).fetchall()
    names = {r["name"] for r in rows}
    assert {"GetByIdAsync", "GetAllAsync", "SaveAsync"}.issubset(names), \
        f"Missing methods in UserRepository. Got: {names}"

check("UserService has 3 async methods", _userservice_has_async_methods)
check("UserRepository has GetByIdAsync, GetAllAsync, SaveAsync", _userrepository_has_three_methods)


# ── 6. Method calls ────────────────────────────────────────────────────────────
print("\n[6] Method call graph")

def _userservice_getuser_calls_repository():
    row = conn.execute("""
        SELECT mc.callee_method FROM method_calls mc
        JOIN types t ON mc.caller_type_id = t.id
        WHERE t.name = 'UserService' AND mc.caller_method = 'GetUserAsync'
        AND mc.callee_method = 'GetByIdAsync'
    """).fetchone()
    assert row, "UserService.GetUserAsync → _userRepository.GetByIdAsync call not tracked"

def _userviewmodel_load_calls_service():
    row = conn.execute("""
        SELECT mc.callee_method FROM method_calls mc
        JOIN types t ON mc.caller_type_id = t.id
        WHERE t.name = 'UserViewModel' AND mc.caller_method = 'LoadAsync'
        AND mc.callee_method = 'ListUsersAsync'
    """).fetchone()
    assert row, "UserViewModel.LoadAsync → _userService.ListUsersAsync call not tracked"

check("UserService.GetUserAsync → _userRepository.GetByIdAsync tracked", _userservice_getuser_calls_repository)
check("UserViewModel.LoadAsync → _userService.ListUsersAsync tracked", _userviewmodel_load_calls_service)


# ── 7. DI registrations ────────────────────────────────────────────────────────
print("\n[7] DI registrations")

def _appsetup_registers_userservice():
    row = conn.execute("""
        SELECT interface_type, impl_type, lifetime FROM registrations
        WHERE interface_type LIKE '%IUserService%'
    """).fetchone()
    assert row, "IUserService registration not found"
    assert "UserService" in (row["impl_type"] or ""), \
        f"Expected UserService impl, got: {row['impl_type']}"
    assert row["lifetime"] == "transient", f"Expected transient, got: {row['lifetime']}"

def _appsetup_registers_userrepository_singleton():
    row = conn.execute("""
        SELECT interface_type, impl_type, lifetime FROM registrations
        WHERE interface_type LIKE '%IUserRepository%'
    """).fetchone()
    assert row, "IUserRepository registration not found"
    assert row["lifetime"] == "singleton", f"Expected singleton, got: {row['lifetime']}"

check("AppSetup registers IUserService → UserService (transient)", _appsetup_registers_userservice)
check("AppSetup registers IUserRepository → UserRepository (singleton)", _appsetup_registers_userrepository_singleton)


# ── 8. Feature index ───────────────────────────────────────────────────────────
print("\n[8] Feature index")

def _user_feature_indexed():
    row = conn.execute(
        "SELECT name, viewmodel, service FROM features WHERE name = 'User'"
    ).fetchone()
    assert row, "User feature not indexed (expected from UserViewModel)"
    assert "UserViewModel" in (row["viewmodel"] or ""), \
        f"Wrong viewmodel: {row['viewmodel']}"
    assert row["service"] is not None, "User feature has no associated service"

check("'User' feature indexed from UserViewModel + UserService", _user_feature_indexed)


# ── 9. Build metadata ──────────────────────────────────────────────────────────
print("\n[9] Build metadata")

def _build_meta_populated():
    meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM build_meta")}
    assert "last_built_at" in meta, "last_built_at missing from build_meta"
    assert meta["build_mode"] == "full", f"Expected full, got {meta.get('build_mode')}"
    assert int(meta["files_analyzed"]) > 0, "files_analyzed should be > 0"
    assert float(meta["duration_seconds"]) > 0, "duration_seconds should be > 0"
    assert "tool_version" in meta

def _file_hashes_populated():
    count = conn.execute("SELECT COUNT(*) FROM file_hashes").fetchone()[0]
    assert count > 0, "file_hashes table is empty after full build"
    # Verify all hashes are 64-char hex (SHA-256)
    bad = conn.execute("SELECT path FROM file_hashes WHERE LENGTH(sha256) != 64").fetchone()
    assert not bad, f"Invalid SHA-256 hash for {bad}"

check("build_meta has all expected keys after full build", _build_meta_populated)
check("file_hashes populated with valid SHA-256 values", _file_hashes_populated)


# ── 10. Incremental rebuild ────────────────────────────────────────────────────
print("\n[10] Incremental rebuild")

USER_SERVICE = FIXTURE / "Core" / "Services" / "UserService.cs"
original_content = USER_SERVICE.read_text()

def _incremental_skips_unchanged():
    result = {}
    def _run():
        build(FIXTURE, DB, verbose=False, incremental=True)
        meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM build_meta")}
        result["analyzed"] = int(meta["files_analyzed"])
        result["total"] = int(meta["total_files"])
    _run()
    assert result["analyzed"] == 0, \
        f"Expected 0 files analyzed (nothing changed), got {result['analyzed']}"

def _incremental_reanalyzes_changed_file():
    # Modify UserService.cs
    USER_SERVICE.write_text(original_content + "\n// incremental test marker")
    try:
        build(FIXTURE, DB, verbose=False, incremental=True)
        meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM build_meta")}
        analyzed = int(meta["files_analyzed"])
        assert analyzed == 1, \
            f"Expected exactly 1 file re-analyzed after edit, got {analyzed}"
        assert meta["build_mode"] == "incremental"
    finally:
        USER_SERVICE.write_text(original_content)  # restore

def _incremental_removes_deleted_file():
    # Copy a file, build, delete it, rebuild — it should vanish from DB
    extra = FIXTURE / "Core" / "Services" / "TempService.cs"
    extra.write_text("""
namespace SampleSolution.Core.Services;
public class TempService { public void DoNothing() {} }
""")
    try:
        build(FIXTURE, DB, verbose=False, incremental=True)
        row = conn.execute("SELECT name FROM types WHERE name='TempService'").fetchone()
        assert row, "TempService not indexed after being added"

        extra.unlink()
        build(FIXTURE, DB, verbose=False, incremental=True)
        row = conn.execute("SELECT name FROM types WHERE name='TempService'").fetchone()
        assert not row, "TempService still in DB after file deleted"
    finally:
        if extra.exists():
            extra.unlink()

check("incremental build — 0 files analyzed when nothing changed", _incremental_skips_unchanged)
check("incremental build — 1 file re-analyzed after editing UserService.cs", _incremental_reanalyzes_changed_file)
check("incremental build — deleted file removed from DB", _incremental_removes_deleted_file)


# ── 11. REST API against real DB ───────────────────────────────────────────────
print("\n[11] REST API against real DB")

def _api_find_userservice():
    from dotnet_graph.api import create_app, _set_db
    from fastapi.testclient import TestClient
    app = create_app(DB)
    client = TestClient(app)
    resp = client.get("/query/types?name=UserService")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    names = [r["name"] for r in data]
    assert "UserService" in names

def _api_members_of_userservice():
    from dotnet_graph.api import create_app
    from fastapi.testclient import TestClient
    app = create_app(DB)
    client = TestClient(app)
    resp = client.get("/query/types/UserService/members")
    assert resp.status_code == 200
    data = resp.json()
    method_names = [m["name"] for m in data["methods"]]
    assert "GetUserAsync" in method_names
    assert "CreateUserAsync" in method_names
    ctor_types = [c["param_type"] for c in data["constructor_parameters"]]
    assert any("IUserRepository" in t for t in ctor_types)

def _api_injectors_of_iuserservice():
    from dotnet_graph.api import create_app
    from fastapi.testclient import TestClient
    app = create_app(DB)
    client = TestClient(app)
    resp = client.get("/query/types/IUserService/injectors")
    assert resp.status_code == 200
    data = resp.json()
    full_names = [r["full_name"] for r in data]
    assert any("UserViewModel" in n for n in full_names), \
        f"UserViewModel not in injectors of IUserService: {full_names}"
    assert any("UserController" in n for n in full_names)

def _api_di_registrations():
    from dotnet_graph.api import create_app
    from fastapi.testclient import TestClient
    app = create_app(DB)
    client = TestClient(app)
    resp = client.get("/query/di-registrations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
    lifetimes = {r["lifetime"] for r in data}
    assert "transient" in lifetimes
    assert "singleton" in lifetimes

check("REST API — GET /query/types?name=UserService returns results", _api_find_userservice)
check("REST API — GET /query/types/UserService/members has methods + ctor params", _api_members_of_userservice)
check("REST API — GET /query/types/IUserService/injectors finds UserViewModel + UserController", _api_injectors_of_iuserservice)
check("REST API — GET /query/di-registrations returns transient + singleton entries", _api_di_registrations)


# ── Cleanup ────────────────────────────────────────────────────────────────────
conn.close()
shutil.rmtree(_tmp_dir, ignore_errors=True)


# ── Summary ────────────────────────────────────────────────────────────────────
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total = len(results)

print(f"\n{'─'*50}")
print(f"  {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} failed)\n")
    print("Failed tests:")
    for name, ok, err in results:
        if not ok:
            print(f"  ✗ {name}")
            print(f"    {err}")
else:
    print("  — all good")
print()

sys.exit(0 if failed == 0 else 1)
