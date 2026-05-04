# What Gets Indexed

dotnet-graph runs the Roslyn AST analyzer over every `.cs` file in your solution and stores the results in a SQLite database at `<root>/.dotnet-graph/knowledge.db`.

## Tables

| Table | What's in it |
|-------|-------------|
| `projects` | `.csproj` files — name, path, domain tag, platform tag |
| `files` | `.cs` source files — path, namespace, project |
| `types` | Every class, interface, enum, record, struct — name, full name, kind, abstract, partial, line |
| `methods` | Method declarations — name, return type, parameters, visibility, async, static, override, line |
| `properties` | Property declarations — name, type, visibility, static, line |
| `field_declarations` | Private/protected fields — name, type, readonly, static, line |
| `constructor_injections` | Constructor parameters per type — used to build the DI graph |
| `relationships` | `implements` and `inherits` edges, resolved to fully-qualified names |
| `usings` | `using` statements per file |
| `registrations` | DI registrations — interface, implementation, lifetime (transient/singleton/scoped) |
| `endpoints` | HTTP call sites — URL pattern, HTTP method, type, line |
| `xaml_views` | `.xaml` files mapped by `x:Class` attribute |
| `config_keys` | Flattened keys from `appConfiguration*.json` per environment |
| `features` | ViewModel-centric feature index — derived from `*ViewModel` class names |
| `method_calls` | Call graph edges — caller type + method → callee expression + method |
| `file_hashes` | SHA-256 per `.cs` file — used to detect what changed between builds |
| `build_meta` | Last build timestamp, duration, file counts, build mode, tool version |

## What is skipped

- Files in `obj/` and `bin/` directories
- Auto-generated files (`*.g.cs`, `*.designer.cs`, `*.g.i.cs`)
- Hidden directories (`.git`, `.claude`, etc.)

## Domain and platform tags

Each project is tagged automatically based on its path:

| Platform tag | Detected from |
|-------------|--------------|
| `android` | path contains `android` |
| `ios` | path contains `ios` or `shareextension` |
| `windows` | path contains `windows` or `maui` |
| `shared` | everything else |

The domain tag is the top-level folder name (e.g. `Productivity`, `Core`, `Api`).

## Feature index

A "feature" is inferred from any class named `*ViewModel`. For example, `UserViewModel` creates a `User` feature entry and links it to `UserService` (or `UserServiceAgent`, `UserManager`) if one exists in the same domain.
