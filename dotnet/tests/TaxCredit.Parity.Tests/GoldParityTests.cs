using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate GP (Gold projection and record tokens): replays every call of <c>parity/goldens/gold.jsonl.gz</c> (production <c>tools/gold_projection.py</c> and
/// <c>tools/tokens.py</c> on CPython 3.12) against <see cref="GoldProjection"/> and <see cref="RecordTokens"/>. Rows are compared cell by cell as typed trees
/// (a Decimal is its exact string, an int an int, a date a date), with the column list of every table, and exceptions by type plus message.
/// </summary>
[Trait("Category", "heavy")]
public sealed class GoldParityTests
{
    private const string File = "gold.jsonl.gz";

    private static readonly string[] Functions =
    [
        "_dec", "_day", "_flag", "record_token", "utc_now", "calculation_id", "employee_period_fact_rows", "employee_eligibility_rows", "onezero_matrix_rows",
        "unit_month_summary_rows", "run_method_summary_row", "unit_year_master_row", "unit_credit_installment_rows", "pipeline",
    ];

    [Fact]
    public void Every_golden_call_matches_python_bit_for_bit() =>
        ClaimGolden.AssertAllMatch(File, GoldInvoke.Invoke, Functions, minimumCalls: 8000, minimumErrors: 1000);

    [Fact]
    public void A_perturbed_output_is_detected_by_the_comparison() =>
        GoldenPerturbation.AssertDetected(File, GoldInvoke.Invoke, ["tie-order", "key-order"], take: 6000);

    [Fact]
    public void A_wrong_cell_type_value_or_scale_is_detected_in_a_table_row()
    {
        var detected = new Dictionary<string, int> { ["dec-as-str"] = 0, ["int-plus-one"] = 0, ["scale"] = 0, ["null-as-str"] = 0 };
        foreach (var call in ClaimGolden.Calls(File).Where(c => !c.ContainsKey("err") && ((string)c["fn"]!).EndsWith("_rows", StringComparison.Ordinal)).Take(1500))
        {
            foreach (var (name, change) in Changes)
            {
                var actual = GoldInvoke.Invoke(call);
                if (Rewrite(actual, change) && ClaimGolden.Compare(call["out"], actual, "$") is not null)
                {
                    detected[name]++;
                }
            }
        }

        foreach (var (name, count) in detected)
        {
            Assert.True(count > 5, $"the comparison cannot fail for '{name}' ({count} detections)");
        }
    }

    [Fact]
    public void The_golden_carries_the_python_column_lists_and_they_are_the_ones_the_port_declares()
    {
        var meta = GoldenFiles.Read(File, "meta").Single().GetProperty("columns");
        Assert.Equal(GoldColumns.All.Count, meta.EnumerateObject().Count());
        foreach (var table in meta.EnumerateObject())
        {
            var python = table.Value.EnumerateArray().Select(c => c.GetString()!).ToList();
            Assert.Equal(python, GoldColumns.All[table.Name]);
        }
    }

    [Fact]
    public void The_clock_is_a_seam_and_microseconds_are_dropped()
    {
        var read = 0;
        var at = new PyDateTime(new DateOnly(2026, 3, 1), 9, 30, 15, 999999, 0);
        var stamp = GoldProjection.UtcNow(() =>
        {
            read++;
            return at;
        });
        Assert.Equal(1, read);
        Assert.Equal("2026-03-01T09:30:15", stamp.IsoFormat());
    }

    [Fact]
    public void A_token_hides_the_employee_and_depends_on_client_programme_year_and_employee()
    {
        var token = RecordTokens.RecordToken(1001, "GA_JTC", 2023, "48685377");
        Assert.Equal(24, token.Length);
        Assert.DoesNotContain("48685377", token, StringComparison.Ordinal);
        Assert.Equal(token, RecordTokens.RecordToken(1001, "GA_JTC", 2023, "48685377"));
        Assert.NotEqual(token, RecordTokens.RecordToken(2003, "GA_JTC", 2023, "48685377"));
        Assert.NotEqual(token, RecordTokens.RecordToken(1001, "GA_JTC", 2024, "48685377"));
        Assert.NotEqual(token, RecordTokens.RecordToken(null, "GA_JTC", 2023, "48685377"));
    }

    private static readonly (string Name, Func<List<object?>, bool> Apply)[] Changes =
    [
        ("dec-as-str", cell => cell[0] is "dec" && Set(cell, 0, "str")),
        ("int-plus-one", cell => cell[0] is "int" && cell[1] is long l && Set(cell, 1, l + 1)),
        ("scale", cell => cell[0] is "dec" && cell[1] is string s && Set(cell, 1, s + "0")),
        ("null-as-str", cell => cell[0] is "null" && Set(cell, 0, "str") && Set(cell, 1, "None")),
    ];

    private static bool Set(List<object?> cell, int index, object? value)
    {
        if (index == 1 && cell.Count == 1)
        {
            cell.Add(value);
        }
        else
        {
            cell[index] = value;
        }

        return true;
    }

    /// <summary>Applies <paramref name="change"/> to the first cell it fits in the first row, so one cell differs from Python's.</summary>
    private static bool Rewrite(object? output, Func<List<object?>, bool> change)
    {
        var rows = (List<object?>)((PyDict)output!)["rows"]!;
        return rows.Count > 0 && ((List<object?>)rows[0]!).Cast<List<object?>>().Any(change);
    }
}
