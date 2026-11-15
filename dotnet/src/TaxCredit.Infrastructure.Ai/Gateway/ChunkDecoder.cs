using System.Text;
using System.Text.Json;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Gateway;

internal sealed class ChunkDecoder
{
    private readonly SortedDictionary<int, Fragments> _tools = [];
    public string? FinishReason { get; private set; }
    public IReadOnlyList<ModelEvent> Decode(JsonElement payload, bool streaming)
    {
        var events = new List<ModelEvent>();
        if (payload.ValueKind != JsonValueKind.Object)
        {
            throw Invalid();
        }

        if (payload.TryGetProperty("error", out _))
        {
            throw Invalid();
        }

        if (payload.TryGetProperty("choices", out var choices))
        {
            foreach (var choice in choices.EnumerateArray())
            {
                DecodeChoice(choice, streaming, events);
            }
        }

        if (payload.TryGetProperty("usage", out var usage) && usage.ValueKind == JsonValueKind.Object)
        {
            events.Add(new ModelUsage(Tokens(usage, "prompt_tokens"), Tokens(usage, "completion_tokens")));
        }

        return events;
    }
    private void DecodeChoice(JsonElement choice, bool streaming, List<ModelEvent> events)
    {
        if (choice.TryGetProperty("finish_reason", out var reason) && reason.ValueKind == JsonValueKind.String)
        {
            FinishReason = SafeFinish(reason.GetString());
        }

        if (!choice.TryGetProperty(streaming ? "delta" : "message", out var message)
            || message.ValueKind != JsonValueKind.Object)
        {
            return;
        }

        if (message.TryGetProperty("content", out var text) && text.ValueKind == JsonValueKind.String
            && text.GetString() is { Length: > 0 } content)
        {
            events.Add(new TextDelta(content));
        }

        if (message.TryGetProperty("tool_calls", out var calls))
        {
            foreach (var call in calls.EnumerateArray())
            {
                AddTool(call, streaming, events);
            }
        }
    }
    private void AddTool(JsonElement call, bool streaming, List<ModelEvent> events)
    {
        int index = call.TryGetProperty("index", out var slot) ? slot.GetInt32() : 0;
        if (index < 0 || _tools.Count >= 128 && !_tools.ContainsKey(index))
        {
            throw Invalid();
        }

        var function = call.GetProperty("function");
        if (!streaming)
        {
            events.Add(new ToolCall(String(call, "id"), String(function, "name"), String(function, "arguments", "{}")));
            return;
        }
        if (!_tools.TryGetValue(index, out var fragments))
        {
            _tools[index] = fragments = new Fragments();
        }

        if (String(call, "id") is { Length: > 0 } id)
        {
            fragments.Id = id;
        }

        fragments.Name.Append(String(function, "name"));
        fragments.Arguments.Append(String(function, "arguments"));
        if (fragments.Name.Length + fragments.Arguments.Length > 1_048_576)
        {
            throw Invalid();
        }
    }
    public IEnumerable<ToolCall> Drain() => _tools.Values.Where(t => t.Name.Length > 0)
        .Select(t => new ToolCall(t.Id, t.Name.ToString(), t.Arguments.Length == 0 ? "{}" : t.Arguments.ToString()));
    private static int Tokens(JsonElement node, string name)
    {
        if (!node.TryGetProperty(name, out var count) || count.ValueKind == JsonValueKind.Null)
        {
            return 0;
        }

        if (!count.TryGetInt32(out int value) || value < 0)
        {
            throw Invalid();
        }

        return value;
    }
    private static string String(JsonElement node, string key, string fallback = "") =>
        node.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString()! : fallback;
    private static string? SafeFinish(string? value) => value is "stop" or "length" or "tool_calls"
        or "content_filter" or "function_call" ? value : null;
    private static ModelException Invalid() => new(ModelErrorKind.Unavailable, "malformed_model_event");
    private sealed class Fragments
    {
        public string Id { get; set; } = "";
        public StringBuilder Name { get; } = new();
        public StringBuilder Arguments { get; } = new();
    }
}
