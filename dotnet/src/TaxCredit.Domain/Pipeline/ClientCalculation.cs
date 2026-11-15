using System.Globalization;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Designations;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Warehouse;

namespace TaxCredit.Domain.Pipeline;

/// <summary>The collaborators of <see cref="ClientCalculation"/>: every port and every ported helper module the run command reads.</summary>
/// <param name="Library">The rule library.</param>
/// <param name="Defaults">The program defaults.</param>
/// <param name="Resolver">The statute, window and payroll resolver.</param>
/// <param name="Fingerprint">The run identity.</param>
/// <param name="Designations">The designation registry (prototype data, DISC-10).</param>
/// <param name="Payroll">Where payroll comes from.</param>
/// <param name="Overrides">Saved base years.</param>
/// <param name="Assessment">The assessment the run dispatches.</param>
/// <param name="Claims">Where claims are recorded.</param>
/// <param name="Writer">Where the gold payload goes.</param>
public sealed record ClientCalculationParts(
    RuleLibrary Library,
    ProgramDefaults Defaults,
    ClientRunResolver Resolver,
    RunFingerprint Fingerprint,
    DesignationRegistry Designations,
    IPayrollSource Payroll,
    IBaseYearOverrides Overrides,
    ClientAssessment Assessment,
    IClaimSink Claims,
    IGoldWriter Writer);

/// <summary>
/// Runs the engine for one client-year and builds the payload the Gold writer receives (Python <c>application/commands/run_client_calculation.py</c>,
/// <c>handle_run_client_calculation</c>). The orchestration around it (mediator pipeline, DI) is not part of this class.
/// </summary>
/// <remarks>
/// A run covers one client-year at employee grain and the WHOLE SERIES at unit grain: a base year is inferred from the years around it and a tranche pays
/// out across the five that follow. Append-only: a rerun writes a new run id and the writer supersedes the prior rows.
/// </remarks>
public sealed partial class ClientCalculation
{
    private static readonly string[] Methods = ["min_max", "pay_period"];
    private readonly ClientCalculationParts _p;
    private readonly ClientCalculationConfig _config;

    /// <summary>Creates the pipeline.</summary>
    /// <param name="parts">The collaborators.</param>
    /// <param name="config">The injected clock, ids and settings.</param>
    public ClientCalculation(ClientCalculationParts parts, ClientCalculationConfig config)
    {
        ArgumentNullException.ThrowIfNull(parts);
        ArgumentNullException.ThrowIfNull(config);
        _p = parts;
        _config = config;
    }

