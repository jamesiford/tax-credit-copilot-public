using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.Ai.Chat;
using TaxCredit.Application.Features.Ai.Streams;

namespace TaxCredit.Api.Tests.Ai;

public sealed class ChatEndpointTests
{
    [Fact]
    public async Task Compound_question_keeps_both_answers_and_one_terminal_event()
    {
        var facts = new ChatFacts();
        await using var host = await Start(facts);
        using var response = await host.Client.PostAsJsonAsync("/api/chat",
            new { message = "Brief me and what else might they qualify for?", client_id = 42, tax_year = 2025 });
        var frames = StreamEndpointTests.Parse(await response.Content.ReadAsStringAsync());
        Assert.Equal(["situation", "discovery"], facts.Intents);
        Assert.Equal(2, frames.Count(f => f.Name == "agent_start"));
        Assert.Single(frames, f => f.Name == "done");
        Assert.Equal("done", frames[^1].Name);
        Assert.Contains(frames, f => f.Name == "token" && f.Data.GetProperty("content").GetString()!.Contains("$1,250", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Portfolio_half_runs_when_client_half_needs_clarification()
    {
        var facts = new ChatFacts();
        await using var host = await Start(facts);
        using var response = await host.Client.PostAsJsonAsync("/api/chat", new { message = "Who should we call first and what else might they qualify for?" });
        var frames = StreamEndpointTests.Parse(await response.Content.ReadAsStringAsync());
        Assert.Equal(["book"], facts.Intents);
        Assert.Contains(frames, f => f.Name == "clarify");
        Assert.Single(frames, f => f.Name == "done");
    }

    [Fact]
    public async Task Empty_message_asks_for_scope_without_reading_figures()
    {
        var facts = new ChatFacts();
        await using var host = await Start(facts);
        using var response = await host.Client.PostAsJsonAsync("/api/chat", new { message = "" });
        var frames = StreamEndpointTests.Parse(await response.Content.ReadAsStringAsync());
        Assert.Equal(["status", "agent_start", "token", "clarify", "agent_end", "done"], frames.Select(f => f.Name));
        Assert.Empty(facts.Intents);
    }

    [Theory]
    [InlineData("""{"message":"their trend","history":[{"role":"user","content":"earlier"}]}""")]
    [InlineData("""{"message":"their trend","history":"earlier"}""")]
    public async Task Invalid_history_is_a_validation_error_before_streaming(string body)
    {
        await using var host = await Start(new());
        using var content = new StringContent(body, System.Text.Encoding.UTF8, "application/json");
        using var response = await host.Client.PostAsync("/api/chat", content);
        Assert.Equal(422, (int)response.StatusCode);
        Assert.False(response.Content.Headers.ContentType?.MediaType == "text/event-stream");
    }

    [Fact]
    public async Task Person_lane_never_reaches_the_narrator()
    {
        var narrator = new StreamNarrator { AvailableFlag = true };
        await using var host = await Start(new(), narrator);
        using var response = await host.Client.PostAsJsonAsync("/api/chat",
            new { message = "Brief me", client_id = 42, tax_year = 2025 });
        _ = await response.Content.ReadAsStringAsync();
        Assert.DoesNotContain("SYNTHETIC-PERSON", narrator.Prompt, StringComparison.Ordinal);
        Assert.Contains("1250", narrator.Prompt, StringComparison.Ordinal);
    }

    private static Task<TestHost> Start(ChatFacts facts, StreamNarrator? narrator = null) =>
        TestHost.Start(services: services =>
        {
            services.AddScoped<IChatClientSource, ChatClients>();
            services.AddSingleton<IChatFactSource>(facts);
            services.AddSingleton<IAiNarrator>(narrator ?? new());
        });

    private sealed class ChatClients : IChatClientSource
    {
        public ValueTask<IReadOnlyList<ChatClient>> ReadAsync(CancellationToken cancellationToken) =>
            ValueTask.FromResult<IReadOnlyList<ChatClient>>([new(42, "Example Books", 2025)]);
    }

    private sealed class ChatFacts : IChatFactSource
    {
        internal List<string> Intents { get; } = [];
        public ValueTask<JsonObject> ReadAsync(string intent, ChatQuery query, CancellationToken cancellationToken)
        {
            Intents.Add(intent);
            return ValueTask.FromResult(JsonNode.Parse("""
                {"facts":{"annual_credit_usd":"1250","employees":[{"employee_id":"SYNTHETIC-PERSON"}]},
                 "blocks":[{"kind":"paragraph","text":"Identified credit: $1,250."}],
                 "user_only_facts":["employees"]}
                """)!.AsObject());
        }
    }
}
