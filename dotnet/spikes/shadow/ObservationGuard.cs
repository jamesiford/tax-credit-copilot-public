using PlatformSpike;

namespace TaxCredit.Shadow;

/// <summary>Scratch writes allowed by the inherited experiment are still forbidden to this observer.</summary>
public static class ObservationGuard
{
    public static void Check(string statement, IEnumerable<string> closedTemplates)
    {
        ArgumentNullException.ThrowIfNull(statement);
        ArgumentNullException.ThrowIfNull(closedTemplates);
        if (!closedTemplates.Contains(statement, StringComparer.Ordinal)
            || !statement.StartsWith("SELECT ", StringComparison.Ordinal)
            || statement.Contains("tcc_scratch_dotnet", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Observation refused.");
        }

        new ScratchGuard("tcc_source", ["Payroll"]).Check(statement);
    }
}
