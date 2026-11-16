using System.Globalization;
using System.Text.RegularExpressions;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Agents;

/// <summary>Builds provider requests from role configuration, preserving immutable-version reuse.</summary>
public sealed partial class AgentPublisher
{
    private readonly IAgentPublishingClient _client;
    private readonly Dictionary<ModelRole, string> _models;
    private readonly string _endpoint;

    /// <summary>Only the injected client may contact a service; construction performs no IO.</summary>
    public AgentPublisher(IAgentPublishingClient client, IReadOnlyDictionary<ModelRole, string> models, string projectEndpoint)
    {
        ArgumentNullException.ThrowIfNull(client);
        ArgumentNullException.ThrowIfNull(models);
        _client = client;
        _models = new Dictionary<ModelRole, string>(models);
        _endpoint = projectEndpoint;
    }

    /// <summary>Publishes in roster order; missing role configuration fails before any request.</summary>
    public async Task<IReadOnlyList<PublishedAgent>> PublishAllAsync(AgentRoster roster,
        IReadOnlyDictionary<string, string>? versionPins = null, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(roster);
        foreach (var role in roster.Specs.Select(spec => spec.Role).Distinct())
        {
            _ = ModelFor(role);
        }

        var published = new List<PublishedAgent>();
        foreach (var spec in roster.Specs)
        {
            var pin = versionPins is not null && versionPins.TryGetValue(spec.Name, out var value) ? value : null;
            published.Add(await PublishAsync(spec, pin, cancellationToken).ConfigureAwait(false));
        }

        return published.AsReadOnly();
    }

    /// <summary>A supplied pin bypasses latest/create; otherwise identical model and instructions are reused.</summary>
    public async Task<PublishedAgent> PublishAsync(AgentSpec spec, string? pin = null, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(spec);
        cancellationToken.ThrowIfCancellationRequested();
        var model = ModelFor(spec.Role);
        var name = "tcc-" + spec.Name;
        var info = !string.IsNullOrEmpty(pin)
            ? await _client.GetVersionAsync(name, pin, cancellationToken).ConfigureAwait(false)
            : await ReuseOrCreateAsync(name, model, spec, cancellationToken).ConfigureAwait(false);
        var id = !string.IsNullOrEmpty(info.Id) ? info.Id : !string.IsNullOrEmpty(info.AgentId) ? info.AgentId : name;
        return new(spec.Name, info.Version, id, PortalUrl(_endpoint, id), model, name);
    }

    private async Task<AgentVersion> ReuseOrCreateAsync(string name, string model, AgentSpec spec, CancellationToken token)
    {
        IReadOnlyList<AgentVersion> versions;
        try { versions = await _client.ListVersionsAsync(name, token).ConfigureAwait(false); }
        catch (OperationCanceledException) { throw; }
        catch (Exception) { versions = []; } // Listing is advisory; create decides whether the provider is available.
        var latest = versions.MaxBy(version => int.TryParse(version.Version, CultureInfo.InvariantCulture, out var value) ? value : 0);
        if (latest?.Definition is { } current && current.Model == model && current.Instructions == spec.Instructions)
        {
            return latest;
        }

        var temperature = SupportsTemperature(model) ? spec.Temperature : null;
        return await _client.CreateVersionAsync(new(name, new(model, spec.Instructions, temperature)), token).ConfigureAwait(false);
    }

    private string ModelFor(ModelRole role) => _models.TryGetValue(role, out var model) && !string.IsNullOrWhiteSpace(model)
        ? model : throw new InvalidOperationException("A model must be supplied for every declared role.");

    /// <summary>Python checks the final slash-delimited deployment component, case-insensitively.</summary>
    public static bool SupportsTemperature(string model) =>
        !model[(model.LastIndexOf('/') + 1)..].Trim().StartsWith("gpt-5", StringComparison.OrdinalIgnoreCase);

    /// <summary>Deep-link projection mirrors the captured publisher without contacting the portal.</summary>
    public static string PortalUrl(string endpoint, string agentId)
    {
        var match = ProjectEndpoint().Match(endpoint);
        return match.Success
            ? $"https://ai.azure.com/build/agents?wsid=/projects/{match.Groups[2].Value}&account={match.Groups[1].Value}#{agentId}"
            : "https://ai.azure.com/";
    }

    [GeneratedRegex(@"^https://([^.]+)\.services\.ai\.azure\.com/api/projects/([^/]+)")]
    private static partial Regex ProjectEndpoint();
}
