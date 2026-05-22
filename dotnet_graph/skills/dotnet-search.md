---
description: Search the dotnet-graph knowledge graph for types, methods, or symbols by keyword. Use when the user asks to "find X", "where is X", "search for X", or wants to locate a class/interface/method in the codebase.
---

# dotnet-search

Search the knowledge graph for a symbol, type, or keyword. Follow this sequence:

## Step 1 — Broad keyword search
Call `mcp__dotnet-graph__search` with the user's term. This hits type names, method names, and property names simultaneously.

## Step 2 — Resolve a specific type
If the search returns a type that matches the intent, call `mcp__dotnet-graph__find_type` with the exact name to get the file path and line number.

## Step 3 — Show members (if asked or ambiguous)
Call `mcp__dotnet-graph__get_type_members` on the resolved type to show its methods, properties, fields, and constructor parameters.

## Output format
Report as a concise table or list:
- Type name → file path : line number
- Key methods with return types
- Any obvious matches from step 1 that the user should know about

If the graph isn't built yet, say: "Run `dotnet-graph build --root <solution>` first."
