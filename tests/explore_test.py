"""Tests for the explore dashboard pipeline: layers, summaries, tours, exporter.

The pure-function tests (classifier, summaries, tours) need no .NET SDK and run
anywhere. The integration test builds the SampleSolution fixture and exercises the
full exporter, so it needs the dotnet SDK like integration_test.py.

Run: uv run --with pytest pytest tests/explore_test.py -v
"""

import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotnet_graph import layers, summaries, tours  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "SampleSolution"


# ── layers (pure) ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,kind,expected", [
    ("UserViewModel", "class", "presentation"),
    ("UserController", "class", "api"),
    ("UserApiClient", "class", "api"),
    ("UserRepository", "class", "data"),
    ("UserService", "class", "service"),
    ("UserManager", "class", "service"),
    ("UserDto", "class", "model"),
    ("AppSetup", "class", "infra"),
    ("LoginPage", "class", "ui"),
    ("CustomerActivity", "class", "ui"),
    ("Color", "enum", "model"),
])
def test_classify_one_by_name(name, kind, expected):
    assert layers.classify_one(name, kind=kind) == expected


def test_viewcontroller_is_ui_not_api():
    # 'ShareViewController' ends in 'Controller' but is a UI type.
    assert layers.classify_one("ShareViewController", kind="class") == "ui"


def test_interface_classified_by_dename():
    assert layers.classify_one("IUserService", kind="interface") == "service"
    assert layers.classify_one("IUserRepository", kind="interface") == "data"


def test_endpoint_flag_is_ignored():
    # The analyzer's endpoint table is too noisy to drive layers, so is_endpoint
    # must not influence classification at all.
    assert layers.classify_one("SearchViewModel", kind="class", is_endpoint=True) == "presentation"
    assert layers.classify_one("Thing", kind="class", is_endpoint=True) == "other"


def test_networking_names_are_api():
    assert layers.classify_one("IInvokeQueryOverHttp", kind="interface") == "api"
    assert layers.classify_one("WebSocketInstance", kind="class") == "api"
    assert layers.classify_one("GraphQLClientRegistration", kind="class") == "api"


def test_client_namespace_is_not_api():
    # '.Client' namespaces hold DTO/schema contracts, not HTTP clients.
    assert layers.classify_one("FormField", kind="class",
                               namespace="ItOps.ApplicationHosting.Schema.Client") != "api"


def test_ui_base_type():
    assert layers.classify_one("LoginScreen", kind="class", bases=["ContentPage"]) == "ui"


def test_classify_all_resolves_interface_from_implementor():
    types = [
        {"full_name": "App.IThing", "name": "IThing", "kind": "interface", "namespace": "App"},
        {"full_name": "App.Thing", "name": "Thing", "kind": "class", "namespace": "App"},
    ]
    rels = [{"from_type": "App.Thing", "to_type": "App.IThing", "kind": "implements"}]
    # Thing has no naming signal -> 'other'; IThing has none either, but resolves
    # to Thing's layer. Both 'other' here, so resolution is a no-op (stays other).
    out = layers.classify_all(types, rels)
    assert out["App.IThing"] == out["App.Thing"]


def test_classify_all_interface_inherits_service_layer():
    types = [
        {"full_name": "App.IGizmo", "name": "IGizmo", "kind": "interface", "namespace": "App"},
        {"full_name": "App.GizmoProcessor", "name": "GizmoProcessor", "kind": "class", "namespace": "App"},
    ]
    rels = [{"from_type": "App.GizmoProcessor", "to_type": "App.IGizmo", "kind": "implements"}]
    out = layers.classify_all(types, rels)
    assert out["App.GizmoProcessor"] == "service"
    assert out["App.IGizmo"] == "service"  # adopted from implementor


# ── summaries (pure) ───────────────────────────────────────────────────────────

def test_extract_purpose():
    note = (
        "# Thing\n\nstructure...\n\n---\n\n## Notes\n"
        "### Purpose\nDoes the important thing for matters. Extra detail.\n\n"
        "### Key Behaviours\n- stuff\n"
    )
    assert summaries.extract_purpose(note) == "Does the important thing for matters."


def test_extract_purpose_skips_placeholder():
    note = "---\n\n## Notes\n> _No notes yet — add purpose here._\n"
    assert summaries.extract_purpose(note) is None


def test_extract_purpose_absent():
    assert summaries.extract_purpose("# Thing\n\nno notes section") is None


