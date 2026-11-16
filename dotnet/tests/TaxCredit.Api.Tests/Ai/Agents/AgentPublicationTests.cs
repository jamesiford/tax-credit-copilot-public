using System.Text.Json;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Agents;

namespace TaxCredit.Api.Tests.Ai.Agents;

public sealed class AgentPublicationTests
{
    private const string Endpoint = "https://contract-account.services.ai.azure.com/api/projects/contract";

    [Fact]
    public async Task All_twelve_publish_in_roster_order_and_resolve_roles_from_supplied_configuration()
    {
        var roster = AgentRoster.Load();
        var client = new RecordingClient();
        var publisher = new AgentPublisher(client, new Dictionary<ModelRole, string>
        {
            [ModelRole.Router] = "configured-router",
            [ModelRole.Narrator] = "configured-narrator",
            [ModelRole.Analysis] = "configured-analysis"
        }, Endpoint);
        var result = await publisher.PublishAllAsync(roster);
        Assert.Equal(12, client.Created.Count);
        Assert.Equal(roster.Specs.Select(spec => "tcc-" + spec.Name), client.Created.Select(request => request.Name));
        Assert.Equal(roster.Specs.Select(spec => spec.Name), result.Select(agent => agent.Name));
        foreach (var (spec, request) in roster.Specs.Zip(client.Created))
        {
            Assert.Equal("configured-" + spec.Role.ToString().ToLowerInvariant(), request.Definition.Model);
        }

        await publisher.PublishAllAsync(roster);
        Assert.Equal(12, client.Created.Count);
    }

    [Fact]
    public async Task A_missing_model_role_refuses_the_whole_pass_before_creating_any_version()
    {
        var client = new RecordingClient();
        var publisher = new AgentPublisher(client, new Dictionary<ModelRole, string> { [ModelRole.Router] = "only-router" }, Endpoint);
        await Assert.ThrowsAsync<InvalidOperationException>(() => publisher.PublishAllAsync(AgentRoster.Load()));
        Assert.Empty(client.Created);
    }

    [Theory]
    [InlineData("gpt-5.4-mini", 0.3, false)]
    [InlineData("provider/ GPT-5 ", 0.3, false)]
    [InlineData("gpt-4.1", 0.3, true)]
    [InlineData("provider/gpt-4o", 0.3, true)]
    [InlineData("gpt-4o", null, false)]
    public async Task Unsupported_or_null_temperature_is_omitted_not_sent_as_null(string model, double? temperature, bool included)
    {
        var client = new RecordingClient();
        await Publisher(client, model).PublishAsync(new("SyntheticAgent", "Exact.\n", temperature: temperature));
        var request = Assert.Single(client.Created);
        using var wire = JsonDocument.Parse(JsonSerializer.Serialize(request.Definition));
        Assert.Equal(included, wire.RootElement.TryGetProperty("temperature", out var value));
        if (included) { Assert.Equal(temperature, value.GetDouble()); }
        Assert.False(wire.RootElement.TryGetProperty("tools", out _));
        Assert.Equal(2 + (included ? 1 : 0), wire.RootElement.EnumerateObject().Count());
    }

    [Fact]
    public async Task Changed_instructions_create_only_one_new_version_and_pins_bypass_list_and_create()
    {
        var roster = AgentRoster.Load();
        var client = new RecordingClient();
        var publisher = Publisher(client, "contract-model");
        await publisher.PublishAllAsync(roster);
        var spec = roster.Specs.Single(spec => spec.Name == "ReportingAgent");
        var changed = new AgentSpec(spec.Name, spec.Instructions + "A new rule.\n", spec.Role, spec.Temperature);
        var result = await publisher.PublishAsync(changed);
        Assert.Equal("2", result.Version);
        Assert.Equal(13, client.Created.Count);
        var lists = client.ListCalls;
        var pinned = await publisher.PublishAsync(changed, "1");
        Assert.Equal("1", pinned.Version);
        Assert.Equal(lists, client.ListCalls);
        Assert.Equal(13, client.Created.Count);
        Assert.Equal(("tcc-ReportingAgent", "1"), Assert.Single(client.Fetched));
    }

    [Fact]
    public async Task Reuse_selects_highest_numeric_version_and_matches_only_model_and_instructions()
    {
        var client = new RecordingClient();
        var spec = new AgentSpec("SyntheticAgent", "Exact.\n", temperature: 0.2);
        client.Versions["tcc-SyntheticAgent"] =
        [
            new("9", "nine", Definition: new("contract-model", "older", 0.2)),
            new("10", "ten", Definition: new("contract-model", spec.Instructions, 0.9)),
            new("non-numeric", "invalid", Definition: new("contract-model", "older", 0.2))
        ];
        var result = await Publisher(client, "contract-model").PublishAsync(spec);
        Assert.Equal("10", result.Version);
        Assert.Equal("ten", result.AgentId);
        Assert.Empty(client.Created);
    }

    [Fact]
    public async Task Listing_failure_defers_to_create_but_cancellation_is_never_swallowed()
    {
        var client = new RecordingClient { ListingFailure = new IOException("Synthetic failure") };
        var spec = AgentRoster.Load().Specs[0];
        await Publisher(client, "contract-model").PublishAsync(spec);
        Assert.Single(client.Created);
        client.ListingFailure = new OperationCanceledException();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Publisher(client, "contract-model").PublishAsync(spec));
        Assert.Single(client.Created);
    }

    [Theory]
    [InlineData(null, "alternate", "alternate")]
    [InlineData(null, null, "tcc-SyntheticAgent")]
    [InlineData("primary", "alternate", "primary")]
    public async Task Published_identity_uses_provider_id_then_agent_id_then_name(string? id, string? alternate, string expected)
    {
        var client = new RecordingClient { Response = new("7", id, alternate) };
        var result = await Publisher(client, "contract-model").PublishAsync(new("SyntheticAgent", "Exact.\n"));
        Assert.Equal(expected, result.AgentId);
        Assert.Equal("7", result.Version);
    }

    internal static AgentPublisher Publisher(RecordingClient client, string model) => new(client,
        Enum.GetValues<ModelRole>().ToDictionary(role => role, _ => model), Endpoint);
}

internal sealed class RecordingClient : IAgentPublishingClient
{
    internal List<AgentPublicationRequest> Created { get; } = [];
    internal Dictionary<string, List<AgentVersion>> Versions { get; } = new(StringComparer.Ordinal);
    internal List<(string Name, string Version)> Fetched { get; } = [];
    internal int ListCalls { get; private set; }
    internal Exception? ListingFailure { get; set; }
    internal AgentVersion? Response { get; set; }

    public Task<IReadOnlyList<AgentVersion>> ListVersionsAsync(string name, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        ListCalls++;
        if (ListingFailure is not null) { throw ListingFailure; }
        return Task.FromResult<IReadOnlyList<AgentVersion>>(Versions.TryGetValue(name, out var versions) ? versions : []);
    }

    public Task<AgentVersion> GetVersionAsync(string name, string version, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        Fetched.Add((name, version));
        return Task.FromResult(Versions[name].Single(item => item.Version == version));
    }

    public Task<AgentVersion> CreateVersionAsync(AgentPublicationRequest request, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        Created.Add(request);
        if (!Versions.TryGetValue(request.Name, out var versions))
        {
            versions = [];
            Versions.Add(request.Name, versions);
        }

        var number = (versions.Count + 1).ToString(System.Globalization.CultureInfo.InvariantCulture);
        var result = Response ?? new AgentVersion(number, $"{request.Name}:{number}", Definition: request.Definition);
        versions.Add(result);
        return Task.FromResult(result);
    }
}
