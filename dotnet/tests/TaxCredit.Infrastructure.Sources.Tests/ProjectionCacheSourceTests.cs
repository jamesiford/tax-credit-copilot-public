using TaxCredit.Application.Ports.Sources;
using TaxCredit.Infrastructure.Sources.Cache;
using TaxCredit.Infrastructure.Sources.Fiscal;
using TaxCredit.Infrastructure.Sources.Fixtures;
using TaxCredit.Infrastructure.Sources.Lookups;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Projection;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Infrastructure.Sources.Tests;

internal sealed class MutableLookups : ISourceLookupReader
{
    internal List<SourceLookupEntry> Held { get; } = [];
    public IReadOnlyList<SourceLookupEntry> Entries(string lookup, long accountId) => Held.ToArray();
}

public sealed class ProjectionCacheSourceTests
{
    private delegate void Edit(Dictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>> tables, SourceMapping mapping);

    /// <summary>One "request": a fresh scoped source over the data as it is now, sharing the singleton cache and lookup store.</summary>
    private static (SqlClientSource Source, RecordingTransport Transport) Request(ClientProjectionCache? cache, Edit? edit = null,
        MutableLookups? store = null, long limit = 10_000)
    {
        var mapping = SourceMapping.Load();
        var tables = SourceTestData.MiniTables(mapping);
        edit?.Invoke(tables, mapping);
        var transport = new RecordingTransport(new MaterializedAnalyticsTransport(mapping, tables));
        var scanner = new SourceScanner(transport, mapping, maximumRows: limit);
        var lookups = new LookupResolver(store, LookupResolver.LoadSeed(Path.Combine(SourceTestData.Root, "backend", "rules", "lookups")));
        return (new SqlClientSource(scanner, new PayrollProjector(mapping, lookups),
            new FiscalRuleAdapter(SourceTestData.Library(), new SqlFiscalRuleReader(scanner), lookups), cache: cache), transport);
    }

    private static Edit AddPayrollRow() => (tables, mapping) => Replace(tables, mapping, rows => [.. rows, Row(mapping, 3, 7)]);

    private static Edit ChangeModified(string stamp) => (tables, mapping) =>
        Replace(tables, mapping, rows => rows.Select(r => Set(r, mapping, "modify_date", stamp)).ToArray());

    private static Edit ChangeHours(string hours) => (tables, mapping) =>
        Replace(tables, mapping, rows => rows.Select(r => Set(r, mapping, "hours", hours)).ToArray());

    private static void Replace(Dictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>> tables, SourceMapping mapping,
        Func<IReadOnlyDictionary<string, object?>[], IReadOnlyDictionary<string, object?>[]> change)
    {
        var physical = mapping.Tables["Payroll"].Physical;
        tables[physical] = change([.. tables[physical]]);
    }

    private static Dictionary<string, object?> Row(SourceMapping mapping, long id, long account) =>
        mapping.Tables["Payroll"].Fields.ToDictionary(f => f.Value.Column,
            f => SourceTestData.Payroll(account, id).GetValueOrDefault(f.Key), StringComparer.Ordinal);

    private static Dictionary<string, object?> Set(IReadOnlyDictionary<string, object?> row, SourceMapping mapping, string field, object? value)
    {
        var copy = row.ToDictionary(p => p.Key, p => p.Value, StringComparer.Ordinal);
        copy[mapping.Tables["Payroll"].Fields[field].Column] = value;
        return copy;
    }

    private static ClientProjectionCache Cache(ManualTime time, int accounts = 8) =>
        new(new ProjectionCacheOptions(true, 64L * 1024 * 1024, accounts, CacheFixtures.Window), time);

    private static int FingerprintQueries(RecordingTransport transport) => transport.Queries.Count(q => q.Kind == "fingerprint");

    [Fact]
    public void With_the_cache_off_every_read_goes_to_the_source_and_nothing_extra_is_asked()
    {
        var (source, transport) = Request(cache: null);
        Assert.Equal(2, source.LoadPayPeriods(7).Count);
        var oneRead = transport.Queries.Count;
        Assert.Equal(2, source.LoadPayPeriods(7).Count);
        Assert.Equal(oneRead * 2, transport.Queries.Count);
        Assert.Equal(0, FingerprintQueries(transport));
        Assert.Same(source.RequireFresh(), source.RequireFresh());
        Assert.Same(NoPayrollFreshness.Instance.RequireFresh(), source.RequireFresh());
    }

    [Fact]
    public void A_later_request_for_the_same_client_inside_the_window_asks_the_source_nothing_at_all()
    {
        using var cache = Cache(new ManualTime());
        var (first, firstTransport) = Request(cache);
        var rows = first.LoadPayPeriods(7);
        Assert.Equal(1, FingerprintQueries(firstTransport));
        var (second, secondTransport) = Request(cache);
        Assert.Same(rows, second.LoadPayPeriods(7));
        Assert.Empty(secondTransport.Queries);
        Assert.Equal(0, secondTransport.DiscoveryCalls);
    }