    /// <summary>Python <c>handle_run_client_calculation</c>: execute the engine and persist every Gold and provenance row it implies.</summary>
    /// <param name="command">The validated command.</param>
    /// <returns>The run's result mapping, key order as Python's.</returns>
    /// <exception cref="ClientRunNotAvailable">When the client-year cannot be answered.</exception>
    /// <exception cref="GoldWriteFailed">When the writer's post-write checks fail.</exception>
    public PyDict Run(RunClientCalculationCommand command)
    {
        ArgumentNullException.ThrowIfNull(command);
        var started = GoldProjection.UtcNow(_config.UtcNow);
        var runId = _config.NewRunId();
        var run = _p.Resolver.ResolveClientRun(command.ClientId, command.State, command.TaxYear, programCode: command.ProgramCode);
        var kwargs = run.EngineKwargs();
        var engineRows = run.Rows.Select(r => r.Row).ToList();
        var results = new Dictionary<string, OneZeroResult>
        {
            ["min_max"] = MinMaxMethod.Run(engineRows, kwargs.TaxYear, kwargs.AnalysisStartMonth, kwargs.Pack, fiscalWindow: kwargs.FiscalWindow),
            ["pay_period"] = PayPeriodMethod.Run(engineRows, kwargs.TaxYear, kwargs.AnalysisStartMonth, kwargs.Pack, fiscalWindow: kwargs.FiscalWindow),
        };
        var identity = _p.Fingerprint.Identity(run, _config.Assumptions);
        var appendedAt = GoldProjection.UtcNow(_config.UtcNow);
        var manifest = BuildManifest(command, run, runId, started, identity);

        var eligibility = new List<GoldRow>();
        var matrix = new List<GoldRow>();
        var months = new List<GoldRow>();
        var summaries = new List<GoldRow>();
        System.Numerics.BigInteger client = command.ClientId;
        System.Numerics.BigInteger year = command.TaxYear;
        foreach (var method in Methods)
        {
            var result = results[method];
            eligibility.AddRange(GoldProjection.EmployeeEligibilityRows(OneZeroResultTrees.Totals(result), OneZeroResultTrees.Averages(result), client, run.ProgramCode, year, method, runId));
            matrix.AddRange(GoldProjection.OneZeroMatrixRows(OneZeroResultTrees.Matrix(result), client, run.ProgramCode, year, method, runId));
            months.AddRange(GoldProjection.UnitMonthSummaryRows(OneZeroResultTrees.Summary(result), client, year, method, runId, OneZeroCalendar.UnreachableMonths(engineRows, result.Months)));
            summaries.Add(GoldProjection.RunMethodSummaryRow(OneZeroResultTrees.Facts(result), client, run.ProgramCode, year, method, runId, result.Summary.Count, appendedAt));
        }

        var replay = ReplayUnitSeries(command.ClientId, run.State, run.ProgramCode, _p.Payroll.LoadPayPeriods(command.ClientId), runId, appendedAt);

        // The requested year's rows stay the ones computed above; the replay only fills the OTHER years, so widening the series cannot move the year somebody is looking at.
        months.AddRange(replay.Months.Where(r => NotRequested(r, command.TaxYear)));
        eligibility.AddRange(replay.Eligibility.Where(r => NotRequested(r, command.TaxYear)));
        matrix.AddRange(replay.Matrix.Where(r => NotRequested(r, command.TaxYear)));
        summaries.AddRange(replay.Summaries.Where(r => NotRequested(r, command.TaxYear)));
        var periods = GoldProjection.EmployeePeriodFactRows(run.Rows.Select(r => r.Dict), command.ClientId, run.ProgramCode, command.TaxYear, runId).ToList();
        periods.AddRange(replay.Periods.Where(r => r.Cells[1].AsInt != command.TaxYear));

        var completed = GoldProjection.UtcNow(_config.UtcNow);
        var payload = new GoldRunPayload(
            command.ClientId, run.ProgramCode, runId, completed, WarehouseVocabulary.RunManifestColumns,
            WarehouseVocabulary.RunManifestColumns.Select(c => ManifestValue(manifest, c)).ToList(),
            periods, eligibility, matrix, months, summaries, replay.Master, replay.Installments);
        var counts = _p.Writer.WriteRun(payload);

        // A claim makes the client appear on the portfolio page.
        var claim = AssessAfterRun(command, run.ProgramCode);
        var violations = _p.Writer.Validate();
        if (violations.Count > 0)
        {
            throw new GoldWriteFailed($"run {runId} violated section 9: " + string.Join("; ", violations.Select(v => $"{v.Query} ({v.RowCount.ToString(CultureInfo.InvariantCulture)} rows)")));
        }

        return Result(command, run, manifest, started, completed, counts, results, claim);
    }

    private static bool NotRequested(GoldRow row, long taxYear) =>
        !(row.Cells[1].AsInt == taxYear && Methods.Contains(row.Cells[2].AsText, StringComparer.Ordinal));

    private RunManifest BuildManifest(RunClientCalculationCommand command, ClientRun run, string runId, PyDateTime started, RunIdentity identity)
    {
        var a = _config.Assumptions;
        return new RunManifest(
            runId, command.ClientId, run.ProgramCode, command.TaxYear, run.Window.Begin, run.Window.End, started,
            // Written at the START of the run: the writer stamps completion only once every Gold row is down, so a run that dies mid-write stays visibly unfinished.
            "running",
            sourceSnapshotId: identity.SourceSnapshotId,
            step1AssumptionSetId: a.Count > 0 ? a[0].SetId : null,
            step1AssumptionSha256: a.Count > 0 ? a[0].Sha256 : null,
            onezeroAssumptionSetId: a.Count > 1 ? a[1].SetId : null,
            onezeroAssumptionSha256: a.Count > 1 ? a[1].Sha256 : null,
            rulePackVersion: identity.RulePackVersion,
            codeCommit: _config.CodeCommit,
            calculationId: identity.CalculationId,
            triggeredBy: command.Actor);
    }

