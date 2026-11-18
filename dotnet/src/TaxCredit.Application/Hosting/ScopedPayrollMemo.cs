using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Hosting;

/// <summary>
/// Within one scope (one HTTP request or one queued item) the same client's payroll is read and projected once. A calculation asks for
/// it four times (resolve, run, unit-series replay, assessment); each ask was a full source read plus projection, so the work and the
/// memory were four times what one observation needs. Only the latest client is kept, so a loop over many clients never accumulates rows,
/// and nothing outlives the scope, so it is not a cache a later request can read stale.
/// </summary>
/// <param name="inner">The real source.</param>
public sealed class ScopedPayrollMemo(IPayrollSource inner) : IPayrollSource
{
    private bool _held;
    private long? _account;
    private IReadOnlyList<PayRow> _rows = [];

    /// <inheritdoc />
    public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId)
    {
        if (_held && _account == accountId) { return _rows; }
        var rows = inner.LoadPayPeriods(accountId);
        _account = accountId;
        _rows = rows;
        _held = true;
        return rows;
    }
}
