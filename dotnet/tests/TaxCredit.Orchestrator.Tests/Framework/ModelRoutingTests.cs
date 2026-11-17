using Microsoft.Extensions.AI;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai;
using TaxCredit.Infrastructure.Ai.Budget;
using TaxCredit.Infrastructure.Ai.Resilience;
using TaxCredit.Infrastructure.Ai.Safety;
using TaxCredit.Orchestrator.Framework;
using TaxCredit.Orchestrator.Tests.Support;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;

namespace TaxCredit.Orchestrator.Tests.Framework;

public sealed class ModelRoutingTests
{
    [Fact]
    public async Task W1_chains_preserve_fallback_and_account_for_each_actual_attempt()
    {
        using var first = new ScriptedModel(ScriptedModel.Error());
        using var second = new ScriptedModel(ScriptedModel.Text("The available evidence is shown."));
        var budget = new InMemoryTokenBudget();
        using var router = new FrameworkModelRouter(new Dictionary<string, IChatClient> { ["gateway"] = first, ["foundry"] = second },
            Chains(["gateway", "foundry"]), budget, Options(), () => "verified-person");
        var answer = await router.GetResponseAsync([new ChatMessage(ChatRole.User, "Read this summary.")]);
        Assert.Equal("The available evidence is shown.", answer.Text);
        Assert.Single(first.Seen);
        Assert.Single(second.Seen);
        Assert.True(budget.Used("verified-person") > 0);
    }

    [Fact]
    public async Task Narrator_override_decides_the_orchestrator_chain_without_discarding_other_roles()
    {
        using var foundry = new ScriptedModel(ScriptedModel.Text("Narrator"));
        using var gateway = new ScriptedModel(ScriptedModel.Text("Router"));
        var chains = Chains(["gateway"]);
        chains[ModelRole.Narrator] = ["foundry"];
        using var router = new FrameworkModelRouter(new Dictionary<string, IChatClient> { ["gateway"] = gateway, ["foundry"] = foundry },
            chains, new InMemoryTokenBudget(), Options());
        var narration = await router.GetResponseAsync([new ChatMessage(ChatRole.User, "Describe the evidence.")]);
        var routing = await router.GetResponseAsync([new ChatMessage(ChatRole.User, "Choose a capability.")],
            new ChatOptions { AdditionalProperties = new() { ["tcc.role"] = ModelRole.Router } });
        Assert.Equal("Narrator", narration.Text);
        Assert.Equal("Router", routing.Text);
    }

    [Fact]
    public async Task Real_framework_loop_runs_inside_the_existing_W1_guard_budget_and_resilience_adapters()
    {
        using var raw = new ScriptedModel(ScriptedModel.Tools(("client_trend", new())), ScriptedModel.Text("The trend is shown."));
        var budget = new InMemoryTokenBudget();
        using var router = new FrameworkModelRouter(new Dictionary<string, IChatClient> { ["foundry"] = raw },
            Chains(["foundry"]), budget, Options());
        var rig = new Rig(router);
        var answer = await rig.SayAsync("How has Cascade trended?");
        Assert.True(answer.NarrationUsed);
        Assert.Equal(2, raw.Seen.Count);
        Assert.True(budget.Used() > 0);
    }

    [Fact]
    public async Task A_text_only_provider_is_skipped_for_framework_calls_but_preserved_for_json_planning()
    {
        using var gateway = new ScriptedModel(ScriptedModel.Text("JSON planner"));
        using var foundry = new ScriptedModel(ScriptedModel.Tools(("client_trend", new())), ScriptedModel.Text("The trend is shown."));
        using var router = new FrameworkModelRouter(new Dictionary<string, IChatClient> { ["gateway"] = gateway, ["foundry"] = foundry },
            Chains(["gateway", "foundry"]), new InMemoryTokenBudget(), Options(),
            supportsTools: new Dictionary<string, bool> { ["gateway"] = false });
        var rig = new Rig(router);
        var answer = await rig.SayAsync("How has Cascade trended?");
        Assert.True(answer.NarrationUsed);
        Assert.Empty(gateway.Seen);
        var plan = await router.GetResponseAsync([new ChatMessage(ChatRole.User, "Choose tools in JSON.")]);
        Assert.Equal("JSON planner", plan.Text);
        Assert.Single(gateway.Seen);
    }

