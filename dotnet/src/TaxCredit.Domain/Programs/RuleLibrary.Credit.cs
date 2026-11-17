using System.Numerics;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

public sealed partial class RuleLibrary
{
    /// <summary>Python <c>program_credit.credit_key</c>: the key a credit is priced by, the named program else the state (its default program).</summary>
    /// <param name="programCode">The program code, or <c>null</c>.</param>
    /// <param name="state">The state.</param>
    /// <returns>The key.</returns>
    public static string CreditKey(string? programCode, string state) => string.IsNullOrEmpty(programCode) ? state : programCode;

    /// <summary>Python <c>program_credit.state_of</c>: the state a program code is priced in, or the upper-cased state itself when given one.</summary>
    /// <param name="programOrState">A program code or a state.</param>
    /// <returns>The state.</returns>
    public string StateOf(string programOrState) => Resolve(programOrState).State;

    /// <summary>Python <c>program_credit.program_per_job_usd</c>: [O3] the statutory dollars per qualifying job; 0.0 for a pct-of-wages program or an unregistered key.</summary>
    /// <param name="programOrState">A program code or a state.</param>
    /// <returns>The amount.</returns>
    public double ProgramPerJobUsd(string programOrState)
    {
        var packFile = Resolve(programOrState).PackFile;
        if (packFile is null)
        {
            return 0.0;
        }

        var benefit = RuleTree.Get(LoadPack(packFile), "benefit", new PyDict());
        var amount = RuleTree.Get(RuleTree.AsMapping(benefit), "amount_per_qualifying_job_usd");
        return RuleTree.Truthy(amount) ? RuleTree.Float(amount) : 0.0;
    }

    /// <summary>Python <c>credit_math.state_per_job_usd</c>: [O3] UX-06, the state-named form of <see cref="ProgramPerJobUsd"/>.</summary>
    /// <param name="state">A state or a program code.</param>
    /// <returns>The amount.</returns>
    public double StatePerJobUsd(string state) => ProgramPerJobUsd(state);

    /// <summary>Python <c>credit_math.apply_one_zero_state_credit</c> with a prior period of 0.0: the state-named wrapper of <see cref="ApplyOneZeroProgramCredit(string, object?)"/>.</summary>
    /// <param name="state">A state or a program code.</param>
    /// <param name="averageHeadcount">The average headcount (anything Python <c>float()</c> accepts).</param>
    /// <returns>The credit tree.</returns>
    public PyDict ApplyOneZeroStateCredit(string state, object? averageHeadcount) =>
        ApplyOneZeroProgramCredit(state, averageHeadcount, 0.0, null);

    /// <summary>Python <c>credit_math.apply_one_zero_state_credit</c>: prices a state's DEFAULT program, or a program when given its code. [F04c.4]</summary>
    /// <param name="state">A state or a program code.</param>
    /// <param name="averageHeadcount">The average headcount.</param>
    /// <param name="priorPeriodAverageHeadcount">The prior period's average headcount.</param>
    /// <param name="thresholdOverride">A NEGOTIATED threshold replacing the statutory one ([L4] CALC-10), or <c>null</c>.</param>
    /// <returns>The credit tree.</returns>
    public PyDict ApplyOneZeroStateCredit(string state, object? averageHeadcount, object? priorPeriodAverageHeadcount, object? thresholdOverride) =>
        ApplyOneZeroProgramCredit(state, averageHeadcount, priorPeriodAverageHeadcount, thresholdOverride);

    /// <summary>Python <c>program_credit.apply_one_zero_program_credit</c> with a prior period of 0.0.</summary>
    /// <param name="programOrState">A program code or a state.</param>
    /// <param name="averageHeadcount">The average headcount.</param>
    /// <returns>The credit tree.</returns>
    public PyDict ApplyOneZeroProgramCredit(string programOrState, object? averageHeadcount) =>
        ApplyOneZeroProgramCredit(programOrState, averageHeadcount, 0.0, null);

    /// <summary>
    /// Python <c>program_credit.apply_one_zero_program_credit</c>: a rule pack's benefit math over an already-computed One/Zero Average Headcount.
    /// Net-new qualifying jobs are the year-over-year delta minus the statutory threshold. An unregistered key returns the structured
    /// <c>no_state_pack</c> answer.
    /// </summary>
    /// <param name="programOrState">A program code or a state.</param>
    /// <param name="averageHeadcount">The average headcount.</param>
    /// <param name="priorPeriodAverageHeadcount">The prior period's average headcount.</param>
    /// <param name="thresholdOverride">A negotiated threshold replacing the statutory one, or <c>null</c>.</param>
    /// <returns>The credit tree.</returns>
    public PyDict ApplyOneZeroProgramCredit(string programOrState, object? averageHeadcount, object? priorPeriodAverageHeadcount, object? thresholdOverride)
    {
        var (key, packFile, state) = Resolve(programOrState);
        return packFile is null
            ? NoStatePackResult(state)
            : CreditFromPack(LoadPack(packFile), (key, state, packFile), averageHeadcount, priorPeriodAverageHeadcount, thresholdOverride);
    }

