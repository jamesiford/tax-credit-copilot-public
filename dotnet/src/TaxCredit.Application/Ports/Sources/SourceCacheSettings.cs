namespace TaxCredit.Application.Ports.Sources;

/// <summary>The setting names and defaults of the per-client projection cache. The cache is off unless an operator turns it on.</summary>
public static class SourceCacheSettings
{
    /// <summary><c>off</c> (default) or <c>on</c>.</summary>
    public const string Mode = "SOURCE_CACHE_MODE";
    /// <summary>Estimated bytes the cache may hold, in megabytes; the Python product's setting of the same name.</summary>
    public const string Megabytes = "SOURCE_CACHE_MB";
    /// <summary>The most clients the cache may hold at once.</summary>
    public const string Accounts = "SOURCE_CACHE_ACCOUNTS";
    /// <summary>How long a matching source fingerprint is trusted before it is taken again.</summary>
    public const string VersionCheckSeconds = "SOURCE_VERSION_CHECK_SECONDS";
    /// <summary>Default size budget.</summary>
    public const long DefaultMegabytes = 512;
    /// <summary>Smallest accepted size budget.</summary>
    public const long MinimumMegabytes = 16;
    /// <summary>Default client count.</summary>
    public const int DefaultAccounts = 64;
    /// <summary>Default fingerprint trust window.</summary>
    public const long DefaultVersionCheckSeconds = 300;
}

/// <summary>
/// Marks a block of payroll reads that feeds a calculation run or a write to a filed number. While it is open the source must
/// not trust any cached projection on the strength of an earlier fingerprint: each read takes a fresh one.
/// </summary>
public interface IPayrollFreshness
{
    /// <summary>Opens the scope; dispose it to leave. Scopes nest and are cheap, and with no cache they do nothing.</summary>
    IDisposable RequireFresh();
}

/// <summary>The scope for a source that holds nothing: nothing can be stale, so nothing is tracked.</summary>
public sealed class NoPayrollFreshness : IPayrollFreshness
{
    /// <summary>The shared instance.</summary>
    public static NoPayrollFreshness Instance { get; } = new();

    private sealed class Scope : IDisposable
    {
        internal static readonly Scope Shared = new();
        public void Dispose() { }
    }

    /// <inheritdoc />
    public IDisposable RequireFresh() => Scope.Shared;
}
