using System.Globalization;
using System.Text.Json;
using TaxCredit.Application.Hosting;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Runs;
using TaxCredit.Domain.Warehouse;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Records append-only human intent and queues its recalculation on the existing durable work path.</summary>
public sealed record SetBaseYearCommand(long ClientId, string UnitId, JsonElement? Body) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

internal sealed class SetBaseYearHandler(IGoldReadPort gold, IManualOverrideRepository overrides, ProgramDefaults defaults,
    IRunBatchRepository queue, IRunManifestRepository manifests, IClock clock, IIdSource ids, IApiPrincipalAccessor principals,
    RunWorkGate gate, RunWorkExecutor executor, IRuntimeConfiguration configuration) : IRequestHandler<SetBaseYearCommand, object>
{
    public ValueTask<object> Handle(SetBaseYearCommand request, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var body = FeatureValues.Document(request.Body);
        long? chosen = body.TryGetValue("base_year", out var raw) && raw is not null ? FeatureValues.Integer(body, "base_year") : null;
        var state = FeatureValues.Text(body, "state");
        var program = FeatureValues.Text(body, "program_code");
        defaults.CheckProgramState(state, program);
        state = defaults.LocationState(request.ClientId, request.UnitId, state, program);
        (_, program) = defaults.ResolveProgram(request.ClientId, state, program, null);
        if (program is null) { throw new PyValueError("No program maps to the location's state."); }
        using var scope = gold.Scope();
        var run = gold.LatestRun(request.ClientId) ?? throw new PyValueError("This client has no calculated run to change.");
        var rows = UnitSeries.Load(gold, request.ClientId, request.UnitId, "min_max", program);
        if (rows.Count == 0) { throw new PyValueError("The run holds no such location."); }
        if (chosen is { } year && (!rows.TryGetValue(year, out var row) || !UnitSeries.Complete(row) || UnitSeries.Open(row)))
        {
            throw new PyValueError("The base must be a complete, closed year held by this location's run.");
        }
        var saved = overrides.BaseYears(request.ClientId, program).TryGetValue(request.UnitId, out var value) ? value : (long?)null;
        if (chosen == saved) { return ValueTask.FromResult<object>(new PyDict().Add("recorded", false).Add("reason", "unchanged").Add("base_year", saved).Add("recalculation", "not_needed")); }
        var actor = FeatureValues.Actor(principals, body, "triggered_by", "system");
        var at = FeatureValues.Now(clock);
        var before = (saved ?? UnitSeries.Inferred(rows)).ToString(CultureInfo.InvariantCulture);
        var adjustment = new ManualOverride(ids.NewId().ToString("N"), (string)run["run_id"]!, request.ClientId, "unit",
            WarehouseVocabulary.BaseYearKey(program, request.UnitId), "base_year", before, chosen?.ToString(CultureInfo.InvariantCulture),
            chosen is null ? "base_year_cleared" : "base_year_set", FeatureValues.Text(body, "justification"), actor,
            PyDateTime.FromIsoFormat(at.IsoFormat().Replace("+00:00", "", StringComparison.Ordinal)));
        overrides.Record(adjustment);
        var taxYear = manifests.Latest(request.ClientId)?.TaxYear ?? rows.Keys.Max();
        var batchId = ids.NewId().ToString("N");
        var batch = new RunBatch
        {
            BatchId = batchId,
            Kind = BatchKind.Calculate,
            ScopeKind = ScopeKind.One,
            ScopeSpec = new PyDict().Add("client_ids", new List<object?> { request.ClientId }).Add("reason", "base_year_override"),
            ProgramCode = program,
            TaxYears = [taxYear],
            Force = true,
            RequestedBy = actor,
            RequestedAt = at
        };
        queue.Create(batch, [new RunBatchItem { ItemId = ids.NewId().ToString("N"), BatchId = batchId, Seq = 0,
            ClientId = request.ClientId, ProgramCode = program, TaxYear = taxYear }]);
        if (configuration.Get("CONTRACT_HOOKS") == "1")
        {
            gate.Defer(async token => { _ = await executor.Drain(token).ConfigureAwait(false); });
        }
        return ValueTask.FromResult<object>(new PyDict().Add("recorded", true).Add("override_id", adjustment.OverrideId)
            .Add("worksite_id", request.UnitId).Add("base_year", chosen).Add("replaced", before).Add("recalculation", "started")
            .Add("durable", overrides.IsDurable).Add("note", chosen is null
                ? "Cleared. The client is being recalculated with the run choosing its own base."
                : "Saved. The client is being recalculated from the chosen base; the grid updates when the new run lands. The previous run stays in Gold as history."));
    }
}
