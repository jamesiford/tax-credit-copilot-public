using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using TaxCredit.Orchestrator.Boundary;
using static TaxCredit.Orchestrator.Tests.Boundary.GatewayTestSupport;

namespace TaxCredit.Orchestrator.Tests.Boundary;

public sealed class GatewayTests
{
    [Fact]
    public async Task Calls_preserve_exact_args_workflow_metadata_and_verified_assertions()
    {
        using var handler = new Handler(async (request, _) =>
        {
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://gateway.example/channel/v1/tools/change_commit", request.RequestUri!.AbsoluteUri);
            Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
            Assert.Equal("service-token", request.Headers.Authorization.Parameter);
            Assert.Equal(IdentityTests.Person, Assert.Single(request.Headers.GetValues("X-Acting-User-Oid")));
            Assert.Equal("conversation-1", Assert.Single(request.Headers.GetValues("X-Conversation-Id")));
            Assert.Equal("response-1", Assert.Single(request.Headers.GetValues("X-Correlation-Id")));
            Assert.False(request.Headers.Contains("X-TCC-Acting-User"));
            Assert.False(request.Headers.Contains("Cookie"));
            var body = JsonNode.Parse(await request.Content!.ReadAsStringAsync(CancellationToken.None))!.AsObject();
            Assert.Equal("001.00", body["args"]!["amount"]!.GetValue<string>());
            Assert.Equal("operation-1", body["idempotency_key"]!.GetValue<string>());
            Assert.Equal("person-only-token", body["confirmation_token"]!.GetValue<string>());
            return JsonResponse("""{"facts":{"amount":"001.00"},"blocks":[],"provenance":{},"warnings":[]}""");
        });
        using var http = new HttpClient(handler);
        var tokens = new Tokens();
        var client = Client(http, tokens);
        var reply = await client.CallToolAsync(IdentityTests.Who(), "change_commit",
            new JsonObject { ["amount"] = "001.00" }, "operation-1", "person-only-token");
        Assert.True(reply.Ok);
        Assert.Equal(1, tokens.Calls);
        Assert.Equal(1, handler.Calls);
    }

    [Fact]
    public async Task Shared_infrastructure_has_no_cross_person_headers_and_acquires_each_token_per_call()
    {
        var seen = new System.Collections.Concurrent.ConcurrentBag<string>();
        using var handler = new Handler((request, _) =>
        {
            seen.Add(Assert.Single(request.Headers.GetValues("X-Acting-User-Oid")));
            return Task.FromResult(JsonResponse("{}"));
        });
        using var http = new HttpClient(handler);
        var tokens = new Tokens();
        var client = Client(http, tokens);
        await Task.WhenAll(client.CallToolAsync(IdentityTests.Who(), "book_rank", []),
            client.CallToolAsync(IdentityTests.Who(IdentityTests.Other), "book_rank", []));
        Assert.Contains(IdentityTests.Person, seen);
        Assert.Contains(IdentityTests.Other, seen);
        Assert.Equal(2, tokens.Calls);
        Assert.Empty(http.DefaultRequestHeaders);
    }

    [Fact]
    public async Task Audit_uses_the_same_identity_context_and_returns_gateway_errors_without_retry()
    {
        using var handler = new Handler(async (request, _) =>
        {
            Assert.EndsWith("/channel/v1/audit/narration", request.RequestUri!.AbsoluteUri, StringComparison.Ordinal);
            var body = JsonNode.Parse(await request.Content!.ReadAsStringAsync(CancellationToken.None));
            Assert.Equal("rejected", body!["verdict"]!.GetValue<string>());
            return JsonResponse("""{"error":{"code":"reader_forbidden","message":"not permitted","retryable":false}}""", HttpStatusCode.Forbidden);
        });
        using var http = new HttpClient(handler);
        var reply = await Client(http).ReportNarrationAsync(IdentityTests.Who(), new JsonObject { ["verdict"] = "rejected" });
        Assert.False(reply.Ok);
        Assert.Equal(403, reply.Status);
        Assert.Equal("reader_forbidden", reply.ErrorCode);
        Assert.Equal("not permitted", reply.ErrorMessage);
        Assert.Equal(1, handler.Calls);
        Assert.Null(reply.ToCapabilityResult("audit"));
    }

