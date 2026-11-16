using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;

namespace TaxCredit.Infrastructure.Ai.Agents;

/// <summary>History remains available, but only the authored current version can validate.</summary>
public sealed class PromptManifest
{
    private readonly ReadOnlyDictionary<string, IReadOnlyDictionary<int, string>> _history;

    private PromptManifest(Dictionary<string, IReadOnlyDictionary<int, string>> history) =>
        _history = new ReadOnlyDictionary<string, IReadOnlyDictionary<int, string>>(history);

    /// <summary>Recorded hashes include superseded versions; no entry is silently refreshed.</summary>
    public IReadOnlyDictionary<string, IReadOnlyDictionary<int, string>> History => _history;

    /// <summary>Loads the immutable history from packaged or operator-supplied metadata.</summary>
    public static PromptManifest Parse(string json)
    {
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;
        if (root.GetProperty("format").GetInt32() != 1)
        {
            throw new InvalidDataException("Prompt manifest must be format 1.");
        }

        var history = new Dictionary<string, IReadOnlyDictionary<int, string>>(StringComparer.Ordinal);
        foreach (var prompt in root.GetProperty("prompts").EnumerateObject())
        {
            var versions = prompt.Value.GetProperty("versions").EnumerateObject().ToDictionary(
                item => int.Parse(item.Name, CultureInfo.InvariantCulture), item => item.Value.GetString()!);
            if (versions.Count == 0 || versions.Values.Any(hash =>
                    hash.Length != 64 || hash.Any(c => c is not (>= '0' and <= '9' or >= 'a' and <= 'f'))))
            {
                throw new InvalidDataException("Manifest versions must contain SHA-256 hashes.");
            }

            history.Add(prompt.Name, new ReadOnlyDictionary<int, string>(versions));
        }

        return new(history);
    }

    /// <summary>Refuses missing, changed, stale or unlogged current definitions before publication.</summary>
    public IReadOnlyList<string> Check(IReadOnlyDictionary<string, VersionedPrompt> prompts)
    {
        ArgumentNullException.ThrowIfNull(prompts);
        var problems = new List<string>();
        foreach (var name in prompts.Keys.Except(_history.Keys).Order(StringComparer.Ordinal))
        {
            problems.Add($"{name}: has no entry in the manifest");
        }

        foreach (var name in _history.Keys.Except(prompts.Keys).Order(StringComparer.Ordinal))
        {
            problems.Add($"{name}: is in the manifest but has no prompt file");
        }

        foreach (var name in prompts.Keys.Intersect(_history.Keys).Order(StringComparer.Ordinal))
        {
            CheckCurrent(prompts[name], _history[name], problems);
        }

        return problems.AsReadOnly();
    }

    private static void CheckCurrent(VersionedPrompt prompt, IReadOnlyDictionary<int, string> versions, List<string> problems)
    {
        if (!versions.TryGetValue(prompt.Version, out var expected))
        {
            problems.Add($"{prompt.Name}: version {prompt.Version} is not in the manifest");
            return;
        }

        if (expected != prompt.Sha256)
        {
            problems.Add($"{prompt.Name}: text changed but version {prompt.Version} did not");
        }

        if (prompt.Version < versions.Keys.Max())
        {
            problems.Add($"{prompt.Name}: version {prompt.Version} is older than a recorded version");
        }

        if (!prompt.HasChangelog)
        {
            problems.Add($"{prompt.Name}: the changelog has no line for version {prompt.Version}");
        }
    }
}
