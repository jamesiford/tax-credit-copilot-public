using System.Net;
using System.Text.Json;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Auth;
using TaxCredit.Infrastructure.Ai.Gateway;
using TaxCredit.Infrastructure.Ai.Runtime;

namespace TaxCredit.Infrastructure.Ai.Tests;

public sealed class GatewayTests
{
    private const string Completion = "data: {\"choices\":[{\"delta\":{\"content\":\"hello \"}}]}\n\n"
        + "data: {\"choices\":[{\"delta\":{\"content\":\"world\"},\"finish_reason\":\"stop\"}],\"usage\":{\"prompt_tokens\":4,\"completion_tokens\":2}}\n\n"
        + "data: [DONE]\n\n";
    [Theory]
    [InlineData(GatewayDialect.OpenAiV1)]
    [InlineData(GatewayDialect.AzureDeployments)]
    public async Task DialectBodyPathAndAuthPrecedence(GatewayDialect dialect)
    {
        var handler = new FakeHttp(async (request, ct) =>
        {
            using var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(ct));
            Assert.Equal(dialect == GatewayDialect.OpenAiV1, body.RootElement.TryGetProperty("model", out _));
            Assert.Contains(dialect == GatewayDialect.OpenAiV1 ? "/v1/chat/completions"
                : "/openai/deployments/test%2Fmodel/chat/completions", request.RequestUri!.AbsoluteUri, StringComparison.Ordinal);
            Assert.Equal("Bearer synthetic-secret", request.Headers.GetValues("Authorization").Single());
            Assert.Equal("trace", request.Headers.GetValues("X-Test").Single());
            Assert.True(body.RootElement.GetProperty("stream_options").GetProperty("include_usage").GetBoolean());
            return FakeHttp.Sse(Completion);
        });
        using var http = new HttpClient(handler);
        var settings = new GatewaySettings(new Uri("https://gateway.invalid"), dialect,
            extraHeaders: new Dictionary<string, string> { ["authorization"] = "forged", ["X-Test"] = "trace" });
        var model = new OpenAiCompatibleChatModel(http, settings, new ApiKeyAuth("Authorization", "Bearer ", "synthetic-secret"));
        var events = await TestStreams.Collect(model.StreamAsync(new ChatRequest("test/model", [new("user", "brief")])));
        Assert.Equal("hello world", TestStreams.Text(events));
        Assert.Equal(new ModelUsage(4, 2), Assert.Single(events.OfType<ModelUsage>()));
        Assert.Equal("stop", Assert.IsType<StreamEnd>(events[^1]).FinishReason);
    }
    [Fact]
    public async Task FragmentedToolsAreReturnedOnceAndNeverExecuted()
    {
        const string payload = "data: {\"choices\":[{\"delta\":{\"tool_calls\":[{\"index\":0,\"id\":\"synthetic-call\",\"function\":{\"name\":\"look\",\"arguments\":\"{\\\"x\\\":\"}}]}}]}\n\n"
            + "data: {\"choices\":[{\"delta\":{\"tool_calls\":[{\"index\":0,\"function\":{\"name\":\"up\",\"arguments\":\"1}\"}}]},\"finish_reason\":\"tool_calls\"}]}\n\n"
            + "data: [DONE]\n";
        using var http = new HttpClient(new FakeHttp((_, _) => Task.FromResult(FakeHttp.Sse(payload))));
        var chat = new OpenAiCompatibleChatModel(http, new(new Uri("https://gateway.invalid")), new NoAuth());
        var tool = Assert.Single((await TestStreams.Collect(chat.StreamAsync(new("test", [new("user", "brief")])))).OfType<ToolCall>());
        Assert.Equal("lookup", tool.Name);
        Assert.Equal("{\"x\":1}", tool.Arguments);
        var runtime = new ChatModelAgentRuntime(chat, _ => "test");
        Assert.Empty((await TestStreams.Collect(runtime.StreamAsync(TestStreams.Request()))).OfType<ToolCall>());
    }
    [Fact]
    public async Task NonStreamingReturnsWholeMessageAndUsage()
    {
        using var http = new HttpClient(new FakeHttp((_, _) => Task.FromResult(FakeHttp.Json(
            "{\"choices\":[{\"message\":{\"content\":\"whole\",\"tool_calls\":[{\"id\":\"call\",\"function\":{\"name\":\"lookup\",\"arguments\":\"{}\"}}]},\"finish_reason\":\"stop\"}],\"usage\":{\"prompt_tokens\":3,\"completion_tokens\":1}}"))));
        var chat = new OpenAiCompatibleChatModel(http, new(new Uri("https://gateway.invalid"), streaming: false), new NoAuth());
        var events = await TestStreams.Collect(chat.StreamAsync(new("test", [new("user", "brief")])));
        Assert.Equal("whole", TestStreams.Text(events));
        Assert.Single(events.OfType<ToolCall>());
        Assert.Equal(4, Assert.Single(events.OfType<ModelUsage>()).Total);
    }
    [Theory]
    [InlineData(401, ModelErrorKind.Authentication)]
    [InlineData(403, ModelErrorKind.Authentication)]
    [InlineData(400, ModelErrorKind.BadRequest)]
    [InlineData(422, ModelErrorKind.BadRequest)]
    [InlineData(429, ModelErrorKind.RateLimited)]
    [InlineData(408, ModelErrorKind.Unavailable)]
    [InlineData(425, ModelErrorKind.Unavailable)]
    [InlineData(500, ModelErrorKind.Unavailable)]
    [InlineData(503, ModelErrorKind.Unavailable)]
    public async Task HttpFailuresDoNotExposeBodiesOrHeaders(int status, ModelErrorKind kind)
    {
        using var http = new HttpClient(new FakeHttp((_, _) =>
        {
            var response = new HttpResponseMessage((HttpStatusCode)status) { Content = new StringContent("SENTINEL-PROMPT-SECRET") };
            response.Headers.TryAddWithoutValidation("Retry-After", "3");
            response.Headers.TryAddWithoutValidation("X-Secret", "SENTINEL-HEADER");
            return Task.FromResult(response);
        }));
        var error = await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(
            new OpenAiCompatibleChatModel(http, new(new Uri("https://gateway.invalid")), new NoAuth())
            .StreamAsync(new("test", [new("user", "SENTINEL-PROMPT")]))));
        Assert.Equal(kind, error.Kind);
        Assert.DoesNotContain("SENTINEL", error.ToString(), StringComparison.Ordinal);
        if (status == 429)
        {
            Assert.Equal(TimeSpan.FromSeconds(3), error.RetryAfter);
        }
    }
    [Theory]
    [InlineData("data: invalid\n", "malformed_model_event")]
    [InlineData("data: {\"choices\":[{\"delta\":{\"content\":\"partial\"}}]}\n", "stream_truncated")]
    [InlineData("data: {\"usage\":{\"prompt_tokens\":-1}}\n", "malformed_model_event")]
    public async Task MalformedAndCutStreamsFailSafely(string payload, string code)
    {
        using var http = new HttpClient(new FakeHttp((_, _) => Task.FromResult(FakeHttp.Sse(payload))));
        var error = await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(
            new OpenAiCompatibleChatModel(http, new(new Uri("https://gateway.invalid")), new NoAuth()).StreamAsync(new("test", []))));
        Assert.Equal(code, error.Code);
    }
    [Fact]
    public void RetryAfterSupportsHttpDatesAndRejectsNonfinite()
    {
        var now = new DateTimeOffset(2026, 10, 21, 7, 27, 30, TimeSpan.Zero);
        Assert.Equal(TimeSpan.FromSeconds(30), OpenAiWire.RetryAfter("Wed, 21 Oct 2026 07:28:00 GMT", now));
        Assert.Equal(TimeSpan.Zero, OpenAiWire.RetryAfter("-2", now));
        Assert.Null(OpenAiWire.RetryAfter("NaN", now));
        Assert.Null(OpenAiWire.RetryAfter("invalid", now));
    }
    [Fact]
    public async Task TransportExceptionsAreRedactedAndCallerCancellationIsNotAnOutage()
    {
        using var http = new HttpClient(new FakeHttp((_, _) => throw new HttpRequestException("SENTINEL")));
        var model = new OpenAiCompatibleChatModel(http, new(new Uri("https://gateway.invalid")), new NoAuth());
        var error = await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(model.StreamAsync(new("test", []))));
        Assert.DoesNotContain("SENTINEL", error.ToString(), StringComparison.Ordinal);
        using var stop = new CancellationTokenSource();
        stop.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => TestStreams.Collect(model.StreamAsync(new("test", []), stop.Token)));
    }
}
