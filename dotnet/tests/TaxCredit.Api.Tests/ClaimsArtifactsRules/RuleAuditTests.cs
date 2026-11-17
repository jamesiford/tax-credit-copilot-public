using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Persistence;
using Xunit;

namespace TaxCredit.Api.Tests.ClaimsArtifactsRules;

public sealed class RuleAuditTests
{
    [Fact]
    public async Task Rule_signoff_survives_scopes_and_captured_retrieval_never_claims_live_success()
    {
        await using var host = await TestHost.Start();
        await host.Client.PostAsJsonAsync("/__contract__/reset", new { profile = "P1" });
        var verified = await host.Client.PostAsJsonAsync("/api/rules/SC_JTC/verify", new { verified_by = "synthetic-practitioner", note = "Reviewed source" });
        Assert.Equal(HttpStatusCode.OK, verified.StatusCode);
        var rules = await Json(await host.Client.GetAsync("/api/rules"));
        Assert.Equal("2026-01-04T06:19+00:00", rules.GetProperty("summary").GetProperty("last_update_iso").GetString());
        Assert.Equal("CO_EZ", rules.GetProperty("recent_changes")[0].GetProperty("credit_code").GetString());
        var sc = rules.GetProperty("rules").EnumerateArray().Single(r => r.GetProperty("code").GetString() == "SC_JTC");
        Assert.True(sc.GetProperty("verified").GetBoolean());
        Assert.Equal("synthetic-practitioner", sc.GetProperty("verification").GetProperty("verified_by").GetString());
        Assert.Equal(HttpStatusCode.NotFound, (await host.Client.PostAsJsonAsync("/api/rules/UNKNOWN/verify", new { verified_by = "synthetic" })).StatusCode);
        var captured = await Json(await host.Client.GetAsync("/api/rules/ingested/GA?tax_year=2025"));
        Assert.NotEmpty(captured.GetProperty("provenance").EnumerateArray());
        var refresh = await Json(await host.Client.GetAsync("/api/rules/ingested/TN/refresh"));
        Assert.Equal("captured", refresh.GetProperty("mode").GetString());
        Assert.All(refresh.GetProperty("sources").EnumerateArray(), s => Assert.Equal(JsonValueKind.Null, s.GetProperty("verified").ValueKind));
        Assert.Equal(HttpStatusCode.ServiceUnavailable, (await host.Client.GetAsync("/api/rules/ingested/GA/refresh?live=true")).StatusCode);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, (await host.Client.PostAsJsonAsync("/api/rules/ingested/GA/apply", new { tax_year = 2025 })).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await host.Client.PostAsJsonAsync("/api/rules/ingested/TN/apply", new { tax_year = 2025 })).StatusCode);
        Assert.Equal(HttpStatusCode.UnprocessableEntity, (await host.Client.PostAsJsonAsync("/api/rules/ingested/GA/apply", new { })).StatusCode);
        var proposals = await Json(await host.Client.GetAsync("/api/rules/ingested/GA/proposals"));
        Assert.Equal("NEEDS_KEY", proposals.GetProperty("web_iq_status").GetString());
    }

    [Fact]
    public async Task Audit_filters_and_collapses_pending_and_finished_requests_without_gateway_execution()
    {
        await using var host = await TestHost.Start();
        await host.Client.PostAsJsonAsync("/__contract__/reset", new { profile = "P1" });
        using (var scope = host.App.Services.CreateScope())
        {
            var repository = scope.ServiceProvider.GetRequiredService<IChannelAuditRepository>();
            repository.Append(Event("pending-request", 0, "begin", "pending", "2026-01-15T12:00:00+00:00"));
            repository.Append(Event("complete-request", 0, "begin", "pending", "2026-01-15T12:01:00+00:00"));
            repository.Append(Event("complete-request", 1, "end", "ok", "2026-01-15T12:02:00+00:00"));
        }
        var audit = await Json(await host.Client.GetAsync("/api/audit/channel?user_oid=synthetic-person&tool=book_rank&limit=20"));
        Assert.Equal(3, audit.GetProperty("events").GetArrayLength());
        var entries = audit.GetProperty("entries");
        Assert.Equal(2, entries.GetArrayLength());
        Assert.Equal("ok", entries[0].GetProperty("outcome").GetString());
        Assert.Equal("pending", entries[1].GetProperty("outcome").GetString());
        Assert.Equal(JsonValueKind.Null, entries[1].GetProperty("finished_at").ValueKind);
        var filtered = await Json(await host.Client.GetAsync("/api/audit/channel?user_oid=synthetic-person&until=2026-01-15T12%3A01%3A00%2B00%3A00"));
        Assert.Single(filtered.GetProperty("events").EnumerateArray());
        Assert.Equal(HttpStatusCode.UnprocessableEntity, (await host.Client.GetAsync("/api/audit/channel?user_oid=synthetic-person&limit=501")).StatusCode);
    }

    private static ChannelAuditEvent Event(string id, long sequence, string phase, string outcome, string time) => new(
        new Dictionary<string, object?>(StringComparer.Ordinal)
        {
            ["audit_id"] = id,
            ["event_seq"] = sequence,
            ["phase"] = phase,
            ["correlation_id"] = id,
            ["channel"] = "api-test",
            ["user_oid"] = "synthetic-person",
            ["identity_assurance"] = "delegated",
            ["tool_name"] = "book_rank",
            ["action_kind"] = "write_commit",
            ["outcome"] = outcome,
            ["occurred_at"] = time,
            ["numeric_guard"] = "n/a",
            ["is_deterministic_path"] = true,
        });

    private static async Task<JsonElement> Json(HttpResponseMessage response)
    {
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<JsonElement>();
    }
}
