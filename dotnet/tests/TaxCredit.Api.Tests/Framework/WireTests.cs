using System.Net;
using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using TaxCredit.Api.Wire;

namespace TaxCredit.Api.Tests.Framework;

public sealed class WireTests
{
    [Theory]
    [InlineData("ok.api-health")]
    [InlineData("ok.api-ready")]
    [InlineData("get-api-health.unknown-query")]
    [InlineData("get-api-ready.unknown-query")]
    public async Task Probes_preserve_health_and_report_observed_readiness(string id)
    {
        await using var host = await TestHost.Start();
        var recording = Corpus.Recording("p1_reads", id);
        using var request = Corpus.Request(recording);
        using var response = await host.Client.SendAsync(request);
        if (id.Contains("ready", StringComparison.Ordinal))
        {
            Assert.Equal(HttpStatusCode.OK, response.StatusCode);
            using var body = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
            Assert.True(body.RootElement.GetProperty("ready").GetBoolean());
            Assert.Equal("ready", body.RootElement.GetProperty("stores").GetProperty("status").GetString());
            Assert.Equal("ready", body.RootElement.GetProperty("source_schema").GetProperty("status").GetString());
            Assert.Equal(1, body.RootElement.GetProperty("source_schema").GetProperty("accounts").GetInt32());
            Assert.Equal("disabled", body.RootElement.GetProperty("ai").GetString());
        }
        else
        {
            await Corpus.AssertJsonResponse(recording, response);
        }
    }

    [Fact]
    public async Task Unknown_routes_and_wrong_methods_are_json_with_allow()
    {
        await using var host = await TestHost.Start();
        using var missing = await host.Client.GetAsync("/not-an-operation");
        Assert.Equal(HttpStatusCode.NotFound, missing.StatusCode);
        Assert.Equal("application/json", missing.Content.Headers.ContentType?.ToString());
        using var wrong = await host.Client.PostAsync("/api/health", null);
        Assert.Equal(HttpStatusCode.MethodNotAllowed, wrong.StatusCode);
        Assert.Contains("GET", wrong.Content.Headers.Allow);
        Assert.Contains("detail", await wrong.Content.ReadAsStringAsync(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Unhandled_errors_are_json_without_a_stack_trace_even_in_development()
    {
        await using var host = await TestHost.Start(routes: app => app.MapGet("/__tests__/failure", (Func<IResult>)(() => throw new InvalidOperationException("private input"))));
        using var response = await host.Client.GetAsync("/__tests__/failure");
        Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
        Assert.Equal("""{"detail":"Internal Server Error"}""", await response.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task Every_handled_error_family_is_preserved()
    {
        await using var host = await TestHost.Start(routes: app =>
        {
            app.MapGet("/__tests__/structured", () => ApiErrors.Detail(409, new { code = "draft_conflict", reason = "conflict" }));
            app.MapGet("/__tests__/batch", () => ApiErrors.RunBatch(422, "empty_selection", "No clients selected."));
            app.MapGet("/__tests__/dependency", () => ApiErrors.Dependency("source_lakehouse", "not configured", "configure the source"));
        });
        using var structuredResponse = await host.Client.GetAsync("/__tests__/structured");
        using var structured = JsonDocument.Parse(await structuredResponse.Content.ReadAsStringAsync());
        Assert.Equal("draft_conflict", structured.RootElement.GetProperty("detail").GetProperty("code").GetString());
        using var batchResponse = await host.Client.GetAsync("/__tests__/batch");
        using var batch = JsonDocument.Parse(await batchResponse.Content.ReadAsStringAsync());
        Assert.Equal("empty_selection", batch.RootElement.GetProperty("detail").GetProperty("code").GetString());
        Assert.Equal("No clients selected.", batch.RootElement.GetProperty("detail").GetProperty("detail").GetString());
        using var dependencyResponse = await host.Client.GetAsync("/__tests__/dependency");
        using var dependency = JsonDocument.Parse(await dependencyResponse.Content.ReadAsStringAsync());
        Assert.Equal("source_lakehouse", dependency.RootElement.GetProperty("dependency").GetString());
    }

    [Fact]
    public async Task Standard_cors_allows_only_configured_origins_and_declared_headers()
    {
        await using var host = await TestHost.Start();
        using var request = new HttpRequestMessage(HttpMethod.Options, "/api/health");
        request.Headers.Add("Origin", "http://localhost:5173");
        request.Headers.Add("Access-Control-Request-Method", "DELETE");
        request.Headers.Add("Access-Control-Request-Headers", "Authorization");
        using var response = await host.Client.SendAsync(request);
        Assert.Equal(HttpStatusCode.NoContent, response.StatusCode);
        Assert.Equal("http://localhost:5173", Assert.Single(response.Headers.GetValues("Access-Control-Allow-Origin")));
        using var foreign = new HttpRequestMessage(HttpMethod.Get, "/api/health");
        foreign.Headers.Add("Origin", "https://untrusted.example.test");
        using var denied = await host.Client.SendAsync(foreign);
        Assert.False(denied.Headers.Contains("Access-Control-Allow-Origin"));
    }
}
