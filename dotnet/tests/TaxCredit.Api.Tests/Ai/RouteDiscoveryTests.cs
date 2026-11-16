using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace TaxCredit.Api.Tests.Ai;

public sealed class RouteDiscoveryTests
{
    [Fact]
    public async Task Ordinary_discovery_serves_the_captured_catalogue_without_a_test_module()
    {
        await using var host = await TestHost.Start();
        using var request = Corpus.Request(Corpus.Recording("p1_artifacts_ai", "capabilities.list"));
        using var response = await host.Client.SendAsync(request);
        Assert.Equal(200, (int)response.StatusCode);
        var actual = JsonNode.Parse(await response.Content.ReadAsStringAsync());
        var expected = JsonNode.Parse(Corpus.Recording("p1_artifacts_ai", "capabilities.list")
            .GetProperty("response").GetProperty("body").GetProperty("value").GetRawText());
        Assert.True(JsonNode.DeepEquals(expected, actual));
    }

    [Theory]
    [InlineData("capabilities.unknown-tool")]
    [InlineData("capabilities.book-rank-bad-arg")]
    [InlineData("capabilities.client-situation-missing-arg")]
    [InlineData("capabilities.args-not-object")]
    [InlineData("capabilities.idempotency-key-too-long")]
    [InlineData("capabilities.debug-tool")]
    [InlineData("summary.bad-page")]
    [InlineData("summary.short-token")]
    [InlineData("summary.bad-month")]
    public async Task Recorded_refusals_are_not_501_stubs(string id)
    {
        var captured = Corpus.Recording("p1_artifacts_ai", id);
        await using var host = await TestHost.Start();
        using var request = Corpus.Request(captured);
        using var response = await host.Client.SendAsync(request);
        Assert.Equal(captured.GetProperty("response").GetProperty("status").GetInt32(), (int)response.StatusCode);
        using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        Assert.True(document.RootElement.TryGetProperty("detail", out _) || document.RootElement.TryGetProperty("error", out _));
    }

    [Fact]
    public async Task Recorded_claim_situation_runs_on_real_W1_repositories()
    {
        await using var host = await TestHost.Start(configuration: new Dictionary<string, string?> { ["DATA_SOURCE"] = "lakehouse" });
        using var reset = await host.Client.PostAsJsonAsync("/__contract__/reset", new { profile = "P1" });
        Assert.Equal(200, (int)reset.StatusCode);
        var recording = Corpus.Recording("p1_artifacts_ai", "capabilities.client-situation");
        using var request = Corpus.Request(recording);
        using var response = await host.Client.SendAsync(request);
        Assert.Equal(200, (int)response.StatusCode);
        var expected = JsonNode.Parse(recording.GetProperty("response").GetProperty("body").GetProperty("value").GetRawText());
        var actual = JsonNode.Parse(await response.Content.ReadAsStringAsync());
        Assert.True(JsonNode.DeepEquals(expected, actual), "First differing path: " + Difference(expected, actual, "$"));
    }

    private static string Difference(JsonNode? expected, JsonNode? actual, string path)
    {
        if (JsonNode.DeepEquals(expected, actual)) { return ""; }
        if (expected is JsonObject left && actual is JsonObject right)
        {
            return left.Select(pair => pair.Key).Union(right.Select(pair => pair.Key), StringComparer.Ordinal)
                .Select(key => Difference(left[key], right[key], path + "." + key)).First(p => p.Length != 0);
        }
        if (expected is JsonArray a && actual is JsonArray b)
        {
            if (a.Count != b.Count) { return path + ".length"; }
            return Enumerable.Range(0, a.Count).Select(i => Difference(a[i], b[i], path + "[" + i + "]")).First(p => p.Length != 0);
        }
        return path;
    }
}
