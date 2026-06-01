"""Guided tours — dependency-ordered walkthroughs of the codebase.

A tour is an ordered list of types that teaches one slice of the system: start at
an entry point (a ViewModel for a feature, or the app bootstrap), then walk its
constructor injections breadth-first so each step depends only on things already
introduced. This is the "quietly teaches you how the pieces fit together" view.

Pure functions over plain dicts — no DB access.
"""

from __future__ import annotations

import re

# Entry points for the "App startup" tour, most-specific first.
_STARTUP_RE = re.compile(
    r"(MainApplication|AppDelegate|AppSetup|AppStart|Bootstrap|Startup|"
    r"^App$|Application$|ApplicationHostBuilder)"
)
_MAX_STEPS = 12


def build_type_index(full_names: list[str]) -> dict[str, str]:
    """Map both full names and unambiguous short names → canonical full name.

    Short names that collide across types are dropped (only full-name lookup works
    for those), so resolution never silently picks the wrong type.
    """
    index: dict[str, str] = {fn: fn for fn in full_names}
    short_counts: dict[str, int] = {}
    for fn in full_names:
        short_counts[fn.split(".")[-1]] = short_counts.get(fn.split(".")[-1], 0) + 1
    for fn in full_names:
        short = fn.split(".")[-1]
        if short_counts[short] == 1:
            index.setdefault(short, fn)
    return index


def _resolve(param_type: str, type_index: dict[str, str]) -> str | None:
    """Resolve an injection's declared type to an internal full name, or None."""
    if not param_type:
        return None
    clean = re.sub(r"<[^>]*>", "", param_type).strip()
    if clean in type_index:
        return type_index[clean]
    short = clean.split(".")[-1]
    return type_index.get(short)


def _walk(
    seed: str,
    injections_by_type: dict[str, list[str]],
    type_index: dict[str, str],
    max_steps: int = _MAX_STEPS,
) -> list[str]:
    """Breadth-first walk from seed following constructor injections."""
    order: list[str] = []
    seen: set[str] = set()
    queue: list[str] = [seed]
    while queue and len(order) < max_steps:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        order.append(current)
        for param in injections_by_type.get(current, []):
            target = _resolve(param, type_index)
            if target and target not in seen and target != current:
                queue.append(target)
    return order


def build_feature_tours(
    features: list[dict],
    injections_by_type: dict[str, list[str]],
    type_index: dict[str, str],
) -> list[dict]:
    """One tour per feature whose ViewModel resolves and has dependencies.

    features: dicts with keys name, viewmodel, domain.
    """
    tours: list[dict] = []
    for f in features:
        vm = f.get("viewmodel")
        if not vm:
            continue
        seed = _resolve(vm, type_index) or (vm if vm in type_index.values() else None)
        if not seed:
            continue
        steps = _walk(seed, injections_by_type, type_index)
        if len(steps) < 2:  # a lone ViewModel teaches nothing
            continue
        tours.append({
            "id": "feature:" + f["name"],
            "title": f"{f['name']} feature",
            "kind": "feature",
            "domain": f.get("domain"),
            "steps": steps,
        })
    tours.sort(key=lambda t: (t.get("domain") or "", -len(t["steps"])))
    return tours


def build_startup_tour(
    types: list[dict],
    injections_by_type: dict[str, list[str]],
    type_index: dict[str, str],
) -> dict | None:
    """A tour that walks app bootstrap into the first services it wires up."""
    seeds = [
        (t["full_name"] or t["name"])
        for t in types
        if _STARTUP_RE.search(t["name"])
    ]
    if not seeds:
        return None
    # Prefer a real Application/Setup seed with the most injections.
    seeds.sort(key=lambda fn: len(injections_by_type.get(fn, [])), reverse=True)
    steps: list[str] = []
    seen: set[str] = set()
    for seed in seeds:
        for s in _walk(seed, injections_by_type, type_index, max_steps=_MAX_STEPS):
            if s not in seen:
                seen.add(s)
                steps.append(s)
            if len(steps) >= _MAX_STEPS:
                break
        if len(steps) >= _MAX_STEPS:
            break
    if len(steps) < 2:
        return None
    return {
        "id": "tour:startup",
        "title": "App startup & bootstrap",
        "kind": "startup",
        "domain": None,
        "steps": steps,
    }


def build_tours(
    features: list[dict],
    types: list[dict],
    injections_by_type: dict[str, list[str]],
    type_index: dict[str, str],
) -> list[dict]:
    """All tours: the startup tour first (if any), then per-feature tours."""
    tours: list[dict] = []
    startup = build_startup_tour(types, injections_by_type, type_index)
    if startup:
        tours.append(startup)
    tours.extend(build_feature_tours(features, injections_by_type, type_index))
    return tours
