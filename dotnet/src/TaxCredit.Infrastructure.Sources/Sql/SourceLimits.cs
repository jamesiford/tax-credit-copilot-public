using System.Globalization;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Sources;

namespace TaxCredit.Infrastructure.Sources.Sql;

/// <summary>
/// The memory bounds on payroll reads, parsed once at startup so a bad value stops the host rather than surfacing on the
/// first large request. An unset or blank setting keeps its default; anything else must be an integer at or above its minimum.
/// </summary>
public sealed record SourceLimits(long MaxAccountRows, int PortfolioMaxAccounts, long PortfolioMaxRows)
{
    /// <summary>The defaults: 1,000,000 rows per client, 25 clients and 5,000,000 rows per portfolio-wide load.</summary>
    public static SourceLimits Default { get; } = new(SourceLimitSettings.DefaultMaxAccountRows,
        SourceLimitSettings.DefaultPortfolioMaxAccounts, SourceLimitSettings.DefaultPortfolioMaxRows);

    /// <summary>Reads and validates the three settings; an invalid value throws <see cref="InvalidOperationException"/>.</summary>
    public static SourceLimits From(IRuntimeConfiguration settings)
    {
        ArgumentNullException.ThrowIfNull(settings);
        return new SourceLimits(
            Parse(settings, SourceLimitSettings.MaxAccountRows, SourceLimitSettings.DefaultMaxAccountRows, SourceLimitSettings.MinimumAccountRows),
            checked((int)Parse(settings, SourceLimitSettings.PortfolioMaxAccounts, SourceLimitSettings.DefaultPortfolioMaxAccounts, 1, int.MaxValue)),
            Parse(settings, SourceLimitSettings.PortfolioMaxRows, SourceLimitSettings.DefaultPortfolioMaxRows, SourceLimitSettings.MinimumAccountRows));
    }

    private static long Parse(IRuntimeConfiguration settings, string name, long fallback, long minimum, long maximum = long.MaxValue)
    {
        var text = settings.Get(name);
        if (string.IsNullOrWhiteSpace(text)) { return fallback; }
        return long.TryParse(text.Trim(), NumberStyles.None, CultureInfo.InvariantCulture, out var value) && value >= minimum && value <= maximum
            ? value
            : throw new InvalidOperationException(name + " must be a whole number of at least "
                + minimum.ToString("N0", CultureInfo.InvariantCulture) + ".");
    }
}
