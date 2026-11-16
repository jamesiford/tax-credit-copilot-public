using System.Runtime.CompilerServices;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Runtime;

namespace TaxCredit.Infrastructure.Ai.Safety;

/// <summary>Runs injection and egress admission before authentication, accounting or provider calls.</summary>
public sealed class GuardedRuntime(IAgentRuntime inner, IModelGuard egress,
    PromptInjectionGuard? injection = null, IAiTelemetry? telemetry = null) : RuntimeDecorator(inner)
{
    /// <inheritdoc/>
    public override async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var codes = injection is null ? [] : PromptInjectionGuard.Scan(request.Prompt);
        if (codes.Count != 0)
        {
            telemetry?.Count("ai.injection_blocked", provider: Name);
            throw new ModelException(ModelErrorKind.InjectionBlocked, "injection_blocked", rules: codes);
        }

        var decision = egress.Evaluate(request, Name);
        if (!decision.Allowed)
        {
            telemetry?.Count("ai.egress_refusals", provider: Name);
            throw new ModelException(ModelErrorKind.EgressRefused, "egress_refused", rules: decision.Rules);
        }

        await foreach (var item in Inner.StreamAsync(request, cancellationToken).ConfigureAwait(false))
        {
            yield return item;
        }
    }
}
