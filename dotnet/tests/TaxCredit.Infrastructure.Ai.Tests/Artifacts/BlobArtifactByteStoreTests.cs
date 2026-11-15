using System.Net;
using Azure.Core;
using Azure.Core.Pipeline;
using Azure.Identity;
using Azure.Storage.Blobs;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Ai.Artifacts;
using TaxCredit.Infrastructure.Ai.Artifacts;

namespace TaxCredit.Infrastructure.Ai.Tests.Artifacts;

public sealed class BlobArtifactByteStoreTests
{
    [Fact]
    public async Task Blob_wire_is_create_only_with_content_type_and_injected_entra_credential()
    {
        using var handler = new BlobHandler();
        using var http = new HttpClient(handler);
        var credential = new FakeCredential();
        var store = Create(http, credential);
        byte[] bytes = [0, 255, 42];
        await store.PutAsync("outputs", "run/file.bin", bytes, "application/octet-stream");
        Assert.Equal("*", handler.IfNoneMatch);
        Assert.Equal("application/octet-stream", handler.ContentType);
        Assert.Equal(bytes, handler.StoredBytes);
        Assert.True(handler.BearerPresent);
        Assert.Contains("https://storage.azure.com/.default", credential.Scopes);
        Assert.Equal(bytes, await store.GetAsync("outputs", "run/file.bin"));

        var conflict = await Assert.ThrowsAsync<ArtifactByteException>(() =>
            store.PutAsync("outputs", "run/file.bin", new byte[] { 9 }, "t").AsTask());
        Assert.Equal("artifact_exists", conflict.Code);
        Assert.Equal(bytes, handler.StoredBytes);
    }

    [Theory]
    [InlineData(404, "BlobNotFound", true)]
    [InlineData(404, "ContainerNotFound", false)]
    [InlineData(403, "AuthorizationFailure", false)]
    [InlineData(500, "InternalError", false)]
    public async Task Only_blob_not_found_is_absence(int status, string code, bool absent)
    {
        using var handler = new BlobHandler { ForcedStatus = status, ForcedCode = code };
        using var http = new HttpClient(handler);
        var store = Create(http, new FakeCredential());
        if (absent)
        {
            Assert.Null(await store.GetAsync("outputs", "run/file.bin"));
        }
        else
        {
            var error = await Assert.ThrowsAsync<ArtifactByteException>(() =>
                store.GetAsync("outputs", "run/file.bin").AsTask());
            Assert.Equal("artifact_store_unavailable", error.Code);
            Assert.Null(error.InnerException);
            Assert.DoesNotContain("private-upstream-body", error.ToString(), StringComparison.Ordinal);
        }
    }

