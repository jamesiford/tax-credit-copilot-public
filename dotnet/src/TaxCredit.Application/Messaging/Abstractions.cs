namespace TaxCredit.Application.Messaging;

/// <summary>A request that produces <typeparamref name="TResponse"/>; the common base of commands and queries.</summary>
/// <typeparam name="TResponse">The response type.</typeparam>
public interface IRequest<out TResponse>;

/// <summary>A write. Every write lands on a number on a filed return, so it passes the full pipeline.</summary>
/// <typeparam name="TResponse">The response type.</typeparam>
public interface ICommand<out TResponse> : IRequest<TResponse>;

/// <summary>A read. Reads answer from stored results and never run the engine (see the Python "A read READS" rule).</summary>
/// <typeparam name="TResponse">The response type.</typeparam>
public interface IQuery<out TResponse> : IRequest<TResponse>;

/// <summary>Handles exactly one request type: one use case per class.</summary>
/// <typeparam name="TRequest">The request type.</typeparam>
/// <typeparam name="TResponse">The response type.</typeparam>
public interface IRequestHandler<in TRequest, TResponse>
    where TRequest : IRequest<TResponse>
{
    /// <summary>Handles the request.</summary>
    /// <param name="request">The request.</param>
    /// <param name="cancellationToken">Cancellation.</param>
    /// <returns>The response.</returns>
    ValueTask<TResponse> Handle(TRequest request, CancellationToken cancellationToken);
}

/// <summary>Delegate to the next stage of the pipeline.</summary>
/// <typeparam name="TResponse">The response type.</typeparam>
/// <returns>The response.</returns>
public delegate ValueTask<TResponse> RequestHandlerDelegate<TResponse>();

/// <summary>A cross-cutting stage wrapped around every handler (authorization, validation, audit, timing).</summary>
/// <typeparam name="TRequest">The request type.</typeparam>
/// <typeparam name="TResponse">The response type.</typeparam>
public interface IPipelineBehavior<in TRequest, TResponse>
    where TRequest : IRequest<TResponse>
{
    /// <summary>Runs the stage, calling <paramref name="next"/> to continue.</summary>
    /// <param name="request">The request.</param>
    /// <param name="next">The next stage.</param>
    /// <param name="cancellationToken">Cancellation.</param>
    /// <returns>The response.</returns>
    ValueTask<TResponse> Handle(TRequest request, RequestHandlerDelegate<TResponse> next, CancellationToken cancellationToken);
}

/// <summary>Dispatches a request through the pipeline to its handler.</summary>
public interface IMediator
{
    /// <summary>Sends a request.</summary>
    /// <typeparam name="TResponse">The response type.</typeparam>
    /// <param name="request">The request.</param>
    /// <param name="cancellationToken">Cancellation.</param>
    /// <returns>The response.</returns>
    ValueTask<TResponse> Send<TResponse>(IRequest<TResponse> request, CancellationToken cancellationToken = default);
}
