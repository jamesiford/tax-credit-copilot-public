using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Sources.Cache;
using TaxCredit.Infrastructure.Sources.Projection;

namespace TaxCredit.Infrastructure.Sources.Tests;

internal sealed class ManualTime : TimeProvider
{
    private DateTimeOffset _now = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);
    public override DateTimeOffset GetUtcNow() => _now;
    internal void Advance(TimeSpan span) => _now += span;
}

internal static class CacheFixtures
{
    internal static readonly TimeSpan Window = TimeSpan.FromSeconds(300);

    internal static PayrollProjection Projection(int rows = 1, int payloadChars = 0)
    {
        var list = Enumerable.Range(0, rows).Select(i => PayRow.Of(new PyDict()
            .Add("Employee_ID", i.ToString(System.Globalization.CultureInfo.InvariantCulture)).Add("Note", new string('x', payloadChars)))).ToList();
        return new PayrollProjection(list, new ProjectionControls(rows, rows, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            new Dictionary<string, int>(), 0, 0, 0, 0), [], "test");
    }

    internal static ProjectionCacheOptions Options(int accounts = 8, long bytes = 64L * 1024 * 1024) =>
        new(true, bytes, accounts, Window);

    internal static ProjectionKey Key(long account) => new(account, "identity");
}

/// <summary>A counting source that hands the cache a stamp and a projection the way the SQL source does.</summary>
internal sealed class FakeSource(long account = 1)
{
    private int _stamps, _loads;
    internal string Stamp { get; set; } = "stamp-1";
    internal int Stamps => Volatile.Read(ref _stamps);
    internal int Loads => Volatile.Read(ref _loads);
    internal Func<PayrollProjection?> Loader { get; set; } = () => CacheFixtures.Projection();
    internal PayrollProjection? Read(ClientProjectionCache cache, bool revalidate = false) => cache.GetOrLoad(CacheFixtures.Key(account), revalidate,
        () => { Interlocked.Increment(ref _stamps); return Stamp; }, () => { Interlocked.Increment(ref _loads); return Loader(); });
}

public sealed class ProjectionCacheCoreTests
{
    private static async Task WaitForJoins(ClientProjectionCache cache, int count)
    {
        var deadline = DateTime.UtcNow.AddSeconds(60);
        while (cache.Joins < count)
        {
            Assert.True(DateTime.UtcNow < deadline, "The callers never joined the in-flight load.");
            await Task.Delay(10);
        }
    }

