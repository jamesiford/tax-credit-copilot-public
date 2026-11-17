using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Budget;

/// <summary>Reservations close the Python check/record race without pretending estimates cap a provider bill.</summary>
public sealed class InMemoryTokenBudget : ITokenBudget
{
    private readonly Lock _sync = new();
    private readonly long? _globalLimit;
    private readonly long? _userLimit;
    private readonly TimeProvider _clock;
    private readonly Dictionary<string, long> _used = new(StringComparer.Ordinal);
    private readonly Dictionary<string, long> _reserved = new(StringComparer.Ordinal);
    private DateOnly _day;
    private long _globalUsed;
    private long _globalReserved;
    private int _generation;
    /// <summary>Null limits disable ceilings; zero admits only zero-token estimates.</summary>
    public InMemoryTokenBudget(long? globalDaily = null, long? principalDaily = null, TimeProvider? clock = null)
    {
        if (globalDaily < 0 || principalDaily < 0)
        {
            throw new ModelException(ModelErrorKind.Configuration, "negative_budget");
        }

        _globalLimit = globalDaily;
        _userLimit = principalDaily;
        _clock = clock ?? TimeProvider.System;
        _day = Today();
    }
    /// <summary>Four characters per token, rounded up for nonempty text.</summary>
    public static int EstimateTokens(string text) => (int)Math.Min(int.MaxValue, ((long)text.Length + 3) / 4);
    /// <inheritdoc/>
    public ITokenReservation Reserve(string principal, int estimatedTokens)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(estimatedTokens);

        lock (_sync)
        {
            Roll();
            if (_globalLimit is { } global && _globalUsed + _globalReserved + estimatedTokens > global)
            {
                throw new ModelException(ModelErrorKind.BudgetExceeded, "overall_budget");
            }

            if (_userLimit is { } user && Get(_used, principal) + Get(_reserved, principal) + estimatedTokens > user)
            {
                throw new ModelException(ModelErrorKind.BudgetExceeded, "per_user_budget");
            }

            _globalReserved += estimatedTokens;
            _reserved[principal] = Get(_reserved, principal) + estimatedTokens;
            return new Reservation(this, principal, estimatedTokens, _generation);
        }
    }
    /// <inheritdoc/>
    public long Used(string? principal = null)
    {
        lock (_sync) { Roll(); return principal is null ? _globalUsed : Get(_used, principal); }
    }
    /// <inheritdoc/>
    public void Reset()
    {
        lock (_sync)
        {
            _generation++;
            _day = Today();
            _globalUsed = _globalReserved = 0;
            _used.Clear();
            _reserved.Clear();
        }
    }
    private DateOnly Today() => DateOnly.FromDateTime(_clock.GetUtcNow().UtcDateTime);
    private void Roll()
    {
        if (Today() != _day)
        {
            Reset();
        }
    }
    private static long Get(Dictionary<string, long> values, string principal) => values.GetValueOrDefault(principal);
    private void Complete(string principal, int estimate, int generation, ModelUsage? usage)
    {
        lock (_sync)
        {
            Roll();
            if (generation == _generation)
            {
                _globalReserved -= estimate;
                _reserved[principal] = Get(_reserved, principal) - estimate;
            }
            if (usage is null)
            {
                return;
            }

            _globalUsed += usage.Total;
            _used[principal] = Get(_used, principal) + usage.Total;
        }
    }
    private sealed class Reservation(InMemoryTokenBudget owner, string principal, int estimate, int generation) : ITokenReservation
    {
        private int _done;
        public void RecordAttempt(ModelUsage usage)
        {
            if (usage.InputTokens < 0 || usage.OutputTokens < 0)
            {
                throw new ArgumentOutOfRangeException(nameof(usage));
            }

            if (Interlocked.Exchange(ref _done, 1) == 0)
            {
                owner.Complete(principal, estimate, generation, usage);
            }
        }
        public void Dispose()
        {
            if (Interlocked.Exchange(ref _done, 1) == 0)
            {
                owner.Complete(principal, estimate, generation, null);
            }
        }
    }
}
