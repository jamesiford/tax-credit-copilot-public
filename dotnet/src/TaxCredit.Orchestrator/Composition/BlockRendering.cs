using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;

namespace TaxCredit.Orchestrator.Composition;

internal static class BlockRendering
{
    internal static string Render(IReadOnlyList<CompositionRun> runs)
    {
        var answering = runs.Where(run => !run.IsLookup).ToArray();
        var parts = new List<string>();
        foreach (var run in answering.Length == 0 ? runs : answering)
        {
            var method = CompositionProjection.String(run.Arguments["method"]);
            if (method is "min_max" or "pay_period")
            {
                parts.Add("### " + (method == "min_max" ? "Min-Max method" : "Pay Period method"));
            }
            foreach (var node in run.Result.Blocks)
            {
                parts.Add(RenderBlock(node));
            }
        }
        return string.Join("\n\n", parts.Where(part => part.Length != 0));
    }

    private static string RenderBlock(JsonNode? node)
    {
        if (node is not JsonObject block || CompositionProjection.String(block["kind"]) is not { } kind ||
            kind is not ("heading" or "paragraph" or "bullets" or "table" or "callout"))
        {
            throw new InvalidOperationException("invalid_block");
        }
        if (block["text"] is not null && CompositionProjection.String(block["text"]) is null)
        {
            throw new InvalidOperationException("invalid_block");
        }
        var text = CompositionProjection.String(block["text"]) ?? "";
        var rows = Rows(block["rows"]);
        return kind switch
        {
            "heading" => "### " + text,
            "paragraph" => text,
            "callout" => string.Join("\n", text.Split('\n').Select(line => "> " + line.TrimEnd('\r'))),
            "bullets" => rows.All(row => row.Length == 1) ?
                string.Join("\n", rows.Select(row => "- " + row[0])) : throw new InvalidOperationException("invalid_block"),
            _ => Table(rows),
        };
    }

    private static string[][] Rows(JsonNode? node)
    {
        if (node is null)
        {
            return [];
        }
        if (node is not JsonArray array)
        {
            throw new InvalidOperationException("invalid_block");
        }
        return array.Select(row => row is JsonArray cells ?
            cells.Select(cell => CompositionProjection.String(cell) ?? throw new InvalidOperationException("invalid_block")).ToArray() :
            throw new InvalidOperationException("invalid_block")).ToArray();
    }

    private static string Table(string[][] rows)
    {
        if (rows.Length == 0)
        {
            return "";
        }
        if (rows[0].Length == 0 || rows.Any(row => row.Length != rows[0].Length))
        {
            throw new InvalidOperationException("invalid_block");
        }
        static string Line(IEnumerable<string> cells) => "| " + string.Join(" | ", cells) + " |";
        static string Cell(string text) => text.Replace("|", "\\|", StringComparison.Ordinal)
            .Replace("\r", " ", StringComparison.Ordinal).Replace("\n", " ", StringComparison.Ordinal);
        return string.Join("\n", new[] { Line(rows[0].Select(Cell)), Line(rows[0].Select(_ => "---")) }
            .Concat(rows.Skip(1).Select(row => Line(row.Select(Cell)))));
    }
}
