using System.Globalization;
using TaxCredit.Application.Features.ReadsCalc;
using TaxCredit.Application.Features.ReadsCalc.Portfolio;
using TaxCredit.Infrastructure.Payroll;

namespace TaxCredit.ServiceDefaults.Hosting;

internal sealed class PortfolioReferenceData(RuntimePaths paths) : IPortfolioReferenceData
{
    public long CountFederalNewHires(long taxYear)
    {
        var year = taxYear.ToString(CultureInfo.InvariantCulture);
        return new PayPeriodCsvAdapter(Path.Combine(paths.Repository, "backend", "data", "payroll.csv"))
            .Rows().LongCount(row => row.TryGetValue("hire_date", out var value) && value is string date
                && date.Trim().StartsWith(year + "-", StringComparison.Ordinal));
    }

    public PortfolioWorksite? Worksite(string unitId) => SiteLabels.Reference(unitId);
}
