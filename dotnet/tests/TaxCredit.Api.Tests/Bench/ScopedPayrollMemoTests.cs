using TaxCredit.Application.Hosting;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Api.Tests.Bench;

public sealed class ScopedPayrollMemoTests
{
    [Fact]
    public void The_same_client_is_read_once_and_a_different_client_replaces_it()
    {
        var source = new CountingSource();
        var memo = new ScopedPayrollMemo(source);
        var first = memo.LoadPayPeriods(1);
        Assert.Same(first, memo.LoadPayPeriods(1));
        Assert.Equal(1, source.Reads);
        memo.LoadPayPeriods(2);
        memo.LoadPayPeriods(1);
        Assert.Equal(3, source.Reads);
    }

    [Fact]
    public void A_failed_read_is_not_remembered()
    {
        var source = new CountingSource { Fail = true };
        var memo = new ScopedPayrollMemo(source);
        Assert.Throws<InvalidOperationException>(() => memo.LoadPayPeriods(1));
        source.Fail = false;
        Assert.Empty(memo.LoadPayPeriods(1));
        Assert.Equal(2, source.Reads);
    }

    private sealed class CountingSource : IPayrollSource
    {
        internal int Reads { get; private set; }

        internal bool Fail { get; set; }

        public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId)
        {
            Reads++;
            return Fail ? throw new InvalidOperationException("source down") : [];
        }
    }
}
