using System.Diagnostics.Metrics;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Infrastructure.Sources.Cache;

namespace TaxCredit.Infrastructure.Sources.Tests;

public sealed class ProjectionCacheSettingsTests
{
    private sealed class Settings(Dictionary<string, string?> values) : IRuntimeConfiguration
    {
        public string? Get(string name) => values.GetValueOrDefault(name);
    }

    private static ProjectionCacheOptions Parse(params (string Name, string? Value)[] values) =>
        ProjectionCacheOptions.From(new Settings(values.ToDictionary(v => v.Name, v => v.Value)));

    [Fact]
    public void Unset_blank_and_off_all_mean_off_with_the_python_defaults()
    {
        foreach (var options in new[] { Parse(), Parse(("SOURCE_CACHE_MODE", "  ")), Parse(("SOURCE_CACHE_MODE", "OFF")) })
        {
            Assert.False(options.Enabled);
            Assert.Equal(new ProjectionCacheOptions(false, 512L * 1024 * 1024, 64, TimeSpan.FromSeconds(300)), options);
        }
    }

    [Fact]
    public void On_and_overrides_are_honoured()
    {
        var options = Parse(("SOURCE_CACHE_MODE", " On "), ("SOURCE_CACHE_MB", "16"), ("SOURCE_CACHE_ACCOUNTS", "1"), ("SOURCE_VERSION_CHECK_SECONDS", "1"));
        Assert.Equal(new ProjectionCacheOptions(true, 16L * 1024 * 1024, 1, TimeSpan.FromSeconds(1)), options);
    }

    [Theory]
    [InlineData("SOURCE_CACHE_MODE", "yes")]
    [InlineData("SOURCE_CACHE_MODE", "1")]
    [InlineData("SOURCE_CACHE_MB", "15")]
    [InlineData("SOURCE_CACHE_MB", "lots")]
    [InlineData("SOURCE_CACHE_ACCOUNTS", "0")]
    [InlineData("SOURCE_CACHE_ACCOUNTS", "-3")]
    [InlineData("SOURCE_VERSION_CHECK_SECONDS", "0")]
    [InlineData("SOURCE_VERSION_CHECK_SECONDS", "1.5")]
    public void An_invalid_value_is_a_startup_error_that_names_the_setting_even_when_the_cache_is_off(string name, string value)
    {
        var error = Assert.Throws<InvalidOperationException>(() => Parse((name, value)));
        Assert.StartsWith(name + " must be", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void The_meter_publishes_hits_misses_evictions_and_the_two_gauges()
    {
        using var cache = new ClientProjectionCache(CacheFixtures.Options(accounts: 1), new ManualTime());
        var totals = new Dictionary<string, long>();
        using var listener = new MeterListener();
        listener.InstrumentPublished = (instrument, l) =>
        {
            if (ReferenceEquals(instrument.Meter, cache.Metrics.Meter)) { l.EnableMeasurementEvents(instrument); }
        };
        listener.SetMeasurementEventCallback<long>((instrument, value, _, _) => totals[instrument.Name] = totals.GetValueOrDefault(instrument.Name) + value);
        listener.Start();
        var (a, b) = (new FakeSource(1), new FakeSource(2));
        a.Read(cache);
        a.Read(cache);
        b.Read(cache);
        listener.RecordObservableInstruments();
        Assert.Equal(1, totals["tcc.source_cache.hits"]);
        Assert.Equal(2, totals["tcc.source_cache.misses"]);
        Assert.Equal(1, totals["tcc.source_cache.evictions"]);
        Assert.Equal(1, totals["tcc.source_cache.entries"]);
        Assert.True(totals["tcc.source_cache.estimated_bytes"] > 0);
    }
}
