using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace DotnetGraph.Analyzer;

public class FileWalker : CSharpSyntaxWalker
{
    private readonly SyntaxTree _tree;

    public string? Namespace { get; private set; }
    public List<string> Usings { get; } = new();
    public List<TypeData> Types { get; } = new();

    private readonly Stack<TypeContext> _typeStack = new();
    private string? _currentCallerMethod;

    private static readonly HashSet<string> ServiceSuffixes = new(StringComparer.OrdinalIgnoreCase)
    {
        "service", "manager", "provider", "repository", "handler",
        "agent", "factory", "store", "cache", "client", "gateway",
        "dispatcher", "coordinator", "processor", "accessor", "resolver",
    };

    public FileWalker(SyntaxTree tree) : base(SyntaxWalkerDepth.Node) => _tree = tree;

    // ── Namespace ──────────────────────────────────────────────────────────

    public override void VisitNamespaceDeclaration(NamespaceDeclarationSyntax node)
    {
        Namespace ??= node.Name.ToString();
        base.VisitNamespaceDeclaration(node);
    }

    public override void VisitFileScopedNamespaceDeclaration(FileScopedNamespaceDeclarationSyntax node)
    {
        Namespace ??= node.Name.ToString();
        base.VisitFileScopedNamespaceDeclaration(node);
    }

    // ── Using directives ───────────────────────────────────────────────────

    public override void VisitUsingDirective(UsingDirectiveSyntax node)
    {
        if (node.StaticKeyword.IsKind(SyntaxKind.None) && node.Alias == null && node.Name != null)
            Usings.Add(node.Name.ToString());
        // No base call — usings have no interesting children
    }

    // ── Types ──────────────────────────────────────────────────────────────

    public override void VisitClassDeclaration(ClassDeclarationSyntax node)
        => HandleTypeDeclaration(node, "class", () => base.VisitClassDeclaration(node));

    public override void VisitInterfaceDeclaration(InterfaceDeclarationSyntax node)
        => HandleTypeDeclaration(node, "interface", () => base.VisitInterfaceDeclaration(node));

    public override void VisitStructDeclaration(StructDeclarationSyntax node)
        => HandleTypeDeclaration(node, "struct", () => base.VisitStructDeclaration(node));

    public override void VisitRecordDeclaration(RecordDeclarationSyntax node)
    {
        var kind = node.ClassOrStructKeyword.IsKind(SyntaxKind.StructKeyword) ? "record struct" : "record";
        HandleTypeDeclaration(node, kind, () => base.VisitRecordDeclaration(node));
    }

    public override void VisitEnumDeclaration(EnumDeclarationSyntax node)
    {
        if (!IsIndexable(node.Modifiers)) return;
        var typeData = new TypeData(node.Identifier.Text, "enum", false, false, false,
            GetLine(node), new(), new(), new(), new(), new(), new(), new(), new(), new());
        AddType(typeData);
        // Enum members are not interesting for the graph
    }

    private void HandleTypeDeclaration(TypeDeclarationSyntax node, string kind, Action visitChildren)
    {
        if (!IsIndexable(node.Modifiers))
        {
            visitChildren(); // still walk — might contain public nested types
            return;
        }

        var mods = node.Modifiers;
        var bases = node.BaseList?.Types
            .Select(t =>
            {
                var s = t.Type.ToString();
                var idx = s.IndexOf('<');
                return idx >= 0 ? s[..idx] : s;
            })
            .ToList() ?? new List<string>();

        var ctx = new TypeContext(
            node.Identifier.Text, kind,
            mods.Any(m => m.IsKind(SyntaxKind.AbstractKeyword)),
            mods.Any(m => m.IsKind(SyntaxKind.PartialKeyword)),
            mods.Any(m => m.IsKind(SyntaxKind.SealedKeyword)),
            GetLine(node), bases);

        _typeStack.Push(ctx);
        visitChildren();
        _typeStack.Pop();

        AddType(ctx.Build());
    }

    private void AddType(TypeData t)
    {
        if (_typeStack.Count == 0)
            Types.Add(t);
        else
            _typeStack.Peek().NestedTypes.Add(t);
    }