    [Theory]
    [InlineData("record", EgressPolicy.AllowAll)]
    [InlineData("employee", EgressPolicy.AllowAll)]
    [InlineData("external", EgressPolicy.BlockExternal)]
    public async Task A_guard_refusal_happens_before_transport_and_never_selects_an_unconfigured_default(string kind, EgressPolicy policy)
    {
        using var raw = new ScriptedModel(ScriptedModel.Text("must not run"));
        using var router = new FrameworkModelRouter(new Dictionary<string, IChatClient> { ["gateway"] = raw },
            Chains(["gateway"]), new InMemoryTokenBudget(), Options() with { Egress = policy });
        var prompt = kind switch
        {
            "record" => "record " + Convert.ToHexStringLower(Enumerable.Range(0, 12).Select(value => (byte)value).ToArray()),
            "employee" => """{"employee_id":"private"}""",
            _ => "Read the supplied evidence.",
        };
        await Assert.ThrowsAsync<ModelException>(() => router.GetResponseAsync([new ChatMessage(ChatRole.User, prompt)]));
        Assert.Empty(raw.Seen);
    }

    [Fact]
    public void Missing_chain_provider_is_a_configuration_error_not_a_default_client()
    {
        var error = Assert.Throws<ModelException>(() => new FrameworkModelRouter(new Dictionary<string, IChatClient>(),
            Chains(["foundry"]), new InMemoryTokenBudget(), Options()));
        Assert.Equal(ModelErrorKind.Configuration, error.Kind);
    }

    [Fact]
    public async Task An_identifier_in_the_reader_question_never_reaches_a_model_wire()
    {
        using var raw = new ScriptedModel(ScriptedModel.Error());
        var rig = new Rig(raw);
        var handle = Convert.ToHexStringLower(Enumerable.Range(0, 12).Select(value => (byte)value).ToArray());
        var answer = await rig.SayAsync("How has Cascade trended? Record " + handle);
        Assert.Equal("keywords", answer.Mode);
        Assert.Empty(raw.Seen);
        Assert.Empty(rig.Gateway.Narrations);
    }

    [Fact]
    public async Task An_SDK_call_timeout_cancels_the_attempt_and_degrades_without_replaying_tools()
    {
        using var raw = new UnresponsiveClient();
        using var router = new FrameworkModelRouter(new Dictionary<string, IChatClient> { ["foundry"] = raw },
            Chains(["foundry"]), new InMemoryTokenBudget(), Options() with
            {
                Resilience = new ResilienceSettings(RetryAttempts: 1, EventGap: TimeSpan.FromMilliseconds(20), Deadline: TimeSpan.FromSeconds(1)),
            });
        var rig = new Rig(router);
        var reply = await rig.SayAsync("How has Cascade trended?");
        Assert.Contains("494.25", reply.Text, StringComparison.Ordinal);
        Assert.Contains("unavailable", reply.Text, StringComparison.Ordinal);
        Assert.Equal(["client_resolve", "client_trend"], rig.Gateway.Calls.Select(call => call.Tool));
        Assert.Equal(1, raw.Calls);
        Assert.True(raw.Cancelled);
    }

    private static Dictionary<ModelRole, IReadOnlyList<string>> Chains(IReadOnlyList<string> chain) =>
        Enum.GetValues<ModelRole>().ToDictionary(role => role, _ => chain);
    private static AiRuntimeOptions Options() => new()
    {
        Resilience = new ResilienceSettings(RetryAttempts: 1, EventGap: TimeSpan.FromSeconds(2), Deadline: TimeSpan.FromSeconds(3)),
    };

    private sealed class UnresponsiveClient : IChatClient
    {
        internal int Calls { get; private set; }
        internal bool Cancelled { get; private set; }
        public async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            Calls++;
            try { await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken); }
            catch (OperationCanceledException) { Cancelled = true; throw; }
            throw new InvalidOperationException("An infinite wait completed.");
        }
        public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages,
            ChatOptions? options = null, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public object? GetService(Type serviceType, object? serviceKey = null) => null;
        public void Dispose() { }
    }
}
