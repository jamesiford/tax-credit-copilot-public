using System.Text.Json.Serialization;

namespace TaxCredit.Infrastructure.Ai.Agents;

/// <summary>SDK-neutral definition; omitted sampling is different from explicitly supplying null.</summary>
public sealed record PromptAgentDefinition(
    [property: JsonPropertyName("model")] string Model,
    [property: JsonPropertyName("instructions")] string Instructions,
    [property: JsonPropertyName("temperature"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] double? Temperature)
{
    /// <summary>No function tools are attached to a prompt agent.</summary>
    [JsonIgnore]
    public IReadOnlyList<string> Tools { get; } = [];
}

/// <summary>The exact create-version seam exercised by a fake, not a claim of installed SDK support.</summary>
public sealed record AgentPublicationRequest(string Name, PromptAgentDefinition Definition)
{
    /// <summary>Captured provider operation.</summary>
    public string Call { get; } = "agents.create_version";
    /// <summary>No extra provider keyword arguments.</summary>
    public IReadOnlyList<string> ExtraKeywordArguments { get; } = [];
}

/// <summary>Provider response with both historical identity shapes supported.</summary>
public sealed record AgentVersion(string Version, string? Id = null, string? AgentId = null, PromptAgentDefinition? Definition = null);

/// <summary>The production SDK adapter is supplied by composition, never silently constructed.</summary>
public interface IAgentPublishingClient
{
    /// <summary>Lists immutable published versions for reuse.</summary>
    Task<IReadOnlyList<AgentVersion>> ListVersionsAsync(string name, CancellationToken cancellationToken);
    /// <summary>Fetches a configured rollback version without creating another.</summary>
    Task<AgentVersion> GetVersionAsync(string name, string version, CancellationToken cancellationToken);
    /// <summary>Creates one immutable version with no additional tools or keyword arguments.</summary>
    Task<AgentVersion> CreateVersionAsync(AgentPublicationRequest request, CancellationToken cancellationToken);
}

/// <summary>Catalog projection separates the internal spec key from the published provider name.</summary>
public sealed record PublishedAgent(string Name, string Version, string AgentId, string PortalUrl, string Model, string PublishedName);
