# dotnet-graph vs. LSP vs. ReSharper MCP

People often ask how dotnet-graph relates to a C# language server (OmniSharp / the
Roslyn language server, over LSP) or to JetBrains' ReSharper/Rider MCP server.
They overlap in that all three can "answer questions about code," but they sit at
very different points on the **precision ↔ cost ↔ portability** spectrum.

## Same engine, different tier

A common assumption is that dotnet-graph and a C# language server are different
*technologies*. They are not — **all of them are built on Roslyn.** OmniSharp and
the newer Roslyn-based LSP server use Roslyn; ReSharper uses its own equivalent
engine. dotnet-graph uses Roslyn too. The real difference is **which tier of
Roslyn each one uses.**

Roslyn is layered:

1. **Syntax / parse layer** — `CSharpSyntaxTree.ParseText`, syntax trees,
   `CSharpSyntaxWalker`. Pure parsing; no symbol resolution.
2. **Semantic layer** — `Compilation`, `SemanticModel`, `ISymbol`,
   `GetSymbolInfo`. Binds names to real symbols; needs the referenced
   assemblies/metadata. *This is the tier a language server lives on.*
3. **Workspace layer** — `MSBuildWorkspace`, `Solution`/`Project`/`Document`.
   Loads `.sln`/`.csproj`, restores packages, tracks live edits.

**dotnet-graph stops at tier 1.** Its analyzer calls
`CSharpSyntaxTree.ParseText(source)` per file and walks the tree with a
`CSharpSyntaxWalker` — it never builds a `Compilation`, a `SemanticModel`, or an
MSBuild workspace. It sees the text `: IUserService` and the string `_repo.Save()`
but never binds them to symbols. **LSP and ReSharper use all three tiers**, which
is what gives them symbol-exact navigation, refactoring, and diagnostics.

### What that actually costs us — and what it doesn't

Crucially, the line is *binding*, not *accuracy of parsing*:

- **Parsing is ground-truth.** Because we reuse the compiler's own parser, our
  *syntactic* facts — which types/methods/fields exist, their modifiers, line
  numbers — are exactly as accurate as the compiler's. That part is genuinely
  LSP-grade.
- **Binding is heuristic.** With no cross-file `Compilation`, we don't know that
  the `User` parsed in file A is the *same symbol* as a `User` referenced in file
  B. We reconstruct that on the Python side via a namespace/using/project scoring
  cascade (`_resolve_relationships`), and the call graph stays name-based — so
  `find_callers("Save")` matches *every* `.Save()` regardless of receiver type. A
  language server gets symbol identity for free, because every syntax tree shares
  one `Compilation`'s symbol table.

So dotnet-graph behaves like a sophisticated **structural/syntactic** analyzer,
not a semantic one — same engine as an LSP, but only its *parser*, not its
*binder*.

The core trade-off:

- **dotnet-graph** — approximate on cross-symbol facts, but cheap, portable, and
  rich in *derived* architectural knowledge.
- **LSP / ReSharper** — symbol-exact, but heavy and coupled to a running server
  or IDE.

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
> heuristic type resolution — comes directly from stopping at Roslyn's syntax
> tier. An opt-in semantic mode would simply **climb to tier 2** (build a
> `Compilation` + `SemanticModel`) — the same Roslyn layer a language server uses
> — making relationship and call resolution symbol-exact. The cost is exactly
> what tier 1 buys us today: it would require a successful restore/build and run
> much slower. That is a deliberate trade-off, not an oversight — syntax-only is
> what lets dotnet-graph index broken, un-restored, or partially-written code in
> seconds.
