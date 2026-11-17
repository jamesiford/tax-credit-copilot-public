using TaxCredit.Domain.Filters;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate DS7 (ingestion family, grid filter): replays every call of <c>parity/goldens/grid_filter.jsonl.gz</c> (production <c>tools/grid_filter.py</c>,
/// CPython 3.12) against <see cref="GridFilter"/>: the compiled SQL text, the bound parameters (int versus float, bit patterns) and the applied map.
/// </summary>
public sealed class GridFilterParityTests
{
    private const string File = "grid_filter.jsonl.gz";
    private static readonly string[] Functions = ["compile_filters", "_number", "_numeric_predicate", "_text_predicate", "_enum_predicate"];

    [Fact]
    public void Every_golden_call_matches_python_bit_for_bit() => ClaimGolden.AssertAllMatch(File, Invoke, Functions, 1500, 1);

    [Fact]
    public void A_column_off_the_whitelist_never_reaches_the_statement()
    {
        // test_grid_filter.TestWhatItRefuses: an injection attempt is just an unknown column.
        var columns = new Dictionary<string, FilterColumn> { ["weeks_worked"] = new("e.weeks_worked", "numeric") };
        var compiled = GridFilter.Compile("1=1 OR x:>=1;DROP TABLE t:~a;salary:>=100", columns);
        Assert.Equal(string.Empty, compiled.Sql);
        Assert.Empty(compiled.Values);
        Assert.Equal(0, compiled.Applied.Count);
    }

    [Fact]
    public void An_unreadable_value_is_dropped_rather_than_matching_everything()
    {
        var columns = new Dictionary<string, FilterColumn> { ["weeks_worked"] = new("e.weeks_worked", "numeric") };
        Assert.Equal(string.Empty, GridFilter.Compile("weeks_worked:banana", columns).Sql);
        Assert.Equal(" AND (e.weeks_worked >= ? AND e.weeks_worked <= ?)", GridFilter.Compile("weeks_worked:52..10", columns).Sql);
    }

    private static object? Invoke(PyDict call)
    {
        var fn = (string)call["fn"]!;
        var a = (PyDict)call["args"]!;
        return fn switch
        {
            "compile_filters" => GridFilter.Compile((string?)a["wire"], Columns(a)).ToTree(),
            "_number" => GridFilter.Number((string)a["text"]!),
            "_numeric_predicate" => Tree(GridFilter.NumericPredicate((string)a["column"]!, (string)a["expr"]!)),
            "_text_predicate" => Tree(GridFilter.TextPredicate((string)a["column"]!, (string)a["expr"]!)),
            "_enum_predicate" => Tree(GridFilter.EnumPredicate((string)a["column"]!, (string)a["expr"]!)),
            _ => throw new PyUnsupportedException("unknown function " + fn),
        };
    }

    private static Dictionary<string, FilterColumn> Columns(PyDict a)
    {
        var map = new Dictionary<string, FilterColumn>(StringComparer.Ordinal);
        foreach (var (name, spec) in (PyDict)a["columns_map"]!)
        {
            var pair = (List<object?>)spec!;
            map[name] = new FilterColumn((string)pair[0]!, (string)pair[1]!);
        }

        return map;
    }

    private static List<object?>? Tree((string Clause, object[] Params)? built) =>
        built is { } b ? [b.Clause, b.Params.Cast<object?>().ToList()] : null;
}
