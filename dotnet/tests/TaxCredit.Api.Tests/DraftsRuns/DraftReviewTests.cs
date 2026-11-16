using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using TaxCredit.Api.Tests.Contract;

namespace TaxCredit.Api.Tests.DraftsRuns;

public sealed class DraftReviewTests
{
    [Fact]
    public async Task A_new_display_address_does_not_make_an_author_a_different_reviewer_and_explicit_off_is_honored()
    {
        await using var host = await TestHost.Start(configuration: new Dictionary<string, string?>
        {
            ["AUTH_MODE"] = "entra",
            ["PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER"] = "yes"
        });
        var first = await RuntimeRequests.Mint(host, new { oid = RuntimeRequests.Writer, upn = "first@example.test" });
        host.Client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", first);
        using var created = await host.Client.PostAsJsonAsync("/api/v2/program-drafts", DraftTests.RecordedBody("create"));
        Assert.Equal(201, (int)created.StatusCode);
        var id = (await created.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("draft_id").GetString();
        using var edited = await host.Client.PutAsJsonAsync($"/api/v2/program-drafts/{id}/documents", DraftTests.RecordedBody("second-fill"));
        Assert.Equal(200, (int)edited.StatusCode);
        using var validated = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{id}/validate", new { });
        Assert.Equal(200, (int)validated.StatusCode);
        using var requested = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{id}/request-review", new { });
        Assert.Equal(200, (int)requested.StatusCode);
        var second = await RuntimeRequests.Mint(host, new { oid = RuntimeRequests.Writer, upn = "second@example.test" });
        host.Client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", second);
        using var refused = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{id}/review", new { decision = "approve" });
        Assert.Equal(422, (int)refused.StatusCode);
        await RuntimeRequests.Env(host, new { PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER = "off" });
        using var approved = await host.Client.PostAsJsonAsync($"/api/v2/program-drafts/{id}/review", new { decision = "approve" });
        Assert.Equal(200, (int)approved.StatusCode);
    }
}
