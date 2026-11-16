using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.Api.Tests.Contract;

public sealed class RuntimeEnvironmentTests
{
    [Fact]
    [Trait("Category", "heavy")]
    public async Task Writer_enforcement_rebuilds_and_resets_while_f14_valid_outcomes_remain_explicit_exceptions()
    {
        await using var host = await RuntimeRequests.Start();
        await RuntimeRequests.Reset(host);
        var reader = await RuntimeRequests.Mint(host, new { });
        using var denied = await Case(host, reader, "reader.draft-create", RuntimeRequests.Acting());
        Assert.Equal(403, (int)denied.StatusCode);
        foreach (var id in new[] { "reader.assess", "reader.run", "reader.rules-verify", "reader.batch-dry-run" })
        {
            using var response = await Case(host, reader, id);
            Assert.Equal(id == "reader.batch-dry-run" ? 202 : 200, (int)response.StatusCode);
        }
        using var drafts = await RuntimeRequests.Send(host, reader, "/api/v2/program-drafts");
        Assert.Equal(200, (int)drafts.StatusCode);
        var writer = await RuntimeRequests.Mint(host, new { oid = RuntimeRequests.Writer });
        using var allowed = await Case(host, writer, "reader.draft-create");
        Assert.Equal(201, (int)allowed.StatusCode);
        await RuntimeRequests.Env(host, new { CHANNEL_ENFORCE_WRITER_FOR_USERS = "false", PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER = "true" });
        using var changed = await Case(host, reader, "reader.draft-create");
        Assert.Equal(201, (int)changed.StatusCode);
        using var observation = await RuntimeRequests.Send(host, reader);
        Assert.Equal("true", (await observation.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("second_reviewer").GetString());
        await RuntimeRequests.Reset(host);
        using var restored = await Case(host, reader, "reader.draft-create");
        Assert.Equal(403, (int)restored.StatusCode);
        Assert.Null(host.App.Services.GetRequiredService<IRuntimeConfiguration>().Get("PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER"));
    }

    [Fact]
    public async Task Signed_caller_limits_are_rebuilt_reset_and_not_shared_by_the_acting_user()
    {
        await using var host = await RuntimeRequests.Start();
        var reader = await RuntimeRequests.Mint(host, new { });
        await RuntimeRequests.Env(host, new { RATE_LIMIT_PER_MINUTE = "1" });
        using var first = await Case(host, reader, "reader.batch-dry-run");
        Assert.Equal(202, (int)first.StatusCode);
        using var second = await Case(host, reader, "reader.batch-dry-run");
        Assert.Equal(429, (int)second.StatusCode);
        Assert.NotNull(second.Headers.RetryAfter);
        await RuntimeRequests.Env(host, new { RATE_LIMIT_PER_MINUTE = "2" });
        using var renewed = await Case(host, reader, "reader.batch-dry-run");
        Assert.Equal(202, (int)renewed.StatusCode);
        await RuntimeRequests.Reset(host);
        using var reset = await Case(host, reader, "reader.batch-dry-run");
        Assert.Equal(202, (int)reset.StatusCode);
        Assert.Equal("60", host.App.Services.GetRequiredService<IRuntimeConfiguration>().Get("RATE_LIMIT_PER_MINUTE"));
    }

    private static Task<HttpResponseMessage> Case(TestHost host, string token, string id, string? acting = null)
    {
        var request = Corpus.Recording("p1_auth", id).GetProperty("request");
        return RuntimeRequests.Send(host, token, request.GetProperty("path").GetString()!,
            new HttpMethod(request.GetProperty("method").GetString()!), request.GetProperty("body").GetProperty("value"), acting);
    }
}
