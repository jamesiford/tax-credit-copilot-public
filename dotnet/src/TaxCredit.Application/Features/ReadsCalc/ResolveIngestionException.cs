using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.ReadsCalc.Ingestion;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;

namespace TaxCredit.Application.Features.ReadsCalc;

/// <summary>A persisted annotation can change source-backed calculations and therefore requires a writer.</summary>
public sealed record ResolveIngestionException(ReadArguments Arguments, string Actor) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

/// <summary>Uses the shared lookup persistence boundary, distinct from Claims finding resolution.</summary>
public sealed class ResolveIngestionExceptionHandler(IServiceScopeFactory scopes) : IRequestHandler<ResolveIngestionException, object>
{
    /// <inheritdoc />
    public ValueTask<object> Handle(ResolveIngestionException request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        return ValueTask.FromResult(ReadHandlerScope.Execute<QcAnnotations>(scopes,
            annotations => annotations.Resolve(request.Arguments, request.Actor)));
    }
}
