using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Features.ReadsCalc.Portfolio;

public sealed partial class ReadsStoredPortfolioBriefs
{
    /// <summary>Reads the eligible population and ranks its cushions; it never re-decides a stored eligibility verdict.</summary>
    public PyDict JobsAtRisk(ClientRunResolver resolver, long accountId, string state, int taxYear, string method = "min_max",
        string? programCode = null, Action<IReadOnlyDictionary<string, object?>>? onRun = null)
    {
        ArgumentNullException.ThrowIfNull(resolver);
        PortfolioValues.ValidateMethod(method);
        ResolvedStatute resolved;
        try
        {
            resolved = resolver.ResolveStatute(accountId, state.ToUpperInvariant(), taxYear, programCode, requireProgram: true);
        }
        catch (ClientRunNotAvailable error)
        {
            return new PyDict().Add("calculated", false).Add("declined", error.Message);
        }
        var read = gold.AtRisk(accountId, taxYear, method, new RiskOptions(
            PortfolioValues.Number(resolved.Floors.MinWeeklyHours), PortfolioValues.Number(resolved.Floors.MinWeeklyWages), ProgramCode: resolved.ProgramCode));
        if (read.GetValueOrDefault("run") is IReadOnlyDictionary<string, object?> run)
        {
            onRun?.Invoke(run);
        }
        if (read.GetValueOrDefault("run") is null || read.GetValueOrDefault("counts") is not IReadOnlyDictionary<string, object?> counts
            || PortfolioValues.Number(counts.GetValueOrDefault("eligible_count")) == 0)
        {
            return NotCalculated(accountId, taxYear);
        }
        var averages = ((IEnumerable<IReadOnlyDictionary<string, object?>>)read["rows"]!).Select(RiskAverage).ToList();
        var cohort = Proximity.FragileCohort(averages, resolved.Floors, PyNumber.OfFloat(5.0), 10,
            population: new PyDict().Add("evaluated", PortfolioValues.Integer(counts.GetValueOrDefault("evaluated")))
                .Add("eligible", PortfolioValues.Integer(counts.GetValueOrDefault("eligible_count"))));
        return cohort.Aggregate(new PyDict().Add("calculated", true).Add("client_id", accountId).Add("tax_year", (long)taxYear)
            .Add("state", resolved.State).Add("program_code", resolved.ProgramCode).Add("method", method),
            (result, pair) => result.Add(pair.Key, pair.Value));
    }

    private static PyDict RiskAverage(IReadOnlyDictionary<string, object?> row)
    {
        var result = new PyDict().Add("Employee_ID", row["employee_id"]).Add("record_token", row["record_token"]);
        foreach (var key in new[] { "weeks_worked", "total_hours", "total_wages", "avg_weekly_hours", "avg_weekly_wages" })
        {
            result.Add(key, PortfolioValues.Number(row.GetValueOrDefault(key)));
        }
        var weight = PortfolioValues.Number(row.GetValueOrDefault("weight"));
        return result.Add("weight", weight == 0 ? 1.0 : weight);
    }
}
