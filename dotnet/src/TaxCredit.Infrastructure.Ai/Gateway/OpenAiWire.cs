using System.Globalization;
using System.Net;
using System.Text.Json;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Gateway;

/// <summary>Pure wire construction and safe status mapping, shared across injected transports.</summary>
public static class OpenAiWire
{
    /// <summary>Encodes deployments as one path segment; v1 selects the model in the body.</summary>
    public static Uri BuildUri(GatewaySettings settings, string model)
    {
        string root = settings.Endpoint.AbsoluteUri.TrimEnd('/');
        return new(settings.Dialect == GatewayDialect.AzureDeployments
            ? $"{root}/openai/deployments/{Uri.EscapeDataString(model)}/chat/completions?api-version={Uri.EscapeDataString(settings.ApiVersion)}"
            : $"{root}/v1/chat/completions");
    }
    /// <summary>Builds the chat-completions dialect without executing offered functions.</summary>
    public static string BuildBody(GatewaySettings settings, ChatRequest request)
    {
        var body = new Dictionary<string, object?>
        {
            ["messages"] = request.Messages.Select(Message).ToArray(),
            ["stream"] = settings.Streaming
        };
        if (settings.Dialect == GatewayDialect.OpenAiV1)
        {
            body["model"] = request.Model;
        }

        if (request.Temperature is not null)
        {
            body["temperature"] = request.Temperature;
        }

        if (settings.Streaming)
        {
            body["stream_options"] = new { include_usage = true };
        }

        if (request.Tools.Count > 0)
        {
            body["tools"] = request.Tools.Select(t => new
            {
                type = "function",
                function = new { name = t.Name, description = t.Description, parameters = t.Parameters }
            }).ToArray();
        }

        return JsonSerializer.Serialize(body);
    }
    private static Dictionary<string, object?> Message(ChatMessage message)
    {
        var body = new Dictionary<string, object?> { ["role"] = message.Role, ["content"] = message.Content };
        if (message.ToolCallId is not null)
        {
            body["tool_call_id"] = message.ToolCallId;
        }

        if (message.ToolCalls?.Count > 0)
        {
            body["tool_calls"] = message.ToolCalls.Select(t => new
            {
                id = t.Id,
                type = "function",
                function = new { name = t.Name, arguments = t.Arguments }
            }).ToArray();
        }

        return body;
    }
    /// <summary>Parses delta seconds or an HTTP date, clamping past dates to zero.</summary>
    public static TimeSpan? RetryAfter(string? value, DateTimeOffset now)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        if (double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out double seconds))
        {
            return double.IsFinite(seconds) && seconds <= TimeSpan.MaxValue.TotalSeconds
                ? TimeSpan.FromSeconds(Math.Max(0, seconds)) : null;
        }

        return DateTimeOffset.TryParse(value, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var date)
            ? date > now ? date - now : TimeSpan.Zero : null;
    }
    /// <summary>Maps status without inspecting an upstream body or credential header.</summary>
    public static ModelException Error(HttpStatusCode status, string? retryAfter, DateTimeOffset now) => new(
        (int)status switch
        {
            401 or 403 => ModelErrorKind.Authentication,
            429 => ModelErrorKind.RateLimited,
            408 or 425 or >= 500 => ModelErrorKind.Unavailable,
            _ => ModelErrorKind.BadRequest
        }, $"http_{(int)status}", RetryAfter(retryAfter, now));
}
