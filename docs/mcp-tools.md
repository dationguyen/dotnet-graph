# MCP Tools

Available when dotnet-graph is registered as an MCP server (via `dotnet-graph install` or `.mcp.json`).

---

## find_type

Find a type by name. Supports exact match or partial (LIKE) search.

```
find_type(name="AuthService")
find_type(name="Auth", exact=false)
```

Returns: name, full name, kind (class/interface/enum/record/struct), file path, line number.

---

## get_type_members

Get all members of a type.

```
get_type_members(name="UserService")
```

Returns: methods (name, return type, params, async, line), properties, fields, constructor injection parameters.

---

## find_implementors

Find all types that implement or inherit from a given type.

```
find_implementors(name="IUserRepository")
```

Returns: concrete classes and any further subclasses.

---

## find_injectors

Find all classes that constructor-inject a given type.

```
find_injectors(name="IUserService")
```

Useful for understanding what depends on a service before refactoring it.

---

## get_method_calls

Get all calls made within a specific method.

```
get_method_calls(type="UserService", method="GetUserAsync")
```

Returns: callee expression, callee method name, line number.

---

## find_callers

Find all callers of a method across the entire codebase.

```
find_callers(method="ValidateToken")
```

Returns: caller type, caller method, file path, line number.

---

## get_di_registrations

List DI registrations, optionally filtered by interface or implementation name.

```
get_di_registrations()
get_di_registrations(name="IAuthService")
```

Returns: interface type, implementation type, lifetime (transient/singleton/scoped), file path.

---

## get_endpoints

List all HTTP endpoints found in the codebase.

```
get_endpoints()
```

Returns: URL pattern, HTTP method, type name, file path, line number.

---

## get_features

Browse the ViewModel-centric feature index. A "feature" is derived from a ViewModel class name.

```
get_features()
get_features(name="User")
```

Returns: feature name, domain, associated ViewModel, associated service, project.

---

## search

Keyword search across type names, method names, and property names.

```
search(q="token")
search(q="refresh")
```

Returns: matched types and members with their locations.

---

## get_stats

Get build metadata and row counts for all indexed tables.

```
get_stats()
```

Returns: last built timestamp, build mode (full/incremental), files analyzed, duration, tool version, and counts for every table.

---

## build_graph

Trigger a knowledge graph rebuild from within the agent.

```
build_graph()            # incremental
build_graph(full=true)   # force full rebuild
```

---

## build_obsidian_vault

Generate an Obsidian vault from the current graph.

```
build_obsidian_vault()
build_obsidian_vault(vault_path="/path/to/output")
```
