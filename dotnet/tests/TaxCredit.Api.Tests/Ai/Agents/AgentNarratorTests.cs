using System.Runtime.CompilerServices;
using System.Text.Json;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Agents;
using TaxCredit.Infrastructure.Ai.Runtime;

namespace TaxCredit.Api.Tests.Ai.Agents;

public sealed class AgentNarratorTests
{
    [Fact]
    public async Task Bridge_supplies_the_validated_spec_and_trusted_facts_to_the_existing_router()
    {
        var runtime = new RecordingRuntime();
        var narrator = Narrator(runtime);
        Assert.True(narrator.Available(["PageSummaryAgent", "OrchestratorAgent"]));
        Assert.False(narrator.Available(["NotAnAgent"]));
        using var facts = JsonDocument.Parse("""{"calculated":false}""");
        var events = new List<ModelEvent>();
        await foreach (var item in narrator.StreamAsync("PageSummaryAgent", "Trusted brief.", "synthetic-reader", facts.RootElement))
        {
            events.Add(item);
        }

        Assert.Collection(events, item => Assert.IsType<TextDelta>(item), item => Assert.IsType<StreamEnd>(item));
        Assert.NotNull(runtime.Request);
        Assert.Equal(AgentRoster.Load().Specs.Single(spec => spec.Name == "PageSummaryAgent").Instructions,
            runtime.Request.Spec.Instructions);
        Assert.Equal("1", runtime.Request.Spec.Version);
        Assert.Equal("Trusted brief.", runtime.Request.Prompt);
        Assert.Equal("synthetic-reader", runtime.Request.Principal);
        Assert.Equal(facts.RootElement.GetRawText(), runtime.Request.TrustedFacts!.Value.GetRawText());
    }

    [Fact]
    public void The_bridge_does_not_make_an_offline_provider_available()
    {
        var narrator = Narrator(new RecordingRuntime { Ready = false });
        Assert.False(narrator.Available(["PageSummaryAgent"]));
    }

    [Fact]
    public async Task Cancellation_flows_to_the_existing_stream_without_becoming_a_fallback()
    {
        var runtime = new RecordingRuntime();
        var narrator = Narrator(runtime);
        using var facts = JsonDocument.Parse("{}");
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
        {
            await foreach (var _ in narrator.StreamAsync("PageSummaryAgent", "Brief.", "synthetic-reader",
                facts.RootElement, cancellation.Token))
            {
                Assert.Fail("Cancelled narration must not yield a token.");
            }
        });
        Assert.Null(runtime.Request);
    }

    private static AgentNarrator Narrator(RecordingRuntime runtime)
    {
        var registry = new ProviderRegistry();
        registry.Register("scripted", () => runtime);
        var router = new ModelRouter(registry, Enum.GetValues<ModelRole>()
            .ToDictionary(role => role, _ => (IReadOnlyList<string>)["scripted"]));
        return new(AgentRoster.Load(), router);
    }

    private sealed class RecordingRuntime : IAgentRuntime
    {
        internal NarrationRequest? Request { get; private set; }
        internal bool Ready { get; init; } = true;
        public string Name => "scripted";
        public bool ReadyFor(string agentName) => Ready;
        public string? VersionOf(string agentName) => "1";
        public ProviderStatus Status() => new(Name, Ready ? ProviderState.Ready : ProviderState.Disabled);

        public async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Request = request;
            await Task.Yield();
            yield return new TextDelta("Trusted narration.");
            yield return new StreamEnd(Name, "configured-model", "1");
        }
    }
}
