using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Infrastructure.Sources.Tests;

public sealed class FootprintBoundTests
{
    private const int Accounts = 1500;

    [Fact]
    public void ABoundedFootprintOverMoreThanOneBatchEqualsTheUnboundedAnswer()
    {
        var (source, _, transport) = SourceTestData.Source(ManyAccounts(SourceMapping.Load()));
        var ids = Enumerable.Range(1, Accounts).Select(i => 1000L + i).Concat([7L, 8L]).ToArray();
        var bounded = source.Footprint(ids);
        var batches = transport.Queries.Where(q => q.Kind == "footprint").ToArray();
        Assert.Equal(2, batches.Length);
        Assert.Equal(SourceScanner.IdBatchSize, batches[0].Parameters.Count);
        Assert.Equal(ids.Length - SourceScanner.IdBatchSize, batches[1].Parameters.Count);
        Assert.Equal(ids.Length, bounded.Count);
        Assert.All(Enumerable.Range(1, Accounts), i => Assert.Equal(["GA"], bounded[1000L + i]));
        Assert.Equal(["GA"], bounded[8]);
        Assert.Equal(["SC"], bounded[7]);
        Assert.Equal(bounded.OrderBy(p => p.Key).Select(p => (p.Key, string.Join(",", p.Value))),
            source.Footprint().OrderBy(p => p.Key).Select(p => (p.Key, string.Join(",", p.Value))));
    }

    [Fact]
    public void FootprintSqlBindsEveryIdAndNeverConcatenatesOne()
    {
        var (_, scanner, _) = SourceTestData.Source();
        var query = Assert.Single(new SourceQueries(scanner).Footprint([123456L, 654321L]));
        Assert.Contains("IN (@p0,@p1)", query.Sql, StringComparison.Ordinal);
        Assert.DoesNotContain("123456", query.Sql, StringComparison.Ordinal);
        Assert.DoesNotContain("654321", query.Sql, StringComparison.Ordinal);
        Assert.Equal(new object?[] { 123456L, 654321L }, query.Parameters);
    }

    [Fact]
    public void NamedClientsAreTheOnlyOnesAskedForAndTheParameterlessReadIsStillTenanted()
    {
        var (source, _, transport) = SourceTestData.Source();
        Assert.Equal(new[] { 8L }, source.Footprint([8L]).Keys);
        Assert.Equal(8L, Assert.Single(Assert.Single(transport.Queries, q => q.Kind == "footprint").Parameters));
        Assert.Empty(source.Footprint([]));
        transport.Queries.Clear();
        _ = source.Footprint();
        Assert.All(transport.Queries.Where(q => q.Kind == "footprint"), q => Assert.Contains(" IN (", q.Sql, StringComparison.Ordinal));
    }

    [Fact]
    public void WithoutAGuardTheHealthyPathAddsNoEstimateQuery()
    {
        var (source, _, transport) = SourceTestData.Source();
        _ = source.Footprint();
        Assert.DoesNotContain(transport.Queries, q => q.Kind == "estimate");
        Assert.All(transport.Queries.Where(q => q.Kind == "footprint"), q => Assert.Null(q.TimeoutSeconds));
    }

    [Theory]
    [InlineData("auto", null, true)]
    [InlineData("auto", 49_999_999L, true)]
    [InlineData("auto", 50_000_000L, true)]
    [InlineData("auto", 50_000_001L, false)]
    [InlineData("on", 900_000_000_000L, true)]
    [InlineData("off", 1L, false)]
    [InlineData("nonsense", 50_000_001L, false)]
    [InlineData(null, 50_000_001L, false)]
    public void EachModeAndTheRowLimitDecideWhetherTheScanRuns(string? mode, long? estimate, bool runs)
    {
        var (_, transport, source) = Guarded(new() { ["PORTFOLIO_FOOTPRINT_MODE"] = mode }, estimate);
        if (runs) { Assert.NotEmpty(source.Footprint([8L])); }
        else
        {
            var refused = Assert.Throws<SourceFootprintUnavailable>(() => source.Footprint([8L]));
            Assert.Equal(mode == "off" ? "footprint_off" : "footprint_too_large", refused.Code);
            Assert.Equal("source_sql", refused.Dependency);
            Assert.Contains("PORTFOLIO_FOOTPRINT_MODE", refused.Remedy, StringComparison.Ordinal);
            if (mode != "off") { Assert.Contains("PORTFOLIO_FOOTPRINT_MAX_ROWS", refused.Remedy, StringComparison.Ordinal); }
        }
        Assert.Equal(runs, transport.Queries.Any(q => q.Kind == "footprint"));
        Assert.Equal(mode is "on" or "off" ? 0 : 1, transport.Queries.Count(q => q.Kind == "estimate"));
    }