    // ── Methods ────────────────────────────────────────────────────────────

    public override void VisitMethodDeclaration(MethodDeclarationSyntax node)
    {
        if (_typeStack.Count == 0) { base.VisitMethodDeclaration(node); return; }

        var vis = GetVisibility(node.Modifiers);
        var mods = node.Modifiers;
        _typeStack.Peek().Methods.Add(new MethodData(
            node.Identifier.Text,
            node.ReturnType.ToString(),
            node.ParameterList.ToString(),
            vis,
            mods.Any(m => m.IsKind(SyntaxKind.AsyncKeyword)),
            mods.Any(m => m.IsKind(SyntaxKind.StaticKeyword)),
            mods.Any(m => m.IsKind(SyntaxKind.OverrideKeyword)),
            mods.Any(m => m.IsKind(SyntaxKind.VirtualKeyword)),
            GetLine(node)));

        var prev = _currentCallerMethod;
        _currentCallerMethod = node.Identifier.Text;
        base.VisitMethodDeclaration(node);
        _currentCallerMethod = prev;
    }

    // ── Properties ─────────────────────────────────────────────────────────

    public override void VisitPropertyDeclaration(PropertyDeclarationSyntax node)
    {
        if (_typeStack.Count == 0) return;

        var mods = node.Modifiers;
        _typeStack.Peek().Properties.Add(new PropertyData(
            node.Identifier.Text,
            node.Type.ToString(),
            GetVisibility(mods),
            mods.Any(m => m.IsKind(SyntaxKind.StaticKeyword)),
            mods.Any(m => m.IsKind(SyntaxKind.OverrideKeyword)),
            GetLine(node)));
        // Don't walk property bodies — accessors rarely have meaningful service calls
    }

    // ── Fields ─────────────────────────────────────────────────────────────

    public override void VisitFieldDeclaration(FieldDeclarationSyntax node)
    {
        if (_typeStack.Count == 0) return;

        var vis = GetVisibility(node.Modifiers);
        if (vis != "private" && vis != "protected") return;

        var mods = node.Modifiers;
        var typeName = node.Declaration.Type.ToString();
        var isReadonly = mods.Any(m => m.IsKind(SyntaxKind.ReadOnlyKeyword));
        var isStatic = mods.Any(m => m.IsKind(SyntaxKind.StaticKeyword));
        var line = GetLine(node);

        foreach (var v in node.Declaration.Variables)
            _typeStack.Peek().Fields.Add(new FieldData(v.Identifier.Text, typeName, vis, isReadonly, isStatic, line));
    }

    // ── Constructors ───────────────────────────────────────────────────────

    public override void VisitConstructorDeclaration(ConstructorDeclarationSyntax node)
    {
        if (_typeStack.Count == 0) { base.VisitConstructorDeclaration(node); return; }

        // Confirm name matches enclosing type (guards against partial-class edge cases)
        if (node.Identifier.Text != _typeStack.Peek().Name)
        {
            base.VisitConstructorDeclaration(node);
            return;
        }

        var parameters = node.ParameterList.Parameters
            .Select(p => new ParameterData(p.Type?.ToString() ?? "object", p.Identifier.Text))
            .ToList();

        _typeStack.Peek().Constructors.Add(
            new ConstructorData(GetVisibility(node.Modifiers), parameters, GetLine(node)));

        var prev = _currentCallerMethod;
        _currentCallerMethod = ".ctor";
        base.VisitConstructorDeclaration(node);
        _currentCallerMethod = prev;
    }

    // ── Invocations (service calls, DI registrations, HTTP endpoints) ──────

