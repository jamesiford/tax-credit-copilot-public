using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Runs;
using TaxCredit.Domain.Warehouse;

namespace TaxCredit.Application.Hosting;

/// <summary>Non-HTTP execution reuses certified resolution, fingerprints, assessment and transactional calculation.</summary>
public sealed class RunItemExecution(ClientRunResolver resolver, IPayrollSource payroll, ClientAssessment assessment,
    IClaimSink claims, IClientCalculationRunner runner, IRunManifestRepository manifests,
    RunFingerprint fingerprints, ClientCalculationConfig config, RunIdentityScope identity,
    IPayrollFreshness? freshness = null)
{
    /// <summary>Resolves the latest runnable year only when the item did not pin one.</summary>
    public ClientRun Resolve(RunBatchItem item, RunBatch batch)
    {
        ArgumentNullException.ThrowIfNull(item);
        ArgumentNullException.ThrowIfNull(batch);
        using var fresh = freshness?.RequireFresh();
        var rows = payroll.LoadPayPeriods(item.ClientId);
        var years = item.TaxYear is { } year ? new[] { year } : ClientAssessment.FiscalYears(rows).OrderDescending().ToArray();
        foreach (var candidate in years)
        {
            try { return resolver.ResolveClientRun(item.ClientId, null, candidate, rows, item.ProgramCode ?? batch.ProgramCode); }
            catch (ClientRunNotAvailable) when (item.TaxYear is null) { }
        }
        throw new ClientRunNotAvailable("No runnable payroll year is available.");
    }

    /// <summary>Assessment-only batches do not publish Gold or claim that a calculation manifest exists.</summary>
    public ItemResult Assess(RunBatchItem item, RunBatch batch)
    {
        using var fresh = freshness?.RequireFresh();
        var rows = payroll.LoadPayPeriods(item.ClientId);
        if (rows.Count == 0) { return new ItemResult { Status = ItemStatus.SkippedNoPayroll, SkipReason = "No payroll is available." }; }
        var result = assessment.Assess(item.ClientId, rows, item.ProgramCode ?? batch.ProgramCode,
            item.TaxYear is { } year ? [year] : batch.TaxYears, batch.RequestedBy, claims);
        return new ItemResult
        {
            Status = result.Assessed.Count == 0 ? ItemStatus.SkippedNoPayroll : ItemStatus.Succeeded,
            SkipReason = result.Assessed.Count == 0 ? "No requested year could be assessed." : null,
            TaxYear = item.TaxYear,
        };
    }

    /// <summary>The unchanged rule needs known evidence on both sides; a missing field means run.</summary>
    public ItemResult Calculate(RunBatchItem item, RunBatch batch, ClientRun run, string runId)
    {
        using var fresh = freshness?.RequireFresh();
        if (!batch.Force && batch.SkipUnchanged)
        {
            var last = manifests.Latest(item.ClientId, run.ProgramCode);
            var decision = UnchangedRule.Decide(RunFingerprint.OfManifest(last),
                fingerprints.Current(run, config.Assumptions, config.CodeCommit), batch.IncludeCodeCommit);
            if (decision.Unchanged)
            {
                return new ItemResult
                {
                    Status = ItemStatus.SkippedUnchanged,
                    RunId = last!.RunId,
                    SkipReason = decision.Reason,
                    TaxYear = run.TaxYear
                };
            }
        }

        using var pinned = identity.Push(runId);
        runner.Run(new RunClientCalculationCommand(item.ClientId, run.TaxYear, ProgramCode: run.ProgramCode,
            AssessTaxYears: batch.TaxYears, Actor: batch.RequestedBy));
        return new ItemResult { Status = ItemStatus.Succeeded, RunId = runId, TaxYear = run.TaxYear };
    }
}
