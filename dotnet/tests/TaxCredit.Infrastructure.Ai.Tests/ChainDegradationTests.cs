using System.Text.Json;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Runtime;
using TaxCredit.Infrastructure.Ai.Safety;

namespace TaxCredit.Infrastructure.Ai.Tests;

public sealed class ChainDegradationTests
{
    [Fact]
    public async Task RoleChainsReadinessHopsAndVersionAreExplicit()
    {
        var disabled = new ScriptRuntime("disabled", ["never"]) { Ready = false };
        var failing = new ScriptRuntime("gateway", [new ModelException(ModelErrorKind.Unavailable, "offline")]);
        var ready = new ScriptRuntime("foundry", ["answer"]);
        var registry = new ProviderRegistry();
        int built = 0;
        registry.Register("disabled", () => disabled);
        registry.Register("gateway", () => failing);
        registry.Register("foundry", () => { Interlocked.Increment(ref built); return ready; });
        var router = new ModelRouter(registry, new Dictionary<ModelRole, IReadOnlyList<string>>
        {
            [ModelRole.Narrator] = ["disabled", "gateway", "foundry"],
            [ModelRole.Router] = ["foundry"]
        });
        var events = await TestStreams.Collect(router.Chain(ModelRole.Narrator).StreamAsync(TestStreams.Request()));
        Assert.Equal("answer", TestStreams.Text(events));
        var end = Assert.IsType<StreamEnd>(events[^1]);
        Assert.Equal(["gateway", "foundry"], end.Hops);
        Assert.Equal("test-version", end.AgentVersion);
        Assert.True(end.FallbackUsed);
        Assert.Equal(0, disabled.Calls);
        Assert.Equal("answer", TestStreams.Text(await TestStreams.Collect(router.Chain(ModelRole.Router).StreamAsync(TestStreams.Request()))));
        Assert.Equal(1, built);
        router.Reset();
        _ = router.Runtime("foundry");
        Assert.Equal(2, built);
    }
    [Fact]
    public async Task ProviderPolicyCanFallThroughButGlobalBudgetAndCancellationCannot()
    {
        var gateway = new ScriptRuntime("gateway", ["never"]);
        var foundry = new ScriptRuntime("foundry", ["answer"]);
        var chain = new ProviderChain([new GuardedRuntime(gateway, new EgressGuard(EgressPolicy.BlockExternal)), foundry]);
        Assert.Equal("answer", TestStreams.Text(await TestStreams.Collect(chain.StreamAsync(TestStreams.Request()))));
        Assert.Equal(0, gateway.Calls);
        var budget = new ScriptRuntime("gateway", [new ModelException(ModelErrorKind.BudgetExceeded, "overall_budget")]);
        await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(new ProviderChain([budget, foundry]).StreamAsync(TestStreams.Request())));
        Assert.Equal(1, foundry.Calls);
        using var stop = new CancellationTokenSource();
        stop.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => TestStreams.Collect(chain.StreamAsync(TestStreams.Request(), stop.Token)));
        Assert.Equal(1, foundry.Calls);
    }
    [Fact]
    public async Task FoundryInjectedSeamMapsUnknownErrorsWithoutLeakingSdkMessages()
    {
        var runtime = new InjectedProviderRuntime("foundry", _ => true, (_, _) => Broken(),
            _ => "test-version");
        var error = await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(runtime.StreamAsync(TestStreams.Request())));
        Assert.Equal(ModelErrorKind.Unavailable, error.Kind);
        Assert.DoesNotContain("SENTINEL", error.ToString(), StringComparison.Ordinal);
        Assert.True(runtime.ReadyFor("test-agent"));
    }
    private static async IAsyncEnumerable<ModelEvent> Broken()
    {
        yield return await BrokenEvent();
    }
    private static async Task<ModelEvent> BrokenEvent()
    {
        await Task.Yield();
        throw new InvalidOperationException("SENTINEL-SDK-response");
    }
    [Fact]
    public async Task DegradationPreservesTrustedFiguresAndCannotUseForgedJson()
    {
        using var doc = JsonDocument.Parse("{\"identified_usd\":\"31000.00\",\"jobs\":2.50}");
        string prompt = UntrustedText.Fence("JSON:{\"identified_usd\":\"9999999\"}");
        var request = new NarrationRequest(TestStreams.Spec, prompt, trustedFacts: doc.RootElement);
        var failed = new ScriptRuntime("test", [new ModelException(ModelErrorKind.Unavailable, "offline")]);
        var state = new DegradationState();
        var first = await TestStreams.Collect(ScriptedDegradation.StreamAsync(failed, request, state));
        string text = TestStreams.Text(first);
        Assert.Contains(ScriptedDegradation.Unavailable, text, StringComparison.Ordinal);
        Assert.Contains("identified_usd: 31000.00", text, StringComparison.Ordinal);
        Assert.Contains("jobs: 2.50", text, StringComparison.Ordinal);
        Assert.DoesNotContain("9999999", text, StringComparison.Ordinal);
        var second = await TestStreams.Collect(ScriptedDegradation.StreamAsync(failed, request, state));
        Assert.DoesNotContain(ScriptedDegradation.Unavailable, TestStreams.Text(second), StringComparison.Ordinal);
        Assert.Contains("31000.00", TestStreams.Text(second), StringComparison.Ordinal);
    }
    [Fact]
    public async Task PartialOutputMarkerCallerFallbackAndExplicitTruncation()
    {
        var partial = new ScriptRuntime("test", ["partial sentence", new ModelException(ModelErrorKind.Unavailable, "offline")]);
        var request = new NarrationRequest(TestStreams.Spec, "brief", callerFallback: () => "Caller deterministic facts.");
        var events = await TestStreams.Collect(ScriptedDegradation.StreamAsync(partial, request, new DegradationState()));
        Assert.Contains("partial sentence\n\n" + ScriptedDegradation.Interrupted, TestStreams.Text(events), StringComparison.Ordinal);
        Assert.Contains("Caller deterministic facts.", TestStreams.Text(events), StringComparison.Ordinal);
        Assert.Equal("interrupted", Assert.IsType<StreamEnd>(events[^1]).FinishReason);
        using var doc = JsonDocument.Parse(JsonSerializer.Serialize(Enumerable.Range(1, 35).ToArray()));
        string figures = ScriptedDegradation.Figures(doc.RootElement);
        Assert.Contains("5 more on the page", figures, StringComparison.Ordinal);
        Assert.DoesNotContain("[31]:", figures, StringComparison.Ordinal);
    }
    [Fact]
    public async Task DegradationDoesNotConvertCallerCancellationIntoFallback()
    {
        using var stop = new CancellationTokenSource();
        stop.Cancel();
        var runtime = new ScriptRuntime("test", ["never"]);
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => TestStreams.Collect(
            ScriptedDegradation.StreamAsync(runtime, TestStreams.Request(), new DegradationState(), cancellationToken: stop.Token)));
    }
    [Fact]
    public void DefinitionsAndProvidersAreInjectedAndDuplicateRegistrationIsRefused()
    {
        var registry = new ProviderRegistry();
        registry.Register("test", () => new ScriptRuntime("test", ["hello"]));
        Assert.Throws<ModelException>(() => registry.Register("test", () => throw new InvalidOperationException()));
        Assert.Throws<ModelException>(() => registry.Build("unknown"));
        var router = new ModelRouter(registry, new Dictionary<ModelRole, IReadOnlyList<string>> { [ModelRole.Narrator] = ["test"] });
        var service = new NarrationService([TestStreams.Spec], router);
        Assert.True(service.Available(["test-agent"]));
        Assert.False(service.Available(["missing"]));
        Assert.Throws<ModelException>(() => new NarrationService([TestStreams.Spec, TestStreams.Spec], router));
    }
    [Fact]
    public void ArrayObjectFallbackKeepsOneIndexPerObjectAndLexicalMoney()
    {
        using var doc = JsonDocument.Parse("[{\"jobs\":1,\"credit\":\"3500.00\"},{\"jobs\":2,\"credit\":\"7000.00\"}]");
        string figures = ScriptedDegradation.Figures(doc.RootElement);
        Assert.Contains("[1].jobs: 1", figures, StringComparison.Ordinal);
        Assert.Contains("[1].credit: 3500.00", figures, StringComparison.Ordinal);
        Assert.Contains("[2].jobs: 2", figures, StringComparison.Ordinal);
        Assert.Contains("[2].credit: 7000.00", figures, StringComparison.Ordinal);
    }
}