    public override void VisitInvocationExpression(InvocationExpressionSyntax node)
    {
        if (_typeStack.Count > 0 && node.Expression is MemberAccessExpressionSyntax ma)
        {
            var methodName = ma.Name.Identifier.Text;
            var expr = ma.Expression.ToString();
            var line = GetLine(node);

            if (ma.Name is GenericNameSyntax gn &&
                methodName is "RegisterType" or "RegisterSingleton" or "RegisterLazySingleton")
            {
                HandleRegistration(gn, methodName, line);
            }
            else if (methodName is "Get" or "Post" or "Put" or "Delete" or "Patch"
                                or "GetAsync" or "PostAsync" or "PutAsync" or "DeleteAsync" or "PatchAsync")
            {
                HandleEndpoint(node, methodName, line);
            }
            else if (_currentCallerMethod != null && IsLikelyServiceCall(expr))
            {
                _typeStack.Peek().MethodCalls.Add(
                    new MethodCallData(_currentCallerMethod, expr, methodName, line));
            }
        }

        base.VisitInvocationExpression(node);
    }

    private void HandleRegistration(GenericNameSyntax gn, string methodName, int line)
    {
        var typeArgs = gn.TypeArgumentList.Arguments.Select(a =>
        {
            var s = a.ToString();
            var idx = s.IndexOf('<');
            return idx >= 0 ? s[..idx] : s;
        }).ToList();

        var lifetime = methodName switch
        {
            "RegisterSingleton" => "singleton",
            "RegisterLazySingleton" => "lazySingleton",
            _ => "transient",
        };

        _typeStack.Peek().Registrations.Add(new RegistrationData(
            methodName,
            typeArgs.Count >= 1 ? typeArgs[0] : null,
            typeArgs.Count >= 2 ? typeArgs[1] : null,
            lifetime, line));
    }

    private void HandleEndpoint(InvocationExpressionSyntax node, string methodName, int line)
    {
        var firstArg = node.ArgumentList.Arguments.FirstOrDefault()?.Expression.ToString();
        if (firstArg is { Length: >= 5 })
            _typeStack.Peek().Endpoints.Add(new EndpointData(
                methodName.Replace("Async", "").ToUpper(),
                firstArg.Trim('"'), line));
    }

    // ── Helpers ────────────────────────────────────────────────────────────

    private int GetLine(SyntaxNode node)
        => _tree.GetLineSpan(node.Span).StartLinePosition.Line + 1;

    private static string GetVisibility(SyntaxTokenList mods)
    {
        if (mods.Any(m => m.IsKind(SyntaxKind.PublicKeyword))) return "public";
        if (mods.Any(m => m.IsKind(SyntaxKind.ProtectedKeyword))) return "protected";
        if (mods.Any(m => m.IsKind(SyntaxKind.InternalKeyword))) return "internal";
        return "private";
    }

    private static bool IsIndexable(SyntaxTokenList mods) =>
        mods.Any(m => m.IsKind(SyntaxKind.PublicKeyword) || m.IsKind(SyntaxKind.InternalKeyword));

    private static bool IsLikelyServiceCall(string expr)
    {
        if (expr.StartsWith("_")) return true;
        var lower = expr.ToLower();
        return ServiceSuffixes.Any(s => lower.EndsWith(s));
    }

    // ── Mutable accumulator per type ───────────────────────────────────────

    private sealed class TypeContext
    {
        private readonly string _kind;
        private readonly bool _isAbstract, _isPartial, _isSealed;
        private readonly int _line;
        private readonly List<string> _bases;

        public string Name { get; }
        public List<MethodData> Methods { get; } = new();
        public List<PropertyData> Properties { get; } = new();
        public List<FieldData> Fields { get; } = new();
        public List<ConstructorData> Constructors { get; } = new();
        public List<RegistrationData> Registrations { get; } = new();
        public List<EndpointData> Endpoints { get; } = new();
        public List<MethodCallData> MethodCalls { get; } = new();
        public List<TypeData> NestedTypes { get; } = new();

        public TypeContext(string name, string kind, bool isAbstract, bool isPartial, bool isSealed, int line, List<string> bases)
        {
            Name = name; _kind = kind; _isAbstract = isAbstract;
            _isPartial = isPartial; _isSealed = isSealed; _line = line; _bases = bases;
        }

        public TypeData Build() => new(
            Name, _kind, _isAbstract, _isPartial, _isSealed, _line, _bases,
            Methods, Properties, Fields, Constructors, Registrations, Endpoints, MethodCalls, NestedTypes);
    }
}