    [Fact]
    public void The_cached_projection_is_the_projection_an_uncached_read_would_have_produced()
    {
        using var cache = Cache(new ManualTime());
        var cached = Request(cache).Source.LoadProjection(7)!;
        var plain = Request(null).Source.LoadProjection(7)!;
        var none = new Dictionary<string, int>();
        Assert.Equal(plain.Controls with { CodeProviders = none }, cached.Controls with { CodeProviders = none });
        Assert.Equal(plain.Controls.CodeProviders.OrderBy(p => p.Key), cached.Controls.CodeProviders.OrderBy(p => p.Key));
        Assert.Equal(plain.Rows.Count, cached.Rows.Count);
        for (var i = 0; i < plain.Rows.Count; i++) { Assert.Equal(plain.Rows[i].Dict.Select(p => (p.Key, p.Value)), cached.Rows[i].Dict.Select(p => (p.Key, p.Value))); }
    }

    [Fact]
    public void A_new_row_is_picked_up_once_the_window_has_passed_and_not_before()
    {
        var time = new ManualTime();
        using var cache = Cache(time);
        Assert.Equal(2, Request(cache).Source.LoadPayPeriods(7).Count);
        Assert.Equal(2, Request(cache, AddPayrollRow()).Source.LoadPayPeriods(7).Count);
        time.Advance(CacheFixtures.Window + TimeSpan.FromSeconds(1));
        var (source, transport) = Request(cache, AddPayrollRow());
        Assert.Equal(3, source.LoadPayPeriods(7).Count);
        Assert.Equal(1, FingerprintQueries(transport));
        Assert.True(transport.Queries.Count > 1);
    }

    [Fact]
    public void A_newer_modified_date_with_the_same_count_is_picked_up_after_the_window()
    {
        var time = new ManualTime();
        using var cache = Cache(time);
        var held = Request(cache).Source.LoadPayPeriods(7);
        time.Advance(CacheFixtures.Window + TimeSpan.FromSeconds(1));
        Assert.NotSame(held, Request(cache, ChangeModified("2024-03-01T00:00:00")).Source.LoadPayPeriods(7));
    }

    [Fact]
    public void A_change_that_keeps_the_count_and_the_maximum_modified_is_not_detected_which_is_the_documented_limit()
    {
        var time = new ManualTime();
        using var cache = Cache(time);
        var held = Request(cache).Source.LoadPayPeriods(7);
        time.Advance(CacheFixtures.Window * 10);
        var (source, transport) = Request(cache, ChangeHours("$10.00"));
        Assert.Same(held, source.LoadPayPeriods(7));
        Assert.Equal(1, FingerprintQueries(transport));
        Assert.Equal(1, new SourceFingerprintReader(new SourceScanner(transport, SourceMapping.Load())).Fingerprint(7).Limitations
            .Count(l => l.StartsWith("Count/max-preserving", StringComparison.Ordinal)));
    }

    [Fact]
    public void A_run_scope_picks_up_a_change_inside_the_window_and_leaving_the_scope_restores_the_window()
    {
        using var cache = Cache(new ManualTime());
        var held = Request(cache).Source.LoadPayPeriods(7);
        var (source, transport) = Request(cache, AddPayrollRow());
        Assert.Same(held, source.LoadPayPeriods(7));
        using (source.RequireFresh())
        {
            Assert.Equal(3, source.LoadPayPeriods(7).Count);
            Assert.Equal(1, FingerprintQueries(transport));
        }
        var after = transport.Queries.Count;
        Assert.Equal(3, source.LoadPayPeriods(7).Count);
        Assert.Equal(after, transport.Queries.Count);
    }

    [Fact]
    public void A_run_scope_on_unchanged_data_reuses_the_rows_for_the_price_of_the_cheap_checks()
    {
        using var cache = Cache(new ManualTime());
        var held = Request(cache).Source.LoadPayPeriods(7);
        var (source, transport) = Request(cache);
        using var fresh = source.RequireFresh();
        Assert.Same(held, source.LoadPayPeriods(7));
        Assert.Equal(1, FingerprintQueries(transport));
        Assert.All(transport.Queries, q => Assert.Equal("fingerprint", q.Kind));
    }

    [Fact]
    public void An_operator_lookup_edit_changes_the_projection_after_the_window()
    {
        var time = new ManualTime();
        using var cache = Cache(time);
        var store = new MutableLookups();
        var before = Request(cache, store: store).Source.LoadPayPeriods(7);
        store.Held.Add(new SourceLookupEntry("pay_code_category", 7, "code", "REG", "Overtime"));
        time.Advance(CacheFixtures.Window + TimeSpan.FromSeconds(1));
        var after = Request(cache, store: store).Source.LoadPayPeriods(7);
        Assert.NotSame(before, after);
        Assert.NotEqual(before[0].Get("Pay_Code"), after[0].Get("Pay_Code"));
        Assert.Equal("Overtime", after[0].Get("Pay_Code"));
    }

