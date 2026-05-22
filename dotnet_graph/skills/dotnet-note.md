---
description: Read or write AI notes for a .NET type in the knowledge graph. Use when the user asks to "add a note", "read the note for X", "document X", "update notes on X", or "what do we know about X" in the context of the graph notes system.
---

# dotnet-note

Interact with the per-type note files stored in `.dotnet-graph/notes/`. Notes have a structural section (auto-generated from the graph) and a `## Notes` section (written by agents).

## Reading a note
`mcp__dotnet-graph__get_or_create_note(type_name="<TypeName>")` — returns the full note content. If the note doesn't exist it is created from current graph data.

Always show the user:
- The note file path
- Whether it was newly created or already existed
- The full `## Notes` content (skip the structural header unless the user asks for it)

## Writing / updating a note
`mcp__dotnet-graph__update_note(type_name="<TypeName>", notes_content="<markdown>")` — replaces the `## Notes` section. The structural header is preserved automatically.

**What to write in notes:**
- Purpose and business responsibility of the type
- Non-obvious behaviour, gotchas, known bugs
- Patterns it participates in (e.g. "uses decorator pattern for caching")
- Work log: what was changed and why, with approximate dates

Do NOT repeat information already visible in the structural section (constructor params, methods, base types) — that is auto-maintained by the graph.

## Refreshing stale structure
`mcp__dotnet-graph__sync_note_structure(type_name="<TypeName>")` — re-generates the structural header from the current graph while keeping the `## Notes` text intact. Use after a `build_graph` if the type has changed significantly.

## Workflow for "document this type"
1. `get_or_create_note` — read existing notes
2. `get_type_members` + `find_injectors` — gather context if needed
3. Draft a clear `## Notes` section covering purpose, gotchas, and any work log
4. `update_note` — persist it
