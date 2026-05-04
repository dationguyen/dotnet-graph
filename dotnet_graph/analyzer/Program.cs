using System.Text.Json;
using Microsoft.CodeAnalysis.CSharp;

namespace DotnetGraph.Analyzer;

internal class Program
{
    static int Main(string[] args)
    {
        string? root = null;
        string? output = null;

        for (int i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--root" when i + 1 < args.Length:
                    root = args[++i];
                    break;
                case "--output" when i + 1 < args.Length:
                    output = args[++i];
                    break;
                case "--help":
                    Console.Error.WriteLine("Usage: RoslynAnalyzer --root <directory> [--output <file>]");
                    return 0;
            }
        }

        if (root == null)
        {
            Console.Error.WriteLine("Error: --root is required");
            return 1;
        }

        var rootDir = new DirectoryInfo(root);
        if (!rootDir.Exists)
        {
            Console.Error.WriteLine($"Error: directory not found: {root}");
            return 1;
        }

        var files = DiscoverCsFiles(rootDir);
        Console.Error.WriteLine($"Analyzing {files.Count} C# files...");

        var results = new List<FileData>(files.Count);
        int errors = 0;
        foreach (var file in files)
        {
            var fileData = AnalyzeFile(file, rootDir);
            if (fileData != null)
                results.Add(fileData);
            else
                errors++;
        }

        Console.Error.WriteLine($"Done: {results.Count} analyzed, {errors} skipped.");

        var json = JsonSerializer.Serialize(results, new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
            WriteIndented = false,
        });

        if (output != null)
            File.WriteAllText(output, json);
        else
            Console.WriteLine(json);

        return 0;
    }

    private static List<FileInfo> DiscoverCsFiles(DirectoryInfo root)
    {
        var sep = Path.DirectorySeparatorChar;
        return root
            .EnumerateFiles("*.cs", SearchOption.AllDirectories)
            .Where(f =>
                !f.FullName.Contains($"{sep}obj{sep}") &&
                !f.FullName.Contains($"{sep}bin{sep}") &&
                !f.Name.EndsWith(".g.cs", StringComparison.OrdinalIgnoreCase) &&
                !f.Name.Contains(".designer.", StringComparison.OrdinalIgnoreCase) &&
                !f.Name.Contains(".g.i.", StringComparison.OrdinalIgnoreCase))
            .ToList();
    }

    private static FileData? AnalyzeFile(FileInfo file, DirectoryInfo root)
    {
        try
        {
            var source = File.ReadAllText(file.FullName);
            var tree = CSharpSyntaxTree.ParseText(source, path: file.FullName);
            var walker = new FileWalker(tree);
            walker.Visit(tree.GetRoot());

            var relativePath = Path.GetRelativePath(root.FullName, file.FullName)
                .Replace(Path.DirectorySeparatorChar, '/');

            return new FileData(relativePath, walker.Namespace, walker.Usings, walker.Types);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"  Warning: {file.Name}: {ex.Message}");
            return null;
        }
    }
}
