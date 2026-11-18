using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Hosting;

/// <summary>
/// Within one scope (one HTTP request or one queued item) the same client's payroll is read and projected once. A calculation asks for
/// it four times (resolve, run, unit-series replay, assessment); each ask was a full source read plus projection, so the work and the
/// memory were four times what one observation needs. Only the latest client is kept, so a loop over many clients never accumulates rows,
/// and nothing outlives the scope, so it is not a cache a later request can read stale.
/// It is also an <see cref="IPayrollFreshness"/>: rows remembered from a read made outside a require-fresh scope are never handed to code inside one,
/// so a run cannot be served rows that the source's own freshness check did not vouch for.
/// </summary>
/// <param name="inner">The real source.</param>
/// <param name="freshness">The source's own require-fresh scope, or null when it has none.</param>
public sealed class ScopedPayrollMemo(IPayrollSource inner, IPayrollFreshness? freshness = null) : IPayrollSource, IPayrollFreshness
{
    private int _fresh;
    private bool _heldFresh;
    private bool _held;
    private long? _account;
    private IReadOnlyList<PayRow> _rows = [];

    /// <inheritdoc />
    public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId)
    {
        if (_held && _account == accountId && (_fresh == 0 || _heldFresh)) { return _rows; }
        var rows = inner.LoadPayPeriods(accountId);
        _account = accountId;
        _rows = rows;
        _held = true;
        _heldFresh = _fresh > 0;
        return rows;
    }

    /// <inheritdoc />
    public IDisposable RequireFresh()
    {
        if (freshness is null) { return NoPayrollFreshness.Instance.RequireFresh(); }
        var inner = freshness.RequireFresh();
        _fresh++;
        return new Leave(this, inner);
    }

    private sealed class Leave(ScopedPayrollMemo owner, IDisposable inner) : IDisposable
    {
        private bool _done;

        public void Dispose()
        {
            if (_done) { return; }
            _done = true;
            owner._fresh--;
            inner.Dispose();
        }
    }
}
