using System.Globalization;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Sources;

namespace TaxCredit.Infrastructure.Sources.Cache;

/// <summary>
/// The parsed cache settings. Parsed once at startup so a bad value stops the host instead of surfacing on a request, and parsed
/// even when the cache is off, so an operator never discovers a typo only on the day they switch it on.
/// </summary>
public sealed record ProjectionCacheOptions(bool Enabled, long MaxBytes, int MaxAccounts, TimeSpan VersionCheck)
{
    private const long Megabyte = 1024 * 1024;

    /// <summary>Off, with the documented defaults for the rest.</summary>
    public static ProjectionCacheOptions Off { get; } = new(false, SourceCacheSettings.DefaultMegabytes * Megabyte,
        SourceCacheSettings.DefaultAccounts, TimeSpan.FromSeconds(SourceCacheSettings.DefaultVersionCheckSeconds));

    /// <summary>Reads and validates the four settings; an invalid value throws <see cref="InvalidOperationException"/>.</summary>
    public static ProjectionCacheOptions From(IRuntimeConfiguration settings)
    {
        ArgumentNullException.ThrowIfNull(settings);
        var megabytes = Parse(settings, SourceCacheSettings.Megabytes, SourceCacheSettings.DefaultMegabytes, SourceCacheSettings.MinimumMegabytes, long.MaxValue / Megabyte);
        var accounts = Parse(settings, SourceCacheSettings.Accounts, SourceCacheSettings.DefaultAccounts, 1, int.MaxValue);
        var seconds = Parse(settings, SourceCacheSettings.VersionCheckSeconds, SourceCacheSettings.DefaultVersionCheckSeconds, 1, 86_400L * 365);
        return new ProjectionCacheOptions(ParseMode(settings.Get(SourceCacheSettings.Mode)), megabytes * Megabyte, (int)accounts, TimeSpan.FromSeconds(seconds));
    }

    private static bool ParseMode(string? mode) => !string.IsNullOrWhiteSpace(mode) && mode.Trim().ToLowerInvariant() switch
    {
        "off" => false,
        "on" => true,
        _ => throw new InvalidOperationException(SourceCacheSettings.Mode + " must be off or on."),
    };

    private static long Parse(IRuntimeConfiguration settings, string name, long fallback, long minimum, long maximum)
    {
        var text = settings.Get(name);
        if (string.IsNullOrWhiteSpace(text)) { return fallback; }
        return long.TryParse(text.Trim(), NumberStyles.None, CultureInfo.InvariantCulture, out var value) && value >= minimum && value <= maximum
            ? value
            : throw new InvalidOperationException(name + " must be a whole number of at least "
                + minimum.ToString("N0", CultureInfo.InvariantCulture) + ".");
    }
}
