using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Designations;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pilot;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Qc;

namespace TaxCredit.Application.Features.ReadsCalc.Calculations;

public sealed partial class ReadsCalculationViews
{
    private static readonly string[] LegacyDesignationSites = ["GA_ATL_HQ", "GA_SAV_DC", "GA_MAC_OPS", "GA_CUM_OPS"];

    private PyDict Qc(ReadArguments args) => QcDetector.RunExceptionReport(Dictionaries(Rows(args)), Year(args), args.Text("state"),
        PyNumber.OfFloat(args.Number("min_wages", 50)), PyNumber.OfFloat(args.Number("min_hours", 4)));

    private static PyDict Designations(ReadArguments args)
    {
        var legacy = LegacyDesignationSites
            .Select(site => KeyValuePair.Create<string, IReadOnlyList<PyDict>>(site,
            [
                Designation(2021, site == "GA_MAC_OPS" ? 2 : 1),
                Designation(2025, 1)
            ])).ToList();
        return new DesignationRegistry(legacy, [], [], () => false)
            .DetectDesignationSplits(args.Text("state", "GA")!, args.WholeNumber("tax_year", 2025));
    }

    private static PyDict Designation(long year, long tier) => Dict(("year", year), ("tier", tier),
        ("designation", tier == 1 ? "Tier 1 — Standard" : "Tier 2 — Less Developed Census Tract"), ("min_new_jobs", tier == 1 ? 2L : 10L));

    private PyDict Reconcile(ReadArguments args)
    {
        var year = Year(args);
        var rows = FiscalRows(Rows(args), year);
        var computed = new PayrollRows(library, defaults).IterStatePacks(rows, year)
            .Where(item => item.ProgramCode == defaults.ProgramCodeForState(item.State))
            .Select(item => Dict(("key", item.State), ("average_headcount", Run(item.Rows, year, item.Pack).AnnualAverage))).ToList();
        // This is the authored synthetic benchmark, not a recording of an endpoint response.
        var benchmark = new[] { ("GA", 61.0), ("NC", 24.08), ("CO", 11.33), ("NY", 10.67), ("SC", 5.12), ("VA", 3.92), ("OH", 3.34), ("FL", 2.58), ("TN", 0.83) }
            .Select(row => Dict(("key", row.Item1), ("average_headcount", row.Item2))).ToList();
        return BenchmarkReconciliation.Reconcile(benchmark, computed).Set("tax_year", year)
            .Set("benchmark_source", Dict(("_synthetic", true), ("tax_year", 2025L),
                ("note", "SYNTHETIC benchmark standing in for the partner's Access/Copilot calc output. Regenerated from the engine on 2026-08-24 after the v7 methodology convergence, so it demonstrates the reconciliation MACHINERY only and cannot detect a calculation error. The real correctness gate is backend/tests/test_engine_parity_reference.py, which runs the partner's reference dataset through the production engine and asserts the certified figures. Swap this file for the partner's per-location head counts to surface genuine discrepancies; the real run happens INSIDE the partner's environment (payroll never leaves the partner).")));
    }
}
