using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Triggers;

/// <summary>What <c>_aggregate</c> keeps per unit: the distinct employees and the summed hours and wages.</summary>
internal sealed class UnitSlot
{
    /// <summary>Distinct employee ids, with Python set equality (<c>1</c>, <c>1.0</c> and <c>True</c> are one member).</summary>
    public HashSet<object> Employees { get; } = [];

    /// <summary>Hours summed in row order with plain float addition.</summary>
    public double TotalHours { get; set; }

    /// <summary>Wages summed in row order with plain float addition.</summary>
    public double TotalWages { get; set; }
}

/// <summary>Python <c>triggers._aggregate</c>: group rows by <c>Worksite_ID</c>, summing hours and wages and collecting employees.</summary>
internal static class UnitAggregation
{
    /// <summary>Groups <paramref name="rows"/> by worksite, in first-seen order.</summary>
    /// <remarks>
    /// Why the order of failures matters: <c>r["Employee_ID"]</c> (KeyError) comes first, then the two <c>float()</c> conversions (ValueError, TypeError),
    /// and only then <c>len(unit)</c>, so a non-string <c>Worksite_ID</c> is a <c>TypeError</c> after the numbers were read.
    /// </remarks>
    /// <param name="rows">The rows.</param>
    /// <returns>Unit id to slot, insertion-ordered.</returns>
    public static List<(string Unit, UnitSlot Slot)> Aggregate(IEnumerable<PyDict> rows)
    {
        var order = new List<(string, UnitSlot)>();
        var index = new Dictionary<string, UnitSlot>(StringComparer.Ordinal);
        foreach (var r in rows)
        {
            var unitCell = r.TryGetValue("Worksite_ID", out var u) ? u : string.Empty;
            var keyText = unitCell as string;
            UnitSlot? slot = null;
            if (keyText is not null && !index.TryGetValue(keyText, out slot))
            {
                slot = new UnitSlot();
                index[keyText] = slot;
                order.Add((keyText, slot));
            }

            var employee = r.TryGetValue("Employee_ID", out var e) ? e : throw new PyKeyError("Employee_ID");
            var hours = ProximityCoerce.FloatOrZero(r, "Hours_Worked");
            var wages = ProximityCoerce.FloatOrZero(r, "Gross_Wages");
            if (keyText is null)
            {
                // Any non-string unit fails `len(unit)` after the numbers were read (the key tuple itself hashes fine).
                throw new PyTypeError("object of type '" + ProximityCoerce.TypeName(unitCell) + "' has no len()");
            }

            slot!.Employees.Add(SetKey(employee));
            slot.TotalHours += hours;
            slot.TotalWages += wages;
        }

        return order;
    }

    /// <summary>The member a Python set would hold for <paramref name="value"/>: bools and integral floats collapse onto the int, text stays text.</summary>
    /// <param name="value">The cell.</param>
    /// <returns>A key whose default equality is Python's.</returns>
    internal static object SetKey(object? value) => value switch
    {
        null => "\0None",
        bool b => b ? 1L : 0L,
        double d when double.IsFinite(d) && d == Math.Floor(d) && Math.Abs(d) < 9e18 => (long)d,
        PyDict or List<object?> => throw new PyTypeError("unhashable type: '" + ProximityCoerce.TypeName(value) + "'"),
        string s => "s" + s,
        _ => value,
    };
}
