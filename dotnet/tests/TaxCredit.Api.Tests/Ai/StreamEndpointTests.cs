using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.Ai.Briefs;
using TaxCredit.Application.Features.Ai.Streams;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Api.Tests.Ai;

public sealed class StreamEndpointTests
{
    [Theory]
    [InlineData("portfolio")]
    [InlineData("client")]
    [InlineData("unit")]
    [InlineData("employee")]
    public async Task Offline_summary_has_exactly_the_brief_fallback_done_sequence(string page)
    {
        var narrator = new StreamNarrator();
        await using var host = await Start(narrator);
        using var response = await host.Client.PostAsJsonAsync("/api/summary",
            new { page, client_id = 42, tax_year = 2025, worksite_id = "UNIT-A", record_token = "synthetic-handle" });
        var events = Parse(await response.Content.ReadAsStringAsync());
        Assert.Equal(200, (int)response.StatusCode);
        Assert.Equal(["brief", "fallback", "done"], events.Select(e => e.Name));
        Assert.Equal("Copilot is not connected; these are the computed facts.", events[1].Data.GetProperty("note").GetString());
        Assert.Null(narrator.Prompt);
    }

    [Fact]
    public async Task Summary_narration_checks_the_finished_text_and_never_prompts_person_facts()
    {
        var narrator = new StreamNarrator { AvailableFlag = true, Tokens = ["A unit with 21 employees ", "has $40,000."] };
        await using var host = await Start(narrator);
        using var response = await host.Client.PostAsJsonAsync("/api/summary", new { page = "unit", client_id = 42, tax_year = 2025, worksite_id = "UNIT-A" });
        var events = Parse(await response.Content.ReadAsStringAsync());
        Assert.Equal(["brief", "agent_start", "token", "token", "agent_end", "check", "done"], events.Select(e => e.Name));
        Assert.Equal("$40,000", Assert.Single(events.Single(e => e.Name == "check").Data.GetProperty("unsupported").EnumerateArray()).GetString());
        Assert.DoesNotContain("SYNTHETIC-PERSON", narrator.Prompt, StringComparison.Ordinal);
        Assert.DoesNotContain("34.76", narrator.Prompt, StringComparison.Ordinal);
        Assert.True(narrator.Disposed);
    }

    [Fact]
    public async Task Upstream_failure_yields_fallback_once_and_releases_the_iterator()
    {
        var narrator = new StreamNarrator { AvailableFlag = true, FailAfterFirst = true };
        await using var host = await Start(narrator);
        using var response = await host.Client.PostAsJsonAsync("/api/summary", new { page = "portfolio" });
        var events = Parse(await response.Content.ReadAsStringAsync());
        Assert.Single(events, e => e.Name == "fallback");
        Assert.Single(events, e => e.Name == "done");
        Assert.DoesNotContain(events, e => e.Name == "check");
        Assert.Equal("done", events[^1].Name);
        Assert.True(narrator.Disposed);
    }

    [Fact]
    public async Task Socket_stream_flushes_before_upstream_finishes_and_disconnect_disposes_it()
    {
        var narrator = new StreamNarrator { AvailableFlag = true, BlockAfterFirst = true, Tokens = ["A Unicode reading: \u00e9.", "end"] };
        await using var host = await AiSocketHost.Start(narrator);
        using var request = new HttpRequestMessage(HttpMethod.Post, "/api/summary") { Content = JsonContent.Create(new { page = "portfolio" }) };
        using var response = await host.Client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead);
        Assert.Equal("text/event-stream", response.Content.Headers.ContentType?.MediaType);
        Assert.Equal("no-cache", response.Headers.CacheControl?.ToString());
        Assert.Equal("no", Assert.Single(response.Headers.GetValues("X-Accel-Buffering")));
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        using var reader = new StreamReader(await response.Content.ReadAsStreamAsync(timeout.Token));
        Assert.Equal("event: brief", await reader.ReadLineAsync(timeout.Token));
        using var payload = JsonDocument.Parse((await reader.ReadLineAsync(timeout.Token))!["data: ".Length..]);
        Assert.Equal("portfolio", payload.RootElement.GetProperty("page").GetString());
        Assert.Equal("", await reader.ReadLineAsync(timeout.Token));
        string? line;
        do { line = await reader.ReadLineAsync(timeout.Token); } while (line is not null && line != "event: token");
        var text = (await reader.ReadLineAsync(timeout.Token))!;
        Assert.Contains("\u00e9", text, StringComparison.Ordinal);
        Assert.False(narrator.Released.Task.IsCompleted);
        response.Dispose();
        reader.Dispose();
        await WaitForDisposal(narrator);
        await host.ScopeDisposed.WaitAsync(timeout.Token);
    }

    [Fact]
    public async Task Cancellation_before_the_first_event_never_opens_a_provider()
    {
        var narrator = new StreamNarrator { AvailableFlag = true };
        await using var host = await Start(narrator);
        await using var scope = host.App.Services.CreateAsyncScope();
        using var stop = new CancellationTokenSource();
        stop.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
        {
            var frames = await scope.ServiceProvider.GetRequiredKeyedService<IMediator>("ai-request").Send(new SummaryQuery("portfolio"), stop.Token);
            await foreach (var _ in frames.WithCancellation(stop.Token)) { }
        });
        Assert.Null(narrator.Prompt);
    }

    [Fact]
    public async Task Missing_scope_emits_error_done_not_an_empty_calculated_brief()
    {
        await using var host = await Start(new());
        using var response = await host.Client.PostAsJsonAsync("/api/summary", new { page = "client" });
        var events = Parse(await response.Content.ReadAsStringAsync());
        Assert.Equal(["error", "done"], events.Select(e => e.Name));
        Assert.Equal("a client summary needs client_id", events[0].Data.GetProperty("detail").GetString());
    }

    internal static (string Name, JsonElement Data)[] Parse(string body) =>
        body.Split("\n\n", StringSplitOptions.RemoveEmptyEntries).Select(block =>
        {
            var lines = block.Split('\n');
            return (lines[0]["event: ".Length..], JsonDocument.Parse(lines[1]["data: ".Length..]).RootElement.Clone());
        }).ToArray();

    private static Task<TestHost> Start(StreamNarrator narrator) => TestHost.Start(services: services =>
    {
        services.AddScoped<IPageFactSource, StreamFacts>();
        services.AddScoped<IPageScope, StreamFacts>();
        services.AddSingleton<IAiNarrator>(narrator);
    });

    private static async Task WaitForDisposal(StreamNarrator narrator)
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        while (!narrator.Disposed) { await Task.Delay(10, deadline.Token); }
    }
}