    [Fact]
    public void A_client_over_the_row_cap_is_refused_every_time_and_never_cached()
    {
        using var cache = Cache(new ManualTime());
        var (source, transport) = Request(cache, limit: 1);
        Assert.Throws<SourceTooLarge>(() => source.LoadPayPeriods(7));
        var after = transport.Queries.Count;
        Assert.Throws<SourceTooLarge>(() => source.LoadPayPeriods(7));
        Assert.True(transport.Queries.Count > after);
        Assert.Equal(0, cache.Count);
    }

    [Fact]
    public void A_failed_source_read_caches_nothing()
    {
        using var cache = Cache(new ManualTime());
        var (source, transport) = Request(cache);
        transport.Failure = new SourceTimedOut(5);
        Assert.ThrowsAny<Exception>(() => source.LoadPayPeriods(7));
        Assert.Equal(0, cache.Count);
        transport.Failure = null;
        Assert.Equal(2, source.LoadPayPeriods(7).Count);
        Assert.Equal(1, cache.Count);
    }

    [Fact]
    public void An_unknown_client_is_not_cached()
    {
        using var cache = Cache(new ManualTime());
        Assert.Empty(Request(cache).Source.LoadPayPeriods(999));
        Assert.Equal(0, cache.Count);
    }

    [Fact]
    public void ClearCache_on_the_source_clears_the_shared_cache()
    {
        using var cache = Cache(new ManualTime());
        var (source, _) = Request(cache);
        source.LoadPayPeriods(7);
        Assert.Equal(1, cache.Count);
        source.ClearCache();
        Assert.Equal(0, cache.Count);
    }

    [Fact]
    public void Two_projectors_with_a_different_mapping_or_policy_have_different_cache_identities()
    {
        var seed = LookupResolver.LoadSeed(Path.Combine(SourceTestData.Root, "backend", "rules", "lookups"));
        string Identity(string json, SourceLookupOptions? options = null) =>
            new PayrollProjector(SourceMapping.Load(json), new LookupResolver(payCodeSeed: seed, options: options)).CacheIdentity;
        var baseline = Identity("{}");
        Assert.Equal(baseline, Identity("{}"));
        Assert.NotEqual(baseline, Identity("{\"transforms\":{\"worksite_location\":\"worksite_only\"}}"));
        Assert.NotEqual(baseline, Identity("{\"transforms\":{\"null_pay_date\":\"exclude\"}}"));
        Assert.NotEqual(baseline, Identity("{}", new SourceLookupOptions(CustomerClassified: true, PayCodePolicy: "strict")));
    }

    private static PayrollProjection ProjectedRows(int rows, out SourceMapping mapping)
    {
        mapping = SourceMapping.Load();
        var active = mapping;
        var template = SourceTestData.Payroll(7, 1);
        var tables = SourceTestData.MiniTables(active);
        Replace(tables, active, _ => Enumerable.Range(1, rows).Select(i => (IReadOnlyDictionary<string, object?>)active.Tables["Payroll"].Fields
            .ToDictionary(f => f.Value.Column, f => f.Key == "payroll_id" ? (object?)(long)i : template.GetValueOrDefault(f.Key), StringComparer.Ordinal)).ToArray());
        var lookups = new LookupResolver(null, LookupResolver.LoadSeed(Path.Combine(SourceTestData.Root, "backend", "rules", "lookups")));
        var dataset = new SourceDatasetReader(new SourceScanner(new MaterializedAnalyticsTransport(active, tables), active, maximumRows: 100_000)).Load(7)!;
        return new PayrollProjector(active, lookups).Project(dataset);
    }

    [Fact]
    public void The_estimate_scales_with_rows_and_sits_near_the_measured_cost_of_an_engine_row()
    {
        // docs/SCALE-S2-REPORT.md measured about 2.6 KB retained per projected row; the estimate must stay in that neighbourhood.
        var small = ProjectionSizeEstimator.Estimate(ProjectedRows(1000, out _));
        var large = ProjectionSizeEstimator.Estimate(ProjectedRows(4000, out _));
        Assert.InRange(large / 4000.0, 2000, 3500);
        Assert.InRange(large / (double)small, 3.5, 4.5);
    }

    [Fact]
    public void The_estimate_is_within_a_factor_of_two_of_the_retained_heap_for_projected_rows()
    {
        // A heap measurement is only meaningful in a quiet process: other tests allocate concurrently. Run it with BENCH_RUN=1 on its own.
        if (Environment.GetEnvironmentVariable("BENCH_RUN") != "1") { return; }
        var before = GC.GetTotalMemory(forceFullCollection: true);
        var projection = ProjectedRows(5000, out _);
        var retained = GC.GetTotalMemory(forceFullCollection: true) - before;
        var estimate = ProjectionSizeEstimator.Estimate(projection);
        Assert.InRange(estimate, retained / 2, retained * 2);
        GC.KeepAlive(projection);
    }
}
