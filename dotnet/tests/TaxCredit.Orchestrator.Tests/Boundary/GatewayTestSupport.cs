using System.Net;
using System.Text;
using Azure.Core;
using TaxCredit.Orchestrator.Boundary;

namespace TaxCredit.Orchestrator.Tests.Boundary;

internal static class GatewayTestSupport
{
    internal static GatewayClient Client(HttpClient http, IServiceTokenProvider? tokens = null, TimeSpan? timeout = null, int maxBytes = 1024) =>
        new(http, tokens ?? new Tokens(), new GatewaySettings(new Uri("https://gateway.example"), "api://gateway", timeout, maxBytes));

    internal static HttpResponseMessage JsonResponse(string json, HttpStatusCode status = HttpStatusCode.OK) =>
        new(status) { Content = new StringContent(json, Encoding.UTF8, "application/json") };

    internal sealed class Handler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send) : HttpMessageHandler
    {
        private int calls;
        public int Calls => calls;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Interlocked.Increment(ref calls);
            return send(request, cancellationToken);
        }
    }

    internal sealed class Tokens(Exception? failure = null) : IServiceTokenProvider
    {
        private int calls;
        public int Calls => calls;
        public ValueTask<string> GetTokenAsync(CancellationToken cancellationToken = default)
        {
            Interlocked.Increment(ref calls);
            return failure is null ? ValueTask.FromResult("service-token") : ValueTask.FromException<string>(failure);
        }
    }

    internal sealed class Credential : TokenCredential
    {
        public string[]? Scopes { get; private set; }
        public int Calls { get; private set; }
        public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
        {
            Scopes = requestContext.Scopes;
            Calls++;
            return new AccessToken("service-token", DateTimeOffset.UtcNow.AddMinutes(5));
        }
        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken) =>
            ValueTask.FromResult(GetToken(requestContext, cancellationToken));
    }

    internal sealed class StalledToken : IServiceTokenProvider
    {
        public ValueTask<string> GetTokenAsync(CancellationToken cancellationToken = default) =>
            new(new TaskCompletionSource<string>().Task);
    }

    internal sealed class SlowStream : MemoryStream
    {
        public bool Disposed { get; private set; }
        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        {
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            return 0;
        }
        protected override void Dispose(bool disposing)
        {
            Disposed = true;
            base.Dispose(disposing);
        }
    }

    internal sealed class NonSeekableStream(byte[] content) : MemoryStream(content)
    {
        public override bool CanSeek => false;
    }
}
