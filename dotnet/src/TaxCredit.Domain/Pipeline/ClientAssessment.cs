using System.Globalization;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Domain.Pipeline;

/// <summary>What an assessment sweep produced: the claims it priced and the cells it declined by name (Python's <c>{"assessed", "declined", "years", "states"}</c>).</summary>
/// <param name="Assessed">The claims recorded for the requested years.</param>
/// <param name="Declined">One <c>{program_code, tax_year, reason, detail}</c> per declined cell.</param>
/// <param name="Years">The requested years.</param>
/// <param name="States">The work states the payroll holds, sorted.</param>
public sealed record AssessmentResult(IReadOnlyList<ProgramClaim> Assessed, IReadOnlyList<PyDict> Declined, IReadOnlyList<long> Years, IReadOnlyList<string> States);

/// <summary>
/// Assess a client's programme-years and record what the engine computes (Python <c>application/assessment.py</c>, <c>assessment_inputs.py</c>,
/// <c>assessment_claims.py</c>). Every year is calculated under its own statute [ADR-005]; nothing is overwritten (a cell past <c>assessed</c> keeps its status
/// and only its identified amount is refreshed).
/// </summary>
public sealed partial class ClientAssessment
{
    private readonly RuleLibrary _library;
    private readonly FiscalSource _fiscal;
    private readonly Func<DateOnly> _today;
    private readonly Func<PyDateTime> _clock;
    private readonly Func<string> _newClaimId;

    /// <summary>Creates the assessment.</summary>
    /// <param name="library">The rule library.</param>
    /// <param name="fiscal">The fiscal window source.</param>
    /// <param name="today">The open-year clock.</param>
    /// <param name="clock">The UTC clock of a refreshed claim.</param>
    /// <param name="newClaimId">The id source of a refreshed claim.</param>
    public ClientAssessment(RuleLibrary library, FiscalSource fiscal, Func<DateOnly> today, Func<PyDateTime> clock, Func<string> newClaimId)
    {
        _library = library;
        _fiscal = fiscal;
        _today = today;
        _clock = clock;
        _newClaimId = newClaimId;
    }

    /// <summary>Python <c>MIN_MONTHS_TO_ASSESS</c>: months of payroll a fiscal year needs before it is worth averaging over twelve.</summary>
    public const int MinMonthsToAssess = 6;

    /// <summary>Python <c>MIN_ROWS_TO_ASSESS</c>: fewer rows than this in a state-year is too thin to mean anything.</summary>
    public const int MinRowsToAssess = 50;

    /// <summary>Python <c>fiscal_years</c>: tax years present in the payroll by the pay date's own year (NOT the fiscal-year label, which differs for a non-calendar filer).</summary>
    /// <param name="rows">The payroll.</param>
    /// <returns>The years, ascending.</returns>
    public static IReadOnlyList<long> FiscalYears(IEnumerable<PayRow> rows)
    {
        var years = new SortedSet<long>();
        foreach (var row in rows)
        {
            var text = row.PayDateText();
            if (text.Length > 0)
            {
                years.Add(PyDate.FromIsoFormat(text).Year);
            }
        }

        return [.. years];
    }

    /// <summary>Python <c>assess_client</c>: run the engine over a client's payroll and record each programme-year.</summary>
    /// <param name="clientId">The client.</param>
    /// <param name="rows">The client's payroll (every year).</param>
    /// <param name="programCode">One program to assess, or <c>null</c> for every program of every state held.</param>
    /// <param name="taxYears">The years to record claims for; empty means every year the payroll covers.</param>
    /// <param name="assessedBy">The actor.</param>
    /// <param name="repository">Where claims are recorded; <c>null</c> computes without persisting.</param>
    /// <returns>What was assessed and what was declined.</returns>
    public AssessmentResult Assess(long clientId, IReadOnlyList<PayRow> rows, string? programCode, IReadOnlyList<long> taxYears, string assessedBy, IClaimSink? repository)
    {
        ArgumentNullException.ThrowIfNull(rows);
        ArgumentNullException.ThrowIfNull(taxYears);
        var requested = taxYears.Count > 0 ? taxYears.Order().ToList() : [.. FiscalYears(rows)];
        if (requested.Count == 0)
        {
            return new AssessmentResult([], [], [], []);
        }

        // Net-new is measured against the year before, so that year is an INPUT and is computed even when nobody asked for it; claims are only RECORDED for requested years.
        var years = requested.Concat(requested.Select(y => y - 1)).Distinct().Order().ToList();
        var states = PySort.Sorted(rows.Select(r => Headcount.RowState(r.Row)).Where(s => s.Length > 0).Distinct(StringComparer.Ordinal), s => s, PyStr.Comparer);
        var sweep = new Sweep(this, clientId, rows, requested, years, string.IsNullOrEmpty(programCode) ? null : PyStr.Upper(programCode));
        sweep.Run(states);
        return new AssessmentResult(AssessedCells(sweep, assessedBy, repository), sweep.Declined, requested, states);
    }