    [Fact]
    public void A_second_read_inside_the_window_is_a_hit_that_asks_the_source_nothing()
    {
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), new ManualTime());
        var source = new FakeSource();
        var first = source.Read(cache);
        var second = source.Read(cache);
        Assert.Same(first, second);
        Assert.Equal(1, source.Loads);
        Assert.Equal(1, source.Stamps);
        Assert.Equal((1, 1), ((int)cache.Metrics.Hits, (int)cache.Metrics.Misses));
    }

    [Fact]
    public void Different_clients_are_different_entries()
    {
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), new ManualTime());
        var one = new FakeSource(1);
        var two = new FakeSource(2);
        Assert.NotSame(one.Read(cache), two.Read(cache));
        Assert.Same(one.Read(cache), one.Read(cache));
        Assert.Equal(2, cache.Count);
        Assert.Equal(2, one.Loads + two.Loads);
    }

    [Fact]
    public void A_different_projection_identity_never_shares_an_entry()
    {
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), new ManualTime());
        var loads = 0;
        PayrollProjection? Load() { loads++; return CacheFixtures.Projection(); }
        cache.GetOrLoad(new ProjectionKey(1, "worksite_only"), false, () => "s", Load);
        cache.GetOrLoad(new ProjectionKey(1, "location_only"), false, () => "s", Load);
        Assert.Equal(2, loads);
    }

    [Fact]
    public void Past_the_window_the_stamp_is_taken_again_and_an_unchanged_one_keeps_the_entry_and_rearms_the_window()
    {
        var time = new ManualTime();
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), time);
        var source = new FakeSource();
        var held = source.Read(cache);
        time.Advance(CacheFixtures.Window + TimeSpan.FromSeconds(1));
        Assert.Same(held, source.Read(cache));
        Assert.Equal((1, 2), (source.Loads, source.Stamps));
        Assert.Same(held, source.Read(cache));
        Assert.Equal(2, source.Stamps);
    }

    [Fact]
    public void The_window_is_a_strict_upper_bound_on_how_long_a_stamp_is_trusted()
    {
        var time = new ManualTime();
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), time);
        var source = new FakeSource();
        source.Read(cache);
        time.Advance(CacheFixtures.Window - TimeSpan.FromMilliseconds(1));
        source.Read(cache);
        Assert.Equal(1, source.Stamps);
        time.Advance(TimeSpan.FromMilliseconds(1));
        source.Read(cache);
        Assert.Equal(2, source.Stamps);
    }

    [Fact]
    public void A_changed_stamp_past_the_window_drops_the_entry_and_reads_again()
    {
        var time = new ManualTime();
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), time);
        var source = new FakeSource();
        var before = source.Read(cache);
        source.Stamp = "stamp-2";
        Assert.Same(before, source.Read(cache));
        time.Advance(CacheFixtures.Window + TimeSpan.FromSeconds(1));
        var after = source.Read(cache);
        Assert.NotSame(before, after);
        Assert.Equal(2, source.Loads);
        Assert.Equal(1, cache.Metrics.Reloads);
        Assert.Same(after, source.Read(cache));
    }

    [Fact]
    public void A_run_ignores_the_window_and_always_takes_a_fresh_stamp()
    {
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), new ManualTime());
        var source = new FakeSource();
        var held = source.Read(cache);
        Assert.Same(held, source.Read(cache, revalidate: true));
        Assert.Equal((1, 2), (source.Loads, source.Stamps));
        source.Stamp = "stamp-2";
        Assert.NotSame(held, source.Read(cache, revalidate: true));
        Assert.Equal((2, 3), (source.Loads, source.Stamps));
    }

    [Fact]
    public void A_page_read_inside_the_window_is_stale_by_design_but_a_run_in_the_same_instant_is_not()
    {
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), new ManualTime());
        var source = new FakeSource();
        var held = source.Read(cache);
        source.Stamp = "stamp-2";
        Assert.Same(held, source.Read(cache));
        Assert.NotSame(held, source.Read(cache, revalidate: true));
    }

    [Fact]
    public void The_least_recently_used_client_is_evicted_when_the_account_bound_is_reached()
    {
        using var cache = new ClientProjectionCache(CacheFixtures.Options(accounts: 2), new ManualTime());
        var (a, b, c) = (new FakeSource(1), new FakeSource(2), new FakeSource(3));
        a.Read(cache);
        b.Read(cache);
        a.Read(cache);
        c.Read(cache);
        Assert.Equal(2, cache.Count);
        Assert.Equal(1, cache.Metrics.Evictions);
        a.Read(cache);
        c.Read(cache);
        Assert.Equal((1, 1), (a.Loads, c.Loads));
        b.Read(cache);
        Assert.Equal(2, b.Loads);
    }

    [Fact]
    public void Entries_are_evicted_until_the_estimated_bytes_fit_and_an_oversize_entry_is_returned_but_not_held()
    {
        var one = ProjectionSizeEstimator.Estimate(CacheFixtures.Projection(1, 20_000));
        using var cache = new ClientProjectionCache(CacheFixtures.Options(bytes: one * 2 + one / 2), new ManualTime());
        FakeSource Source(long id) => new(id) { Loader = () => CacheFixtures.Projection(1, 20_000) };
        var (a, b, c) = (Source(1), Source(2), Source(3));
        a.Read(cache);
        b.Read(cache);
        Assert.Equal(2, cache.Count);
        Assert.True(cache.EstimatedBytes <= one * 2 + one / 2);
        c.Read(cache);
        Assert.Equal(2, cache.Count);
        Assert.Equal(1, cache.Metrics.Evictions);
        Assert.True(cache.EstimatedBytes <= one * 2 + one / 2);
        a.Read(cache);
        Assert.Equal(2, a.Loads);

        var big = new FakeSource(9) { Loader = () => CacheFixtures.Projection(1, 200_000) };
        Assert.NotNull(big.Read(cache));
        Assert.NotNull(big.Read(cache));
        Assert.Equal(2, big.Loads);
        Assert.Equal(2, cache.Count);
    }

    [Fact]
    public void A_failed_load_caches_nothing_and_the_next_read_tries_again()
    {
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), new ManualTime());
        var source = new FakeSource { Loader = () => throw new InvalidOperationException("outage") };
        Assert.Throws<InvalidOperationException>(() => source.Read(cache));
        Assert.Equal(0, cache.Count);
        source.Loader = () => CacheFixtures.Projection();
        Assert.NotNull(source.Read(cache));
        Assert.Equal(2, source.Loads);
        Assert.Equal(1, cache.Count);
    }

    [Fact]
    public void A_failed_stamp_serves_nothing_even_when_an_entry_is_held()
    {
        var time = new ManualTime();
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), time);
        new FakeSource().Read(cache);
        time.Advance(CacheFixtures.Window + TimeSpan.FromSeconds(1));
        Assert.Throws<InvalidOperationException>(() =>
            cache.GetOrLoad(CacheFixtures.Key(1), false, () => throw new InvalidOperationException("endpoint down"), () => CacheFixtures.Projection()));
    }

    [Fact]
    public void An_unknown_client_is_not_cached()
    {
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), new ManualTime());
        var source = new FakeSource { Loader = () => null };
        Assert.Null(source.Read(cache));
        Assert.Null(source.Read(cache));
        Assert.Equal((2, 0), (source.Loads, cache.Count));
    }

    [Fact]
    public async Task Concurrent_reads_of_one_client_run_one_load_and_share_its_result()
    {
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), new ManualTime());
        using var entered = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        var source = new FakeSource { Loader = () => { entered.Set(); release.Wait(); return CacheFixtures.Projection(); } };
        var readers = Enumerable.Range(0, 8).Select(_ => Task.Run(() => source.Read(cache))).ToArray();
        Assert.True(entered.Wait(TimeSpan.FromSeconds(10)));
        await WaitForJoins(cache, 7);
        release.Set();
        var results = await Task.WhenAll(readers);
        Assert.Equal(1, source.Loads);
        Assert.All(results, r => Assert.Same(results[0], r));
    }

    [Fact]
    public async Task Waiters_share_the_failure_of_the_load_they_joined_instead_of_retrying_it()
    {
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), new ManualTime());
        using var entered = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        var source = new FakeSource { Loader = () => { entered.Set(); release.Wait(); throw new InvalidOperationException("outage"); } };
        var readers = Enumerable.Range(0, 4).Select(_ => Task.Run(() => source.Read(cache))).ToArray();
        Assert.True(entered.Wait(TimeSpan.FromSeconds(10)));
        await WaitForJoins(cache, 3);
        release.Set();
        foreach (var reader in readers) { await Assert.ThrowsAsync<InvalidOperationException>(() => reader); }
        Assert.Equal(1, source.Loads);
    }

    [Fact]
    public async Task A_run_does_not_take_the_result_of_a_load_that_began_before_it_asked()
    {
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), new ManualTime());
        using var entered = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        var source = new FakeSource { Loader = () => { entered.Set(); release.Wait(); return CacheFixtures.Projection(); } };
        var page = Task.Run(() => source.Read(cache));
        Assert.True(entered.Wait(TimeSpan.FromSeconds(10)));
        var run = Task.Run(() => source.Read(cache, revalidate: true));
        await WaitForJoins(cache, 1);
        release.Set();
        await Task.WhenAll(page, run);
        Assert.Equal(2, source.Stamps);
        Assert.Equal(1, source.Loads);
    }

    [Fact]
    public void Clear_empties_the_cache()
    {
        using var cache = new ClientProjectionCache(CacheFixtures.Options(), new ManualTime());
        var source = new FakeSource();
        source.Read(cache);
        cache.Clear();
        Assert.Equal((0, 0L), (cache.Count, cache.EstimatedBytes));
        source.Read(cache);
        Assert.Equal(2, source.Loads);
    }

    [Fact]
    public void The_invalidation_scenario_can_fail_when_the_rule_is_broken()
    {
        // The same scenario under the real rule and under mutated rules: it must notice each mutation, or it proves nothing.
        static bool ReloadsOnChange(Func<string, string, bool>? rule)
        {
            var time = new ManualTime();
            using var cache = new ClientProjectionCache(CacheFixtures.Options(), time, rule);
            var source = new FakeSource();
            source.Read(cache);
            source.Stamp = "stamp-2";
            time.Advance(CacheFixtures.Window + TimeSpan.FromSeconds(1));
            source.Read(cache);
            return source.Loads == 2;
        }
        Assert.True(ReloadsOnChange(null));
        Assert.False(ReloadsOnChange((_, _) => true));
        Assert.False(ReloadsOnChange((held, taken) => held.Length == taken.Length));
    }
}
