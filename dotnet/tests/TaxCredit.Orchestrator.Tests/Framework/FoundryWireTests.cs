using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using Azure.Core;
using Microsoft.Extensions.AI;
using TaxCredit.Orchestrator.Framework;
using TaxCredit.Orchestrator.Tests.Support;

namespace TaxCredit.Orchestrator.Tests.Framework;

public sealed class FoundryWireTests
{
    [Theory]
    [InlineData("https://synthetic.services.ai.azure.com/api/projects/test", "https://synthetic.openai.azure.com/openai/v1/chat/completions")]
    [InlineData("https://sovereign.example.test/api/projects/test", "https://sovereign.example.test/openai/v1/chat/completions")]
    public async Task Actual_openai_adapter_uses_entra_and_v1_deployment_wire_shape(string endpoint, string expectedUrl)
    {
        var credential = new LocalCredential();
        using var handler = new CaptureHandler();
        using var http = new HttpClient(handler);
        using var model = FoundryModelClientFactory.Create(new Uri(endpoint),
            "model-deployment", credential, http);
        var result = await model.GetResponseAsync([new ChatMessage(ChatRole.User, "reader question")],
            new ChatOptions { Instructions = "instructions" }, CancellationToken.None);
        Assert.Equal("safe prose", result.Text);
        Assert.Equal(expectedUrl, handler.Url);
        Assert.Equal("Bearer", handler.Authorization?.Split(' ')[0]);
        Assert.Equal(["https://cognitiveservices.azure.com/.default"], credential.Scopes);
        Assert.Equal("model-deployment", handler.Body!["model"]!.GetValue<string>());
        Assert.Contains("reader question", handler.Body.ToJsonString(), StringComparison.Ordinal);
        Assert.Equal(0.2, handler.Body["temperature"]!.GetValue<double>(), 6);
        Assert.False(handler.Body.ContainsKey("top_p"));
        Assert.False(handler.HasApiKey);
    }

    [Theory]
    [InlineData("http://synthetic.services.ai.azure.com")]
    [InlineData("https://user:password@synthetic.services.ai.azure.com")]
    [InlineData("https://synthetic.services.ai.azure.com?credential=value")]
    public void Unsafe_endpoint_is_refused_before_any_credential_is_created(string uri) =>
        Assert.Throws<ArgumentException>(() => FoundryModelClientFactory.OpenAiBase(new Uri(uri)));

    [Fact]
    public async Task Real_framework_loop_sends_only_projected_tools_and_fact_paths_on_the_official_wire()
    {
        using var handler = new CaptureHandler("""
            {"id":"chatcmpl-test","object":"chat.completion","created":1,"model":"model-deployment","choices":[{
            "index":0,"message":{"role":"assistant","content":null,"tool_calls":[{"id":"call-1","type":"function",
            "function":{"name":"client_trend","arguments":"{}"}}]},"finish_reason":"tool_calls"}]}
            """, """
            {"id":"chatcmpl-test","object":"chat.completion","created":1,"model":"model-deployment","choices":[{
            "index":0,"message":{"role":"assistant","content":"The trend is shown below."},"finish_reason":"stop"}]}
            """);
        using var http = new HttpClient(handler);
        using var model = FoundryModelClientFactory.Create(new Uri("https://synthetic.services.ai.azure.com"),
            "gpt-5.4-mini", new LocalCredential(), http);
        var rig = new Rig(model);
        var reply = await rig.SayAsync("How has Cascade trended?");
        Assert.True(reply.NarrationUsed);
        Assert.Equal(2, handler.Bodies.Count);
        var tools = handler.Bodies[0]["tools"]!.ToJsonString();
        Assert.DoesNotContain("client_id", tools, StringComparison.Ordinal);
        Assert.DoesNotContain("_commit", tools, StringComparison.Ordinal);
        Assert.All(handler.Bodies, body =>
        {
            Assert.False(body.ContainsKey("temperature"));
            Assert.False(body.ContainsKey("top_p"));
            Assert.DoesNotContain("tcc.turn", body.ToJsonString(), StringComparison.Ordinal);
        });
        var toolAnswer = handler.Bodies[1]["messages"]!.AsArray().Last()!;
        Assert.Equal("tool", toolAnswer["role"]!.ToString());
        Assert.Contains("{{facts.", toolAnswer["content"]!.ToString(), StringComparison.Ordinal);
        Assert.DoesNotContain("494.25", toolAnswer["content"]!.ToString(), StringComparison.Ordinal);
    }

    private sealed class LocalCredential : TokenCredential
    {
        public string[] Scopes { get; private set; } = [];
        public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Scopes = requestContext.Scopes;
            return new AccessToken("synthetic-not-a-credential", DateTimeOffset.UtcNow.AddMinutes(10));
        }
        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext,
            CancellationToken cancellationToken) => ValueTask.FromResult(GetToken(requestContext, cancellationToken));
    }

    private sealed class CaptureHandler(params string[] responses) : HttpMessageHandler
    {
        private readonly Queue<string> _responses = new(responses);
        internal List<JsonObject> Bodies { get; } = [];
        public string? Url { get; private set; }
        public string? Authorization { get; private set; }
        public JsonObject? Body { get; private set; }
        public bool HasApiKey { get; private set; }
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Url = request.RequestUri!.ToString();
            Authorization = request.Headers.Authorization?.ToString();
            HasApiKey = request.Headers.Contains("api-key");
            Body = JsonNode.Parse(await request.Content!.ReadAsStringAsync(cancellationToken))!.AsObject();
            Bodies.Add(Body);
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(_responses.TryDequeue(out var response) ? response : """
                    {"id":"chatcmpl-test","object":"chat.completion","created":1,"model":"model-deployment",
                    "choices":[{"index":0,"message":{"role":"assistant","content":"safe prose"},"finish_reason":"stop"}],
                    "usage":{"prompt_tokens":12,"completion_tokens":2,"total_tokens":14}}
                    """, Encoding.UTF8, "application/json"),
            };
        }
    }
}