    /// <summary>
    /// Python <c>program_credit.credit_from_pack</c>: the benefit step over a pack document already in hand; <paramref name="names"/> is
    /// <c>(key, state, pack file)</c>. The one body behind the rules-folder path and the portal's draft preview, so a preview prices with the engine's own formula.
    /// </summary>
    /// <param name="pack">The pack document.</param>
    /// <param name="names">The key, the state and the pack file name.</param>
    /// <param name="averageHeadcount">The average headcount.</param>
    /// <param name="priorPeriodAverageHeadcount">The prior period's average headcount.</param>
    /// <param name="thresholdOverride">A negotiated threshold, or <c>null</c>.</param>
    /// <returns>The credit tree.</returns>
    public PyDict CreditFromPack(PyDict pack, (string Key, string State, string PackFile) names, object? averageHeadcount, object? priorPeriodAverageHeadcount, object? thresholdOverride)
    {
        ArgumentNullException.ThrowIfNull(pack);
        var average = RuleTree.Float(averageHeadcount);
        var prior = RuleTree.Float(priorPeriodAverageHeadcount);
        var threshold = thresholdOverride is not null
            ? RuleTree.Float(thresholdOverride)
            : RuleTree.Float(RuleTree.Sub(RuleTree.Sub(pack, "thresholds"), "minimum_new_jobs"));
        var years = ProximityCoerce.ToInt(RuleTree.Sub(RuleTree.Sub(pack, "benefit"), "benefit_period_years"));
        // max(0.0, x) keeps its first operand unless x is strictly greater, so a NaN delta reads 0.0; round(x, 2) is banker's on the exact binary value.
        var qualifying = PyRound.Round(PyArith.Max(0.0, PyArith.Max(0.0, average - prior) - threshold), 2);
        var (perJob, annual) = BenefitAmounts(RuleTree.Sub(pack, "benefit"), qualifying, names.Key, names.PackFile);
        var lifetime = RuleTree.Int(RuleTree.Big(annual) * RuleTree.Big(years));
        RecordStep(pack, average, prior, threshold, (qualifying, annual, lifetime));
        return Result(pack, names.State, (average, prior, threshold, qualifying), (perJob, annual, years));
    }

    /// <summary>
    /// Python <c>program_credit.combine_program_entity_credits</c>: [I2] CALC-06, the credit for a program that PROHIBITS entity combination.
    /// Each legal entity (FEIN) is its own taxpayer: the threshold applies to each entity's Average Headcount independently and the credits are summed.
    /// </summary>
    /// <param name="programOrState">A program code or a state.</param>
    /// <param name="feinBreakdown">Entity code to an aggregate holding <c>average_headcount</c>.</param>
    /// <returns>The per-FEIN breakdown and the combined totals.</returns>
    public PyDict CombineProgramEntityCredits(string programOrState, PyDict feinBreakdown)
    {
        ArgumentNullException.ThrowIfNull(feinBreakdown);
        var perFein = new PyDict();
        double sumAnnual = 0.0, sumLifetime = 0.0, sumQualifying = 0.0;
        foreach (var (code, agg) in feinBreakdown)
        {
            var credit = ApplyOneZeroProgramCredit(programOrState, RuleTree.Sub(agg, "average_headcount"));
            perFein.Set(code, new PyDict()
                .Add("average_headcount", RuleTree.Sub(agg, "average_headcount"))
                .Add("qualifying_jobs", credit["qualifying_jobs"])
                .Add("annual_credit_usd", credit["annual_credit_usd"])
                .Add("lifetime_credit_usd", credit["lifetime_credit_usd"]));
            // float += int converts the int to a double (OverflowError beyond 1.8e308), so the sums are floats, as in Python.
            sumAnnual += RuleTree.Float(credit["annual_credit_usd"]);
            sumLifetime += RuleTree.Float(credit["lifetime_credit_usd"]);
            sumQualifying += RuleTree.Float(credit["qualifying_jobs"]);
        }

        return new PyDict()
            .Add("per_fein", perFein)
            .Add("combined_annual_credit_usd", RuleTree.RoundInt(sumAnnual))
            .Add("combined_lifetime_credit_usd", RuleTree.RoundInt(sumLifetime))
            .Add("combined_qualifying_jobs", PyRound.Round(sumQualifying, 2));
    }

    /// <summary>Python <c>credit_math.combine_entity_credits</c>: [I2] CALC-06, the state-named wrapper of <see cref="CombineProgramEntityCredits"/>.</summary>
    /// <param name="state">A state or a program code.</param>
    /// <param name="feinBreakdown">Entity code to an aggregate holding <c>average_headcount</c>.</param>
    /// <returns>The per-FEIN breakdown and the combined totals.</returns>
    public PyDict CombineEntityCredits(string state, PyDict feinBreakdown) => CombineProgramEntityCredits(state, feinBreakdown);

    private (string Key, string? PackFile, string State) Resolve(string key)
    {
        var keyUpper = PyStr.Upper(key);
        var entry = ProgramForCode(keyUpper);
        return (keyUpper, PackFileFor(keyUpper), entry is { State.Length: > 0 } ? entry.State! : keyUpper);
    }

    // `(per job, annual credit)` for whichever benefit shape the pack declares.
    private (object PerJob, object Annual) BenefitAmounts(object? benefitRaw, double qualifying, string key, string packFile)
    {
        var benefit = benefitRaw as PyDict ?? throw new PyUnsupportedException("a benefit that is not an object is not modelled");
        object perJob;
        if (benefit.ContainsKey("amount_per_qualifying_job_usd"))
        {
            perJob = RuleTree.Float(benefit["amount_per_qualifying_job_usd"]);
        }
        else if (benefit.ContainsKey("amount_per_qualifying_job_pct_of_wages"))
        {
            var wage = AverageWage(key);
            perJob = RuleTree.RoundInt(wage * RuleTree.Float(benefit["amount_per_qualifying_job_pct_of_wages"]));
        }
        else
        {
            throw new PyValueError($"pack {packFile} has no recognized benefit shape");
        }

        return (perJob, RuleTree.RoundInt(qualifying * RuleTree.Float(perJob)));
    }

    private double AverageWage(string key) =>
        (_wages ?? throw new PyUnsupportedException("no payroll wage source is configured for a percentage-of-wages benefit")).AverageProgramWage(key);
}
