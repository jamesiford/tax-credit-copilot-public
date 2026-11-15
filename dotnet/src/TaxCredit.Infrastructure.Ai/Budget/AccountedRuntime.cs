using System.Runtime.CompilerServices;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Runtime;

namespace TaxCredit.Infrastructure.Ai.Budget;

/// <summary>Placed inside retry, this charges each physical attempt once, including cancelled or failed attempts.</summary>
public sealed class AccountedRuntime(IAgentRuntime inner, ITokenBudget budget, IAiTelemetry? telemetry = null) : RuntimeDecorator(inner)
{
    /// <inheritdoc/>
    public override async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        int input = InMemoryTokenBudget.EstimateTokens(request.Prompt);
        using var reservation = Reserve(request.Principal, input);
        ModelUsage? reported = null;
        StreamEnd? end = null;
        int chars = 0;
        try
        {
            await foreach (var item in Inner.StreamAsync(request, cancellationToken).ConfigureAwait(false))
            {
                if (item is StreamEnd terminal)
                {
                    end = terminal;
                    continue;
                }
                if (item is ModelUsage usage)
                {
                    reported = usage;
                }

                if (item is TextDelta text)
                {
                    chars = checked(chars + text.Text.Length);
                }

                yield return item;
            }
            if (reported is null)
            {
                yield return new ModelUsage(input, (chars + 3) / 4, Estimated: true);
            }
            if (end is not null)
            {
                yield return end;
            }
        }
        finally { reservation.RecordAttempt(reported ?? new ModelUsage(input, (chars + 3) / 4, Estimated: true)); }
    }
    private ITokenReservation Reserve(string principal, int input)
    {
        try { return budget.Reserve(principal, input); }
        catch (ModelException error) when (error.Kind == ModelErrorKind.BudgetExceeded)
        {
            telemetry?.Count("ai.budget_refusals", provider: Name,
                scope: error.Code == "per_user_budget" ? "per-user" : "overall");
            throw;
        }
    }
}
