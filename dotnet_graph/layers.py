"""Architectural-layer classification for types.

Maps every type to one of a small set of architectural layers (UI, Presentation,
API, Service, Data, Model, Infrastructure, Other) using deterministic heuristics
over the type's name, namespace, base types, and endpoint membership. Tuned for
.NET / MAUI / MvvmCross conventions.

This is a *derived interpretation*, not a source fact, so it lives outside the
SQLite schema and is computed at dashboard-export time. Everything here is a pure
function of its inputs — it can be reused verbatim to populate a DB column later
without rework.
"""

from __future__ import annotations

import re

# Ordered layers — order doubles as the top-to-bottom flow in the dashboard.
LAYERS: list[dict] = [
    {"id": "ui", "label": "UI", "color": "#4ea1ff",
     "desc": "Views, pages, activities, fragments, cells, renderers — what the user sees."},
    {"id": "presentation", "label": "Presentation", "color": "#9d7bff",
     "desc": "ViewModels and presenters — UI state and commands (MVVM)."},
    {"id": "api", "label": "API", "color": "#ff6fae",
     "desc": "HTTP/GraphQL clients, controllers, endpoints — the network boundary."},
    {"id": "service", "label": "Service", "color": "#ffb454",
     "desc": "Services, managers, handlers, providers — business logic."},
    {"id": "data", "label": "Data", "color": "#7fd962",
     "desc": "Repositories, stores, DbContext, DAOs — persistence access."},
    {"id": "model", "label": "Model", "color": "#46c9c3",
     "desc": "DTOs, entities, records, enums — plain data shapes."},
    {"id": "infra", "label": "Infrastructure", "color": "#c0843a",
     "desc": "Setup, bootstrap, DI, extensions, helpers, converters, factories."},
    {"id": "other", "label": "Other", "color": "#8a95a3",
     "desc": "Uncategorized types."},
]

LAYER_IDS = [lyr["id"] for lyr in LAYERS]
LAYER_COLOR = {lyr["id"]: lyr["color"] for lyr in LAYERS}
LAYER_LABEL = {lyr["id"]: lyr["label"] for lyr in LAYERS}

# Base types that strongly imply a UI element (MAUI / Xamarin / MvvmCross).
_UI_BASES = re.compile(
    r"(Page|ContentView|UIViewController|UIView|Activity|Fragment|"
    r"ViewCell|ViewController|Renderer|Application|AppDelegate|Window|Cell|Layout)$"
)

# Suffix → layer. Checked in order; first match wins. Longest/most-specific first.
_NAME_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"ViewModel$"), "presentation"),
    (re.compile(r"(Presenter|Navigator)$"), "presentation"),
    (re.compile(r"(UIViewController|ViewController|View|Page|Activity|Fragment|"
                r"Cell|Renderer|Dialog|Popup|Sheet|Control|Widget|Adapter|"
                r"ViewHolder)$"), "ui"),
    # Network boundary — caught by name. Anchored suffixes plus a few networking
    # word-stems (so IInvokeQueryOverHttp, ISocketIOInstance, GraphQL* qualify even
    # though they don't end in a suffix). Runs before Service so HttpService → api.
    (re.compile(r"(ApiService|ApiClient|HttpClient|GraphQLClient|RestClient|"
                r"Gateway|Controller|Endpoint)$"), "api"),
    (re.compile(r"(GraphQL|WebSocket|SocketIO|RemoteQuery|OverHttp|HttpQuery|HttpClient)"), "api"),
    (re.compile(r"(Repository|DataStorage|DataStore|Store|DbContext|Dao|Database)$"), "data"),
    (re.compile(r"(Service|Manager|Provider|Handler|Processor|Engine|Coordinator|"
                r"Orchestrator|Worker|Scheduler|Dispatcher|Notifier|Validator|"
                r"Mapper|Resolver|Interactor|UseCase)$"), "service"),
    (re.compile(r"(Dto|Entity|Model|Record|Request|Response|Result|Args|Event|"
                r"Message|Payload|Options|Settings|Config|Configuration|Info|"
                r"Snapshot|State|Item)$"), "model"),
    (re.compile(r"(Setup|Bootstrap|Startup|Builder|Factory|Extensions|Helper|"
                r"Helpers|Utils|Utilities|Converter|Module|Installer|Registrar|"
                r"Initializer|Middleware|Filter|Attribute|Behavior|Behaviour)$"), "infra"),
]

