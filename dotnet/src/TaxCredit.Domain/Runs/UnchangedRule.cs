namespace TaxCredit.Domain.Runs;

/// <summary>Everything that decides a client-year's answer, as the manifest records it; <c>null</c> means unknown (Python <c>Fingerprint</c>, a frozen dataclass).</summary>
public sealed record Fingerprint
{
    /// <summary>Digest of ONE year's payroll.</summary>
    public string? CalculationId { get; init; }

    /// <summary>The step 1 assumption set hash.</summary>
    public string? Step1AssumptionSha256 { get; init; }

    /// <summary>The One/Zero assumption set hash.</summary>
    public string? OnezeroAssumptionSha256 { get; init; }

    /// <summary>The rule pack version that priced the run.</summary>
    public string? RulePackVersion { get; init; }

    /// <summary>The code commit that produced the run.</summary>
    public string? CodeCommit { get; init; }

    /// <summary>The tax year of the run.</summary>
    public long? TaxYear { get; init; }

    /// <summary>A digest of ALL the client's authored-year payroll (<c>application/runs/fingerprint.py</c>). [F04b.1]</summary>
    public string? SourceSnapshotId { get; init; }
}

/// <summary>The "unchanged" rule (Python <c>unchanged_decision</c>): a conclusion that needs evidence, where absence of evidence means run.</summary>
public static class UnchangedRule
{
    /// <summary>
    /// Python <c>unchanged_decision</c>: <c>(unchanged, reason)</c>, true only when every compared value is known on both sides and equal.
    /// Known means truthy in Python, so an empty string is as unknown as <c>null</c>; the first failing comparison, in the order of the
    /// pairs, names the reason.
    /// </summary>
    /// <param name="last">The last successful run's fingerprint, or <c>null</c> for none.</param>
    /// <param name="current">The fingerprint of the run that would happen now.</param>
    /// <param name="includeCodeCommit">Whether a changed code commit counts as a change.</param>
    /// <returns>The verdict and its reason text.</returns>
    public static (bool Unchanged, string Reason) Decide(Fingerprint? last, Fingerprint current, bool includeCodeCommit = false)
    {
        ArgumentNullException.ThrowIfNull(current);
        if (last is null)
        {
            return (false, "no earlier successful run for this client and programme");
        }

        if (last.TaxYear != current.TaxYear)
        {
            return (false, $"the latest run was for TY{Show(last.TaxYear)}, not TY{Show(current.TaxYear)}: cannot tell, so run");
        }

        foreach (var (name, before, now) in Pairs(last, current, includeCodeCommit))
        {
            if (string.IsNullOrEmpty(before) || string.IsNullOrEmpty(now))
            {
                return (false, $"{name} is not recorded on one side: cannot tell, so run");
            }

            if (!string.Equals(before, now, StringComparison.Ordinal))
            {
                return (false, $"{name} changed");
            }
        }

        return (true, "calculation fingerprint, assumption hashes and rule pack are identical to the last run");
    }

    // f"TY{x}" prints None for an unknown year.
    private static string Show(long? year) => year is null ? "None" : year.Value.ToString(System.Globalization.CultureInfo.InvariantCulture);

    // The order is the contract: it decides which reason a fingerprint that differs in several ways reports.
    private static List<(string Name, string? Before, string? Now)> Pairs(Fingerprint last, Fingerprint current, bool includeCodeCommit)
    {
        var pairs = new List<(string, string?, string?)>
        {
            ("client-wide data fingerprint", last.SourceSnapshotId, current.SourceSnapshotId),
            ("calculation fingerprint", last.CalculationId, current.CalculationId),
            ("step 1 assumption hash", last.Step1AssumptionSha256, current.Step1AssumptionSha256),
            ("one/zero assumption hash", last.OnezeroAssumptionSha256, current.OnezeroAssumptionSha256),
            ("rule pack version", last.RulePackVersion, current.RulePackVersion),
        };
        if (includeCodeCommit)
        {
            pairs.Add(("code commit", last.CodeCommit, current.CodeCommit));
        }

        return pairs;
    }
}
