using System.Globalization;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Sources;

namespace TaxCredit.Infrastructure.Sources.Sql;

/// <summary>
/// Decides whether the payroll footprint may be scanned at all, and for how long. The footprint is a GROUP BY over a
/// table that can hold billions of rows, and a page that waits for it holds a statement open on the server; so
/// before running it the guard consults a row estimate that does not scan, and the statement runs under its own
/// timeout. Behaviour follows the Python product (<c>footprint_guard.py</c>), with the SQL catalogue as the only estimate.
/// </summary>
/// <remarks>
/// One instance per host: the source is scoped per request, so the estimate and a remembered timeout live here to
/// stop a polled page repeating them on every load. Settings are read on every call so a change is honoured.
/// </remarks>
public sealed class FootprintGuard(IRuntimeConfiguration settings, TimeProvider? clock = null)
{
    /// <summary>The setting that selects <c>auto</c>, <c>on</c> or <c>off</c>.</summary>
    public const string ModeSetting = "PORTFOLIO_FOOTPRINT_MODE";
    /// <summary>The setting that bounds the estimated payroll rows <c>auto</c> will scan.</summary>
    public const string MaxRowsSetting = "PORTFOLIO_FOOTPRINT_MAX_ROWS";
    /// <summary>The setting that bounds one footprint statement, in seconds.</summary>
    public const string TimeoutSetting = "PORTFOLIO_FOOTPRINT_TIMEOUT_SECONDS";
    /// <summary>The setting that bounds how long an estimate or a timeout is remembered, in seconds.</summary>
    public const string CacheSetting = "PORTFOLIO_FOOTPRINT_CACHE_SECONDS";

    private readonly TimeProvider _clock = clock ?? TimeProvider.System;
    private readonly Lock _gate = new();
    private (DateTimeOffset At, long? Rows)? _estimate;
    private DateTimeOffset? _timedOutAt;

    /// <summary>The statement timeout the footprint query runs under.</summary>
    public int TimeoutSeconds => Positive(TimeoutSetting, 20);

    /// <summary>The pure decision: <c>off</c> never runs, <c>on</c> always runs, <c>auto</c> refuses above the limit when an estimate exists.</summary>
    public static SourceFootprintUnavailable? Refusal(string mode, long? estimatedRows, long maxRows)
    {
        ArgumentNullException.ThrowIfNull(mode);
        if (mode == "off")
        {
            return new SourceFootprintUnavailable("footprint_off", "the footprint read is switched off (" + ModeSetting + "=off).",
                "Set " + ModeSetting + "=auto to read it where the table is small enough.");
        }
        if (mode == "on" || estimatedRows is not { } rows || rows <= maxRows) { return null; }
        return new SourceFootprintUnavailable("footprint_too_large",
            $"the payroll table is estimated at {rows.ToString("N0", CultureInfo.InvariantCulture)} rows, over {MaxRowsSetting} ({maxRows.ToString("N0", CultureInfo.InvariantCulture)}); the footprint is not scanned.",
            $"Raise {MaxRowsSetting}, set {ModeSetting}=on to run it under {TimeoutSetting}, or use a pre-aggregated read once one exists.");
    }

    /// <summary>The refusal for a statement the server cancelled at <paramref name="seconds"/>.</summary>
    public static SourceFootprintUnavailable TimedOut(int seconds) => new("footprint_timeout",
        $"the footprint query exceeded {TimeoutSetting} ({seconds}s) and was cancelled on the server.",
        $"Raise {TimeoutSetting}, or set {ModeSetting}=off until a pre-aggregated read exists.");

    /// <summary>
    /// Throws a typed refusal when the footprint must not run now; otherwise returns the timeout to run under.
    /// <paramref name="estimate"/> is invoked only in <c>auto</c> mode and only when no fresh estimate is held.
    /// </summary>
    public int Admit(Func<long?> estimate)
    {
        ArgumentNullException.ThrowIfNull(estimate);
        var timeout = TimeoutSeconds;
        if (RememberedTimeout()) { throw TimedOut(timeout); }
        var mode = (settings.Get(ModeSetting) ?? "auto").Trim().ToLowerInvariant();
        mode = mode is "on" or "off" ? mode : "auto";
        var rows = mode == "auto" ? Estimate(estimate) : null;
        if (Refusal(mode, rows, Positive(MaxRowsSetting, 50_000_000L)) is { } refusal) { throw refusal; }
        return timeout;
    }

    /// <summary>Records that a footprint statement timed out, so the next calls fail fast instead of repeating it.</summary>
    public void RememberTimeout()
    {
        lock (_gate) { _timedOutAt = _clock.GetUtcNow(); }
    }

    private bool RememberedTimeout()
    {
        lock (_gate) { return _timedOutAt is { } at && _clock.GetUtcNow() - at < TimeSpan.FromSeconds(Positive(CacheSetting, 300)); }
    }

    private long? Estimate(Func<long?> read)
    {
        var ttl = TimeSpan.FromSeconds(Positive(CacheSetting, 300));
        lock (_gate)
        {
            if (_estimate is { } held && _clock.GetUtcNow() - held.At < ttl) { return held.Rows; }
        }
        var rows = read();
        lock (_gate) { _estimate = (_clock.GetUtcNow(), rows); }
        return rows;
    }

    private int Positive(string name, int fallback) =>
        int.TryParse(settings.Get(name), NumberStyles.Integer, CultureInfo.InvariantCulture, out var value) && value > 0 ? value : fallback;

    private long Positive(string name, long fallback) =>
        long.TryParse(settings.Get(name), NumberStyles.Integer, CultureInfo.InvariantCulture, out var value) && value > 0 ? value : fallback;
}
