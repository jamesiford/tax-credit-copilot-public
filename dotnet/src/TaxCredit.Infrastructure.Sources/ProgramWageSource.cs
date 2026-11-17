using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure.Payroll;

namespace TaxCredit.Infrastructure.Sources;

/// <summary>Deferred program-wage I/O uses configured committed annual payroll; credit arithmetic stays in RuleLibrary.</summary>
public sealed class ProgramWageSource(string path, Func<string, string> stateForProgram) : IProgramWageSource
{
    /// <inheritdoc />
    public double AverageProgramWage(string programOrState)
    {
        var state = stateForProgram(programOrState);
        var rows = new PayPeriodCsvAdapter(path).Rows().Where(r =>
            r.TryGetValue("location_state", out var value) && value as string == state).ToArray();
        if (rows.Length == 0) { return 0.0; }
        var total = rows.Aggregate(System.Numerics.BigInteger.Zero, (sum, row) => sum
            + System.Numerics.BigInteger.Parse((string)row["annual_wage"]!, System.Globalization.CultureInfo.InvariantCulture));
        return (double)total / rows.Length;
    }
}