    [Fact]
    public void TheConfiguredLimitAndTimeoutReachTheStatement()
    {
        var (_, transport, source) = Guarded(new() { ["PORTFOLIO_FOOTPRINT_MAX_ROWS"] = "10", ["PORTFOLIO_FOOTPRINT_TIMEOUT_SECONDS"] = "7" }, 10);
        _ = source.Footprint([8L]);
        Assert.All(transport.Queries.Where(q => q.Kind is "footprint" or "estimate"), q => Assert.Equal(7, q.TimeoutSeconds));
        var (_, _, tooBig) = Guarded(new() { ["PORTFOLIO_FOOTPRINT_MAX_ROWS"] = "10" }, 11);
        Assert.Equal("footprint_too_large", Assert.Throws<SourceFootprintUnavailable>(() => tooBig.Footprint([8L])).Code);
        var (_, defaults, plain) = Guarded([], null);
        _ = plain.Footprint([8L]);
        Assert.Equal(20, Assert.Single(defaults.Queries, q => q.Kind == "footprint").TimeoutSeconds);
    }

    [Fact]
    public void TheEstimateIsReadOnceUntilItExpires()
    {
        var clock = new Clock();
        var settings = new Settings(new() { ["PORTFOLIO_FOOTPRINT_CACHE_SECONDS"] = "60" });
        var guard = new FootprintGuard(settings, clock);
        var calls = 0;
        long? Estimate() { calls++; return 5; }
        _ = guard.Admit(Estimate);
        _ = guard.Admit(Estimate);
        Assert.Equal(1, calls);
        clock.Now = clock.Now.AddSeconds(61);
        _ = guard.Admit(Estimate);
        Assert.Equal(2, calls);
    }

    [Fact]
    public void ATimedOutScanIsTypedNamesTheSettingsAndIsRememberedWithoutRepeatingTheScan()
    {
        var (_, transport, source) = Guarded([], null);
        transport.TimeOut.Add("footprint");
        var failure = Assert.Throws<SourceFootprintUnavailable>(() => source.Footprint([8L]));
        Assert.Equal("footprint_timeout", failure.Code);
        Assert.IsNotAssignableFrom<SourceUnavailable>(failure);
        Assert.Contains("PORTFOLIO_FOOTPRINT_TIMEOUT_SECONDS", failure.Remedy, StringComparison.Ordinal);
        Assert.Contains("(20s)", failure.Reason, StringComparison.Ordinal);
        var scans = transport.Queries.Count(q => q.Kind == "footprint");
        Assert.Equal("footprint_timeout", Assert.Throws<SourceFootprintUnavailable>(() => source.Footprint([8L])).Code);
        Assert.Equal(scans, transport.Queries.Count(q => q.Kind == "footprint"));
    }

    [Fact]
    public void AnEstimateThatCannotBeReadMeansNoEstimateNotARefusal()
    {
        var (_, transport, source) = Guarded([], null);
        transport.TimeOut.Add("estimate");
        Assert.NotEmpty(source.Footprint([8L]));
    }

    [Fact]
    public void OnlyAStatementWithItsOwnLimitMapsTheDriverTimeoutAndNeverToAnOutage()
    {
        var own = new AnalyticsQuery("x", [], "Payroll", new Dictionary<string, string>(), Kind: "footprint", TimeoutSeconds: 20);
        var timeout = Assert.IsType<SourceTimedOut>(SqlAnalyticsTransport.SqlFailure(-2, own));
        Assert.Equal(20, timeout.Seconds);
        Assert.IsNotType<SourceUnavailable>(timeout);
        Assert.IsType<SourceUnavailable>(SqlAnalyticsTransport.SqlFailure(-2, own with { TimeoutSeconds = null }));
        Assert.IsType<SourceQueryRejected>(SqlAnalyticsTransport.SqlFailure(102, own));
    }

