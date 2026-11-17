using System.Net;
using System.Text.Json;
using Azure.Core;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Auth;
using TaxCredit.Infrastructure.Ai.Gateway;

namespace TaxCredit.Infrastructure.Ai.Tests;

public sealed class TokenAuthTests
{
    [Fact]
    public async Task ConcurrentRefreshCoalescesAndExpiryAndInvalidationRefetch()
    {
        var time = new FakeTime();
        var source = new TokenSource(time);
        var auth = new CachedTokenAuth(source, "api://synthetic/.default", time);
        var headers = await Task.WhenAll(Enumerable.Range(0, 20).Select(_ => auth.HeadersAsync().AsTask()));
        Assert.Equal(1, source.Calls);
        Assert.Single(headers.Select(h => h["Authorization"]).Distinct());
        Assert.Equal("api://synthetic", source.Audience);
        time.Advance(TimeSpan.FromSeconds(241));
        await auth.HeadersAsync();
        Assert.Equal(2, source.Calls);
        auth.Invalidate();
        await auth.HeadersAsync();
        Assert.Equal(3, source.Calls);
    }
    [Fact]
    public async Task WrongAudienceExpiredAndCredentialErrorsAreSafe()
    {
        var time = new FakeTime();
        foreach (var source in new IModelTokenSource[]
        {
            new TokenSource(time) { WrongAudience = true },
            new TokenSource(time) { Expired = true },
            new TokenSource(time) { Failure = true }
        })
        {
            var error = await Assert.ThrowsAsync<ModelException>(() => new CachedTokenAuth(source, "api://synthetic", time).HeadersAsync().AsTask());
            Assert.Equal(ModelErrorKind.Authentication, error.Kind);
            Assert.DoesNotContain("SENTINEL", error.ToString(), StringComparison.Ordinal);
        }

    }
    [Fact]
    public async Task JwtAudienceCannotDisagreeWithTokenSourceMetadata()
    {
        var time = new FakeTime();
        string payload = Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes("{\"aud\":\"api://other\"}")).TrimEnd('=');
        var source = new FixedTokenSource(new ModelAccessToken("e30." + payload + ".signature", "api://synthetic", time.GetUtcNow().AddHours(1)));
        using var auth = new CachedTokenAuth(source, "api://synthetic", time);
        var error = await Assert.ThrowsAsync<ModelException>(() => auth.HeadersAsync().AsTask());
        Assert.Equal("token_audience_mismatch", error.Code);
    }
    private sealed class FixedTokenSource(ModelAccessToken token) : IModelTokenSource
    {
        public ValueTask<ModelAccessToken> AcquireAsync(string audience, CancellationToken cancellationToken) => ValueTask.FromResult(token);
    }
    [Fact]
    public async Task Http401InvalidatesWithoutAutomaticallyRetrying()
    {
        var time = new FakeTime();
        var source = new TokenSource(time);
        var auth = new CachedTokenAuth(source, "api://synthetic", time);
        bool reject = false;
        var handler = new FakeHttp((_, _) => Task.FromResult(reject
            ? new HttpResponseMessage(HttpStatusCode.Unauthorized) : FakeHttp.Sse("data: [DONE]\n")));
        using var http = new HttpClient(handler);
        var model = new OpenAiCompatibleChatModel(http, new(new Uri("https://gateway.invalid")), auth);
        await TestStreams.Collect(model.StreamAsync(new("test", [])));
        reject = true;
        await Assert.ThrowsAsync<ModelException>(() => TestStreams.Collect(model.StreamAsync(new("test", []))));
        Assert.Equal(1, source.Calls);
        reject = false;
        await TestStreams.Collect(model.StreamAsync(new("test", [])));
        Assert.Equal(2, source.Calls);
        Assert.Equal(3, handler.Calls);
    }
    [Fact]
    public async Task OAuthFormExpiryAndAudienceAreInjectedWithoutLiveCredentials()
    {
        var time = new FakeTime();
        using var http = new HttpClient(new FakeHttp(async (request, ct) =>
        {
            string form = await request.Content!.ReadAsStringAsync(ct);
            Assert.Contains("grant_type=client_credentials", form, StringComparison.Ordinal);
            Assert.Contains("client_secret=synthetic-secret", form, StringComparison.Ordinal);
            Assert.Contains("scope=synthetic-scope", form, StringComparison.Ordinal);
            return FakeHttp.Json("{\"access_token\":\"synthetic-token\",\"expires_in\":120,\"aud\":\"api://synthetic\"}");
        }));
        var source = new OAuthTokenSource(http, new("https://token.invalid"), "synthetic-client", "synthetic-secret", "synthetic-scope", time);
        var token = await source.AcquireAsync("api://synthetic", CancellationToken.None);
        Assert.Equal(time.GetUtcNow().AddSeconds(120), token.ExpiresAt);
        Assert.DoesNotContain("synthetic-secret", source.ToString(), StringComparison.Ordinal);
        Assert.DoesNotContain("synthetic-token", token.ToString(), StringComparison.Ordinal);
    }
    [Theory]
    [InlineData(400, ModelErrorKind.Authentication)]
    [InlineData(401, ModelErrorKind.Authentication)]
    [InlineData(503, ModelErrorKind.Unavailable)]
    public async Task OAuthErrorsNeverReadOrEchoBodies(int status, ModelErrorKind kind)
    {
        using var http = new HttpClient(new FakeHttp((_, _) => Task.FromResult(new HttpResponseMessage((HttpStatusCode)status)
        { Content = new StringContent("SENTINEL-secret") })));
        var source = new OAuthTokenSource(http, new("https://token.invalid"), "synthetic-client", "synthetic-secret");
        var error = await Assert.ThrowsAsync<ModelException>(() => source.AcquireAsync("api://synthetic", CancellationToken.None).AsTask());
        Assert.Equal(kind, error.Kind);
        Assert.DoesNotContain("SENTINEL", error.ToString(), StringComparison.Ordinal);
    }
    [Fact]
    public async Task EntraUsesDefaultScopeAndCancellationSurvives()
    {
        var credential = new FakeCredential();
        var source = new EntraTokenSource(credential);
        var token = await source.AcquireAsync("api://synthetic", CancellationToken.None);
        Assert.Equal("api://synthetic/.default", credential.Scope);
        Assert.Equal("api://synthetic", token.Audience);
        using var stop = new CancellationTokenSource();
        stop.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => source.AcquireAsync("api://synthetic", stop.Token).AsTask());
    }
    private sealed class TokenSource(FakeTime time) : IModelTokenSource
    {
        public int Calls { get; private set; }
        public string? Audience { get; private set; }
        public bool WrongAudience { get; init; }
        public bool Expired { get; init; }
        public bool Failure { get; init; }
        public async ValueTask<ModelAccessToken> AcquireAsync(string audience, CancellationToken cancellationToken)
        {
            Calls++;
            Audience = audience;
            await Task.Yield();
            cancellationToken.ThrowIfCancellationRequested();
            if (Failure)
            {
                throw new InvalidOperationException("SENTINEL");
            }

            return new("synthetic-token", WrongAudience ? "api://other" : audience,
                time.GetUtcNow().AddSeconds(Expired ? -1 : 300));
        }
    }
    private sealed class FakeCredential : TokenCredential
    {
        public string? Scope { get; private set; }
        public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken) => throw new NotSupportedException();
        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Scope = requestContext.Scopes.Single();
            return ValueTask.FromResult(new AccessToken("synthetic-token", DateTimeOffset.UtcNow.AddHours(1)));
        }
    }
}
