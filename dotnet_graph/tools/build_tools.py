"""MCP tools for building and updating the knowledge graph."""

from __future__ import annotations

from pathlib import Path
from typing import Callable


def register_build_tools(mcp, get_db_path: Callable[[], Path]) -> None:

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
