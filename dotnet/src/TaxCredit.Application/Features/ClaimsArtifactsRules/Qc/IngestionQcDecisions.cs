using System.Globalization;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Qc;

/// <summary>Client/year-scoped annotations for ReadsCalc ingestion; distinct from findings lifecycle and never wired into the writer.</summary>
public interface IIngestionQcDecisions
{
    /// <summary>A fresh certified resolution snapshot for an explicitly opted-in read.</summary>
    QcResolutionStore Snapshot(long clientId, long taxYear);
}

internal sealed class IngestionQcDecisions(ILookupStore store) : IIngestionQcDecisions
{
    public QcResolutionStore Snapshot(long clientId, long taxYear)
    {
        var snapshot = new QcResolutionStore();
        var year = taxYear.ToString(CultureInfo.InvariantCulture);
        foreach (var entry in store.Entries("ingestion_qc", clientId).Where(e => e.ClientId == clientId && e.KeyKind == year))
        {
            snapshot.Set(entry.Key, (PyDict)PyJson.Loads(entry.ValueJson)!);
        }
        return snapshot;
    }
}

/// <summary>Publishes a durable ingestion annotation through authorization and audit.</summary>
public sealed record ResolveIngestionQc(long ClientId, long TaxYear, string ExceptionId, string Resolution,
    string? KeepWorksite, string Actor) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

internal sealed class ResolveIngestionQcHandler(ILookupStore store, IClock clock) : IRequestHandler<ResolveIngestionQc, object>
{
    public ValueTask<object> Handle(ResolveIngestionQc request, CancellationToken cancellationToken)
    {
        if (string.IsNullOrEmpty(request.ExceptionId) || request.Resolution is not ("accept" or "assign" or "drop" or "flag")
            || request.Resolution == "assign" && string.IsNullOrEmpty(request.KeepWorksite))
        {
            throw new FeatureRefusalException(422, "A QC exception and valid resolution are required; assign also requires keep_worksite.");
        }
        var decision = new PyDict().Add("resolution", request.Resolution).Add("keep_worksite", request.KeepWorksite);
        store.Put(new LookupEntry("ingestion_qc", request.ClientId, request.TaxYear.ToString(CultureInfo.InvariantCulture),
            request.ExceptionId, PyJson.Dumps(decision), request.Actor), FeatureValues.Now(clock));
        return ValueTask.FromResult<object>(decision);
    }
}
