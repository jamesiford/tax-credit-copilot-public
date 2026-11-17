using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Gateway.Tests;

public sealed class GatewayFailureTests
{
    [Fact]
    public async Task Required_opening_audit_failure_prevents_the_application_read()
    {
        var audit = new AuditSink { FailPhase = "begin" };
        var bridge = new ReadBridge("unexpected");
        await using var host = Fixture(audit, bridge);
        await host.InitializeAsync();
        using var response = await host.Tool("calc_walkthrough", await host.Token(), new() { ["client_id"] = 1001, ["tax_year"] = 2025 });
        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        Assert.Equal("audit_unavailable", (await response.Content.ReadFromJsonAsync<JsonObject>())!["error"]!["code"]!.ToString());
        Assert.Equal(0, bridge.Calls);
    }

    [Fact]
    public async Task Closing_audit_failure_does_not_mask_a_successful_tool_or_lose_the_opening_event()
    {
        var audit = new AuditSink { FailPhase = "end" };
        await using var host = Fixture(audit, new ReadBridge("unexpected"));
        await host.InitializeAsync();
        var response = await host.Invoke("client_situation", await host.Token(), new() { ["client_id"] = 1001 });
        Assert.Equal(1001, response["facts"]!["client_id"]!.GetValue<long>());
        Assert.Single(audit.Events, item => Equals(item.Fields["phase"], "begin"));
    }

    [Theory]
    [InlineData("timeout", 504, "timeout")]
    [InlineData("cancelled", 504, "timeout")]
    [InlineData("unexpected", 500, "internal_error")]
    [InlineData("oversize", 502, "bad_response")]
    public async Task Execution_errors_close_the_audit_and_never_become_trusted_facts(string mode, int status, string code)
    {
        var audit = new AuditSink();
        await using var host = Fixture(audit, new ReadBridge(mode));
        await host.InitializeAsync();
        var token = await host.Token();
        using var response = await host.Tool("calc_walkthrough", token, new() { ["client_id"] = 1001, ["tax_year"] = 2025 });
        Assert.Equal(status, (int)response.StatusCode);
        Assert.Equal(code, (await response.Content.ReadFromJsonAsync<JsonObject>())!["error"]!["code"]!.ToString());
        Assert.Contains(audit.Events, item => Equals(item.Fields["phase"], "end") &&
            Equals(item.Fields["outcome"], "error") && Equals(item.Fields["error"], code));
        var check = await host.Invoke("verify_figures", token, new() { ["draft_text"] = "Client 1001" });
        Assert.Equal("rejected", check["facts"]!["status"]!.ToString());
    }

    [Theory]
    [InlineData("malformed", 422)]
    [InlineData("args", 422)]
    [InlineData("key", 422)]
    [InlineData("oversize", 413)]
    public async Task A_verified_write_rejected_before_dispatch_has_one_safe_refusal_audit(string mode, int status)
    {
        var audit = new AuditSink();
        var bridge = new ReadBridge("unexpected");
        await using var host = Fixture(audit, bridge);
        await host.InitializeAsync();
        var body = mode switch
        {
            "malformed" => "{",
            "args" => """{"args":[]}""",
            "key" => new JsonObject { ["idempotency_key"] = new string('x', 201) }.ToJsonString(),
            _ => new JsonObject { ["text"] = new string('x', 65536) }.ToJsonString(),
        };
        using var request = new HttpRequestMessage(HttpMethod.Post, "/channel/v1/tools/claim_record_commit");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", await host.Token(GatewayFixture.Writer));
        request.Content = new StringContent(body, Encoding.UTF8, "application/json");
        using var response = await host.Client.SendAsync(request);
        Assert.Equal(status, (int)response.StatusCode);
        var row = Assert.Single(audit.Events);
        Assert.Equal("single", row.Fields["phase"]);
        Assert.Equal("refused", row.Fields["outcome"]);
        Assert.Equal("claim_record_commit", row.Fields["tool_name"]);
        Assert.DoesNotContain(body, row.Fields["request_summary"]!.ToString()!, StringComparison.Ordinal);
        Assert.Equal(0, bridge.Calls);
    }

    [Fact]
    public async Task A_mcp_write_with_non_object_arguments_is_refused_and_audited_before_the_sdk_dispatches()
    {
        var audit = new AuditSink();
        var bridge = new ReadBridge("unexpected");
        await using var host = Fixture(audit, bridge);
        await host.InitializeAsync();
        var token = await host.Token(GatewayFixture.Writer);
        var (session, _) = await host.Initialize(token);
        using var response = await host.Rpc(token, session, new
        {
            jsonrpc = "2.0",
            id = 2,
            method = "tools/call",
            @params = new { name = "claim_record_commit", arguments = Array.Empty<int>() },
        });
        Assert.Equal(-32602, (await response.Content.ReadFromJsonAsync<JsonObject>())!["error"]!["code"]!.GetValue<int>());
        var row = Assert.Single(audit.Events);
        Assert.Equal("refused", row.Fields["outcome"]);
        Assert.Equal("claim_record_commit", row.Fields["tool_name"]);
        Assert.Equal(0, bridge.Calls);
    }

    private static GatewayFixture Fixture(AuditSink audit, ReadBridge bridge) => new(services =>
    {
        services.RemoveAll<IChannelAuditRepository>();
        services.AddSingleton<IChannelAuditRepository>(audit);
        services.RemoveAll<ICapabilityReadBridge>();
        services.AddScoped<ICapabilityReadBridge>(_ => bridge);
    });

    private sealed class ReadBridge(string mode) : ICapabilityReadBridge
    {
        public int Calls { get; private set; }
        public Task<CapabilityRead> ReadAsync(string capability, JsonObject arguments, ApiPrincipal principal, CancellationToken cancellationToken)
        {
            Calls++;
            return mode switch
            {
                "timeout" => throw new TimeoutException("private dependency diagnostics must not escape"),
                "cancelled" => throw new OperationCanceledException("private timeout diagnostics must not escape"),
                "oversize" => Task.FromResult(new CapabilityRead(new JsonObject
                {
                    ["steps"] = new JsonArray(),
                    ["client_id"] = 1001,
                    ["unexpected_payload"] = new string('x', 1024 * 1024),
                }, Blocks: new JsonArray())),
                _ => throw new InvalidOperationException("private exception text must not escape"),
            };
        }
    }

    private sealed class AuditSink : IChannelAuditRepository
    {
        public string? FailPhase { get; init; }
        public List<ChannelAuditEvent> Events { get; } = [];
        public void Append(ChannelAuditEvent auditEvent)
        {
            if (Equals(auditEvent.Fields["phase"], FailPhase)) { throw new InvalidOperationException("private audit diagnostics"); }
            Events.Add(auditEvent);
        }
        public void Append(AgentActionAudit action) { }
        public IReadOnlyList<ChannelAuditEvent> ForUser(string userOid, PyDateTime? since = null, PyDateTime? until = null, string? tool = null, int limit = 200) =>
            Events.Where(item => Equals(item.Fields["user_oid"], userOid)).ToArray();
        public IReadOnlyList<ChannelAuditEvent> ByCorrelation(string correlationId) =>
            Events.Where(item => Equals(item.Fields["correlation_id"], correlationId)).ToArray();
        public IReadOnlyList<AgentActionAudit> Recent(string? agentName = null, int limit = 100) => [];
    }
}
