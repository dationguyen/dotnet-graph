# dotnet-graph vs. LSP vs. ReSharper MCP

People often ask how dotnet-graph relates to a C# language server (OmniSharp / the
Roslyn language server, over LSP) or to JetBrains' ReSharper/Rider MCP server.
They overlap in that all three can "answer questions about code," but they sit at
very different points on the **precision ↔ cost ↔ portability** spectrum.

## The one difference that drives everything: syntax vs. semantic

dotnet-graph runs a Roslyn **`CSharpSyntaxWalker`** — it parses the *syntax tree
only* and never builds a `Compilation` or `SemanticModel`. It sees the text
`: IUserService` and the string `_repo.Save()`, but it does not bind them to real
symbols. As a result:

- **Type resolution is heuristic** — a name like `Foo` is matched to a full type
  via a namespace/using/project scoring cascade, not by the compiler.
- **The call graph is name-based** — `find_callers("Save")` matches *every*
  `.Save()` in the codebase regardless of the receiver's type.

LSP and ReSharper both run the **full semantic engine**: real symbol binding,
overload resolution, generic instantiation, exact inheritance graphs. When
ReSharper says "12 usages of `Save`," it means *that exact symbol* — no false
positives.

That is the core trade-off:

- **dotnet-graph** — approximate on raw language facts, but cheap, portable, and
  rich in *derived* architectural knowledge.
- **LSP / ReSharper** — exact, but heavy and coupled to a running server or IDE.

## At a glance

| Axis | dotnet-graph | LSP (OmniSharp / Roslyn) | ReSharper MCP |
|---|---|---|---|
| Analysis | Syntax-only, heuristic resolution | Full semantic model | Full semantic model (ReSharper engine) |
| State | Pre-built **SQLite snapshot**, incremental on file hash | **Live in-memory**, reflects unsaved buffers | Live IDE solution model |
| Needs a build / NuGet restore? | **No** — works on broken or un-restored code | Yes — project must load/restore | Yes — full IDE load |
| Runtime footprint | A SQLite file + a Python process; headless/CI-friendly | A language server tied to an editor | **Rider/ReSharper IDE + license**, heavyweight |
| "Who calls X?" precision | Name-match (noisy) | Exact symbol | Exact symbol |
| Refactors (rename, extract) | ❌ read-only | ✅ | ✅ (its specialty) |
| Diagnostics / errors / completion | ❌ | ✅ | ✅ |
| Cross-session memory | ✅ **knowledge notes** persist | ❌ stateless | ❌ stateless |
| Domain abstractions | ✅ DI graph, DI registrations, feature index, architectural layers, guided tours | ❌ raw language facts only | ❌ raw language facts only |
| Built for LLM consumption | ✅ compact, pre-shaped answers | ❌ verbose editor protocol | ⚠️ shaped, but IDE-bound |

## Where each one wins

### dotnet-graph

- You want an **AI agent** to ask *architectural* questions — "who injects
  `AuthService`?", "what's the feature map?", "give me an app-startup tour" — and
  get token-cheap, pre-digested answers. LSP and ReSharper have no concept of a
  "feature" or an "architectural layer"; those are dotnet-graph's *derived
  interpretations*, not language facts.
- The code **doesn't compile or isn't restored**, or you're running **headless /
  in CI** with no IDE available.
- You want **persistent domain knowledge** — the knowledge notes survive across
  sessions. Neither LSP nor ReSharper remember anything between runs.
- You want to query a **whole solution at once** as a fast, stateless snapshot.

### LSP (OmniSharp / Roslyn language server)

- You need **live, exact** go-to-definition, find-references, and diagnostics
  inside an editor, reflecting unsaved edits, with no false positives.

### ReSharper MCP

- You want that same semantic exactness **plus refactorings and deep code
  inspections** exposed to an agent — accepting the cost of a running JetBrains
  IDE and a license. Like LSP, it knows raw language facts but not your DI /
  feature / layer story.

## The honest one-liner

- **LSP / ReSharper** = ground-truth language *semantics* — live, exact,
  editor/IDE-bound, no memory.
- **dotnet-graph** = a queryable, persistent *knowledge graph and architectural
  narrative* over a snapshot — approximate on raw facts, but it answers questions
  the others structurally can't, cheaply, to an AI, without an IDE or a successful
  build.

They are **complementary more than competing**: reach for ReSharper/LSP to *edit
precisely*, and for dotnet-graph to *understand and navigate architecture* (and to
give an agent durable cross-session memory).

> **On precision:** the largest accuracy gap — name-only call matching and
> heuristic type resolution — comes directly from the syntax-only design. An
> opt-in semantic mode (building a `Compilation` + `SemanticModel`) would close
> it, at the cost of requiring a restore/build and slower analysis. That is a
> deliberate trade-off, not an oversight: syntax-only is what lets dotnet-graph
> index broken, un-restored, or partially-written code in seconds.
