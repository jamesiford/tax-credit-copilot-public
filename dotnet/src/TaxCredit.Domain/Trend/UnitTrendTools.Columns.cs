using System.Numerics;
using TaxCredit.Domain.BaseYear;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Trend;

public static partial class UnitTrendTools
{
    /// <summary>Python <c>tranche_columns</c>: the YR1..YRn credit stream, one column per year on the grid.</summary>
    /// <param name="result">The engine result.</param>
    /// <param name="years">The years to report (any order, repeats allowed: each gets its own column).</param>
    /// <returns>One dictionary per requested year.</returns>
    public static IReadOnlyList<PyDict> TrancheColumns(BaseYearResult result, IReadOnlyList<long> years)
    {
        ArgumentNullException.ThrowIfNull(result);
        ArgumentNullException.ThrowIfNull(years);
        var installmentByYear = new Dictionary<long, double>();
        var creationsByYear = new Dictionary<long, List<long>>();
        foreach (var tranche in result.TrancheEvents)
        {
            foreach (var installment in tranche.Installments)
            {
                // Python: installment_by_year.get(year, 0.0) + float(credit_usd), accumulated in event then installment order.
                installmentByYear[installment.Year] = installmentByYear.GetValueOrDefault(installment.Year) + ProximityCoerce.ToFloat(PyNum.IntTree(installment.CreditUsd));
                if (!creationsByYear.TryGetValue(installment.Year, out var creations))
                {
                    creations = [];
                    creationsByYear[installment.Year] = creations;
                }

                creations.Add(tranche.CreationYear);
            }
        }

        var withPayroll = result.Years.Select(y => y.Year).ToHashSet();
        return years.Select(year => new PyDict()
            .Add("tax_year", year)
            .Add("claimable_usd", PyNum.IntTree(PyRound.RoundToInteger(installmentByYear.GetValueOrDefault(year))))
            .Add("from_creation_years", creationsByYear.TryGetValue(year, out var c) ? c.Distinct().Order().Select(v => (object?)v).ToList() : [])
            // No payroll for the year yet: the installment assumes the job is still there, which is a projection and has to read as one.
            .Add("projected", !withPayroll.Contains(year) && year != result.BaseYear))
            .ToList();
    }
}