    private List<ProgramClaim> AssessedCells(Sweep sweep, string assessedBy, IClaimSink? repository)
    {
        var assessed = new List<ProgramClaim>();
        var cells = PySort.Sorted(sweep.Averages, kv => kv.Key, Comparer<(string Code, long Year)>.Create((a, b) => PyStr.Compare(a.Code, b.Code) is var c and not 0 ? c : a.Year.CompareTo(b.Year)));
        foreach (var ((code, year), average) in cells)
        {
            if (!sweep.Requested.Contains(year))
            {
                continue; // computed only to serve as the next year's base
            }

            var prior = sweep.Averages.TryGetValue((code, year - 1), out var p) ? p : (double?)null;
            if (PricedClaim(sweep.ClientId, code, year, average, prior, assessedBy) is not { } claim)
            {
                continue;
            }

            if (repository is not null)
            {
                if (repository.Current(sweep.ClientId, claim.ProgramCode, year) is { } existing && existing.Status != ClaimStatus.NotAssessed)
                {
                    claim = Refreshed(existing, claim, assessedBy);
                }

                repository.Record(claim);
            }

            assessed.Add(claim);
        }

        return assessed;
    }

    /// <summary>Python <c>priced_claim</c>: the <c>assessed</c> claim for one program-year, or <c>null</c> when the program is not registered.</summary>
    /// <remarks>
    /// A missing prior year means this is the earliest year held, so it is its own base; the old <c>0.0</c> fallback asserted nobody worked here the year before and
    /// made the entire headcount net-new.
    /// </remarks>
    private ProgramClaim? PricedClaim(long clientId, string programCode, long year, double average, double? prior, string assessedBy)
    {
        var packFile = _library.PackFileFor(programCode);
        var code = _library.ProgramForCode(programCode)?.Code;
        if (string.IsNullOrEmpty(code))
        {
            return null;
        }

        var isBase = prior is null;
        var baseAverage = prior ?? average;
        var credit = _library.ApplyOneZeroProgramCredit(code, average, baseAverage, null);
        return ProgramClaim.Create(new ClaimSpec
        {
            ClientId = clientId,
            ProgramCode = code,
            TaxYear = year,
            Status = ClaimStatus.Assessed,
            Provenance = Provenance.Computed,
            IdentifiedUsd = PyDecimal.Parse(ProximityCoerce.Str(Or(credit, "annual_credit_usd", 0L))),
            AverageHeadcount = PyRound.Round(average, 2),
            BaseAverageHeadcount = PyRound.Round(baseAverage, 2),
            ThresholdJobs = ProximityCoerce.ToFloat(Or(credit, "threshold", 0L)),
            IsBaseYear = isBase,
            AssumptionSetId = credit.TryGetValue("assumption_set_id", out var set) ? set as string : null,
            RulePackVersion = packFile ?? "None",
            DecidedBy = assessedBy,
            ClaimId = _newClaimId(),
            EffectiveFrom = _clock(),
        });
    }

    // Python `credit.get(key) or fallback`.
    private static object Or(PyDict d, string key, object fallback) => d.TryGetValue(key, out var v) && ProximityCoerce.Truthy(v) ? v! : fallback;

    /// <summary>Python <c>refreshed</c>: the cell's current decision carrying the new evidence; a recalculation is new EVIDENCE, not a new decision.</summary>
    private ProgramClaim Refreshed(ProgramClaim existing, ProgramClaim claim, string assessedBy)
    {
        var moment = _clock();
        return ProgramClaim.Create(existing.ToSpec() with
        {
            ClaimId = _newClaimId(),
            IdentifiedUsd = claim.IdentifiedUsd,
            AverageHeadcount = claim.AverageHeadcount,
            BaseAverageHeadcount = claim.BaseAverageHeadcount,
            ThresholdJobs = claim.ThresholdJobs,
            IsBaseYear = claim.IsBaseYear,
            AssumptionSetId = claim.AssumptionSetId,
            RulePackVersion = claim.RulePackVersion,
            DecidedBy = assessedBy,
            DecidedAt = moment,
            EffectiveFrom = moment,
            EffectiveTo = null,
        });
    }
}
