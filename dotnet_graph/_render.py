"""Shared markdown rendering for knowledge notes and the Obsidian vault."""

from __future__ import annotations

import re


def _safe_filename(name: str) -> str:
    name = re.sub(r"<[^>]*>", "", name)
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return name.strip()


def _wikilink(full_name: str) -> str:
    short = full_name.split(".")[-1] if "." in full_name else full_name
    short = re.sub(r"<[^>]*>", "", short)
    safe_full = _safe_filename(full_name)
    if short == safe_full:
        return f"[[{short}]]"
    return f"[[{safe_full}|{short}]]"


def _normalize_domain(domain: str | None) -> str | None:
    if domain and (domain.startswith(".") or "/" in domain or "\\" in domain):
        return None
    return domain


def _type_lines(t, bases, injects, injectors, methods, props) -> list[str]:
    """Render a type as structural markdown lines (frontmatter through Properties).

    bases:     [(to_type, kind), ...]          — already deduplicated
    injects:   [(param_type, param_name), ...] — already deduplicated
    injectors: [full_name, ...]                — first 20 shown, remainder noted
    methods:   iterable of rows with name, return_type, visibility, is_async, line
    props:     iterable of rows with name, type_name, visibility, line
    """
    lines: list[str] = []
    domain = _normalize_domain(t["domain"])

    tags = [t["kind"] or "type"]
    if domain:
        tags.append(domain.lower().replace(" ", "-"))
    if t["name"].endswith("ViewModel"):
        tags.append("viewmodel")
    elif t["kind"] == "interface":
        tags.append("interface")

    lines += ["---"]
    lines += [f"kind: {t['kind'] or 'type'}"]
    if t["namespace"]:
        lines += [f"namespace: \"{t['namespace']}\""]
    if t["project_name"]:
        lines += [f"project: \"{t['project_name']}\""]
    if domain:
        lines += [f"domain: \"{domain}\""]
    lines += [f"tags: [{', '.join(tags)}]"]
    lines += ["---", ""]
    lines += [f"# {t['name']}", ""]

    if t["project_name"]:
        lines += [f"**Project:** {t['project_name']}  "]
    if t["namespace"]:
        lines += [f"**Namespace:** `{t['namespace']}`  "]
    if t["file_path"]:
        lines += [f"**File:** `{t['file_path']}`  "]
    lines += [""]

    if bases:
        lines += ["## Inherits / Implements"]
        for to_type, kind in bases:
            lines += [f"- *{kind}* → {_wikilink(to_type)}"]
        lines += [""]

    if injects:
        lines += ["## Constructor Injections"]
        for param_type, param_name in injects:
            lines += [f"- `{param_name}` : {_wikilink(param_type)}"]
        lines += [""]

    if injectors:
        all_injectors = list(injectors)
        overflow = len(all_injectors) - 20
        lines += ["## Injected By"]
        for name in all_injectors[:20]:
            lines += [f"- {_wikilink(name)}"]
        if overflow > 0:
            lines += [f"- *(and {overflow} more)*"]
        lines += [""]

    sorted_methods = sorted(methods, key=lambda m: m["line"] or 0)
    if sorted_methods:
        lines += ["## Methods"]
        lines += ["| Name | Returns | Async | Visibility |"]
        lines += ["|------|---------|-------|------------|"]
        for m in sorted_methods:
            async_mark = "✓" if m["is_async"] else ""
            lines += [f"| `{m['name']}` | `{m['return_type'] or ''}` | {async_mark} | {m['visibility'] or 'public'} |"]
        lines += [""]

    sorted_props = sorted(props, key=lambda p: p["line"] or 0)
    if sorted_props:
        lines += ["## Properties"]
        for p in sorted_props:
            lines += [f"- `{p['name']}` : `{p['type_name']}` *({p['visibility'] or 'public'})*"]
        lines += [""]

    return lines
