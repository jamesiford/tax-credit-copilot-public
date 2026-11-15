using System.Security.Cryptography;
using System.Text;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Runs;
using TaxCredit.Domain.Warehouse;

namespace TaxCredit.Domain.Pipeline;

/// <summary>An active assumption set with the content hash of its file (Python <c>{"set_id", "sha256"}</c>); the label alone would not catch an edited set.</summary>
/// <param name="SetId">The set's <c>assumption_set_id</c>, or its file stem.</param>
/// <param name="Sha256">The SHA-256 of the file's bytes, lowercase hex.</param>
public sealed record AssumptionIdentity(string SetId, string Sha256);

/// <summary>The manifest values every run derives from its inputs (Python <c>RunIdentity</c>).</summary>
/// <param name="CalculationId">The digest of one year's payroll and everything that decides its answer.</param>
/// <param name="RulePackVersion">The pack path the floors came from.</param>
/// <param name="SourceSnapshotId">A digest of ALL the client's payroll inside any authored year's window; <c>null</c> when nothing is authored.</param>
public sealed record RunIdentity(string CalculationId, string RulePackVersion, string? SourceSnapshotId = null);

/// <summary>
/// The identity of a client-year run: what decides its answer, as the manifest records it (Python <c>application/runs/fingerprint.py</c>, ADR-012). One
/// derivation, used by the run command when it stamps a manifest and by the orchestrator when it asks "would this run produce the same thing?".
/// </summary>
/// <param name="library">The rule library.</param>
/// <param name="fiscal">The fiscal window source.</param>
public sealed class RunFingerprint(RuleLibrary library, FiscalSource fiscal)
{
    private static readonly string[] RowFields =
        ["Employee_ID", "Worksite_ID", "Entity_FEIN", "Pay_Period_Start", "Pay_Period_End", "Pay_Date", "Hours_Worked", "Gross_Wages", "Pay_Code"];

    /// <summary>
    /// Python <c>client_data_fingerprint</c>: a digest of the client's payroll rows paid inside any authored year's window, independent of row order;
    /// <c>null</c> when there are no windows to judge by ("cannot tell", never a digest of nothing).
    /// </summary>
    /// <param name="stateRows">The client's payroll in the state.</param>
    /// <param name="windows"><c>(begin, end)</c> ISO date text per authored year.</param>
    /// <returns>64 lowercase hex digits, or <c>null</c>.</returns>
    public static string? ClientDataFingerprint(IEnumerable<PayRow> stateRows, IReadOnlyList<(string Begin, string End)> windows)
    {
        ArgumentNullException.ThrowIfNull(stateRows);
        ArgumentNullException.ThrowIfNull(windows);
        if (windows.Count == 0)
        {
            return null;
        }

        var lines = new List<string>();
        foreach (var row in stateRows)
        {
            var paid = row.PayDateText();
            if (windows.Any(w => PyStr.Compare(w.Begin, paid) <= 0 && PyStr.Compare(paid, w.End) <= 0))
            {
                lines.Add(string.Join('\0', RowFields.Select(f => Shown(row.Get(f)))));
            }
        }

        var sorted = PySort.Sorted(lines, l => l, PyStr.Comparer);
        return Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join('\n', sorted))));
    }

    /// <summary>Python <c>authored_windows</c>: <c>(begin, end)</c> ISO dates of each authored year's fiscal window for this client, where one resolves.</summary>
    /// <param name="accountId">The client.</param>
    /// <param name="programCode">The program.</param>
    /// <returns>The windows, ascending by year.</returns>
    public IReadOnlyList<(string Begin, string End)> AuthoredWindows(long? accountId, string programCode)
    {
        var output = new List<(string, string)>();
        if (!library.CodeToPack.TryGet(programCode, out var packFile))
        {
            return output;
        }

        foreach (var year in library.AuthoredYears(packFile))
        {
            if (fiscal.FiscalWindowForStateYear(accountId, programCode, year) is { } window)
            {
                output.Add((GoldProjection.IsoFormat(window.Begin), GoldProjection.IsoFormat(window.End)));
            }
        }

        return output;
    }

    /// <summary>Python <c>run_identity</c>: the calculation id and rule pack version for a resolved client run.</summary>
    /// <param name="run">The run.</param>
    /// <param name="assumptions">The active assumption sets.</param>
    /// <returns>The identity.</returns>
    public RunIdentity Identity(ClientRun run, IReadOnlyList<AssumptionIdentity> assumptions)
    {
        ArgumentNullException.ThrowIfNull(run);
        ArgumentNullException.ThrowIfNull(assumptions);
        var floors = run.Floors.AsDict();
        var calculationId = GoldProjection.CalculationId(
            run.AccountId, run.ProgramCode, run.TaxYear, run.Window.Begin, run.Window.End, floors,
            assumptions.Select(a => (object?)a.SetId).ToList(), run.Rows.Select(r => r.Dict));
        var source = floors.TryGetValue("source", out var s) && ProximityCoerce.Truthy(s) ? ProximityCoerce.Str(s) : string.Empty;
        return new RunIdentity(calculationId, source, ClientDataFingerprint(run.StateRows, AuthoredWindows(run.AccountId, run.ProgramCode)));
    }

    /// <summary>Python <c>current_fingerprint</c>: what a run started now would record, without running the engine.</summary>
    /// <param name="run">The run.</param>
    /// <param name="assumptions">The active assumption sets.</param>
    /// <param name="codeCommit">The commit.</param>
    /// <returns>The fingerprint.</returns>
    public Fingerprint Current(ClientRun run, IReadOnlyList<AssumptionIdentity> assumptions, string codeCommit)
    {
        var identity = Identity(run, assumptions);
        return new Fingerprint
        {
            CalculationId = identity.CalculationId,
            Step1AssumptionSha256 = assumptions.Count > 0 ? assumptions[0].Sha256 : null,
            OnezeroAssumptionSha256 = assumptions.Count > 1 ? assumptions[1].Sha256 : null,
            RulePackVersion = Blank(identity.RulePackVersion),
            CodeCommit = Blank(codeCommit),
            TaxYear = run.TaxYear,
            SourceSnapshotId = identity.SourceSnapshotId,
        };
    }

    /// <summary>Python <c>manifest_fingerprint</c>: the fingerprint recorded on a manifest (every empty value reads as unknown), or <c>null</c> when there is no earlier run.</summary>
    /// <param name="manifest">The manifest or <c>null</c>.</param>
    /// <returns>The fingerprint or <c>null</c>.</returns>
    public static Fingerprint? OfManifest(RunManifest? manifest) => manifest is null
        ? null
        : new Fingerprint
        {
            CalculationId = Blank(manifest.CalculationId),
            Step1AssumptionSha256 = Blank(manifest.Step1AssumptionSha256),
            OnezeroAssumptionSha256 = Blank(manifest.OnezeroAssumptionSha256),
            RulePackVersion = Blank(manifest.RulePackVersion),
            CodeCommit = Blank(manifest.CodeCommit),
            TaxYear = manifest.TaxYear,
            SourceSnapshotId = Blank(manifest.SourceSnapshotId),
        };

    // Python `x or None` over text: the empty string is as unknown as None.
    private static string? Blank(string? text) => string.IsNullOrEmpty(text) ? null : text;

    // Python `str(row.get(field) or "")`.
    private static string Shown(object? value) => ProximityCoerce.Truthy(value) ? ProximityCoerce.Str(value) : string.Empty;
}
