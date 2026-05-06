"""MCP tools for building and updating the knowledge graph."""

from __future__ import annotations

from pathlib import Path
from typing import Callable


def register_build_tools(mcp, get_db_path: Callable[[], Path]) -> None:

    @mcp.tool()
    def build_obsidian_vault(vault_dir: str = "") -> str:
        """Generate an Obsidian vault from the knowledge graph.

        Creates one markdown note per type with WikiLinks for inheritance,
        DI injections, and reverse-injection relationships. Open the output
        directory in Obsidian and switch to Graph View to explore visually.

        vault_dir: output directory (default: <root>/.dotnet-graph/obsidian)
        """
        from dotnet_graph.obsidian import build_vault

        db_path = get_db_path()
        if not db_path or not db_path.exists():
            return "No graph found. Run build_graph first."

        vault_path = Path(vault_dir).resolve() if vault_dir else db_path.parent / "obsidian"
        n = build_vault(db_path, vault_path, verbose=False)
        return (
            f"Vault built: {n} notes → `{vault_path}`\n\n"
            f"Open `{vault_path}` in Obsidian and switch to **Graph View**."
        )

    @mcp.tool()
    def get_or_create_note(type_name: str, notes_dir: str = "") -> str:
        """Get or create an enriched knowledge note for a type.

        Notes live in .dotnet-graph/notes/<Domain>/<TypeName>.md. Each note has
        the structural data from the graph (methods, DI, inheritance) plus a
        ## Notes section for AI-maintained context (purpose, business logic,
        gotchas, work log).

        Call this when you read or modify a type. If the note already exists,
        returns its current content. If not, creates one from graph data with an
        empty Notes section ready to fill in. Use update_note to write to the
        Notes section.

        type_name: class or interface name (partial or full match)
        notes_dir: notes directory (default: <root>/.dotnet-graph/notes)
        """
        from dotnet_graph.notes import get_or_create_note as _impl

        db_path = get_db_path()
        if not db_path or not db_path.exists():
            return "No graph found. Run build_graph first."

        notes_path = Path(notes_dir).resolve() if notes_dir else db_path.parent / "notes"
        result = _impl(db_path, type_name, notes_path)

        if "error" in result:
            return result["error"]

        status = "Created" if result["created"] else "Existing"
        return f"{status} note: `{result['path']}`\n\n{result['content']}"

    @mcp.tool()
    def update_note(type_name: str, notes_content: str, notes_dir: str = "") -> str:
        """Replace the ## Notes section of a knowledge note.

        Writes AI-maintained context (purpose, business logic, gotchas, work log)
        into the note for a type. The structural section (methods, properties,
        injections) is left untouched. Creates the note first if it doesn't exist.

        type_name: class or interface name (partial or full match)
        notes_content: full text to place under the ## Notes heading (do not
                       include the heading itself)
        notes_dir: notes directory (default: <root>/.dotnet-graph/notes)
        """
        from dotnet_graph.notes import update_note as _impl

        db_path = get_db_path()
        if not db_path or not db_path.exists():
            return "No graph found. Run build_graph first."

        notes_path = Path(notes_dir).resolve() if notes_dir else db_path.parent / "notes"
        result = _impl(db_path, type_name, notes_content, notes_path)

        if "error" in result:
            return result["error"]

        return f"Updated note: `{result['path']}`\n\n{result['content']}"

    @mcp.tool()
    def sync_note_structure(type_name: str, notes_dir: str = "") -> str:
        """Refresh the structural section of a knowledge note from current graph data.

        Re-generates Methods, Properties, Injections, and Inheritance from the
        live graph while preserving the entire ## Notes section (purpose, business
        logic, work log). Call this after running build_graph if the type's
        structure has changed. Creates the note first if it doesn't exist yet.

        type_name: class or interface name (partial or full match)
        notes_dir: notes directory (default: <root>/.dotnet-graph/notes)
        """
        from dotnet_graph.notes import sync_note_structure as _impl

        db_path = get_db_path()
        if not db_path or not db_path.exists():
            return "No graph found. Run build_graph first."

        notes_path = Path(notes_dir).resolve() if notes_dir else db_path.parent / "notes"
        result = _impl(db_path, type_name, notes_path)

        if "error" in result:
            return result["error"]

        if result.get("created"):
            return f"Created note: `{result['path']}`\n\n{result['content']}"
        if result.get("refreshed"):
            return f"Refreshed note: `{result['path']}`\n\n{result['content']}"
        return f"Note has no standard marker — returned unchanged: `{result['path']}`\n\n{result['content']}"

    @mcp.tool()
    def build_graph(root: str) -> str:
        """Build (or rebuild) the knowledge graph for a .NET solution.

        root: absolute path to the solution root directory (the folder containing .csproj files).
        The graph DB is stored at <root>/.dotnet-graph/knowledge.db by default.
        """
        from dotnet_graph.builder import build

        root_path = Path(root).resolve()
        if not root_path.is_dir():
            return f"Error: directory not found: {root}"

        db_path = get_db_path() or (root_path / ".dotnet-graph" / "knowledge.db")
        try:
            build(root_path, db_path, verbose=True)
            return f"Graph built at `{db_path}`."
        except Exception as e:
            return f"Build failed: {e}"