    [Fact]
    public async Task Network_failure_propagates_without_endpoint_or_upstream_details()
    {
        using var handler = new BlobHandler { NetworkFailure = true };
        using var http = new HttpClient(handler);
        var error = await Assert.ThrowsAsync<ArtifactByteException>(() =>
            Create(http, new FakeCredential()).GetAsync("outputs", "run/file.bin").AsTask());
        Assert.Equal(503, error.StatusCode);
        Assert.DoesNotContain("private-upstream-body", error.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Credential_failure_is_safe_unavailability_and_never_anonymous_access()
    {
        using var handler = new BlobHandler();
        using var http = new HttpClient(handler);
        var error = await Assert.ThrowsAsync<ArtifactByteException>(() =>
            Create(http, new FailingCredential()).GetAsync("outputs", "run/file.bin").AsTask());
        Assert.Equal("artifact_store_unavailable", error.Code);
        Assert.False(handler.BearerPresent);
        Assert.Null(error.InnerException);
        Assert.DoesNotContain("private-upstream-body", error.ToString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Cancellation_is_not_an_absent_blob_or_a_dependency_failure()
    {
        using var handler = new BlobHandler();
        using var http = new HttpClient(handler);
        using var cancellation = new CancellationTokenSource();
        await cancellation.CancelAsync();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            Create(http, new FakeCredential()).GetAsync("outputs", "run/file.bin", cancellation.Token).AsTask());
    }

    [Fact]
    public async Task A_storage_challenge_cannot_acquire_a_token_for_another_resource()
    {
        using var handler = new BlobHandler
        {
            ForcedStatus = 401,
            ForcedCode = "NoAuthenticationInformation",
            Challenge = "Bearer authorization_uri=\"https://login.microsoftonline.com/common/oauth2/authorize\", resource_id=\"https://unexpected.invalid/\""
        };
        using var http = new HttpClient(handler);
        var credential = new FakeCredential();
        var error = await Assert.ThrowsAsync<ArtifactByteException>(() =>
            Create(http, credential).GetAsync("outputs", "run/file.bin").AsTask());
        Assert.Equal("artifact_store_unavailable", error.Code);
        Assert.Equal(1, credential.Calls);
        Assert.Equal(new[] { "https://storage.azure.com/.default" }, credential.Scopes);
    }

    private static BlobArtifactByteStore Create(HttpClient http, TokenCredential credential)
    {
        var options = new BlobClientOptions { Transport = new HttpClientTransport(http) };
        options.Retry.MaxRetries = 0;
        var services = new ServiceCollection();
        services.AddBlobArtifactBytes(new Uri("https://storage.invalid"), credential, options);
        return Assert.IsType<BlobArtifactByteStore>(Assert.Single(services).ImplementationInstance);
    }

    private sealed class FakeCredential : TokenCredential
    {
        internal string[] Scopes { get; private set; } = [];
        internal int Calls { get; private set; }

        public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Calls++;
            Scopes = requestContext.Scopes;
            return new AccessToken(Guid.NewGuid().ToString("N"), DateTimeOffset.UtcNow.AddHours(1));
        }

        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken) =>
            ValueTask.FromResult(GetToken(requestContext, cancellationToken));
    }

    private sealed class FailingCredential : TokenCredential
    {
        public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken) =>
            throw new AuthenticationFailedException("private-upstream-body");

        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken) =>
            throw new AuthenticationFailedException("private-upstream-body");
    }

    private sealed class BlobHandler : HttpMessageHandler
    {
        internal int? ForcedStatus { get; init; }
        internal string ForcedCode { get; init; } = "InternalError";
        internal bool NetworkFailure { get; init; }
        internal string? Challenge { get; init; }
        internal byte[]? StoredBytes { get; private set; }
        internal string? IfNoneMatch { get; private set; }
        internal string? ContentType { get; private set; }
        internal bool BearerPresent { get; private set; }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (NetworkFailure)
            {
                throw new HttpRequestException("private-upstream-body");
            }
            BearerPresent = request.Headers.Authorization?.Scheme == "Bearer";
            if (ForcedStatus is { } status)
            {
                var response = Error(status, ForcedCode);
                if (Challenge is not null)
                {
                    response.Headers.TryAddWithoutValidation("WWW-Authenticate", Challenge);
                }
                return response;
            }
            if (request.Method == HttpMethod.Put)
            {
                IfNoneMatch = string.Join(",", request.Headers.IfNoneMatch);
                ContentType = request.Headers.TryGetValues("x-ms-blob-content-type", out var types)
                    ? types.Single() : request.Content?.Headers.ContentType?.MediaType;
                if (StoredBytes is not null)
                {
                    return Error(412, "ConditionNotMet");
                }
                StoredBytes = await request.Content!.ReadAsByteArrayAsync(cancellationToken);
                return Response(HttpStatusCode.Created, []);
            }
            return StoredBytes is null ? Error(404, "BlobNotFound") : Response(HttpStatusCode.OK, StoredBytes);
        }

        private static HttpResponseMessage Response(HttpStatusCode status, byte[] body)
        {
            var response = new HttpResponseMessage(status) { Content = new ByteArrayContent(body) };
            response.Headers.Add("ETag", "\"synthetic-etag\"");
            response.Headers.Add("x-ms-request-id", Guid.NewGuid().ToString("N"));
            response.Content.Headers.LastModified = DateTimeOffset.UtcNow;
            return response;
        }

        private static HttpResponseMessage Error(int status, string code)
        {
            var response = Response((HttpStatusCode)status, System.Text.Encoding.UTF8.GetBytes("private-upstream-body"));
            response.Headers.Add("x-ms-error-code", code);
            return response;
        }
    }
}