    // Python `getattr(manifest, column)` for each of the manifest's columns.
    private static object? ManifestValue(RunManifest m, string column) => column switch
    {
        "run_id" => m.RunId,
        "client_id" => m.ClientId,
        "entity_id" => m.EntityId,
        "program_code" => m.ProgramCode,
        "tax_year" => m.TaxYear,
        "fiscal_year_begin" => m.FiscalYearBegin,
        "fiscal_year_end" => m.FiscalYearEnd,
        "source_snapshot_id" => m.SourceSnapshotId,
        "step1_assumption_set_id" => m.Step1AssumptionSetId,
        "step1_assumption_sha256" => m.Step1AssumptionSha256,
        "onezero_assumption_set_id" => m.OnezeroAssumptionSetId,
        "onezero_assumption_sha256" => m.OnezeroAssumptionSha256,
        "rule_pack_version" => m.RulePackVersion,
        "code_commit" => m.CodeCommit,
        "calculation_id" => m.CalculationId,
        "run_started_at" => m.RunStartedAt,
        "run_completed_at" => m.RunCompletedAt,
        "run_status" => m.RunStatus,
        "superseded_by_run_id" => m.SupersededByRunId,
        "triggered_by" => m.TriggeredBy,
        _ => throw new PyAttributeError($"'RunManifest' object has no attribute '{column}'"),
    };

    /// <summary>Python <c>handle_assess_client</c> as the run dispatches it: every payroll row of the client, claims recorded for the requested years.</summary>
    private AssessmentResult AssessAfterRun(RunClientCalculationCommand command, string programCode)
    {
        var rows = _p.Payroll.LoadPayPeriods(command.ClientId);
        if (rows.Count == 0)
        {
            throw new ClientHasNoPayroll($"No payroll for client {command.ClientId.ToString(CultureInfo.InvariantCulture)} in the active data source.");
        }

        return _p.Assessment.Assess(command.ClientId, rows, programCode, command.AssessTaxYears ?? [], command.Actor, _p.Claims);
    }

    private PyDict Result(
        RunClientCalculationCommand command, ClientRun run, RunManifest manifest, PyDateTime started, PyDateTime completed,
        IReadOnlyList<KeyValuePair<string, long>> counts, Dictionary<string, OneZeroResult> results, AssessmentResult claim)
    {
        var written = counts.Aggregate(new PyDict(), (d, kv) => d.Add(kv.Key, kv.Value));
        return new PyDict()
            .Add("run_id", manifest.RunId)
            .Add("client_id", command.ClientId)
            .Add("tax_year", command.TaxYear)
            .Add("state", run.State)
            .Add("program_code", run.ProgramCode)
            .Add("run_status", "success")
            .Add("run_started_at", started.IsoFormat() + "Z")
            .Add("run_completed_at", completed.IsoFormat() + "Z")
            .Add("calculation_id", manifest.CalculationId)
            .Add("code_commit", manifest.CodeCommit)
            .Add("rows_written", written)
            .Add("validation", new PyDict().Add("queries_run", _config.Section9QueryCount).Add("violations", new List<object?>()))
            .Add("summary", new PyDict()
                .Add("employees_evaluated", (long)results["min_max"].TotalHoursAndWages.Count)
                .Add("min_max_eligible", (long)results["min_max"].EligibleEmployees.Count)
                .Add("pay_period_eligible", (long)results["pay_period"].EligibleEmployees.Count))
            .Add("claim", new PyDict().Add("assessed", (long)claim.Assessed.Count).Add("declined", (long)claim.Declined.Count));
    }
}

/// <summary>Python <c>ClientHasNoPayroll</c> (a <c>LookupError</c>): no payroll for this client in the active data source; distinct from a missing dataset.</summary>
/// <param name="message">The reason.</param>
public sealed class ClientHasNoPayroll(string message) : PyException("ClientHasNoPayroll", message);
