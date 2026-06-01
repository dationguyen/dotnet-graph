"""Plain-English one-line summaries for types.

Two sources, in priority order:
1. The **Purpose** line of an existing enriched knowledge note (hand-written by an
   agent) — the highest-quality summary available.
2. A deterministic templated fallback derived from the type's kind, architectural
   layer, injector count, and feature membership — so *every* node gets a sensible
   one-liner even with zero notes.

Pure functions; the only I/O is reading note files in `load_note_purposes`.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._render import _safe_filename
from .layers import LAYER_LABEL

# Matches the agent-maintained note tail and its Purpose subsection.
_PURPOSE_RE = re.compile(
    r"##\s*Notes\b.*?###\s*Purpose\s*\n(.*?)(?:\n\s*###|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_PLACEHOLDER = re.compile(r"^_?no notes yet", re.IGNORECASE)


def extract_purpose(note_text: str) -> str | None:
    """Pull the first meaningful line of the ### Purpose block, if any."""
    m = _PURPOSE_RE.search(note_text)
    if not m:
        return None
    block = m.group(1).strip()
    for line in block.splitlines():
        line = line.strip().lstrip(">").strip()
        if line and not _PLACEHOLDER.match(line):
            return _first_sentence(line)
    return None


def _first_sentence(text: str, limit: int = 240) -> str:
    """First sentence (or clause), capped so node tooltips stay short."""
    text = re.sub(r"\s+", " ", text).strip().rstrip("*_`")
    # Split on sentence end, but not on abbreviations like "e.g." mid-line.
    m = re.search(r"(.+?[.!?])(\s|$)", text)
    out = m.group(1) if m else text
    if len(out) > limit:
        out = out[: limit - 1].rstrip() + "…"
    return out


def load_note_purposes(notes_dir: Path) -> dict[str, str]:
    """Map note filename-stem → Purpose line for every note under notes_dir.

    Keyed by the same `_safe_filename(full_name)` stem the notes are written with,
    so callers resolve a type by `_safe_filename(full_name)`.
    """
    purposes: dict[str, str] = {}
    if not notes_dir or not notes_dir.is_dir():
        return purposes
    for path in notes_dir.rglob("*.md"):
        try:
            purpose = extract_purpose(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if purpose:
            purposes[path.stem] = purpose
    return purposes


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def fallback_summary(
    name: str,
    kind: str | None,
    layer_id: str,
    *,
    injector_count: int = 0,
    impl_count: int = 0,
    feature: str | None = None,
    is_abstract: bool = False,
) -> str:
    """Deterministic one-liner when no note Purpose exists."""
    layer = LAYER_LABEL.get(layer_id, "Type")

    if layer_id == "presentation" and name.endswith("ViewModel"):
        feat = feature or _spaced(name[: -len("ViewModel")])
        base = f"ViewModel backing the {feat} screen." if feat else "ViewModel."
        return base

    if kind == "interface":
        if impl_count:
            return f"{layer} contract — implemented by {_plural(impl_count, 'type')}."
        return f"{layer} contract (interface)."

    if kind == "enum":
        return "Enumeration of named values."

    if kind in ("record", "struct") or layer_id == "model":
        return f"Data shape ({kind or 'model'})."

    if injector_count:
        kindword = "abstract " + (kind or "class") if is_abstract else (kind or "class")
        return f"{layer} {kindword} injected into {_plural(injector_count, 'type')}."

    if layer_id == "ui":
        return f"UI {kind or 'component'} — {_spaced(name)}."

    if layer_id == "infra":
        return f"Infrastructure {kind or 'class'} — {_spaced(name)}."

    return f"{layer} {kind or 'type'}."


def _spaced(camel: str) -> str:
    """`GlobalSearchList` → `Global Search List` for friendlier prose."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", camel)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    return s.strip()


def summarize(
    full_name: str,
    name: str,
    kind: str | None,
    layer_id: str,
    *,
    note_purposes: dict[str, str],
    injector_count: int = 0,
    impl_count: int = 0,
    feature: str | None = None,
    is_abstract: bool = False,
) -> tuple[str, bool]:
    """Return (summary, from_note). Prefers a note Purpose, else a fallback."""
    purpose = note_purposes.get(_safe_filename(full_name))
    if purpose:
        return purpose, True
    return fallback_summary(
        name, kind, layer_id,
        injector_count=injector_count, impl_count=impl_count,
        feature=feature, is_abstract=is_abstract,
    ), False
