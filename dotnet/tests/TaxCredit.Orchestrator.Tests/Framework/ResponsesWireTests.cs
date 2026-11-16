using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.TestHost;
using TaxCredit.Orchestrator.Hosting;

namespace TaxCredit.Orchestrator.Tests.Framework;

public sealed class ResponsesWireTests
{
    [Fact]
    public async Task Installed_host_extracts_input_and_frames_one_complete_text_response_and_readiness()
    {
        var turn = new Probe();
        await using var app = ResponsesHosting.Build([], turn, builder =>
            builder.WebApplicationBuilder.WebHost.UseTestServer());
        await app.StartAsync();
        using var client = app.GetTestClient();
        using var readiness = await client.GetAsync("/readiness");
        Assert.Equal(HttpStatusCode.OK, readiness.StatusCode);
        using var response = await client.PostAsJsonAsync("/responses", new
        {
            input = new[] { new { role = "user", content = new[] { new { type = "input_text", text = "hello" } } } },
            stream = false,
            store = false,
        });
        var body = await response.Content.ReadAsStringAsync();
        Assert.True(response.IsSuccessStatusCode, body);
        var wire = JsonNode.Parse(body)!;
        Assert.Equal("completed", wire["status"]?.GetValue<string>());
        Assert.Equal("Guarded answer.", wire["output"]?[0]?["content"]?[0]?["text"]?.GetValue<string>());
        Assert.Equal("hello", turn.Request?.Text);
        Assert.False(string.IsNullOrEmpty(turn.Request?.ResponseId));
        await app.StopAsync();
    }

    [Fact]
    public async Task Client_cancellation_reaches_the_real_handler_without_emitting_a_completed_answer()
    {
        var turn = new BlockingProbe();
        await using var app = ResponsesHosting.Build([], turn, builder =>
            builder.WebApplicationBuilder.WebHost.UseTestServer());
        await app.StartAsync();
        using var client = app.GetTestClient();
        using var cancel = new CancellationTokenSource();
        var pending = client.PostAsJsonAsync("/responses", new { input = "wait", stream = false, store = false }, cancel.Token);
        await turn.Started.Task.WaitAsync(TimeSpan.FromSeconds(5));
        cancel.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () => await pending);
        await turn.Cancelled.Task.WaitAsync(TimeSpan.FromSeconds(5));
        await app.StopAsync();
    }

    private sealed class Probe : IResponseTurn
    {
        public ResponseTurnRequest? Request { get; private set; }
        public Task<string> AnswerAsync(ResponseTurnRequest request, CancellationToken cancellationToken)
        {
            Request = request;
            cancellationToken.ThrowIfCancellationRequested();
            return Task.FromResult("Guarded answer.");
        }
    }

    private sealed class BlockingProbe : IResponseTurn
    {
        public TaskCompletionSource Started { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Cancelled { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public async Task<string> AnswerAsync(ResponseTurnRequest request, CancellationToken cancellationToken)
        {
            Started.SetResult();
            try { await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken); }
            finally { Cancelled.SetResult(); }
            return "must not complete";
        }
    }
}
