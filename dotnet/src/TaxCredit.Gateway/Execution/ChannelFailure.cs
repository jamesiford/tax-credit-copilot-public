using System.Text.Json.Nodes;

namespace TaxCredit.Gateway.Execution;

internal sealed class ChannelFailure(int status, string code, string message, bool retryable = false) : Exception(message)
{
    internal int Status { get; } = status;
    internal string Code { get; } = code;
    internal bool Retryable { get; } = retryable;
    internal JsonObject Body(string? correlation = null)
    {
        var body = new JsonObject { ["error"] = new JsonObject { ["code"] = Code, ["message"] = Message, ["retryable"] = Retryable } };
        if (correlation is not null) { body["correlation_id"] = correlation; }
        return body;
    }
}
