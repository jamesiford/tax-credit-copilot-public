using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>Shared post-processing of the matrix (Python <c>_dedupe_one_per_month</c>, <c>_build_summary</c>).</summary>
internal static class OneZeroSummary
{
    /// <summary>Enforces "no employee has more than one non-zero in any month": the LAST unit row wins; losers become int 0.</summary>
    public static List<MatrixRow> DedupeOnePerMonth(IReadOnlyList<MatrixRow> matrix)
    {
        var copy = matrix.Select(r => r.Clone()).ToList();
        var byEmployee = new OrderedDictionary<NullableKey, List<int>>();
        for (var i = 0; i < copy.Count; i++)
        {
            var key = new NullableKey(copy[i].EmployeeId);
            if (!byEmployee.TryGetValue(key, out var list))
            {
                list = [];
                byEmployee[key] = list;
            }

            list.Add(i);
        }

        foreach (var indexes in byEmployee.Values)
        {
            if (indexes.Count <= 1)
            {
                continue;
            }

            for (var m = 0; m < 12; m++)
            {
                var withValue = indexes.Where(i => Value(copy[i].Months[m]) > 0).ToList();
                if (withValue.Count > 1)
                {
                    var keeper = withValue[^1];
                    foreach (var i in withValue.Where(i => i != keeper))
                    {
                        copy[i].Months[m] = PyNumber.OfInt(0);
                    }
                }
            }
        }

        return copy;
    }

    /// <summary>Per-unit month totals, per-unit average headcount and the annual average across units.</summary>
    public static (List<UnitSummary> Summary, List<KeyValuePair<string?, double>> AveragePerUnit, double AnnualAverage) Build(IReadOnlyList<MatrixRow> matrix)
    {
        var byUnit = new OrderedDictionary<NullableKey, double[]>();
        foreach (var row in matrix)
        {
            var key = new NullableKey(row.WorksiteId);
            if (!byUnit.TryGetValue(key, out var cols))
            {
                cols = new double[12];
                byUnit[key] = cols;
            }

            for (var m = 0; m < 12; m++)
            {
                cols[m] += Value(row.Months[m]);
            }
        }

        var summary = new List<UnitSummary>();
        var averages = new List<KeyValuePair<string?, double>>();
        var units = PySort.Sorted(byUnit.Keys, k => k.Value, KeyOrder.Single);
        foreach (var unit in units)
        {
            var cols = byUnit[unit].Select(c => PyRound.Round(c, 2)).ToList();
            var total = PyRound.Round(PySum.Sum(cols), 2);
            var avg = PyRound.Round(total / 12.0, 2);
            summary.Add(new UnitSummary(unit.Value, cols, total, avg));
            averages.Add(new KeyValuePair<string?, double>(unit.Value, avg));
        }

        var annual = averages.Count == 0 ? 0.0 : PyRound.Round(PySum.Sum(averages.Select(a => a.Value).ToList()), 2);
        return (summary, averages, annual);
    }

    internal static double Value(PyNumber n) => n.IsInt ? n.IntValue : n.FloatValue;
}
