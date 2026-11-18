using System.Globalization;
using System.Text;

namespace TaxCredit.Api.Tests.Bench;

internal sealed record Span(string Id, string? ParentId, string Name, TimeSpan Duration, DateTime Start, Dictionary<string, object?> Tags);

/// <summary>Turns recorded spans into a per-stage table with exclusive ("self") time, so the rows add up to the wall clock.</summary>
internal static class SpanTable
{
    // A stage groups spans by the question the owner asks; Domain compute is what is left inside run.calculation.
    private static readonly (string Stage, Func<Span, string?, bool> Match)[] Stages =
    [
        ("resolve and authorize", (s, _) => s.Name is "item" or "resolve" or "calculate" or "unchanged-check"),
        ("fingerprint", (s, _) => s.Name == "fingerprint"),
        ("source read (SQL stream)", (s, _) => s.Name == "source.scan" || s.Name == "source.read" || s.Name == "source.load"),
        ("projection (source rows to pay rows)", (s, _) => s.Name == "source.project"),
        ("engine + gold projection + replay (Domain, derived)", (s, _) => s.Name == "run.calculation"),
        ("gold prepare (value conversion)", (s, _) => s.Name == "gold.prepare"),
        ("persistence writes (inserts)", (s, parent) => s.Name is "persist.insert" or "persist.manifest" or "sql.insert-batch" || (s.Name == "sql.execute" && parent == "sql.insert-batch")),
        ("persistence other statements", (s, parent) => (s.Name == "sql.execute" && parent != "sql.insert-batch") || s.Name is "persist.retire" or "persist.supersede" or "persist.observation"),
        ("persistence reads and validation", (s, _) => s.Name is "sql.query" or "persist.validate" or "gold.validate"),
        ("publication and queue", (s, _) => s.Name is "publish" or "gold.write"),
        ("commit", (s, _) => s.Name is "db.commit" or "db.begin"),
    ];

    internal static string Render(Span[] spans, TimeSpan wall)
    {
        var childTime = spans.Where(s => s.ParentId is not null).GroupBy(s => s.ParentId!)
            .ToDictionary(g => g.Key, g => g.Aggregate(TimeSpan.Zero, (a, s) => a + s.Duration));
        TimeSpan Self(Span s) => s.Duration - (childTime.TryGetValue(s.Id, out var c) ? c : TimeSpan.Zero);
        var names = spans.ToDictionary(s => s.Id, s => s.Name);
        var text = new StringBuilder();
        text.AppendLine("-- stage (exclusive time; rows add up to the item) --");
        var accounted = TimeSpan.Zero;
        foreach (var (stage, match) in Stages)
        {
            var group = spans.Where(s => match(s, s.ParentId is not null && names.TryGetValue(s.ParentId, out var n) ? n : null)).ToArray();
            var self = group.Aggregate(TimeSpan.Zero, (a, s) => a + Self(s));
            accounted += self;
            text.AppendLine(string.Create(CultureInfo.InvariantCulture, $"{stage,-58} {self.TotalSeconds,9:F2}s  {group.Length,6} spans"));
        }
        text.AppendLine(string.Create(CultureInfo.InvariantCulture, $"{"unattributed (outside any span)",-58} {(wall - accounted).TotalSeconds,9:F2}s"));
        text.AppendLine("-- span (exclusive s | inclusive s | count) --");
        foreach (var g in spans.GroupBy(s => s.Name + Suffix(s)).OrderByDescending(g => g.Aggregate(TimeSpan.Zero, (a, s) => a + Self(s))))
        {
            var self = g.Aggregate(TimeSpan.Zero, (a, s) => a + Self(s));
            var total = g.Aggregate(TimeSpan.Zero, (a, s) => a + s.Duration);
            var rows = g.Sum(s => s.Tags.TryGetValue("rows", out var r) ? Convert.ToInt64(r, CultureInfo.InvariantCulture) : 0);
            var bytes = g.Sum(s => s.Tags.TryGetValue("bytes", out var b) ? Convert.ToInt64(b, CultureInfo.InvariantCulture) : 0);
            text.AppendLine(string.Create(CultureInfo.InvariantCulture,
                $"{g.Key,-44} {self.TotalSeconds,9:F3} {total.TotalSeconds,9:F3} {g.Count(),7}  rows={rows} bytes={bytes}"));
        }
        return text.ToString();
    }

    private static string Suffix(Span s) =>
        s.Name is "persist.insert" or "gold.prepare" or "source.scan" or "sql.insert-batch" && s.Tags.TryGetValue("table", out var t) ? "[" + t + "]" : "";
}
