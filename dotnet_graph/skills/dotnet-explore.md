---
description: Deep-dive into a single .NET type or service using the knowledge graph. Use when the user asks "how does X work", "tell me about X service", "analyze X", "what does X depend on", or "who uses X".
---

# dotnet-explore

Produce a full picture of a single type. Run all steps in parallel where possible.

## Step 1 — Locate the type
`mcp__dotnet-graph__find_type(name="<TypeName>")` — confirms existence, gets kind and file location.

## Step 2 — Get members (parallel with steps 3–4)
`mcp__dotnet-graph__get_type_members(name="<TypeName>")` — methods, properties, fields, constructor params.

## Step 3 — Find what it depends on (parallel)
`mcp__dotnet-graph__find_implementors(name="<TypeName>")` — who implements or extends it.

## Step 4 — Find who uses it (parallel)
`mcp__dotnet-graph__find_injectors(name="<TypeName>")` — classes that constructor-inject this type.

## Step 5 — Trace key methods (on demand)
For each interesting method the user asks about (or the top 2–3 public methods):
`mcp__dotnet-graph__get_method_calls(type="<TypeName>", method="<MethodName>")`
`mcp__dotnet-graph__find_callers(method="<MethodName>")`

## Output format
Structure the report as:

**`TypeName`** (`kind`) — `file:line`

**Inherits / Implements**: ...

**Constructor injects**: param_type as param_name, ...

**Methods**: name → return_type (async if applicable)

**Used by** (injectors): TypeA, TypeB, ...

**Implemented by**: ConcreteA, ConcreteB, ...

**Method flow** (if traced): method calls list

Keep it dense — one line per item. Only expand details where the user asked.
