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
