using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Agents;

/// <summary>Publication declarations, not the page's display profiles.</summary>
public sealed record AgentDeclaration(string Module, string Name, string Prompt, ModelRole Role, double? Temperature)
{
    /// <summary>Agents narrate; tools always remain on the host.</summary>
    public IReadOnlyList<string> Tools { get; } = [];
}

/// <summary>Validates the entire estate before exposing any publishable definition.</summary>
public sealed class AgentRoster
{
    private static readonly string[] Fields = ["module", "name", "prompt", "role", "temperature", "tools"];

    private AgentRoster(IReadOnlyList<AgentDeclaration> agents,
        IReadOnlyDictionary<string, VersionedPrompt> prompts, PromptManifest manifest)
    {
        Agents = agents;
        Prompts = prompts;
        Manifest = manifest;
        Specs = Array.AsReadOnly(agents.Select(agent => new AgentSpec(agent.Name, prompts[agent.Prompt].Text,
            agent.Role, agent.Temperature, prompts[agent.Prompt].Version.ToString(CultureInfo.InvariantCulture))).ToArray());
    }

    /// <summary>Original publication order, never alphabetically reordered.</summary>
    public IReadOnlyList<AgentDeclaration> Agents { get; }
    /// <summary>Validated current bodies keyed by Markdown stem.</summary>
    public IReadOnlyDictionary<string, VersionedPrompt> Prompts { get; }
    /// <summary>Full recorded history, including channel narrator versions one through four.</summary>
    public PromptManifest Manifest { get; }
    /// <summary>Definitions ready for the existing W1 model router.</summary>
    public IReadOnlyList<AgentSpec> Specs { get; }

    /// <summary>The default is portable embedded resources; operator files require an explicit source.</summary>
    public static AgentRoster Load(IAgentResources? resources = null)
    {
        resources ??= new PackagedAgentResources();
        using var document = JsonDocument.Parse(resources.Read("roster.json"));
        var root = document.RootElement;
        if (root.GetProperty("format").GetInt32() != 1 || root.GetProperty("agents").ValueKind != JsonValueKind.Array)
        {
            throw new InvalidDataException("Agent roster must be format 1 with an agents list.");
        }

        var agents = root.GetProperty("agents").EnumerateArray().Select(ParseDeclaration).ToArray();
        CheckUnique(agents);
        var prompts = resources.PromptNames.ToDictionary(name => name,
            name => VersionedPrompt.Parse(name, resources.Read(name + ".md")), StringComparer.Ordinal);
        CheckCoverage(root, agents, prompts.Keys);
        var manifest = PromptManifest.Parse(resources.Read("manifest.json"));
        var problems = manifest.Check(prompts);
        if (problems.Count != 0)
        {
            throw new InvalidDataException(string.Join("; ", problems));
        }

        return new(Array.AsReadOnly(agents), new ReadOnlyDictionary<string, VersionedPrompt>(prompts), manifest);
    }

    private static AgentDeclaration ParseDeclaration(JsonElement raw)
    {
        if (raw.ValueKind != JsonValueKind.Object ||
            !raw.EnumerateObject().Select(field => field.Name).Order(StringComparer.Ordinal)
                .SequenceEqual(Fields.Order(StringComparer.Ordinal)))
        {
            throw new InvalidDataException("An agent entry has exactly the declared roster fields.");
        }

        var module = RequiredString(raw, "module");
        var name = RequiredString(raw, "name");
        var prompt = RequiredString(raw, "prompt");
        var role = RequiredString(raw, "role") switch
        {
            "router" => ModelRole.Router,
            "narrator" => ModelRole.Narrator,
            "analysis" => ModelRole.Analysis,
            _ => throw new InvalidDataException("Unknown model role.")
        };
        var temperature = ParseTemperature(raw.GetProperty("temperature"));
        if (raw.GetProperty("tools").ValueKind != JsonValueKind.Array || raw.GetProperty("tools").GetArrayLength() != 0)
        {
            throw new InvalidDataException("Agents hold no tools.");
        }

        return new(module, name, prompt, role, temperature);
    }

    private static string RequiredString(JsonElement raw, string key) =>
        raw.GetProperty(key).ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(raw.GetProperty(key).GetString())
            ? raw.GetProperty(key).GetString()!
            : throw new InvalidDataException("Agent identifiers must be non-empty strings.");

    private static double? ParseTemperature(JsonElement raw)
    {
        if (raw.ValueKind == JsonValueKind.Null) { return null; }
        if (raw.ValueKind != JsonValueKind.Number || !raw.TryGetDouble(out var value) || value is < 0 or > 2 || !double.IsFinite(value))
        {
            throw new InvalidDataException("Temperature must be null or a number from zero to two.");
        }

        return value;
    }

    private static void CheckUnique(AgentDeclaration[] agents)
    {
        foreach (var values in new[] { agents.Select(a => a.Module), agents.Select(a => a.Name), agents.Select(a => a.Prompt) })
        {
            if (values.Distinct(StringComparer.Ordinal).Count() != agents.Length)
            {
                throw new InvalidDataException("Two agents share a module, name or prompt.");
            }
        }
    }

    private static void CheckCoverage(JsonElement root, AgentDeclaration[] agents, IEnumerable<string> names)
    {
        var present = names.ToHashSet(StringComparer.Ordinal);
        var used = agents.Select(agent => agent.Prompt).ToHashSet(StringComparer.Ordinal);
        var excluded = root.TryGetProperty("excluded_prompts", out var value)
            ? value.EnumerateObject().ToDictionary(item => item.Name, item => item.Value.GetString(), StringComparer.Ordinal)
            : new Dictionary<string, string?>(StringComparer.Ordinal);
        if (used.Except(present).Any() || excluded.Keys.Any(name => !present.Contains(name) || used.Contains(name)) ||
            excluded.Values.Any(string.IsNullOrWhiteSpace) || present.Except(used).Except(excluded.Keys).Any())
        {
            throw new InvalidDataException("Every prompt must have a file and be assigned or explicitly excluded with a reason.");
        }
    }
}
