using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// The projection against <c>docs/data/schema/tcc-schema.fabric.sql</c>: the column lists are the DDL's, and what Python (and so the port) puts in each
/// cell can be stored in the column the DDL declares. Where the two disagree the Python is ported and the disagreement is pinned here as a finding.
/// </summary>
[Trait("Category", "heavy")]
public sealed class GoldDdlTests
{
    [Fact]
    public void The_column_lists_are_the_ddls_in_name_and_order_for_all_seven_tables()
    {
        var ddl = GoldDdl.Parse();
        foreach (var (table, columns) in GoldColumns.All)
        {
            Assert.True(ddl.ContainsKey(table), table + " is not in the DDL");
            Assert.Equal(ddl[table].Select(c => c.Name), columns);
        }
    }

    [Fact]
    public void The_cells_the_projection_builds_fit_the_ddl_except_where_a_finding_says_otherwise()
    {
        var ddl = GoldDdl.Parse();
        var found = new SortedDictionary<string, int>(StringComparer.Ordinal);
        var checkedCells = 0;
        foreach (var call in ClaimGolden.Calls("gold.jsonl.gz").Where(c => !c.ContainsKey("err") && (c["fn"] is "pipeline" || IsSeries(c))))
        {
            var tables = call["fn"] is "pipeline" ? GoldInvoke.PipelineRows(call) : Single(GoldInvoke.RowsOf(call));
            foreach (var (table, rows) in tables)
            {
                foreach (var row in rows)
                {
                    for (var i = 0; i < row.Cells.Count; i++)
                    {
                        checkedCells++;
                        foreach (var why in GoldDdl.Violations(ddl[table][i], row.Cells[i]))
                        {
                            var key = $"{table}.{row.Columns[i]}: {why}";
                            found[key] = found.GetValueOrDefault(key) + 1;
                        }
                    }
                }
            }
        }

        Assert.True(checkedCells > 1_000_000, $"only {checkedCells} cells were checked");
        Assert.Equal(Expected, found.Select(kv => $"{kv.Key} x{kv.Value}").ToList());
    }


    [Fact]
    public void A_null_can_reach_a_not_null_column_only_through_the_inputs_named_in_the_findings()
    {
        var ddl = GoldDdl.Parse();
        var found = new SortedSet<string>(StringComparer.Ordinal);
        foreach (var call in ClaimGolden.Calls("gold.jsonl.gz").Where(c => !c.ContainsKey("err") && ((string)c["fn"]!).EndsWith("_rows", StringComparison.Ordinal) || c["fn"] is "run_method_summary_row" or "unit_year_master_row"))
        {
            if (call.ContainsKey("err"))
            {
                continue;
            }

            var (table, rows) = GoldInvoke.RowsOf(call);
            foreach (var row in rows)
            {
                for (var i = 0; i < row.Cells.Count; i++)
                {
                    if (row.Cells[i].Kind == GoldKind.Null && !ddl[table][i].Nullable)
                    {
                        found.Add($"{table}.{row.Columns[i]}");
                    }
                }
            }
        }

        Assert.True(ExpectedNulls.SequenceEqual(found), "NOT NULL columns that received NULL: " + string.Join(", ", found));
    }

    /// <summary>NOT NULL columns Python can write NULL into when the input is missing or empty (finding GP-02): <c>_dec(None)</c> and <c>_day(None)</c> are NULL and nothing guards the column.</summary>
    private static readonly string[] ExpectedNulls =
    [
        "employee_eligibility.weight", "employee_period_fact.pay_period_end", "employee_period_fact.pay_period_start", "onezero_matrix.month_01",
        "run_method_summary.annual_average", "unit_credit_installment.claimable_usd", "unit_credit_installment.jobs_maintained", "unit_credit_installment.per_job_usd",
        "unit_credit_installment.tax_year", "unit_credit_installment.tranche_jobs", "unit_month_summary.month_01", "unit_month_summary.month_02",
        "unit_month_summary.month_03", "unit_month_summary.month_04", "unit_month_summary.month_05", "unit_month_summary.month_06", "unit_month_summary.month_07",
        "unit_month_summary.month_08", "unit_month_summary.month_09", "unit_month_summary.month_10", "unit_month_summary.month_11", "unit_month_summary.month_12",
    ];

    /// <summary>The DDL violations found over the pipeline and the realistic credit series; see findings GP-02 to GP-05.</summary>
    private static readonly string[] Expected = [];

    private static Dictionary<string, IReadOnlyList<GoldRow>> Single((string Table, IReadOnlyList<GoldRow> Rows) built) => new() { [built.Table] = built.Rows };

    private static bool IsSeries(PyDict c) => c.TryGetValue("args", out var a) && a is PyDict d && d.ContainsKey("series");
}
