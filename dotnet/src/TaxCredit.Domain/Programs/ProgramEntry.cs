using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>Mirrors Python <c>RegistryError</c> (a <c>ValueError</c> subclass): the manifest or an entry in it cannot be used; the message names the file, the entry and the field.</summary>
/// <param name="message">What cannot be used and why.</param>
public sealed class RegistryError(string message) : PyException("RegistryError", message);

/// <summary>The program registry's vocabulary (Python module constants in <c>domain/programs.py</c>). [ADR-013]</summary>
public static class ProgramVocabulary
{
    /// <summary>Credit models the engine prices today: headcount delta over the base year times a flat per-job amount (Python <c>SUPPORTED_CREDIT_MODELS</c>).</summary>
    public static IReadOnlyList<string> SupportedCreditModels { get; } = ["per_net_new_job"];

    /// <summary>Headcount models: the One/Zero pay-period and min-max methods (Python <c>SUPPORTED_HEADCOUNT_MODELS</c>).</summary>
    public static IReadOnlyList<string> SupportedHeadcountModels { get; } = ["one_zero"];

    /// <summary>
    /// What a person may type (Python <c>STORED_LIFECYCLES</c>). <c>calculable</c> is deliberately absent: it is derived from
    /// authored year packs, because a typed "calculable" is a claim nothing checks. [ADR-005]
    /// </summary>
    public static IReadOnlyList<string> StoredLifecycles { get; } = ["draft", "described", "retired"];

    /// <summary>Jurisdiction levels (Python <c>JURISDICTION_LEVELS</c>).</summary>
    public static IReadOnlyList<string> JurisdictionLevels { get; } = ["federal", "state", "local"];
}

/// <summary>Which supported models a program uses (Python <c>EngineProfile</c>, a frozen dataclass).</summary>
public sealed record EngineProfile
{
    /// <summary>The credit model (default <c>per_net_new_job</c>).</summary>
    public string CreditModel { get; init; } = "per_net_new_job";

    /// <summary>The headcount model (default <c>one_zero</c>).</summary>
    public string HeadcountModel { get; init; } = "one_zero";
}

/// <summary>One program in the registry (Python <c>ProgramEntry</c>, a frozen dataclass). <see cref="Lifecycle"/> is the stored ceiling; see <see cref="Status"/> for the effective one.</summary>
public sealed record ProgramEntry
{
    /// <summary>The program code.</summary>
    public required string Code { get; init; }

    /// <summary>The display name.</summary>
    public required string Name { get; init; }

    /// <summary>The jurisdiction level.</summary>
    public required string Level { get; init; }

    /// <summary>The jurisdiction code.</summary>
    public required string JurisdictionCode { get; init; }

    /// <summary>The rule-pack file name.</summary>
    public required string PackFile { get; init; }

    /// <summary>The state, <c>null</c> for a federal program.</summary>
    public string? State { get; init; }

    /// <summary>The stored lifecycle (default <c>described</c>).</summary>
    public string Lifecycle { get; init; } = "described";

    /// <summary>The engine profile (default: the one supported pair).</summary>
    public EngineProfile EngineProfile { get; init; } = new();

    /// <summary>Free-text notes.</summary>
    public string Notes { get; init; } = string.Empty;

    /// <summary>
    /// Python <c>status(authored_years)</c>: <c>retired</c> and <c>draft</c> stand; otherwise <c>calculable</c> exactly when a year
    /// pack is authored, else <c>described</c>. Any other stored text (even <c>calculable</c>) falls through to the derived answer.
    /// </summary>
    /// <param name="authoredYears">The authored years; <c>null</c> and empty are both "none" (Python truthiness).</param>
    /// <returns>The effective status.</returns>
    public string Status(IReadOnlyCollection<long>? authoredYears)
    {
        if (Lifecycle is "retired" or "draft")
        {
            return Lifecycle;
        }

        return authoredYears is { Count: > 0 } ? "calculable" : "described";
    }
}
