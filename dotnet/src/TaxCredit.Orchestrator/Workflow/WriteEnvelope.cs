using System.Text.Json;
using System.Text.Json.Nodes;

namespace TaxCredit.Orchestrator.Workflow;

internal static class WriteEnvelope
{
    internal static string? Token(WriteGatewayReply reply)
    {
        if (reply.Body.ValueKind != JsonValueKind.Object
            || !reply.Body.TryGetProperty("facts", out JsonElement facts)
            || facts.ValueKind != JsonValueKind.Object
            || !facts.TryGetProperty("confirmation", out JsonElement confirmation)
            || confirmation.ValueKind != JsonValueKind.Object
            || !confirmation.TryGetProperty("token", out JsonElement token)
            || token.ValueKind != JsonValueKind.String)
        {
            return null;
        }

        string? value = token.GetString();
        return string.IsNullOrWhiteSpace(value) ? null : value;
    }

    internal static WriteGatewayReply Sanitize(WriteGatewayReply reply, string? token = null)
    {
        JsonNode? root = JsonNode.Parse(reply.Body.GetRawText());
        Scrub(root, token);
        return reply with { Body = JsonSerializer.SerializeToElement(root) };
    }

    private static void Scrub(JsonNode? node, string? token)
    {
        if (node is JsonObject obj)
        {
            foreach (string key in obj.Select(pair => pair.Key).ToArray())
            {
                if (key.Equals("token", StringComparison.OrdinalIgnoreCase)
                    || key.Equals("confirmation_token", StringComparison.OrdinalIgnoreCase))
                {
                    obj.Remove(key);
                }
                else
                {
                    ReplaceOrRecurse(obj[key], value => obj[key] = value, token);
                }
            }
        }
        else if (node is JsonArray array)
        {
            for (int i = 0; i < array.Count; i++)
            {
                int index = i;
                ReplaceOrRecurse(array[i], value => array[index] = value, token);
            }
        }
    }

    private static void ReplaceOrRecurse(JsonNode? node, Action<string> replace, string? token)
    {
        if (token is not null && node is JsonValue value && value.TryGetValue(out string? text))
        {
            replace(text.Replace(token, "[withheld]", StringComparison.Ordinal));
        }
        else
        {
            Scrub(node, token);
        }
    }

    internal static string Error(WriteGatewayReply reply)
    {
        if (reply.Body.ValueKind == JsonValueKind.Object
            && reply.Body.TryGetProperty("error", out JsonElement error)
            && error.ValueKind == JsonValueKind.Object
            && error.TryGetProperty("code", out JsonElement code)
            && code.ValueKind == JsonValueKind.String)
        {
            return code.GetString() ?? "gateway_refused";
        }

        return "gateway_refused";
    }
}
