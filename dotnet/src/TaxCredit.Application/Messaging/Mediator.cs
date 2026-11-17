using System.Collections.Concurrent;
using Microsoft.Extensions.DependencyInjection;

namespace TaxCredit.Application.Messaging;

/// <summary>
/// The in-house mediator (see ADR 0003): resolves the handler and the pipeline behaviours from the container and
/// composes them so the first registered behaviour runs outermost. About a screenful of code, no licence exposure.
/// </summary>
/// <param name="services">The container used to resolve handlers and behaviours.</param>
public sealed class Mediator(IServiceProvider services) : IMediator
{
    private static readonly ConcurrentDictionary<Type, object> Invokers = new();

    /// <inheritdoc />
    public ValueTask<TResponse> Send<TResponse>(IRequest<TResponse> request, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(request);
        var invoker = (RequestInvoker<TResponse>)Invokers.GetOrAdd(request.GetType(), static requestType =>
            Activator.CreateInstance(typeof(RequestInvoker<,>).MakeGenericType(requestType, typeof(TResponse)))!);
        return invoker.Invoke(request, services, cancellationToken);
    }

    private abstract class RequestInvoker<TResponse>
    {
        public abstract ValueTask<TResponse> Invoke(IRequest<TResponse> request, IServiceProvider provider, CancellationToken cancellationToken);
    }

    private sealed class RequestInvoker<TRequest, TResponse> : RequestInvoker<TResponse>
        where TRequest : IRequest<TResponse>
    {
        public override ValueTask<TResponse> Invoke(IRequest<TResponse> request, IServiceProvider provider, CancellationToken cancellationToken)
        {
            var typed = (TRequest)request;
            var handler = provider.GetRequiredService<IRequestHandler<TRequest, TResponse>>();
            RequestHandlerDelegate<TResponse> next = () => handler.Handle(typed, cancellationToken);
            foreach (var behavior in provider.GetServices<IPipelineBehavior<TRequest, TResponse>>().Reverse())
            {
                var inner = next;
                var current = behavior;
                next = () => current.Handle(typed, inner, cancellationToken);
            }

            return next();
        }
    }
}
