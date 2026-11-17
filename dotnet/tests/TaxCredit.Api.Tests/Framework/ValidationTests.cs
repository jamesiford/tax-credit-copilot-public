using System.Text.Json;

namespace TaxCredit.Api.Tests.Framework;

public sealed class ValidationTests
{
    [Theory]
    [InlineData("p1_workspace_unavailable", "source-search.limit-0")]
    [InlineData("p1_workspace_unavailable", "source-search.limit-201")]
    [InlineData("p1_workspace_unavailable", "onezero-contributors.bad-method")]
    [InlineData("p1_workspace_unavailable", "onezero-contributors.month-12")]
    [InlineData("p1_workspace_unavailable", "onezero-method.bad")]
    [InlineData("p1_workspace_unavailable", "short-token")]
    public async Task Validation_preserves_recorded_status_locations_and_constraint_types(string scenario, string id)
    {
        await using var host = await TestHost.Start();
        var recording = Corpus.Recording(scenario, id);
        using var request = Corpus.Request(recording);
        using var response = await host.Client.SendAsync(request);
        Assert.Equal(422, (int)response.StatusCode);
        using var body = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        var actual = body.RootElement.GetProperty("detail").EnumerateArray().ToArray();
        var expected = recording.GetProperty("response").GetProperty("body").GetProperty("value").GetProperty("detail").EnumerateArray().ToArray();
        Assert.Equal(expected.Length, actual.Length);
        for (var i = 0; i < expected.Length; i++)
        {
            Assert.Equal(expected[i].GetProperty("type").GetString(), actual[i].GetProperty("type").GetString());
            Assert.True(JsonElement.DeepEquals(expected[i].GetProperty("loc"), actual[i].GetProperty("loc")));
        }
    }

    [Fact]
    public async Task Empty_missing_and_nonobject_bodies_never_bind_to_default_models()
    {
        await using var host = await TestHost.Start();
        foreach (var text in new[] { "", "{", "null", "[]", "\"text\"" })
        {
            using var response = await host.Client.PostAsync("/api/workspace/employee", new StringContent(text));
            Assert.Equal(422, (int)response.StatusCode);
            Assert.Equal("application/json", response.Content.Headers.ContentType?.ToString());
        }

        using var missing = await host.Client.PostAsync("/api/workspace/employee", new StringContent("{}"));
        using var document = JsonDocument.Parse(await missing.Content.ReadAsStringAsync());
        Assert.Equal("missing", document.RootElement.GetProperty("detail")[0].GetProperty("type").GetString());
    }

    [Theory]
    [InlineData("/api/v2/clients/not-an-integer/units")]
    [InlineData("/api/v2/clients/99999999999999999999/units")]
    [InlineData("/api/v2/clients/1/units?limit=0")]
    [InlineData("/api/v2/clients/1/units?limit=")]
    [InlineData("/api/workspace/onezero/bogus")]
    [InlineData("/api/simulate/portfolio/2023?state=GA&magnitude=999999999")]
    [InlineData("/api/progress/2023?state=GA&within=-1")]
    public async Task Invalid_inputs_are_refused_before_a_stub_or_store(string path)
    {
        await using var host = await TestHost.Start();
        using var response = await host.Client.GetAsync(path);
        Assert.Equal(422, (int)response.StatusCode);
        Assert.Contains("detail", await response.Content.ReadAsStringAsync(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Unknown_fields_do_not_invalidate_models_that_allow_them()
    {
        await using var host = await TestHost.Start();
        using var response = await host.Client.PostAsync("/api/workspace/source/search?unknown=1", new StringContent("""{"q":"","unknown":true}"""));
        Assert.Equal(503, (int)response.StatusCode);
    }
}