# Namespace segment → layer (lowercased segment match). Weaker than name rules.
_NS_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(views?|pages?|controls?|widgets?)\b"), "ui"),
    (re.compile(r"\b(viewmodels?|presenters?)\b"), "presentation"),
    # NOTE: deliberately narrow. 'client' and 'http' namespace segments hold lots
    # of non-network types (client-side DTO/schema contracts, HTTP serializers),
    # so they are NOT API signals — only genuinely API-named types (handled by the
    # name rules above) land here.
    (re.compile(r"\b(graphql|webapi|web[\s_-]?services?)\b"), "api"),
    (re.compile(r"\b(repositor(y|ies)|persistence|storage|data)\b"), "data"),
    (re.compile(r"\b(services?|managers?|handlers?|providers?)\b"), "service"),
    (re.compile(r"\b(models?|dtos?|entities|entity|contracts?|messages?|events?)\b"), "model"),
    (re.compile(r"\b(setup|bootstrap|di|infrastructure|extensions?|helpers?|"
                r"utils?|utilities|converters?|factor(y|ies))\b"), "infra"),
]


def _short(full_name: str) -> str:
    """Last dotted segment, stripped of generic arity (`Foo<T>` / ``Foo`1``)."""
    s = full_name.split(".")[-1]
    s = re.sub(r"<[^>]*>", "", s)
    s = re.sub(r"`\d+$", "", s)
    return s


def classify_one(
    name: str,
    *,
    kind: str | None = None,
    namespace: str | None = None,
    bases: list[str] | None = None,
    is_endpoint: bool = False,
) -> str:
    """Classify a single type. Pure; no DB access.

    Precedence: name → base type → namespace → kind → other.

    The `is_endpoint` flag is accepted for API compatibility but **not used**: this
    analyzer's endpoint table is a noisy heuristic (it indexes settings keys, not
    just HTTP routes), so it produced false 'api' tags (e.g. AppStart). Genuine API
    types are network-named and caught by the name rules. Interfaces are classified
    by their own name here; resolution against implementors happens in
    `classify_all`.
    """
    short = _short(name)

    # Interface I-prefixed: classify on the de-prefixed name (IFooService → service).
    probe = short
    if kind == "interface" and re.match(r"^I[A-Z]", short):
        probe = short[1:]

    for pat, layer in _NAME_RULES:
        if pat.search(probe):
            return layer

    for b in (bases or []):
        if _UI_BASES.search(_short(b)):
            return "ui"

    if namespace:
        ns = namespace.lower()
        for pat, layer in _NS_RULES:
            if pat.search(ns):
                return layer

    if kind in ("enum", "record", "struct"):
        return "model"

    return "other"


def classify_all(
    types: list[dict],
    rels: list[dict] | None = None,
    endpoint_types: set[str] | None = None,
) -> dict[str, str]:
    """Classify every type. Returns {full_name: layer_id}.

    types: dicts with keys full_name, name, kind, namespace.
    rels:  dicts with keys from_type, to_type, kind ('inherits'/'implements').
    endpoint_types: set of full_names (or short names) that expose HTTP endpoints.

    Two passes: (1) classify each type independently; (2) re-home interfaces that
    landed in 'other' onto the dominant layer of their implementors, so an
    interface like `IThing` inherits the layer of the concrete `Thing`.
    """
    rels = rels or []
    endpoint_types = endpoint_types or set()

    bases_by_type: dict[str, list[str]] = {}
    implementors_by_iface: dict[str, list[str]] = {}
    for r in rels:
        bases_by_type.setdefault(r["from_type"], []).append(r["to_type"])
        if r["kind"] == "implements":
            implementors_by_iface.setdefault(r["to_type"], []).append(r["from_type"])

    result: dict[str, str] = {}
    for t in types:
        fn = t["full_name"] or t["name"]
        is_ep = fn in endpoint_types or t["name"] in endpoint_types
        result[fn] = classify_one(
            t["name"],
            kind=t.get("kind"),
            namespace=t.get("namespace"),
            bases=bases_by_type.get(fn, []),
            is_endpoint=is_ep,
        )

    # Pass 2: interfaces stuck in 'other' adopt their implementors' dominant layer.
    by_full = {(t["full_name"] or t["name"]): t for t in types}
    for iface, impls in implementors_by_iface.items():
        if result.get(iface) != "other":
            continue
        votes: dict[str, int] = {}
        for impl in impls:
            lyr = result.get(impl)
            if lyr and lyr != "other":
                votes[lyr] = votes.get(lyr, 0) + 1
        if votes:
            result[iface] = max(votes, key=votes.get)

    return result


def layer_legend() -> list[dict]:
    """The ordered layer metadata for the dashboard legend."""
    return LAYERS
