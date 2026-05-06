# Handoff — notes feature (2026-05-06)

This file was written by the Claude Code session in `smokeballmobile` to brief the session here.

## What was built

A **knowledge notes** system that lets AI agents accumulate domain knowledge about types as they work, persisting it across sessions. Notes live alongside the auto-generated Obsidian vault but are never overwritten by `build_graph` or `build_obsidian_vault`.

## Files changed

### New: `dotnet_graph/notes.py`
Core module. Key function:

```python
get_or_create_note(db_path: Path, type_name: str, notes_dir: Path) -> dict
```

- Looks up the type in `knowledge.db`
- Returns `{"path", "content", "created": False}` if a note already exists
- Creates `notes/<Domain>/<Project>/<TypeName>.md` from graph data if not — with a `## Notes` section placeholder
- Grouping: `<Domain>` comes from the project's domain field (e.g. `Productivity`), `<Project>` is the project name (e.g. `MatterManagement.Memos.Mobile`)

Helper: `note_path_for(full_name, domain, project, notes_dir) -> Path`

### Modified: `dotnet_graph/tools/build_tools.py`
Added new MCP tool `get_or_create_note` — wraps `notes.py`. Registered alongside `build_obsidian_vault` and `build_graph`.

### Modified: `dotnet_graph/cli.py`
- Added `dotnet-graph note <TypeName>` CLI command
- Updated `_CLAUDE_MD_SECTION` with the notes workflow (new row in tool table + `### Knowledge Notes` section explaining when/how to use `get_or_create_note`)

## Intended workflow (for AI agents using this)

1. Agent reads or modifies a source file
2. Calls `get_or_create_note("TypeName")` — creates the note if it doesn't exist
3. Uses the obsidian MCP's `edit_file` to update the `## Notes` section with:
   - `### Purpose` — what the type does in business terms
   - `### Key Behaviours` — patterns, invariants, gotchas
   - `### Work Log` — ticket + date + what changed and why

## What needs to happen next

- [ ] Bump version in `pyproject.toml` (currently `0.1.6` → suggest `0.1.7`)
- [ ] Publish to PyPI so `uvx dotnet-graph` picks up the new `get_or_create_note` tool
- [ ] Consider adding a `list_notes` MCP tool (search across existing notes)
- [ ] Consider a `sync_note_structure` helper that updates the structure section of an existing note when the graph changes (currently only the Notes section is preserved)

## Live test results

Tested against `smokeballmobile` (1,884 types, 5,058 methods):
- `get_or_create_note(db, "TaskService", notes_dir)` → `Productivity/Tasking.ManageTasks.Mobile/TaskService.md` ✓
- `get_or_create_note(db, "AddEditMemoViewModel", notes_dir)` → `Productivity/MatterManagement.Memos.Mobile/AddEditMemoViewModel.md` ✓
- `get_or_create_note(db, "MemosListViewModel", notes_dir)` → `Productivity/MatterManagement.Memos.Mobile/MemosListViewModel.md` ✓

All three notes have been enriched with real domain knowledge and live at:
```
smokeballmobile/.dotnet-graph/notes/
├── Productivity/
│   ├── MatterManagement.Memos.Mobile/
│   │   ├── AddEditMemoViewModel.md
│   │   └── MemosListViewModel.md
│   └── Tasking.ManageTasks.Mobile/
│       ├── AddEditTaskViewModel.md
│       └── TaskService.md
└── README.md
```
