using System.Globalization;
using System.Text.Json;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Warehouse;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Uses the shared atomic runner, including assessment claims and durable manifest publication.</summary>
public sealed record CalculateClientCommand(long ClientId, JsonElement? Body) : ICommand<object>, IRequirePolicy
{
    /// <summary>The retained valid-request reader.run exception is enforced at the outer access boundary.</summary>
    public Policy Policy => Policy.Open;
}

internal sealed class CalculateClientHandler(IClientCalculationRunner runner, ProgramDefaults defaults,
    TaxCredit.Application.Ports.Auth.IApiPrincipalAccessor principals) : IRequestHandler<CalculateClientCommand, object>
{
    public ValueTask<object> Handle(CalculateClientCommand request, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var body = FeatureValues.Document(request.Body);
        var command = new RunClientCalculationCommand(request.ClientId, FeatureValues.Integer(body, "year"),
            FeatureValues.Text(body, "state"), FeatureValues.Text(body, "program_code"), FeatureValues.Years(body, "assess_years"),
            FeatureValues.Actor(principals, body, "triggered_by", "system")).Validated(defaults);
        return ValueTask.FromResult<object>(runner.Run(command));
    }
}

/// <summary>Reads the same manifest destination used by synchronous and queued calculation.</summary>
public sealed record LatestClientRunQuery(long ClientId) : IQuery<object>;

internal sealed class LatestClientRunHandler(IRunManifestRepository repository, IClock clock) : IRequestHandler<LatestClientRunQuery, object>
{
    public ValueTask<object> Handle(LatestClientRunQuery request, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var manifest = repository.Latest(request.ClientId) ?? throw new DraftsRunsRefusalException(404, "This client has not been calculated yet.");
        var completed = manifest.RunCompletedAt?.IsoFormat();
        return ValueTask.FromResult<object>(new PyDict().Add("run_id", manifest.RunId).Add("client_id", manifest.ClientId)
            .Add("tax_year", manifest.TaxYear).Add("program_code", manifest.ProgramCode).Add("run_status", manifest.RunStatus)
            .Add("run_started_at", manifest.RunStartedAt.IsoFormat()).Add("run_completed_at", completed)
            .Add("calculation_id", manifest.CalculationId).Add("code_commit", manifest.CodeCommit)
            .Add("rule_pack_version", manifest.RulePackVersion).Add("triggered_by", manifest.TriggeredBy)
            .Add("fresh", completed is not null && (clock.UtcNow - DateTimeOffset.Parse(completed, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal)).TotalSeconds < 3600));
    }
}
