using System.Text.Json.Nodes;
using TaxCredit.Orchestrator.Boundary;

namespace TaxCredit.Orchestrator.Tests.Boundary;

internal static class DiagnosticTestSupport
{
    internal const string Project = "https://aif-example.services.ai.azure.com/api/projects/proj-example";
    internal static readonly Dictionary<string, string?> EmptyEnvironment = [];

    internal static SafeDebugDiagnostics Diagnostics(Probe probe, TimeSpan? stepTimeout = null, TimeSpan? totalTimeout = null) =>
        new(new DiagnosticOptions(EmptyEnvironment, gatewayUrl: "https://target.example",
            stepTimeout: stepTimeout, totalTimeout: totalTimeout), probe);

    internal static JsonNode FirstTarget(JsonObject report) => report["targets"]![0]!;

    internal sealed class Probe : IDiagnosticNetworkProbe
    {
        internal List<string> Calls { get; } = [];
        internal Func<string, CancellationToken, Task<IReadOnlyList<string>>> Resolve { get; init; } =
            (_, _) => Task.FromResult<IReadOnlyList<string>>(["20.1.1.1"]);
        internal Func<string, CancellationToken, Task> Connect { get; init; } = (_, _) => Task.CompletedTask;
        internal Func<string, string, CancellationToken, Task<int>> Tls { get; init; } = (_, _, _) => Task.FromResult(404);
        internal Func<Uri, CancellationToken, Task<int>> Http { get; init; } = (_, _) => Task.FromResult(401);

        public Task<IReadOnlyList<string>> ResolveAsync(string host, CancellationToken cancellationToken)
        {
            Calls.Add("resolve:" + host);
            return Resolve(host, cancellationToken);
        }
        public Task ConnectAsync(string address, CancellationToken cancellationToken)
        {
            Calls.Add("connect:" + address);
            return Connect(address, cancellationToken);
        }
        public Task<int> TlsGetStatusAsync(string host, string address, CancellationToken cancellationToken)
        {
            Calls.Add("tls:" + host);
            return Tls(host, address, cancellationToken);
        }
        public Task<int> HttpGetStatusAsync(Uri uri, CancellationToken cancellationToken)
        {
            Calls.Add("http:" + uri.AbsoluteUri);
            return Http(uri, cancellationToken);
        }
    }

    internal sealed class UnreadableContent : HttpContent
    {
        protected override Task SerializeToStreamAsync(Stream stream, System.Net.TransportContext? context) =>
            Task.FromException(new InvalidOperationException("The private diagnostic response body must never be read."));
        protected override bool TryComputeLength(out long length)
        {
            length = 0;
            return false;
        }
    }
}
