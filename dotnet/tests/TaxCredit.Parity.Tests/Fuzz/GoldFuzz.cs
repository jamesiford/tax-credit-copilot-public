using System.Numerics;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Differential fuzz of <c>tools/gold_projection.py</c> and <c>tools/tokens.py</c>: every row builder over payroll, totals, averages, matrix and summary
/// rows whose cells are edge-pool values (ties at the cent, 28-digit decimals, NaN, non-strings), absent or None, plus the credit-layer rows
/// and the calculation id. Outputs compare as typed cells.
/// </summary>
internal sealed class GoldFuzz : FuzzFamily
{
    private static readonly string[] Programs = ["GA_JTC", "NC_JTEC", "SC_JTC", string.Empty, "ga\u00e9", "a\0b", "XX"];

    public override string Name => "gold_projection";

    public override IReadOnlyList<string> Functions { get; } =
    [
        "_dec", "_day", "_flag", "record_token", "calculation_id", "employee_period_fact_rows", "employee_eligibility_rows", "onezero_matrix_rows",
        "unit_month_summary_rows", "run_method_summary_row", "unit_year_master_row", "unit_credit_installment_rows",
    ];

    public override Func<PyDict, string?> CreateChecker() => call => Replay(call, GoldInvoke.Invoke);

    public override FamilyCase Generate(Rng r, string id)
    {
        var fn = r.Pick(Functions);
        var args = new PyDict();
        switch (fn)
        {
            case "_dec":
                args.Add("value", GoldPools.Dec(r)).Add("places", r.Chance(0.5) ? 2L : 4L);
                break;
            case "_day":
                args.Add("value", GoldPools.Day(r));
                break;
            case "_flag":
                args.Add("value", GoldPools.Flag(r));
                break;
            case "record_token":
                args.Add("account_id", r.Pick(new object?[] { null, 0L, 1L, 1001L, 2000L, -1L, BigInteger.Pow(10, 20), BigInteger.Pow(2, 63), -BigInteger.Pow(2, 63) - 1 }))
                    .Add("program_code", r.Pick(Programs)).Add("tax_year", r.Pick(new object[] { 2023L, 0L, -1L, BigInteger.Pow(10, 20) })).Add("employee_id", GoldPools.EmployeeId(r));
                break;
            case "calculation_id":
                args = GoldTables.CalculationId(r);
                break;
            case "unit_year_master_row":
                args = GoldCredit.MasterRow(r);
                break;
            case "unit_credit_installment_rows":
                args = GoldCredit.Installments(r);
                break;
            case "run_method_summary_row":
                args = GoldCredit.RunSummary(r, Common(r, withProgram: true));
                break;
            default:
                args = GoldTables.Table(r, fn, Common(r, withProgram: fn != "unit_month_summary_rows"));
                break;
        }

        return new FamilyCase(id, fn, args);
    }

    private static PyDict Common(Rng r, bool withProgram)
    {
        var d = new PyDict().Add("client_id", r.Pick(new object[] { 1001L, 1001L, 1002L, 2000L, 2003L }));
        if (withProgram)
        {
            d.Add("program_code", r.Pick(Programs));
        }

        d.Add("tax_year", r.Pick(new object[] { 2023L, 2024L, 2019L, 2020L, 2026L }));
        d.Add("method", r.Pick(new[] { "min_max", "pay_period", string.Empty, "m\u00e9thode" }));
        return d.Add("run_id", r.Pick(new[] { "R1", "R-\u00e9", "R9", string.Empty }));
    }
}
