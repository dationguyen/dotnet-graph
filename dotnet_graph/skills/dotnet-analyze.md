---
description: Project-wide analysis of the .NET knowledge graph — endpoints, DI registrations, features, and graph stats. Use when the user asks "what endpoints exist", "show me the DI setup", "what features are there", "give me an overview of the project", or "what's in the graph".
---

# dotnet-analyze

Run a project-wide analysis. Choose the appropriate tools based on what the user wants:

## Available analyses

### Graph health / overview
`mcp__dotnet-graph__get_stats()` — last build time, mode (full/incremental), files analyzed, row counts for every table. Always run this first as a sanity check.

### HTTP endpoints
`mcp__dotnet-graph__get_endpoints()` — all routes grouped by HTTP method and URL pattern, with controller/handler type and file location.

### DI registrations
`mcp__dotnet-graph__get_di_registrations()` — interface → implementation mappings with lifetimes (transient/scoped/singleton). Pass a name to filter: `get_di_registrations(name="IAuth")`.

### Feature index
`mcp__dotnet-graph__get_features()` — ViewModel-centric feature list grouped by domain. Shows the ViewModel, associated service, and project for each feature.

## Output format

For **overview**: show build timestamp, mode, file count, and a table of key row counts (types, methods, endpoints, registrations).

For **endpoints**: group by HTTP method, show `METHOD /path → TypeName (file:line)`.

For **DI**: table of `IInterface → ConcreteImpl [lifetime]` sorted by interface name.

For **features**: group by domain, list feature name → ViewModel → service.

If multiple aspects are requested, run all relevant MCP calls in parallel and present each section with a header.
