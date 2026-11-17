using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Pilot;

/// <summary>
/// The parallel-calculation reconciliation harness (Python <c>tools/reconcile.py</c>, PILOT-04): given a benchmark (the partner's numbers) and our
/// computed numbers, a per-row match/diff report within an agreed tolerance.
/// </summary>
public static class BenchmarkReconciliation
{
    /// <summary>Python <c>DEFAULT_TOLERANCE</c>, in Average Headcount units.</summary>
    public const double DefaultTolerance = 0.5;

    /// <summary>Python <c>reconcile</c>: row-for-row reconciliation of a benchmark against computed values.</summary>
    /// <param name="benchmark">The benchmark rows, each a dictionary carrying <paramref name="key"/> and <paramref name="value"/>.</param>
    /// <param name="computed">Our computed rows.</param>
    /// <param name="key">The row key's field name.</param>
    /// <param name="value">The compared value's field name.</param>
    /// <param name="tolerance">The agreed tolerance (an int or float, echoed as given); <c>null</c> is <see cref="DefaultTolerance"/>.</param>
    /// <returns>The report tree: per-row status (<c>match</c>, <c>within_tolerance</c>, <c>mismatch</c>, <c>missing_computed</c>, <c>missing_benchmark</c>) and a summary.</returns>
    /// <exception cref="PyValueError">When a value is text that is not a number.</exception>
    /// <exception cref="PyTypeError">When a value is not a number or text.</exception>
    public static PyDict Reconcile(
        IReadOnlyList<PyDict> benchmark,
        IReadOnlyList<PyDict> computed,
        string key = "key",
        string value = "average_headcount",
        PyNumber? tolerance = null)
    {
        ArgumentNullException.ThrowIfNull(benchmark);
        ArgumentNullException.ThrowIfNull(computed);
        var tol = tolerance ?? PyNumber.OfFloat(DefaultTolerance);
        var comp = Index(computed, key, value);
        var bench = Index(benchmark, key, value);

        var rows = new List<object?>();
        long matches = 0, within = 0, mismatches = 0;
        var keys = bench.Keys.Concat(comp.Keys).Distinct(StringComparer.Ordinal);
        foreach (var k in PySort.Sorted(keys, s => s, PyStr.Comparer))
        {
            var hasB = bench.TryGetValue(k, out var b);
            var hasC = comp.TryGetValue(k, out var c);
            if (!hasB)
            {
                rows.Add(Row(k, null, c, null, "missing_benchmark"));
                continue;
            }

            if (!hasC)
            {
                rows.Add(Row(k, b, null, null, "missing_computed"));
                continue;
            }

            var diff = PyRound.Round(c - b, 4);
            string status;
            if (Math.Abs(diff) < 1e-9)
            {
                status = "match";
                matches++;
            }
            else if (PyNum.LessOrEqual(Math.Abs(diff), tol))
            {
                status = "within_tolerance";
                within++;
            }
            else
            {
                status = "mismatch";
                mismatches++;
            }

            rows.Add(Row(k, b, c, diff, status));
        }

        var anyMissing = rows.Cast<PyDict>().Any(r => ((string)r["status"]!).StartsWith("missing", StringComparison.Ordinal));
        return new PyDict().Add("_roadmap_tag", "P1").Add("_story", "PILOT-04").Add("tolerance", PyNum.Tree(tol)).Add("rows", rows)
            .Add("summary", new PyDict()
                .Add("row_count", (long)rows.Count).Add("exact_matches", matches).Add("within_tolerance", within).Add("mismatches", mismatches)
                .Add("reconciled", mismatches == 0 && !anyMissing));
    }

    /// <summary>Python <c>{str(r[key]): float(r[value]) for r in rows if key in r and value in r}</c>: a later duplicate replaces the value, keeping the first position.</summary>
    private static OrderedMap<string, double> Index(IReadOnlyList<PyDict> rows, string key, string value)
    {
        var map = new OrderedMap<string, double>();
        foreach (var r in rows)
        {
            if (r.ContainsKey(key) && r.ContainsKey(value))
            {
                // Evaluation order matters for which exception surfaces: the key is rendered before the value is converted.
                var k = ProximityCoerce.Str(r[key]);
                map.Set(k, ProximityCoerce.ToFloat(r[value]));
            }
        }

        return map;
    }

    private static PyDict Row(string key, double? benchmark, double? computed, double? diff, string status) =>
        new PyDict().Add("key", key).Add("benchmark", benchmark).Add("computed", computed).Add("diff", diff).Add("status", status);
}
