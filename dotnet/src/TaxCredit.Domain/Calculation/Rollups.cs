using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>
/// Rolling a One/Zero matrix up to a coarser grain (Python <c>domain/calculation/rollups.py</c>). Presentation of a result, not
/// part of computing one: nothing in the engine calls these. Rows are dicts (<see cref="PyDict"/>) because the Python functions
/// take any key name and any <c>months</c> list, and their behaviour on missing or mistyped cells is part of the contract.
/// </summary>
public static class Rollups
{
    private const int Months = 12;
    private const string Unattributed = "(unattributed)";

    /// <summary>Python <c>rollup_matrix_by_field</c>: <c>{field value: {month_totals, total, average_headcount}}</c>, keys in code point order.</summary>
    /// <param name="matrix">The matrix rows.</param>
    /// <param name="field">The grouping field (for example <c>Entity_FEIN</c>).</param>
    /// <returns>The roll-up.</returns>
    public static PyDict ByField(IReadOnlyList<PyDict> matrix, string field)
    {
        ArgumentNullException.ThrowIfNull(matrix);
        var byKey = new Dictionary<string, double[]>(StringComparer.Ordinal);
        foreach (var row in matrix)
        {
            Accumulate(byKey, KeyOf(row, field), row);
        }

        var result = new PyDict();
        foreach (var key in PySort.Sorted(byKey.Keys, k => k, PyStr.Comparer))
        {
            result.Add(key, Totals(byKey[key], new PyDict()));
        }

        return result;
    }

    /// <summary>
    /// Python <c>rollup_matrix_by_two_fields</c>: one dict per (field_a, field_b) pair, sorted by the pair. When the two field
    /// names collide with each other or with an output key, the later assignment wins and the first position is kept, as in a dict literal.
    /// </summary>
    /// <param name="matrix">The matrix rows.</param>
    /// <param name="fieldA">The first grouping field (for example <c>Worksite_ID</c>).</param>
    /// <param name="fieldB">The second grouping field (for example <c>Entity_FEIN</c>).</param>
    /// <returns>The sorted list of roll-up rows.</returns>
    public static List<PyDict> ByTwoFields(IReadOnlyList<PyDict> matrix, string fieldA, string fieldB)
    {
        ArgumentNullException.ThrowIfNull(matrix);
        var byKey = new Dictionary<(string, string), double[]>();
        foreach (var row in matrix)
        {
            var key = (KeyOf(row, fieldA), KeyOf(row, fieldB));
            if (!byKey.TryGetValue(key, out var cols))
            {
                cols = new double[Months];
                byKey[key] = cols;
            }

            Add(cols, row);
        }

        var order = Comparer<(string A, string B)>.Create(CompareKeys);
        var result = new List<PyDict>();
        foreach (var key in PySort.Sorted(byKey.Keys, k => k, order))
        {
            var head = new PyDict().Set(fieldA, key.Item1).Set(fieldB, key.Item2);
            result.Add(Totals(byKey[key], head));
        }

        return result;
    }

    private static int CompareKeys((string A, string B) x, (string A, string B) y)
    {
        var c = PyStr.Compare(x.A, y.A);
        return c != 0 ? c : PyStr.Compare(x.B, y.B);
    }

    private static void Accumulate(Dictionary<string, double[]> byKey, string key, PyDict row)
    {
        if (!byKey.TryGetValue(key, out var cols))
        {
            cols = new double[Months];
            byKey[key] = cols;
        }

        Add(cols, row);
    }

    // `row.get(field, "") or "(unattributed)"`: a falsy value (absent, None, "", 0, False) is unattributed. A truthy non-str key
    // would be a valid dict key in Python whose sort order against str raises; no payroll column holds one, so it is refused.
    private static string KeyOf(PyDict row, string field)
    {
        if (!row.TryGetValue(field, out var v) || !ProximityCoerce.Truthy(v))
        {
            return Unattributed;
        }

        return v as string ?? throw new PyUnsupportedException("A non-text grouping value is not modelled");
    }

    private static void Add(double[] cols, PyDict row)
    {
        for (var m = 0; m < Months; m++)
        {
            if (row["months"] is not List<object?> months)
            {
                throw new PyUnsupportedException("A months value that is not a list is not modelled");
            }

            cols[m] += m < months.Count ? Operand(months[m]) : throw new PyIndexError("list index out of range");
        }
    }

    // `float += value`: ints convert exactly (an int beyond a double is an OverflowError); None, str, list and dict are a TypeError.
    private static double Operand(object? v) => v switch
    {
        double d => d,
        long or bool or BigInteger => ProximityCoerce.ToFloat(v),
        _ => throw new PyTypeError("unsupported operand type(s) for +=: 'float' and '" + ProximityCoerce.TypeName(v) + "'"),
    };

    private static PyDict Totals(double[] sums, PyDict head)
    {
        var cols = sums.Select(c => PyRound.Round(c, 2)).ToList();
        var total = PyRound.Round(PySum.Sum(cols), 2);
        return head
            .Set("month_totals", cols.Select(c => (object?)c).ToList())
            .Set("total", total)
            .Set("average_headcount", PyRound.Round(total / 12.0, 2));
    }
}
