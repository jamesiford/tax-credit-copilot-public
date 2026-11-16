using TaxCredit.Application.Features.ReadsCalc.Calculations;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;

namespace TaxCredit.Application.Features.ReadsCalc;

/// <summary>Explicitly requested source-backed calculation, not a read of an accepted Gold result.</summary>
public sealed record CalculateViewQuery(string Operation, ReadArguments Arguments) : IQuery<object>;

/// <summary>Composes certified deterministic tools without creating a second engine.</summary>
public sealed class CalculateViewHandler(ReadsCalculationViews views) : IRequestHandler<CalculateViewQuery, object>
{
    /// <inheritdoc />
    public ValueTask<object> Handle(CalculateViewQuery request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        return ValueTask.FromResult(views.Execute(request.Operation, request.Arguments));
    }
}

/// <summary>A reviewer annotation is a writer command even though it does not recompute the accepted run.</summary>
public sealed record ReviewOneZeroEmployee(ReadArguments Arguments) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

/// <summary>The review uses persisted lookup decisions and the same deterministic detail service as its read.</summary>
public sealed class ReviewOneZeroEmployeeHandler(ReadsCalculationViews views) : IRequestHandler<ReviewOneZeroEmployee, object>
{
    /// <inheritdoc />
    public ValueTask<object> Handle(ReviewOneZeroEmployee request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        return ValueTask.FromResult(views.Execute("POST /api/onezero/employee/{employee_id}/review", request.Arguments));
    }
}
