using System.Collections;
using System.Resources;
using System.Text;

namespace TaxCredit.Infrastructure.Ai.Agents;

/// <summary>Allows packaged prompts and explicitly located operator bundles to share validation.</summary>
public interface IAgentResources
{
    /// <summary>Reads roster.json, manifest.json or a prompt's Markdown filename.</summary>
    string Read(string name);

    /// <summary>Lists Markdown stems only; the manifest is metadata, not an agent.</summary>
    IReadOnlyList<string> PromptNames { get; }
}

/// <summary>Default SDK resx glob embeds this bundle without deployment-directory assumptions.</summary>
public sealed class PackagedAgentResources : IAgentResources
{
    private static readonly ResourceManager Resources = new(
        "TaxCredit.Infrastructure.Ai.Agents.Resources.Prompts", typeof(PackagedAgentResources).Assembly);

    /// <inheritdoc/>
    public string Read(string name) =>
        Resources.GetString(name, System.Globalization.CultureInfo.InvariantCulture)
        ?? throw new InvalidDataException("Agent resource is missing.");

    /// <inheritdoc/>
    public IReadOnlyList<string> PromptNames => Resources
        .GetResourceSet(System.Globalization.CultureInfo.InvariantCulture, true, true)!
        .Cast<DictionaryEntry>().Select(entry => (string)entry.Key)
        .Where(name => name.EndsWith(".md", StringComparison.Ordinal))
        .Select(Path.GetFileNameWithoutExtension).Select(name => name!)
        .Order(StringComparer.Ordinal).ToArray();
}

/// <summary>An explicit absolute bundle directory avoids searching a planner's source checkout.</summary>
public sealed class DirectoryAgentResources : IAgentResources
{
    private static readonly UTF8Encoding StrictUtf8 = new(false, true);
    private readonly string _directory;

    /// <summary>The directory contains agents.json and prompts/ with Markdown and manifest.json.</summary>
    public DirectoryAgentResources(string baseDirectory)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(baseDirectory);
        if (!Path.IsPathFullyQualified(baseDirectory))
        {
            throw new ArgumentException("An absolute agent bundle directory is required.", nameof(baseDirectory));
        }

        _directory = baseDirectory;
    }

    /// <inheritdoc/>
    public string Read(string name)
    {
        if (name != Path.GetFileName(name) || name.IndexOfAny(['\\', '/', ':']) >= 0)
        {
            throw new InvalidDataException("Invalid agent resource name.");
        }

        var path = name == "roster.json"
            ? Path.Combine(_directory, "agents.json")
            : Path.Combine(_directory, "prompts", name);
        // Python read_text uses universal newlines and keeps a BOM, unlike ReadAllText.
        return StrictUtf8.GetString(File.ReadAllBytes(path))
            .Replace("\r\n", "\n", StringComparison.Ordinal).Replace('\r', '\n');
    }

    /// <inheritdoc/>
    public IReadOnlyList<string> PromptNames => Directory
        .EnumerateFiles(Path.Combine(_directory, "prompts"), "*.md")
        .Select(Path.GetFileNameWithoutExtension).Select(name => name!)
        .Order(StringComparer.Ordinal).ToArray();
}
