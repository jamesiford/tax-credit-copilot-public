using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;
using TaxCredit.Orchestrator.Boundary;

namespace TaxCredit.Orchestrator.Tests.Support;

internal sealed class LocalGatewayTransport(FakeGateway gateway) : HttpMessageHandler
{
    internal List<JsonObject> Bodies { get; } = [];
    internal List<IReadOnlyDictionary<string, string>> Headers { get; } = [];
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        var headers = request.Headers.ToDictionary(pair => pair.Key.ToLowerInvariant(), pair => string.Join(",", pair.Value), StringComparer.Ordinal);
        Headers.Add(headers);
        if (request.Headers.Authorization?.Scheme != "Bearer" || headers["x-acting-tenant"] != Rig.Tenant)
        {
            return new HttpResponseMessage(HttpStatusCode.Unauthorized);
        }
        var body = JsonNode.Parse(await request.Content!.ReadAsStringAsync(cancellationToken))!.AsObject();
        Bodies.Add((JsonObject)body.DeepClone());
        var identity = Rig.Person(headers["x-acting-user-oid"], headers["x-conversation-id"], headers["x-correlation-id"]);
        GatewayReply reply;
        if (request.RequestUri!.AbsolutePath.EndsWith("/audit/narration", StringComparison.Ordinal))
        {
            reply = await gateway.ReportNarrationAsync(identity, body, cancellationToken);
        }
        else
        {
            var name = request.RequestUri.Segments[^1];
            reply = await gateway.CallToolAsync(identity, name, body["args"]!.AsObject(),
                body["idempotency_key"]?.ToString(), body["confirmation_token"]?.ToString(), cancellationToken);
        }
        return new HttpResponseMessage((HttpStatusCode)reply.Status) { Content = JsonContent.Create(reply.Body) };
    }
}
