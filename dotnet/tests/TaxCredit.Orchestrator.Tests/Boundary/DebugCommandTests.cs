using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging;
using TaxCredit.Orchestrator.Boundary;

namespace TaxCredit.Orchestrator.Tests.Boundary;

public sealed class DebugCommandTests
{
    [Theory]
    [InlineData("/whoami")]
    [InlineData("/netcheck")]
    [InlineData("/modelprobe")]
    public async Task Debug_off_commands_are_inert_with_no_identity_or_diagnostic_calls(string command)
    {
        var diagnostics = new Diagnostics();
        var logger = new TestLogger();
        var handler = new DebugCommandHandler(new IdentityOptions(IdentityTests.Tenant), diagnostics, logger);
        Assert.Null(await handler.TryHandleAsync(command, new IdentityContext()));
        Assert.Equal(0, diagnostics.Calls);
        Assert.Empty(logger.Messages);
    }

    [Fact]
    public async Task Enabled_startup_warns_and_whoami_resolves_header_case_without_exposing_credentials()
    {
        var logger = new TestLogger();
        var handler = new DebugCommandHandler(
            new IdentityOptions(IdentityTests.Tenant, sources: ["client-headers"], debugWhoami: true), logger: logger);
        var context = new IdentityContext(new Dictionary<string, string>
        {
            ["X-Client-Acting-User-Oid"] = IdentityTests.Person,
            ["X-Client-Acting-User-Name"] = "Pat Writer",
            ["Authorization"] = "Bearer secret-token",
            ["Cookie"] = "private-cookie",
            ["X-Unknown-Private"] = "private-header",
        }, ConversationId: "conversation-1");
        var text = await handler.TryHandleAsync(" /WhOaMi ", context,
            new DebugRuntimeState(["foundry"], ToolsAvailable: true, ModelConfigured: true));
        var report = JsonNode.Parse(text!)!;
        Assert.Equal("client-headers", report["identity"]!["source"]!.GetValue<string>());
        Assert.Equal(IdentityTests.Person, report["identity"]!["oid"]!.GetValue<string>());
        Assert.Equal("Pat Writer", report["identity"]!["display_name"]!.GetValue<string>());
        Assert.Equal("conversation-1", report["identity"]!["conversation"]!.GetValue<string>());
        Assert.Equal("foundry", report["providers"]![0]!.GetValue<string>());
        Assert.Equal(0, report["turns"]!["audit_failures"]!.GetValue<int>());
        Assert.DoesNotContain("secret-token", text!, StringComparison.Ordinal);
        Assert.DoesNotContain("private-cookie", text!, StringComparison.Ordinal);
        Assert.DoesNotContain("private-header", text!, StringComparison.Ordinal);
        Assert.DoesNotContain("Authorization", text!, StringComparison.OrdinalIgnoreCase);
        var warning = Assert.Single(logger.Messages);
        Assert.Equal(LogLevel.Warning, warning.Level);
        Assert.Contains("CHANNEL_DEBUG_WHOAMI is ON", warning.Message, StringComparison.Ordinal);
        Assert.Contains("DEMO-CLEANUP.md", warning.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Enabled_whoami_explains_absent_signals_but_hides_an_opaque_partition_identifier()
    {
        var handler = new DebugCommandHandler(new IdentityOptions(IdentityTests.Tenant, debugWhoami: true));
        var text = await handler.TryHandleAsync("/whoami", new IdentityContext(AgentUserId: "opaque-private-partition",
            ConversationChainId: "chain"));
        var report = JsonNode.Parse(text!)!;
        Assert.False(report["identity"]!["resolved"]!.GetValue<bool>());
        Assert.Contains("no configured source", report["identity"]!["reason"]!.GetValue<string>(), StringComparison.Ordinal);
        Assert.Equal("x-agent-user-id", report["signals"]!["present"]![0]!.GetValue<string>());
        Assert.Equal("opaque", report["signals"]!["agent_user_id"]!["kind"]!.GetValue<string>());
        Assert.DoesNotContain("opaque-private-partition", text!, StringComparison.Ordinal);
        Assert.False(report["signals"]!["agent_user_id"]!.AsObject().ContainsKey("value"));
    }

    [Fact]
    public void Agent_guid_shape_reports_only_the_explicitly_permitted_identity_value()
    {
        var report = IdentityPresenter.DescribeSignals(new IdentityContext(
            new Dictionary<string, string> { ["x-ms-user-identity"] = IdentityTests.Person },
            AgentUserId: IdentityTests.Person));
        var shape = report["agent_user_id"]!;
        Assert.Equal("guid", shape["kind"]!.GetValue<string>());
        Assert.Equal(36, shape["length"]!.GetValue<int>());
        Assert.True(shape["equals_an_oid_signal"]!.GetValue<bool>());
        Assert.Equal(IdentityTests.Person, shape["value"]!.GetValue<string>());
        Assert.Null(IdentityPresenter.DescribeSignals(new IdentityContext())["agent_user_id"]);
    }

    [Theory]
    [InlineData("/netcheck", "targets")]
    [InlineData("/modelprobe", "ok")]
    public async Task Enabled_diagnostics_use_only_injected_local_collaborators(string command, string expected)
    {
        var diagnostics = new Diagnostics();
        var handler = new DebugCommandHandler(new IdentityOptions(IdentityTests.Tenant, debugWhoami: true), diagnostics);
        var report = JsonNode.Parse((await handler.TryHandleAsync(command, new IdentityContext()))!)!.AsObject();
        Assert.True(report.ContainsKey(expected));
        Assert.Equal(1, diagnostics.Calls);
    }

    [Fact]
    public async Task Missing_diagnostics_is_explicitly_unconfigured_not_live_network_fallback()
    {
        var handler = new DebugCommandHandler(new IdentityOptions(IdentityTests.Tenant, debugWhoami: true));
        var report = JsonNode.Parse((await handler.TryHandleAsync("/netcheck", new IdentityContext()))!)!;
        Assert.False(report["ok"]!.GetValue<bool>());
        Assert.Equal("diagnostics_not_configured", report["error"]!.GetValue<string>());
        Assert.Null(await handler.TryHandleAsync("ordinary question", new IdentityContext()));
    }

    private sealed class Diagnostics : IDebugDiagnostics
    {
        public int Calls { get; private set; }
        public Task<JsonObject> RunNetcheckAsync(CancellationToken cancellationToken = default)
        {
            Calls++;
            return Task.FromResult(new JsonObject { ["targets"] = new JsonArray() });
        }
        public Task<JsonObject> RunModelProbeAsync(CancellationToken cancellationToken = default)
        {
            Calls++;
            return Task.FromResult(new JsonObject { ["ok"] = true });
        }
    }

    private sealed class TestLogger : ILogger<DebugCommandHandler>
    {
        public List<(LogLevel Level, string Message)> Messages { get; } = [];
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
        public bool IsEnabled(LogLevel logLevel) => true;
        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception,
            Func<TState, Exception?, string> formatter) => Messages.Add((logLevel, formatter(state, exception)));
    }
}
