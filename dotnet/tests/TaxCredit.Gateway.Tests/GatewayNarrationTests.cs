using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Gateway.Tests;

public sealed class GatewayNarrationTests(GatewayFixture host) : IClassFixture<GatewayFixture>
{
    private static Dictionary<string, string> Headers => new()
    {
        ["X-Acting-User-Oid"] = GatewayFixture.Reader,
        ["X-Acting-User-Name"] = "Synthetic Person",
        ["X-Acting-Tenant"] = GatewayFixture.Tenant,
        ["X-Channel"] = "teams",
        ["X-Conversation-Id"] = "narration-conversation",
        ["X-Correlation-Id"] = "narration-correlation",
    };

    [Theory]
    [InlineData("none", 401)]
    [InlineData("delegated", 403)]
    [InlineData("agent-empty", 422)]
    [InlineData("agent-bad", 422)]
    public async Task Narration_authentication_and_agent_validation_have_the_required_order(string shape, int status)
    {
        var token = shape == "none" ? null : await host.Token(agent: shape.StartsWith("agent-", StringComparison.Ordinal));
        var report = shape == "agent-bad" ? new { agent_name = "synthetic", prompt_sha256 = "bad", guard_status = "pass" } : (object)new { };
        using var response = await host.Send("POST", "/channel/v1/audit/narration", token, report, Headers);
        Assert.Equal(status, (int)response.StatusCode);
    }

    [Theory]
    [InlineData("pass", 0)]
    [InlineData("rejected", 2)]
    public async Task Durable_narration_rows_are_person_attributed_and_never_store_submitted_prose(string verdict, int violations)
    {
        var name = "synthetic-narrator-" + verdict;
        using var response = await host.Send("POST", "/channel/v1/audit/narration", await host.Token(agent: true),
            new
            {
                agent_name = name,
                prompt_sha256 = new string('a', 64),
                guard_status = verdict,
                violations_count = violations,
                output_summary = "Narrator-supplied prose is not audit evidence.",
                tool_names = new[] { "book_rank" }
            }, Headers);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = (await response.Content.ReadFromJsonAsync<JsonObject>())!;
        Assert.True(body["agent_action_recorded"]!.GetValue<bool>());
        using var scope = host.Services.CreateScope();
        var repository = scope.ServiceProvider.GetRequiredService<IChannelAuditRepository>();
        var row = Assert.Single(repository.Recent(name));
        Assert.Equal(verdict == "pass", Convert.ToBoolean(row.Fields["is_deterministic_path"], System.Globalization.CultureInfo.InvariantCulture));
        Assert.DoesNotContain("Narrator-supplied", row.Fields["output_summary"]!.ToString(), StringComparison.Ordinal);
        var audit = repository.ByCorrelation("narration-correlation");
        Assert.Contains(audit, item => Equals(item.Fields["audit_id"], body["audit_id"]!.ToString()) &&
            Equals(item.Fields["user_oid"], GatewayFixture.Reader) && Equals(item.Fields["numeric_guard"], verdict));
    }
}
