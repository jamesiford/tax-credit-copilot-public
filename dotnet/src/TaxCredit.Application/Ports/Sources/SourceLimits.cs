using System.Globalization;

namespace TaxCredit.Application.Ports.Sources;

/// <summary>The setting names and defaults that bound how much payroll one request may pull into memory.</summary>
public static class SourceLimitSettings
{
    /// <summary>Per-client payroll row ceiling; the Python product's setting of the same name.</summary>
    public const string MaxAccountRows = "SOURCE_MAX_ACCOUNT_ROWS";
    /// <summary>The most clients a portfolio-wide payroll load will read.</summary>
    public const string PortfolioMaxAccounts = "SOURCE_PORTFOLIO_MAX_ACCOUNTS";
    /// <summary>The running payroll row total a portfolio-wide load may not pass.</summary>
    public const string PortfolioMaxRows = "SOURCE_PORTFOLIO_MAX_ROWS";
    /// <summary>The smallest accepted per-client ceiling.</summary>
    public const long MinimumAccountRows = 1000;
    /// <summary>Default per-client ceiling, held until a measurement justifies a higher one.</summary>
    public const long DefaultMaxAccountRows = 1_000_000;
    /// <summary>Default portfolio client count.</summary>
    public const int DefaultPortfolioMaxAccounts = 25;
    /// <summary>Default portfolio running row total.</summary>
    public const long DefaultPortfolioMaxRows = 5_000_000;

    internal static string Format(long value) => value.ToString("N0", CultureInfo.InvariantCulture);
}

/// <summary>
/// A portfolio-wide payroll load refused before reading, because the book is too large to hold in memory at once.
/// </summary>
public sealed class SourcePortfolioTooLarge : SourceFailureException
{
    /// <summary>The refusal for a book with more clients than <see cref="SourceLimitSettings.PortfolioMaxAccounts"/> allows.</summary>
    public static SourcePortfolioTooLarge ForAccounts(int accounts, int limit) => new("accounts", accounts, limit,
        $"the book has {SourceLimitSettings.Format(accounts)} clients, over {SourceLimitSettings.PortfolioMaxAccounts} ({SourceLimitSettings.Format(limit)}).",
        $"Select fewer clients, or raise {SourceLimitSettings.PortfolioMaxAccounts} if the host has the memory.");

    /// <summary>The refusal for a running row total over <see cref="SourceLimitSettings.PortfolioMaxRows"/>.</summary>
    public static SourcePortfolioTooLarge ForRows(long rows, long limit) => new("rows", rows, limit,
        $"the portfolio holds at least {SourceLimitSettings.Format(rows)} payroll rows, over {SourceLimitSettings.PortfolioMaxRows} ({SourceLimitSettings.Format(limit)}).",
        $"Select fewer clients, or raise {SourceLimitSettings.PortfolioMaxRows} if the host has the memory.");

    private SourcePortfolioTooLarge(string measure, long observed, long limit, string reason, string remedy)
        : base("portfolio_too_large", "source_sql", reason + " " + remedy)
    {
        Measure = measure;
        Observed = observed;
        Limit = limit;
    }

    /// <summary>Which bound tripped: <c>accounts</c> or <c>rows</c>.</summary>
    public string Measure { get; }
    /// <summary>The count that crossed the bound (for rows, the running total at the account that crossed it).</summary>
    public long Observed { get; }
    /// <summary>The configured bound.</summary>
    public long Limit { get; }
}