def test_fallback_viewmodel():
    s = summaries.fallback_summary("TaskListViewModel", "class", "presentation")
    assert "Task List" in s and "ViewModel" in s


def test_fallback_interface_with_impls():
    s = summaries.fallback_summary("IFoo", "interface", "service", impl_count=3)
    assert "3 type" in s


def test_summarize_prefers_note():
    note_purposes = {"App.Foo": "The real purpose."}
    s, from_note = summaries.summarize("App.Foo", "Foo", "class", "service", note_purposes=note_purposes)
    assert from_note and s == "The real purpose."


def test_summarize_fallback_when_no_note():
    s, from_note = summaries.summarize("App.Bar", "Bar", "class", "service",
                                       note_purposes={}, injector_count=2)
    assert not from_note and "injected into 2" in s


# ── tours (pure) ───────────────────────────────────────────────────────────────

def test_type_index_drops_ambiguous_short_names():
    idx = tours.build_type_index(["A.Foo", "B.Foo", "A.Bar"])
    assert idx["A.Foo"] == "A.Foo"
    assert "Bar" in idx  # unique short name resolvable
    assert idx["Bar"] == "A.Bar"
    assert "Foo" not in idx  # ambiguous -> dropped


def test_walk_follows_injections_breadth_first():
    idx = tours.build_type_index(["VM", "SvcA", "SvcB", "Repo"])
    inj = {"VM": ["SvcA", "SvcB"], "SvcA": ["Repo"]}
    order = tours._walk("VM", inj, idx)
    assert order[0] == "VM"
    assert set(order) == {"VM", "SvcA", "SvcB", "Repo"}
    assert order.index("SvcA") < order.index("Repo")  # BFS: siblings before grandchild


def test_feature_tour_skips_lonely_viewmodel():
    feats = [{"name": "Lonely", "viewmodel": "App.LonelyViewModel", "domain": "X"}]
    idx = tours.build_type_index(["App.LonelyViewModel"])
    assert tours.build_feature_tours(feats, {}, idx) == []


def test_feature_tour_built_with_dependencies():
    feats = [{"name": "Login", "viewmodel": "App.LoginViewModel", "domain": "Auth"}]
    idx = tours.build_type_index(["App.LoginViewModel", "App.IAuth"])
    inj = {"App.LoginViewModel": ["App.IAuth"]}
    out = tours.build_feature_tours(feats, inj, idx)
    assert len(out) == 1
    assert out[0]["steps"] == ["App.LoginViewModel", "App.IAuth"]


# ── exporter (integration — needs dotnet SDK) ────────────────────────────────────

@pytest.fixture(scope="module")
def fixture_db():
    if not shutil.which("dotnet"):
        pytest.skip("dotnet SDK not available")
    from dotnet_graph.builder import build
    tmp = tempfile.mkdtemp(prefix="explore-test-")
    db = Path(tmp) / "knowledge.db"
    build(FIXTURE, db, verbose=False, incremental=False)
    yield db
    shutil.rmtree(tmp, ignore_errors=True)


def test_build_data_shape(fixture_db):
    from dotnet_graph.explore import build_data
    data = build_data(fixture_db, fixture_db.parent / "notes")
    for key in ("nodes", "edges", "members", "tours", "layers", "stats", "registrations"):
        assert key in data
    assert data["stats"]["types"] > 0
    # every node has a layer + a summary
    for n in data["nodes"]:
        assert n["layer"] in (layers.LAYER_IDS + ["external"])
        assert n["summary"]


def test_fixture_layers_assigned(fixture_db):
    from dotnet_graph.explore import build_data
    data = build_data(fixture_db, fixture_db.parent / "notes")
    layer_of = {n["name"]: n["layer"] for n in data["nodes"]}
    assert layer_of.get("UserViewModel") == "presentation"
    assert layer_of.get("UserRepository") == "data"
    assert layer_of.get("UserService") == "service"
    assert layer_of.get("UserController") == "api"


def test_build_dashboard_writes_files(fixture_db, tmp_path):
    from dotnet_graph.explore import build_dashboard
    stats = build_dashboard(fixture_db, tmp_path, fixture_db.parent / "notes", verbose=False)
    assert (tmp_path / "index.html").exists()
    data_js = (tmp_path / "data.js").read_text(encoding="utf-8")
    assert data_js.startswith("window.EXPLORE = ")
    assert stats["types"] > 0
