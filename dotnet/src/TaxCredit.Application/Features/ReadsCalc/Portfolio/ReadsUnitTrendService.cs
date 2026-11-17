using System.Globalization;
using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Designations;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Trend;

namespace TaxCredit.Application.Features.ReadsCalc.Portfolio;

/// <summary>Explicit compute request, not the Gold-backed page read.</summary>
/// <param name="State">A state or an explicitly named program's state.</param>
/// <param name="AccountId">Source client, or the fixture's default.</param>
/// <param name="Method">Certified method name.</param>
/// <param name="BaseYear">An optional base label, not a headcount override.</param>
/// <param name="ProgramCode">Explicit program for a multi-program state.</param>
public sealed record UnitTrendRequest(string State, long? AccountId = null, string Method = "min_max",
    long? BaseYear = null, string? ProgramCode = null);

/// <summary>Full multi-year compute assembly over the certified resolver and trend helpers; never used for ordinary Gold reads.</summary>
/// <param name="payroll">The selected source, loaded once per query.</param>
/// <param name="resolver">The host's program/fiscal resolver.</param>
/// <param name="library">The same rule library used by the resolver.</param>
/// <param name="designations">Client-keyed prototype designations.</param>
/// <param name="referenceData">Display-only legacy site metadata.</param>
public sealed partial class ReadsUnitTrendService(IPayrollSource payroll, ClientRunResolver resolver, RuleLibrary library,
    DesignationRegistry designations, IPortfolioReferenceData referenceData)
{
    /// <summary>Declines unsupported/thin years by name, and keeps missing unit-years absent rather than zero-filled.</summary>
    public PyDict Execute(UnitTrendRequest query)
    {
        ArgumentNullException.ThrowIfNull(query);
        PortfolioValues.ValidateMethod(query.Method);
        var state = query.State.ToUpperInvariant();
        var candidates = UnitTrendQueryHelpers.CandidateYears(library, query.ProgramCode ?? state);
        if (candidates.Count == 0)
        {
            throw new ClientRunNotAvailable("no year-scoped rule packs authored for " + state);
        }
        var rows = payroll.LoadPayPeriods(query.AccountId);
        if (rows.Count == 0)
        {
            throw new ClientRunNotAvailable("no payroll in the active data source");
        }
        var replay = Replay(query, rows, candidates);
        if (replay.Units.Count == 0)
        {
            throw new ClientRunNotAvailable("no year could be resolved: " + string.Join("; ", replay.Declined.Select(d => d["reason"])));
        }
        var units = Assemble(query, rows, replay);
        return new PyDict().Add("account_id", query.AccountId).Add("state", state).Add("program_code", replay.Program)
            .Add("method", query.Method).Add("years", PortfolioValues.List(replay.Units.Keys.Order()))
            .Add("declined_years", PortfolioValues.List(replay.Declined)).Add("units", PortfolioValues.List(units))
            .Add("year_meta", PortfolioValues.List(replay.Meta.OrderBy(p => p.Key).Select(p => p.Value)))
            .Add("totals", new PyDict().Add("units", (long)units.Count)
                .Add("annual_credit_usd", units.Aggregate(System.Numerics.BigInteger.Zero, (sum, u) => sum + PortfolioValues.Integer(u["total_annual_credit_usd"])))
                .Add("tranche_lifetime_usd", units.Aggregate(System.Numerics.BigInteger.Zero, (sum, u) => sum + PortfolioValues.Integer(u["total_tranche_lifetime_usd"]))))
            .Add("disclosures", TrendDisclosures.Build(replay.Meta, units));
    }

    private ReplayResult Replay(UnitTrendRequest query, IReadOnlyList<PayRow> rows, IReadOnlyList<long> candidates)
    {
        var replay = new ReplayResult();
        foreach (var year in candidates)
        {
            try
            {
                var run = resolver.ResolveClientRun(query.AccountId, query.State, year, rows, query.ProgramCode);
                var result = PortfolioValues.Run(run, query.Method);
                var unreachable = OneZeroCalendar.UnreachableMonths(run.Rows.Select(r => r.Row).ToList(), result.Months);
                var reachable = result.Months.Count - unreachable.Count;
                if (reachable < UnitTrendQueryHelpers.MinReachableMonths)
                {
                    replay.Declined.Add(Declined(year, $"payroll reaches {reachable.ToString(CultureInfo.InvariantCulture)} of {result.Months.Count.ToString(CultureInfo.InvariantCulture)} monthly measuring dates; a twelve-month average would be mostly zeroes"));
                    continue;
                }
                replay.Program = run.ProgramCode;
                replay.Units.Set(year, UnitTrendTools.AggregateUnits(Rollups.ByTwoFields(OneZeroResultTrees.Matrix(result), "Worksite_ID", "Entity_FEIN")));
                replay.Meta.Set(year, Metadata(run, result, unreachable));
            }
            catch (ClientRunNotAvailable error)
            {
                replay.Declined.Add(Declined(year, error.Message));
            }
        }
        return replay;
    }

    private PyDict Metadata(ClientRun run, OneZeroResult result, IReadOnlyList<long> unreachable) => new PyDict()
        .Add("tax_year", run.TaxYear).Add("fiscal", run.Window.AsDict())
        .Add("months", PortfolioValues.List(result.Months.Select(PortfolioValues.Iso)))
        .Add("unreachable_months", PortfolioValues.List(unreachable)).Add("months_reachable", (long)(result.Months.Count - unreachable.Count))
        .Add("thresholds", run.Floors.AsDict()).Add("eligible_employees", (long)result.EligibleEmployees.Count)
        .Add("annual_average", result.AnnualAverage).Add("benefit", UnitTrendQueryHelpers.YearBenefit(library, run.ProgramCode, run.TaxYear));

    private static PyDict Declined(long year, string reason) =>
        new PyDict().Add("tax_year", year.ToString(CultureInfo.InvariantCulture)).Add("reason", reason);

    private sealed class ReplayResult
    {
        internal OrderedMap<long, IReadOnlyList<PyDict>> Units { get; } = new();
        internal OrderedMap<long, PyDict> Meta { get; } = new();
        internal List<PyDict> Declined { get; } = [];
        internal string Program { get; set; } = "";
    }
}
