using System.Text.Json.Serialization;

namespace DotnetGraph.Analyzer;

public record FileData(
    [property: JsonPropertyName("path")] string Path,
    [property: JsonPropertyName("namespace")] string? Namespace,
    [property: JsonPropertyName("usings")] List<string> Usings,
    [property: JsonPropertyName("types")] List<TypeData> Types
);

public record TypeData(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("kind")] string Kind,
    [property: JsonPropertyName("is_abstract")] bool IsAbstract,
    [property: JsonPropertyName("is_partial")] bool IsPartial,
    [property: JsonPropertyName("is_sealed")] bool IsSealed,
    [property: JsonPropertyName("line")] int Line,
    [property: JsonPropertyName("bases")] List<string> Bases,
    [property: JsonPropertyName("methods")] List<MethodData> Methods,
    [property: JsonPropertyName("properties")] List<PropertyData> Properties,
    [property: JsonPropertyName("fields")] List<FieldData> Fields,
    [property: JsonPropertyName("constructors")] List<ConstructorData> Constructors,
    [property: JsonPropertyName("registrations")] List<RegistrationData> Registrations,
    [property: JsonPropertyName("endpoints")] List<EndpointData> Endpoints,
    [property: JsonPropertyName("method_calls")] List<MethodCallData> MethodCalls,
    [property: JsonPropertyName("nested_types")] List<TypeData> NestedTypes
);

public record MethodData(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("return_type")] string ReturnType,
    [property: JsonPropertyName("parameters")] string Parameters,
    [property: JsonPropertyName("visibility")] string Visibility,
    [property: JsonPropertyName("is_async")] bool IsAsync,
    [property: JsonPropertyName("is_static")] bool IsStatic,
    [property: JsonPropertyName("is_override")] bool IsOverride,
    [property: JsonPropertyName("is_virtual")] bool IsVirtual,
    [property: JsonPropertyName("line")] int Line
);

public record PropertyData(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("type_name")] string TypeName,
    [property: JsonPropertyName("visibility")] string Visibility,
    [property: JsonPropertyName("is_static")] bool IsStatic,
    [property: JsonPropertyName("is_override")] bool IsOverride,
    [property: JsonPropertyName("line")] int Line
);

public record FieldData(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("type_name")] string TypeName,
    [property: JsonPropertyName("visibility")] string Visibility,
    [property: JsonPropertyName("is_readonly")] bool IsReadonly,
    [property: JsonPropertyName("is_static")] bool IsStatic,
    [property: JsonPropertyName("line")] int Line
);

public record ConstructorData(
    [property: JsonPropertyName("visibility")] string Visibility,
    [property: JsonPropertyName("parameters")] List<ParameterData> Parameters,
    [property: JsonPropertyName("line")] int Line
);

public record ParameterData(
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("name")] string Name
);

public record RegistrationData(
    [property: JsonPropertyName("registration_type")] string RegistrationType,
    [property: JsonPropertyName("interface_type")] string? InterfaceType,
    [property: JsonPropertyName("impl_type")] string? ImplType,
    [property: JsonPropertyName("lifetime")] string Lifetime,
    [property: JsonPropertyName("line")] int Line
);

public record EndpointData(
    [property: JsonPropertyName("http_method")] string HttpMethod,
    [property: JsonPropertyName("url_pattern")] string UrlPattern,
    [property: JsonPropertyName("line")] int Line
);

public record MethodCallData(
    [property: JsonPropertyName("caller_method")] string CallerMethod,
    [property: JsonPropertyName("callee_expr")] string CalleeExpr,
    [property: JsonPropertyName("callee_method")] string CalleeMethod,
    [property: JsonPropertyName("line")] int Line
);
