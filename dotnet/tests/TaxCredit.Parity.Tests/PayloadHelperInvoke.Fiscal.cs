using System.Globalization;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Runs;
using TaxCredit.Domain.Warehouse;

namespace TaxCredit.Parity.Tests;

internal static partial class PayloadHelperInvoke
{
    private static readonly FiscalSource AssumedWindows = new(World.Library, new NoFiscalRules());
    private static readonly ClientRunResolver Resolver = new(World.Library, Defaults, AssumedWindows, World.Csv);
    private static readonly RunFingerprint Fingerprints = new(World.Library, AssumedWindows);

    private static object? Fiscal(PyDict call, PyDict a) => (string)call["fn"]! switch
    {
        "client_fiscal_window" => AssumedWindows.ClientFiscalWindow(MaybeLong(a["account_id"]), (long)a["tax_year"]!, (string)a["convention"]!).AsDict(),
        "fiscal_window_for_state_year" => AssumedWindows.FiscalWindowForStateYear(MaybeLong(a["account_id"]), (string)a["state"]!, (long)a["tax_year"]!)?.AsDict(),
        "window_for_state_year" => Span(AssumedWindows.WindowForStateYear(MaybeLong(a["account_id"]), (string)a["state"]!, (long)a["tax_year"]!)),
        "_window_from_rule" => WindowFromRule(a),
        "client_fiscal_window_rules" => WithRules(a),
        "resolve_statute" => StatuteTree(Resolver.ResolveStatute(MaybeLong(a["account_id"]), (string?)a["state"], (long)a["tax_year"]!, (string?)a["program_code"], (bool)a["require_program"]!)),
        "resolve_client_run" => RunTree(Resolver.ResolveClientRun(MaybeLong(a["account_id"]), (string?)a["state"], (long)a["tax_year"]!, null, (string?)a["program_code"], (bool)a["require_program"]!)),
        "resolve_client_run_rows" => RunTree(Resolver.ResolveClientRun(1001, "GA", (long)a["tax_year"]!, RowsOf((string)a["rows"]!), null, ((string)a["rows"]!) != "csv:0")),
        "run_identity" => Identity(a),
        "client_data_fingerprint" => RunFingerprint.ClientDataFingerprint(RowsOf((string)a["rows"]!), Windows(a["windows"])),
        "authored_windows" => Fingerprints.AuthoredWindows(MaybeLong(a["account_id"]), (string)a["program_code"]!).Select(w => (object?)new List<object?> { w.Begin, w.End }).ToList(),
        "manifest_fingerprint" => Manifest(a),
        _ => throw new PyUnsupportedException("unknown function " + call["fn"]),
    };

    private static List<object?>? Span((DateOnly Begin, DateOnly End)? window) =>
        window is { } w ? [Tag(w.Begin), Tag(w.End)] : null;

    private static PyDict Tag(DateOnly d) => new PyDict().Add("$date", d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture));

    private static List<(string, string)> Windows(object? v) => ((List<object?>)v!).Cast<List<object?>>().Select(w => ((string)w[0]!, (string)w[1]!)).ToList();

    private static PyDict? WindowFromRule(PyDict a) =>
        FiscalSource.WindowFromRule(new FiscalRule((string?)a["name"], (string?)a["rule_expression"], a["begin"], a["end"]), 7, (long)a["tax_year"]!, (string)a["convention"]!)?.AsDict();

    private static PyDict WithRules(PyDict a)
    {
        var good = new FiscalRule("override:y", "E", new DateOnly(2023, 7, 1), new DateOnly(2024, 6, 30));
        IReadOnlyList<FiscalRule>? stored = (string)a["rules"]! switch
        {
            "none" => null,
            "empty" => [],
            "first-unusable" => [new FiscalRule("x", null, null, null), good],
            _ => [new FiscalRule("EntityFiscalYearRules", "J", new DateOnly(2023, 7, 1), new DateOnly(2024, 6, 30))],
        };
        return new FiscalSource(World.Library, new StoredRules(stored)).ClientFiscalWindow(MaybeLong(a["account_id"]), (long)a["tax_year"]!, (string)a["convention"]!).AsDict();
    }

    private static PyDict StatuteTree(ResolvedStatute s) => new PyDict()
        .Add("account_id", s.AccountId).Add("state", s.State).Add("program_code", s.ProgramCode).Add("tax_year", s.TaxYear)
        .Add("floors", s.Floors.AsDict()).Add("pack", PackTree(s.Pack)).Add("window", s.Window.AsDict());

    private static PyDict RunTree(ClientRun r)
    {
        var engine = r.EngineKwargs();
        var tree = StatuteTree(r.Statute);
        return tree.Add("n_rows", (long)r.Rows.Count).Add("n_state_rows", (long)r.StateRows.Count).Add("rows_digest", RowDigest(r.Rows)).Add("state_rows_digest", RowDigest(r.StateRows))
            .Add("engine", new PyDict().Add("tax_year", engine.TaxYear).Add("analysis_start_month", Tag(engine.AnalysisStartMonth)).Add("fiscal_window", Span(engine.FiscalWindow)));
    }

    private static PyDict Identity(PyDict a)
    {
        var run = Resolver.ResolveClientRun(1001, "GA", (long)a["tax_year"]!, RowsOf((string)a["rows"]!));
        var identity = Fingerprints.Identity(run, World.Assumptions);
        var fields = new PyDict().Add("calculation_id", identity.CalculationId).Add("rule_pack_version", identity.RulePackVersion).Add("source_snapshot_id", identity.SourceSnapshotId);
        return new PyDict().Add("identity", fields).Add("fingerprint", FingerprintTree(Fingerprints.Current(run, World.Assumptions, "c0ffee")));
    }

    private static PyDict? FingerprintTree(Fingerprint? f) => f is null
        ? null
        : new PyDict().Add("calculation_id", f.CalculationId).Add("step1_assumption_sha256", f.Step1AssumptionSha256).Add("onezero_assumption_sha256", f.OnezeroAssumptionSha256)
            .Add("rule_pack_version", f.RulePackVersion).Add("code_commit", f.CodeCommit).Add("tax_year", f.TaxYear).Add("source_snapshot_id", f.SourceSnapshotId);

    private static PyDict? Manifest(PyDict a)
    {
        var begin = new DateOnly(2024, 1, 1);
        var end = new DateOnly(2024, 12, 31);
        var started = new PyDateTime(new DateOnly(2026, 1, 1), 0, 0, 0, 0, null);
        return (string?)a["manifest"] switch
        {
            null => FingerprintTree(RunFingerprint.OfManifest(null)),
            "full" => FingerprintTree(RunFingerprint.OfManifest(new RunManifest(
                "r", 1, "GA_JTC", 2024, begin, end, started, "success", sourceSnapshotId: "snap", step1AssumptionSha256: "s1", onezeroAssumptionSha256: string.Empty,
                rulePackVersion: "v", codeCommit: "abc", calculationId: "calc"))),
            _ => FingerprintTree(RunFingerprint.OfManifest(new RunManifest("r", 1, "GA_JTC", 2020, begin, end, started, "success", onezeroAssumptionSha256: "x", calculationId: string.Empty, rulePackVersion: string.Empty))),
        };
    }

    private sealed class StoredRules(IReadOnlyList<FiscalRule>? rules) : IFiscalRuleSource
    {
        public bool HoldsClientRules => true;

        public IReadOnlyList<FiscalRule>? RulesWithOverrides(long accountId) => rules;
    }
}