    [Theory]
    [InlineData("not JSON <secret-token>", "bad_response")]
    [InlineData("{", "bad_response")]
    [InlineData("", "bad_response")]
    public async Task Non_json_is_a_sanitized_failure_even_on_HTTP_success(string response, string expected)
    {
        using var handler = new Handler((_, _) => Task.FromResult(JsonResponse(response)));
        using var http = new HttpClient(handler);
        var reply = await Client(http).CallToolAsync(IdentityTests.Who(), "book_rank", []);
        Assert.False(reply.Ok);
        Assert.Equal(200, reply.Status);
        Assert.Equal(expected, reply.ErrorCode);
        Assert.DoesNotContain("secret-token", reply.Body.ToJsonString(), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("[1,2]")]
    [InlineData("null")]
    [InlineData("\"hello\"")]
    public async Task Non_object_json_is_retained_under_detail_without_becoming_a_capability(string json)
    {
        using var handler = new Handler((_, _) => Task.FromResult(JsonResponse(json)));
        using var http = new HttpClient(handler);
        var reply = await Client(http).CallToolAsync(IdentityTests.Who(), "book_rank", []);
        Assert.True(reply.Body.ContainsKey("detail"));
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(json), reply.Body["detail"]));
        Assert.Null(reply.ToCapabilityResult("book_rank"));
    }

    [Fact]
    public async Task Network_and_credential_failures_never_reflect_exception_messages()
    {
        using var handler = new Handler((_, _) => throw new HttpRequestException("Bearer secret-token https://private-url"));
        using var http = new HttpClient(handler);
        var transport = await Client(http).CallToolAsync(IdentityTests.Who(), "book_rank", []);
        var credential = await Client(http, new Tokens(new InvalidOperationException("credential=secret-token")))
            .CallToolAsync(IdentityTests.Who(), "book_rank", []);
        Assert.All(new[] { transport, credential }, reply =>
        {
            Assert.False(reply.Ok);
            Assert.Equal(0, reply.Status);
            Assert.Equal("gateway_unreachable", reply.ErrorCode);
            Assert.DoesNotContain("secret-token", reply.Body.ToJsonString(), StringComparison.Ordinal);
        });
        Assert.Equal(1, handler.Calls);
    }

    [Fact]
    public async Task Timeout_is_explicit_unknown_outcome_and_never_automatically_retried()
    {
        using var handler = new Handler(async (_, cancellation) =>
        {
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellation);
            return JsonResponse("{}");
        });
        using var http = new HttpClient(handler);
        var reply = await Client(http, timeout: TimeSpan.FromMilliseconds(30))
            .CallToolAsync(IdentityTests.Who(), "change_commit", [], "stable-operation", "token");
        Assert.Equal("timeout", reply.ErrorCode);
        Assert.Equal(0, reply.Status);
        Assert.Equal(1, handler.Calls);
    }

    [Fact]
    public async Task Token_acquisition_is_bounded_even_if_a_provider_does_not_observe_cancellation()
    {
        using var handler = new Handler((_, _) => Task.FromResult(JsonResponse("{}")));
        using var http = new HttpClient(handler);
        var reply = await Client(http, new StalledToken(), TimeSpan.FromMilliseconds(30))
            .CallToolAsync(IdentityTests.Who(), "book_rank", []);
        Assert.Equal("timeout", reply.ErrorCode);
        Assert.Equal(0, handler.Calls);
    }

    [Fact]
    public async Task Response_body_reading_is_inside_the_timeout_and_disposes_the_response_stream()
    {
        await using var stream = new SlowStream();
        using var handler = new Handler((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StreamContent(stream),
        }));
        using var http = new HttpClient(handler);
        var reply = await Client(http, timeout: TimeSpan.FromMilliseconds(30)).CallToolAsync(IdentityTests.Who(), "book_rank", []);
        Assert.Equal("timeout", reply.ErrorCode);
        Assert.True(stream.Disposed);
    }

    [Fact]
    public async Task Caller_cancellation_is_propagated_without_becoming_an_unreachable_reply()
    {
        using var started = new SemaphoreSlim(0);
        using var handler = new Handler(async (_, cancellation) =>
        {
            started.Release();
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellation);
            return JsonResponse("{}");
        });
        using var http = new HttpClient(handler);
        using var cancellation = new CancellationTokenSource();
        var call = Client(http).CallToolAsync(IdentityTests.Who(), "book_rank", [], cancellationToken: cancellation.Token);
        await started.WaitAsync();
        await cancellation.CancelAsync();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => call);
        Assert.Equal(1, handler.Calls);
    }

    [Fact]
    public async Task Pre_cancelled_call_does_not_acquire_a_token_or_send()
    {
        using var handler = new Handler((_, _) => Task.FromResult(JsonResponse("{}")));
        using var http = new HttpClient(handler);
        var tokens = new Tokens();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Client(http, tokens)
            .CallToolAsync(IdentityTests.Who(), "book_rank", [], cancellationToken: new CancellationToken(true)));
        Assert.Equal(0, tokens.Calls);
        Assert.Equal(0, handler.Calls);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Response_size_is_bounded_for_known_and_streamed_content_lengths(bool knownLength)
    {
        using var handler = new Handler((_, _) =>
        {
            HttpContent content = knownLength
                ? new StringContent(new string('x', 100), Encoding.UTF8, "application/json")
                : new StreamContent(new NonSeekableStream(Encoding.UTF8.GetBytes(new string('x', 100))));
            if (!knownLength)
            {
                content.Headers.ContentLength = null;
            }
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = content });
        });
        using var http = new HttpClient(handler);
        var reply = await Client(http, maxBytes: 16).CallToolAsync(IdentityTests.Who(), "book_rank", []);
        Assert.False(reply.Ok);
        Assert.Equal("response_too_large", reply.ErrorCode);
    }

    [Theory]
    [InlineData("../audit/narration")]
    [InlineData("https://attacker.example")]
    [InlineData("tool?override=yes")]
    [InlineData("tool/name")]
    public async Task Tool_names_cannot_escape_the_fixed_gateway_path(string tool)
    {
        using var http = new HttpClient();
        await Assert.ThrowsAsync<ArgumentException>(() => Client(http).CallToolAsync(IdentityTests.Who(), tool, []));
    }

    [Fact]
    public async Task Azure_token_adapter_requests_only_the_gateway_application_scope()
    {
        var credential = new Credential();
        var settings = new GatewaySettings(new Uri("https://gateway.example"), "api://channel-gateway/");
        var provider = new AzureCredentialTokenProvider(credential, settings.Scope);
        Assert.Equal("service-token", await provider.GetTokenAsync());
        Assert.Equal("service-token", await provider.GetTokenAsync());
        Assert.Equal("api://channel-gateway/.default", Assert.Single(credential.Scopes!));
        Assert.Equal(2, credential.Calls);
    }

}
