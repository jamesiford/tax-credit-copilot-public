using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Claims;

/// <summary>The derived readings of a claim: variance, outcome, exposure, opportunity, proximity to the threshold and the priority band.</summary>
public sealed partial record ProgramClaim
{
    /// <summary>Within this many jobs of the statutory minimum, either side, is "on the line" (Python <c>ON_THE_LINE_JOBS</c>).</summary>
    public const double OnTheLineJobs = 1.0;

    /// <summary>
    /// Python <c>variance_usd</c>: <c>identified - claimed</c>, signed on purpose (positive is money left on the table, negative is
    /// money claimed that cannot be substantiated); the subtraction is rounded to 28 digits like any <c>Decimal</c> operation.
    /// </summary>
    public PyDecimal VarianceUsd => PyDecimalOps.Subtract(IdentifiedUsd, ClaimedUsd);

    /// <summary>Python <c>variance_is_computable</c>: false where <c>identified</c> is not a finding about the client (a base year).</summary>
    public bool VarianceIsComputable => !IsBaseYear;

    /// <summary>Python <c>outcome</c>: how this cell reads.</summary>
    public Outcome Outcome
    {
        get
        {
            if (Status == ClaimStatus.NotAssessed)
            {
                return Outcome.NotAssessed;
            }

            // Before any comparison: a base year has nothing to compare against, and over-claimed would be an invented finding.
            if (IsBaseYear)
            {
                return Outcome.BaseYear;
            }

            var variance = VarianceUsd;
            if (!Status.IsClaimed())
            {
                return PyDecimalOps.Compare(IdentifiedUsd, ClaimMoney.Materiality) <= 0 ? Outcome.CorrectlyNotClaimed : Outcome.Unclaimed;
            }

            if (PyDecimalOps.Compare(PyDecimalOps.Abs(variance), ClaimMoney.Materiality) <= 0)
            {
                return Outcome.Confirmed;
            }

            return PyDecimalOps.Compare(variance, PyDecimalOps.Zero) > 0 ? Outcome.UnderClaimed : Outcome.OverClaimed;
        }
    }

    /// <summary>Python <c>is_exposure</c>: claimed more than we can substantiate, or certified below what was claimed.</summary>
    public bool IsExposure
    {
        get
        {
            if (IsBaseYear)
            {
                return false;
            }

            if (Outcome == Outcome.OverClaimed)
            {
                return true;
            }

            return Status == ClaimStatus.Certified
                && PyDecimalOps.Compare(PyDecimalOps.Subtract(ClaimedUsd, CertifiedUsd), ClaimMoney.Materiality) > 0;
        }
    }

    /// <summary>
    /// Python <c>opportunity_usd</c>: recoverable dollars only, never negative. <c>max(Decimal("0"), variance)</c> keeps the FIRST
    /// operand on a tie, so a zero variance reads <c>0</c> whatever its exponent (<c>0.00</c> becomes <c>0</c>).
    /// </summary>
    public PyDecimal OpportunityUsd => IsBaseYear
        ? PyDecimalOps.Zero
        : (PyDecimalOps.Compare(VarianceUsd, PyDecimalOps.Zero) > 0 ? VarianceUsd : PyDecimalOps.Zero);

    /// <summary>Python <c>net_new_jobs</c>: qualifying jobs above the frozen base, or <c>null</c> if not assessed.</summary>
    public double? NetNewJobs
    {
        get
        {
            if (AverageHeadcount is not { } average || BaseAverageHeadcount is not { } baseline)
            {
                return null;
            }

            // max(0.0, x) is x only when x > 0.0; NaN and -0.0 fall back to the literal 0.0.
            var delta = average - baseline;
            return PyRound.Round(delta > 0.0 ? delta : 0.0, 2);
        }
    }

    /// <summary>Python <c>jobs_to_threshold</c>: jobs still needed to cross the minimum; <c>0.0</c> means already over, <c>null</c> means unknown.</summary>
    public double? JobsToThreshold
    {
        get
        {
            if (NetNewJobs is not { } netNew || ThresholdJobs is not { } threshold)
            {
                return null;
            }

            var gap = threshold - netNew;
            return PyRound.Round(gap > 0.0 ? gap : 0.0, 2);
        }
    }

    /// <summary>
    /// Python <c>jobs_margin</c>: signed distance from the minimum (negative is short). Unlike <see cref="JobsToThreshold"/> it is
    /// not clamped at zero, which is what makes "about to lose eligibility" computable. May be <c>-0.0</c> after rounding.
    /// </summary>
    public double? JobsMargin
    {
        get
        {
            if (NetNewJobs is not { } netNew || ThresholdJobs is not { } threshold)
            {
                return null;
            }

            return PyRound.Round(netNew - threshold, 2);
        }
    }

    /// <summary>Python <c>near_threshold</c>: short of the minimum, but by less than one whole job.</summary>
    public bool NearThreshold => JobsToThreshold is { } gap && gap > 0 && gap <= 1.0;

    /// <summary>
    /// Python <c>priority_band</c>: why you would call about this cell. The order of the tests is the decision.
    /// <b>A band is never derived from an unverified claim</b>: exposure needs a verified filing, and where the claimed side is
    /// unverified only <c>identified_usd</c>, the one number we computed, decides whether something is outstanding.
    /// </summary>
    public PriorityBand PriorityBand
    {
        get
        {
            if (IsBaseYear)
            {
                return PriorityBand.Settled;
            }

            if (Status == ClaimStatus.NotAssessed)
            {
                return PriorityBand.NotAssessed;
            }

            if (IsExposure && Provenance.Verified())
            {
                return PriorityBand.Exposed;
            }

            if (JobsMargin is { } margin && Math.Abs(margin) <= OnTheLineJobs)
            {
                return PriorityBand.OnTheLine;
            }

            var outstanding = Provenance.Verified() ? OpportunityUsd : IdentifiedUsd;
            return PyDecimalOps.Compare(outstanding, ClaimMoney.Materiality) > 0 ? PriorityBand.UnclaimedAtScale : PriorityBand.Settled;
        }
    }
}
