using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Streams;

namespace TaxCredit.Application.Features.Ai.Chat;

/// <summary>A chat pipeline receives the canonical capability envelope, not payroll or an HTTP response.</summary>
public interface IChatFactSource
{
    /// <summary>Executes only a whitelisted deterministic intent for the explicit request scope.</summary>
    ValueTask<JsonObject> ReadAsync(string intent, ChatQuery query, CancellationToken cancellationToken);
}

internal static class NarrationLanes
{
    internal static JsonObject Trusted(JsonObject envelope)
    {
        var facts = (envelope["facts"] as JsonObject)?.DeepClone().AsObject() ?? new JsonObject();
        if (envelope["user_only_facts"] is JsonArray userOnly)
        {
            foreach (var name in userOnly.Select(n => n?.GetValue<string>()).OfType<string>()) { facts.Remove(name); }
        }
        return facts;
    }

    internal static string Render(JsonObject envelope)
    {
        if (envelope["blocks"] is not JsonArray blocks) { return ""; }
        var rendered = blocks.OfType<JsonObject>().Select(block =>
        {
            var text = block["text"]?.ToString() ?? "";
            var rows = (block["rows"] as JsonArray)?.OfType<JsonArray>().ToArray() ?? [];
            return block["kind"]?.ToString() switch
            {
                "heading" => "### " + text,
                "paragraph" => text,
                "callout" => string.Join("\n", text.Split('\n').Select(line => "> " + line)),
                "bullets" => string.Join("\n", rows.Select(row => "- " + row[0])),
                "table" => Table(rows),
                _ => ""
            };
        });
        return string.Join("\n\n", rendered.Append(envelope["disclaimer"]?.ToString() ?? "").Where(s => s.Length > 0));
    }

    private static string Table(JsonArray[] rows)
    {
        if (rows.Length == 0) { return ""; }
        var lines = rows.Select(row => "| " + string.Join(" | ", row.Select(c =>
            (c?.ToString() ?? "").Replace("|", "\\|", StringComparison.Ordinal).Replace('\n', ' '))) + " |").ToList();
        lines.Insert(1, "| " + string.Join(" | ", rows[0].Select(_ => "---")) + " |");
        return string.Join("\n", lines);
    }
}
