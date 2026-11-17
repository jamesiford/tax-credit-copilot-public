using System.Diagnostics;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Application.Pipeline;

/// <summary>Who may run a command (Python <c>application/authorization.py</c> <c>Policy</c>).</summary>
public enum Policy
{
    /// <summary>Anyone may run it; a deliberate, named decision rather than an omission.</summary>
    Open,

    /// <summary>The person must be entitled to write.</summary>
    Writer,
}

/// <summary>Implemented by a request that declares who may run it.</summary>
public interface IRequirePolicy
{
    /// <summary>The policy the pipeline enforces.</summary>
    Policy Policy { get; }
}

/// <summary>Implemented by a request that can validate itself.</summary>
public interface IValidatable
{
    /// <summary>Returns the validation failures; empty when valid.</summary>
    IReadOnlyList<string> Validate();
}

/// <summary>Port: decides whether the current person is entitled to a policy.</summary>
public interface IAuthorizer
{
    /// <summary>True when the person may run requests under <paramref name="policy"/>.</summary>
    /// <param name="policy">The policy.</param>
    /// <returns>Whether the person is entitled.</returns>
    bool IsEntitled(Policy policy);
}

/// <summary>Port: the bounded in-memory audit trail (the durable trail lives in the operational store).</summary>
public interface IAuditLog
{
    /// <summary>Records the outcome of a request, including failures and refusals.</summary>
    /// <param name="record">The entry.</param>
    void Record(AuditRecord record);
}

/// <summary>One audit entry.</summary>
/// <param name="Request">The request type name.</param>
/// <param name="Outcome">One of <c>ok</c>, <c>refused</c>, <c>invalid</c>, <c>error</c>.</param>
/// <param name="Elapsed">Time spent in the handler.</param>
public sealed record AuditRecord(string Request, string Outcome, TimeSpan Elapsed);

/// <summary>Raised when the person is not entitled to run a command.</summary>
/// <param name="message">Detail.</param>
public sealed class RefusedException(string message) : Exception(message);

/// <summary>Raised when a request fails validation.</summary>
/// <param name="failures">The failures.</param>
public sealed class ValidationFailedException(IReadOnlyList<string> failures) : Exception("Validation failed: " + string.Join("; ", failures))
{
    /// <summary>The individual failures.</summary>
    public IReadOnlyList<string> Failures { get; } = failures;
}

/// <summary>
/// Stage 1: Authorization. A request that declares a policy on a pipeline with no authorizer is refused, not waved
/// through (Python ADR-008). There is deliberately no TenantScope stage: with no employer binding it would run and
/// always pass, which reads as a control.
/// </summary>
/// <typeparam name="TRequest">The request type.</typeparam>
/// <typeparam name="TResponse">The response type.</typeparam>
/// <param name="authorizer">The authorizer, or null when none is configured.</param>
public sealed class AuthorizationBehavior<TRequest, TResponse>(IAuthorizer? authorizer = null) : IPipelineBehavior<TRequest, TResponse>
    where TRequest : IRequest<TResponse>
{
    /// <inheritdoc />
    public ValueTask<TResponse> Handle(TRequest request, RequestHandlerDelegate<TResponse> next, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(next);
        if (request is IRequirePolicy { Policy: not Policy.Open } required && (authorizer is null || !authorizer.IsEntitled(required.Policy)))
        {
            throw new RefusedException($"{typeof(TRequest).Name} requires policy {required.Policy}");
        }

        return next();
    }
}

/// <summary>Stage 2: Validation.</summary>
/// <typeparam name="TRequest">The request type.</typeparam>
/// <typeparam name="TResponse">The response type.</typeparam>
public sealed class ValidationBehavior<TRequest, TResponse> : IPipelineBehavior<TRequest, TResponse>
    where TRequest : IRequest<TResponse>
{
    /// <inheritdoc />
    public ValueTask<TResponse> Handle(TRequest request, RequestHandlerDelegate<TResponse> next, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(next);
        if (request is IValidatable validatable)
        {
            var failures = validatable.Validate();
            if (failures.Count > 0)
            {
                throw new ValidationFailedException(failures);
            }
        }

        return next();
    }
}

/// <summary>Stage 4: Audit and timing. Records failed writes too, because "somebody tried and it errored" is a real question.</summary>
/// <typeparam name="TRequest">The request type.</typeparam>
/// <typeparam name="TResponse">The response type.</typeparam>
/// <param name="audit">The audit log.</param>
public sealed class AuditBehavior<TRequest, TResponse>(IAuditLog audit) : IPipelineBehavior<TRequest, TResponse>
    where TRequest : IRequest<TResponse>
{
    /// <inheritdoc />
    public async ValueTask<TResponse> Handle(TRequest request, RequestHandlerDelegate<TResponse> next, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(next);
        var watch = Stopwatch.StartNew();
        var name = typeof(TRequest).Name;
        try
        {
            var response = await next().ConfigureAwait(false);
            audit.Record(new AuditRecord(name, "ok", watch.Elapsed));
            return response;
        }
        catch (RefusedException)
        {
            audit.Record(new AuditRecord(name, "refused", watch.Elapsed));
            throw;
        }
        catch (ValidationFailedException)
        {
            audit.Record(new AuditRecord(name, "invalid", watch.Elapsed));
            throw;
        }
#pragma warning disable CA1031 // Any failure is audited, then rethrown unchanged.
        catch (Exception)
        {
            audit.Record(new AuditRecord(name, "error", watch.Elapsed));
            throw;
        }
#pragma warning restore CA1031
    }
}
