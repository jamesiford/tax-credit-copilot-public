using System.Text;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Infrastructure.Rules;

/// <summary>Where the rules folder is. The folder is configuration (Python <c>RULES_DIR</c> and <c>PROGRAM_REGISTRY_FILE</c>), never a copy of it.</summary>
public sealed record RulePackOptions
{
    /// <summary>The rules folder, for example <c>backend/rules</c>.</summary>
    public required string RulesDirectory { get; init; }

    /// <summary>The registry manifest; <c>null</c> means <c>registry/programs.json</c> inside <see cref="RulesDirectory"/>.</summary>
    public string? RegistryFile { get; init; }

    /// <summary>The captured ingestion configs (<c>backend/data/rules_ingested</c>); <c>null</c> means the ingestion hook is "none".</summary>
    public string? IngestedConfigDirectory { get; init; }

    /// <summary>The JSON Schema file of rule packs; <c>null</c> means <c>schema/rule-pack.schema.json</c> inside <see cref="RulesDirectory"/> (Python reads it beside the module, which is the same file).</summary>
    public string? SchemaFile { get; init; }
}

/// <summary>
/// <see cref="IRulePackSource"/> over a folder of JSON files: the adapter that reads the SAME <c>rules/</c> tree the Python tools read.
/// </summary>
/// <remarks>
/// Text is read as Python's <c>read_text(encoding="utf-8")</c> does: strict UTF-8, a byte-order mark kept (so a BOM-prefixed manifest fails the
/// same way), and universal newlines. A relative path that would leave the rules folder is refused; Python would follow it, but no manifest names one.
/// </remarks>
public sealed class JsonRulePackSource : IRulePackSource
{
    private static readonly UTF8Encoding Strict = new(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true);
    private readonly string _root;
    private readonly string _registryFile;

    /// <summary>Initialises the source.</summary>
    /// <param name="options">The folder and optional manifest location.</param>
    public JsonRulePackSource(RulePackOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        _root = Path.GetFullPath(options.RulesDirectory);
        _registryFile = options.RegistryFile is { Length: > 0 } custom
            ? Path.GetFullPath(custom)
            : Path.Combine(_root, "registry", "programs.json");
    }

    /// <inheritdoc />
    public string RulesDirectory => _root;

    /// <inheritdoc />
    public string RegistryFile => _registryFile;

    /// <inheritdoc />
    public bool Exists(string relativePath) => File.Exists(Resolve(relativePath)) || Directory.Exists(Resolve(relativePath));

    /// <inheritdoc />
    public bool IsFile(string relativePath) => File.Exists(Resolve(relativePath));

    /// <inheritdoc />
    public bool IsDirectory(string relativePath) => Directory.Exists(Resolve(relativePath));

    /// <inheritdoc />
    public string ReadText(string relativePath) => Read(Resolve(relativePath));

    /// <inheritdoc />
    public IReadOnlyList<string> ListJsonStems(string relativeFolder)
    {
        var folder = Resolve(relativeFolder);
        return Directory.Exists(folder)
            ? Directory.EnumerateFiles(folder).Select(f => Path.GetFileName(f)).Where(n => n.EndsWith(".json", StringComparison.OrdinalIgnoreCase)).Select(n => Path.GetFileNameWithoutExtension(n)).ToList()
            : [];
    }

    /// <inheritdoc />
    public long? RegistryStamp() =>
        File.Exists(_registryFile) ? (File.GetLastWriteTimeUtc(_registryFile) - DateTime.UnixEpoch).Ticks * 100L : null;

    /// <inheritdoc />
    public string ReadRegistryText() => Read(_registryFile);

    private static string Read(string fullPath)
    {
        if (!File.Exists(fullPath))
        {
            throw new PyFileNotFoundError($"[Errno 2] No such file or directory: '{fullPath}'");
        }

        var text = Strict.GetString(File.ReadAllBytes(fullPath));
        return text.Replace("\r\n", "\n", StringComparison.Ordinal).Replace('\r', '\n');
    }

    private string Resolve(string relativePath)
    {
        var full = Path.GetFullPath(Path.Combine(_root, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        var inside = string.Equals(full, _root, StringComparison.OrdinalIgnoreCase)
            || full.StartsWith(_root.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
        return inside ? full : throw new InvalidOperationException($"path escapes the rules folder: {relativePath}");
    }
}

/// <summary><see cref="IIngestedConfigFiles"/> over the captured ingestion folder (<c>backend/data/rules_ingested</c>).</summary>
public sealed class JsonIngestedConfigFiles : IIngestedConfigFiles
{
    private static readonly UTF8Encoding Strict = new(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true);
    private readonly string _root;

    /// <summary>Initialises the reader.</summary>
    /// <param name="directory">The folder holding the ingested configs.</param>
    public JsonIngestedConfigFiles(string directory)
    {
        ArgumentNullException.ThrowIfNull(directory);
        _root = Path.GetFullPath(directory);
    }

    /// <inheritdoc />
    public string? ReadText(string fileName)
    {
        var full = Path.GetFullPath(Path.Combine(_root, fileName));
        if (!full.StartsWith(_root.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException($"path escapes the ingested-config folder: {fileName}");
        }

        return File.Exists(full)
            ? Strict.GetString(File.ReadAllBytes(full)).Replace("\r\n", "\n", StringComparison.Ordinal).Replace('\r', '\n')
            : null;
    }
}
