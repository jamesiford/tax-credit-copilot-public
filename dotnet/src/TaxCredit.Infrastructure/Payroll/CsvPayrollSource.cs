using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Infrastructure.Payroll;

/// <summary>
/// The <c>csv</c> data source of <c>infrastructure/payroll/pay_period_source.load_pay_periods</c>: one tenant's pay periods from the committed fixture.
/// </summary>
/// <remarks>
/// Why a different tenant is empty: the fixture holds exactly one tenant, and asking for another must return nothing rather than that tenant's rows, or a caller
/// asking for client 42 would compute figures for the wrong company. A missing file reads as no rows.
/// </remarks>
/// <param name="path">The CSV file.</param>
/// <param name="fixtureAccountId">The one tenant the fixture holds (Python <c>fixture_account_id()</c>).</param>
public sealed class CsvPayrollSource(string path, long? fixtureAccountId) : IPayrollSource
{
    private IReadOnlyList<PayRow>? _rows;

    /// <inheritdoc />
    public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId)
    {
        if (accountId is not null && accountId != fixtureAccountId)
        {
            return [];
        }

        return _rows ??= PayRow.Of(CsvPayroll.Typed(new PayPeriodCsvAdapter(path).Rows()));
    }
}

/// <summary>A payroll source over rows already in memory, one list per tenant: the shape of the multi-tenant lakehouse source (no tenant named means no rows).</summary>
/// <param name="rowsByClient">Each tenant's rows.</param>
public sealed class InMemoryPayrollSource(IReadOnlyDictionary<long, IReadOnlyList<PayRow>> rowsByClient) : IPayrollSource
{
    /// <inheritdoc />
    public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId) =>
        accountId is { } id && rowsByClient.TryGetValue(id, out var rows) ? rows : [];
}