    [Fact]
    public void TheGuardDecisionTableCatchesEveryMutantOfIt()
    {
        Assert.Empty(DecisionDisagreements(Real));
        Assert.NotEmpty(DecisionDisagreements((mode, rows, max) => mode == "off" || rows >= max));
        Assert.NotEmpty(DecisionDisagreements((mode, rows, max) => mode == "off" || (mode != "on" && rows > max * 2)));
        Assert.NotEmpty(DecisionDisagreements((mode, rows, max) => mode == "off" || (mode == "auto" && rows < 0)));
        Assert.NotEmpty(DecisionDisagreements((mode, rows, max) => mode != "on" && rows > max));
        Assert.NotEmpty(DecisionDisagreements((mode, rows, max) => mode == "off" || rows > max));
        Assert.NotEmpty(DecisionDisagreements((mode, rows, max) => mode == "off" || (mode != "on" && rows is null)));

        static bool Real(string mode, long? rows, long max) => FootprintGuard.Refusal(mode, rows, max) is not null;
    }

    private static List<string> DecisionDisagreements(Func<string, long?, long, bool> refuses)
    {
        var expected = new (string Mode, long? Rows, long Max, bool Refused)[]
        {
            ("off", null, 10, true), ("off", 1, 10, true), ("off", 99, 10, true),
            ("on", null, 10, false), ("on", 99, 10, false),
            ("auto", null, 10, false), ("auto", 9, 10, false), ("auto", 10, 10, false), ("auto", 11, 10, true),
        };
        return expected.Where(e => refuses(e.Mode, e.Rows, e.Max) != e.Refused).Select(e => $"{e.Mode}/{e.Rows}").ToList();
    }

    private static (FootprintGuard Guard, RecordingTransport Transport, SqlClientSource Source) Guarded(
        Dictionary<string, string?> values, long? estimate)
    {
        var guard = new FootprintGuard(new Settings(values));
        var (source, _, transport) = SourceTestData.Source(guard: guard);
        transport.Estimate = estimate;
        return (guard, transport, source);
    }

    private static Dictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>> ManyAccounts(SourceMapping mapping)
    {
        var tables = SourceTestData.MiniTables(mapping);
        List<IReadOnlyDictionary<string, object?>> Append(string logical, IEnumerable<Dictionary<string, object?>> rows)
        {
            var table = mapping.Tables[logical];
            var all = tables[table.Physical].ToList();
            all.AddRange(rows.Select(row => (IReadOnlyDictionary<string, object?>)table.Fields.ToDictionary(
                f => f.Value.Column, f => row.TryGetValue(f.Key, out var value) ? value : null, StringComparer.Ordinal)));
            tables[table.Physical] = all;
            return all;
        }
        var ids = Enumerable.Range(1, Accounts).Select(i => 1000L + i).ToArray();
        _ = Append("Account", ids.Select(id => SourceTestData.Row(("account_id", id), ("name", "Synthetic " + id))));
        _ = Append("Location", ids.Select(id => SourceTestData.Row(("location_id", 10_000 + id), ("account_id", id), ("address_id", 2L), ("client_location_id", "GA_" + id))));
        _ = Append("Payroll", ids.Select(id =>
        {
            var row = SourceTestData.Payroll(id, 5000 + id);
            row["location_id"] = 10_000 + id;
            row["worksite_location_id"] = 10_000 + id;
            return row;
        }));
        return tables;
    }

    private sealed class Settings(Dictionary<string, string?> values) : IRuntimeConfiguration
    {
        public string? Get(string name) => values.GetValueOrDefault(name);
    }

    private sealed class Clock : TimeProvider
    {
        internal DateTimeOffset Now { get; set; } = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);
        public override DateTimeOffset GetUtcNow() => Now;
    }
}
