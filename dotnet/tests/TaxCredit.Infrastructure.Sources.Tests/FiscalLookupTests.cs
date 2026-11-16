using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Sources.Fiscal;
using TaxCredit.Infrastructure.Sources.Lookups;

namespace TaxCredit.Infrastructure.Sources.Tests;

public sealed class FiscalLookupTests
{
    private static readonly FiscalRule SourceRule = new("synthetic source", null, "2023-07-01", "2024-06-30");

    [Fact]
    public void SourcePrecedesOverrideAndClientPrecedesGlobalWithProvenance()
    {
        var reader = new RuleReader { Rules = [SourceRule] };
        var lookup = new LookupDouble
        {
            Values = [FiscalOverride(0, "2023-01-01", "2023-12-31"), FiscalOverride(7, "2023-10-01", "2024-09-30")],
        };
        var fiscal = new FiscalRuleAdapter(SourceTestData.Library(), reader, new LookupResolver(lookup));
        Assert.Equal(new DateOnly(2023, 7, 1), fiscal.ClientFiscalWindow(7, 2023, "begins").Begin);
        Assert.Equal(0, lookup.Calls);
        reader.Rules = [];
        var own = fiscal.ClientFiscalWindow(7, 2023, "begins");
        Assert.Equal(new DateOnly(2023, 10, 1), own.Begin);
        Assert.Contains("app-owned override", own.Note, StringComparison.Ordinal);
        Assert.False(own.Assumed);
        Assert.Equal(new DateOnly(2023, 1, 1), fiscal.ClientFiscalWindow(8, 2023, "begins").Begin);
    }

    [Theory]
    [InlineData(false, "empty")]
    [InlineData(true, "unreadable")]
    public void EmptyAndUnreadableBothAssumeButCarryDifferentDiagnostics(bool unreadable, string state)
    {
        var reader = new RuleReader { Rules = unreadable ? null : [] };
        var fiscal = new FiscalRuleAdapter(SourceTestData.Library(), reader, new LookupResolver());
        var diagnostic = fiscal.ReadWithDiagnostic(7).Diagnostic;
        Assert.Equal(state, diagnostic.SourceState);
        var window = fiscal.ClientFiscalWindow(7, 2024, "begins");
        Assert.True(window.Assumed);
        Assert.Equal("assumed_calendar", window.Basis);
    }

    [Fact]
    public void ClassifiedSqlOutageFallbackOffAssumesAndOnUsesOnlyBoundedFixtureRules()
    {
        var reader = new RuleReader { Failure = new SourceUnavailable() };
        var fallback = new RuleReader { Rules = [SourceRule] };
        var off = new FiscalRuleAdapter(SourceTestData.Library(), reader, new LookupResolver(), fixtureFallback: fallback);
        Assert.True(off.ClientFiscalWindow(7, 2023, "begins").Assumed);
        Assert.Equal(0, fallback.Calls);
        var on = new FiscalRuleAdapter(SourceTestData.Library(), reader, new LookupResolver(),
            allowFixtureFallback: true, fixtureFallback: fallback);
        Assert.False(on.ClientFiscalWindow(7, 2023, "begins").Assumed);
        Assert.True(on.ReadWithDiagnostic(7).Diagnostic.FallbackUsed);
        Assert.Equal("unreadable", on.ReadWithDiagnostic(7).Diagnostic.SourceState);
        Assert.Equal("materialized_fixture", on.ReadWithDiagnostic(7).Diagnostic.Provider);
        var notConfigured = new FiscalRuleAdapter(SourceTestData.Library(), reader, new LookupResolver(), allowFixtureFallback: true);
        Assert.Throws<SourceUnavailable>(() => notConfigured.ClientFiscalWindow(7, 2023, "begins"));
    }

    [Fact]
    public void ProgrammingAndSchemaErrorsDoNotTriggerOutageFallback()
    {
        var fallback = new RuleReader { Rules = [SourceRule] };
        foreach (var exception in new Exception[] { new InvalidOperationException("synthetic bug"),
                     new SourceSchemaMismatch("Entity", ["account_id"]), new SourceQueryRejected() })
        {
            var fiscal = new FiscalRuleAdapter(SourceTestData.Library(), new RuleReader { Failure = exception }, new LookupResolver(),
                allowFixtureFallback: true, fixtureFallback: fallback);
            Assert.Throws(exception.GetType(), () => fiscal.ClientFiscalWindow(7, 2023, "begins"));
        }
        Assert.Equal(0, fallback.Calls);
    }

    [Theory]
    [InlineData(null, null)]
    [InlineData("junk", "2024-01-01")]
    [InlineData("2024-01-01", "2023-01-01")]
    public void StrictMissingMalformedRulesPropagateThroughCertifiedDomainAndStateResolver(string? begin, string? end)
    {
        var lookups = new LookupResolver(options: new SourceLookupOptions(FiscalPolicy: "strict"));
        var fiscal = new FiscalRuleAdapter(SourceTestData.Library(), new RuleReader
        {
            Rules = [new FiscalRule("synthetic", null, begin, end)],
        }, lookups);
        Assert.Throws<FiscalRulesMissing>(() => fiscal.ClientFiscalWindow(7, 2023, "begins"));
        Assert.Throws<FiscalRulesMissing>(() => new FiscalSource(SourceTestData.Library(), fiscal).ClientFiscalWindow(7, 2023, "begins"));
        Assert.Throws<FiscalRulesMissing>(() => fiscal.FiscalWindowForStateYear(7, "GA", 2023));
    }

    [Fact]
    public void StrictAbsentRulesAndUnavailableLookupNeverDisappearInWindowResolver()
    {
        var strict = new FiscalRuleAdapter(SourceTestData.Library(), new RuleReader { Rules = [] },
            new LookupResolver(options: new SourceLookupOptions(FiscalPolicy: "strict")));
        Assert.Throws<FiscalRulesMissing>(() => strict.WindowForStateYear(7, "GA", 2023));
        var unavailable = new FiscalRuleAdapter(SourceTestData.Library(), new RuleReader { Rules = [] },
            new LookupResolver(new LookupDouble { Failure = new SourceUnavailable("lookup") }));
        Assert.Throws<SourceUnavailable>(() => unavailable.FiscalWindowForStateYear(7, "GA_JTC", 2023));
        Assert.Null(unavailable.FiscalWindowForStateYear(7, "UNKNOWN", 2023));
    }

    [Theory]
    [InlineData("not-json")]
    [InlineData("{}")]
    [InlineData("{\"fiscal_year_begin\":42,\"fiscal_year_end\":\"2024-12-31\"}")]
    public void MalformedAuthoredOverridesAreTypedFailuresNotFixtureFallback(string value)
    {
        var fallback = new RuleReader { Rules = [SourceRule] };
        var fiscal = new FiscalRuleAdapter(SourceTestData.Library(), new RuleReader { Rules = [] },
            new LookupResolver(new LookupDouble
            {
                Values = [new("entity_fiscal_year_rules", 7, "rule", "default", value)],
            }, options: new SourceLookupOptions(FiscalPolicy: "strict")),
            allowFixtureFallback: true, fixtureFallback: fallback);
        var failure = Assert.Throws<FiscalRulesMissing>(() => fiscal.ClientFiscalWindow(7, 2024, "begins"));
        Assert.Null(failure.InnerException);
        Assert.Equal(0, fallback.Calls);
    }

    [Fact]
    public void SqlFiscalReaderTouchesOnlyTwoFilteredTablesForOneClient()
    {
        var (source, _, transport) = SourceTestData.Source();
        var one = source.ClientFiscalWindow(7, 2023, "begins");
        var two = source.ClientFiscalWindow(8, 2023, "begins");
        Assert.Equal(new DateOnly(2023, 7, 1), one.Begin);
        Assert.Equal(new DateOnly(2023, 1, 1), two.Begin);
        Assert.DoesNotContain(transport.Queries, q => q.Table == "Payroll");
        Assert.All(transport.Queries, q => Assert.Contains(q.Table, new[] { "Entity", "EntityFiscalYearRules" }));
        Assert.Contains(transport.Queries, q => q.Table == "EntityFiscalYearRules" && q.Sql.Contains(" IN (", StringComparison.Ordinal));
    }

    [Fact]
    public void BothTaxYearConventionsShiftThroughPureResolverAndLeapDayCannotBeInvented()
    {
        var fiscal = new FiscalRuleAdapter(SourceTestData.Library(), new RuleReader { Rules = [SourceRule] }, new LookupResolver());
        Assert.Equal(new DateOnly(2024, 7, 1), fiscal.ClientFiscalWindow(7, 2024, "begins").Begin);
        Assert.Equal(new DateOnly(2023, 7, 1), fiscal.ClientFiscalWindow(7, 2024, "ends").Begin);
        var leap = new FiscalRule("synthetic", null, "2024-02-29", "2025-02-28");
        Assert.Null(FiscalSource.WindowFromRule(leap, 7, 2025, "begins"));
        Assert.NotNull(FiscalSource.WindowFromRule(leap, 7, 2024, "begins"));
    }

    [Fact]
    public void CsvHoldsNoClientRulesAndDoesNotReadUnusedDependencies()
    {
        var reader = new RuleReader { Failure = new InvalidOperationException("must not open") };
        var fiscal = new FiscalRuleAdapter(SourceTestData.Library(), reader, new LookupResolver(), holdsClientRules: false);
        Assert.False(fiscal.HoldsClientRules);
        Assert.True(new FiscalSource(SourceTestData.Library(), fiscal).ClientFiscalWindow(7, 2024, "begins").Assumed);
        Assert.Equal(0, reader.Calls);
    }

    [Fact]
    public void CodeCategoryClientGlobalPrecedenceAndEffectiveDatesAreScopedAgain()
    {
        var entries = new LookupDouble
        {
            Values = [
                new("pay_code_category", 0, "code", "REG", "Bonus"),
                new("pay_code_category", 7, "category", "42", "Regular"),
                new("pay_code_category", 7, "code", "REG", "Overtime"),
                new("pay_code_category", 9, "code", "REG", "Mileage"),
                new("pay_code_category", 7, "code", "FUTURE", "Bonus", EffectiveFrom: new DateOnly(2999, 1, 1)),
            ],
        };
        var resolver = new LookupResolver(entries);
        Assert.Equal("Overtime", resolver.PayCode(7, "reg", 42).Category);
        Assert.Equal("Regular", resolver.PayCode(7, "XQ", 42).Category);
        Assert.Equal("Bonus", resolver.PayCode(8, "REG", 42).Category);
        Assert.Null(resolver.PayCode(7, "FUTURE").Category);
    }

    [Fact]
    public void CustomerClassificationRejectsSeedUntilMappingsAreAuthored()
    {
        var tables = SourceTestData.MiniTables();
        var dataset = new TaxCredit.Infrastructure.Sources.Projection.SourceDatasetReader(SourceTestData.Source(tables).Scanner).Load(7)!;
        var strict = SourceTestData.Lookups(new SourceLookupOptions(CustomerClassified: true));
        Assert.Throws<UnmappedPayCodes>(() => new TaxCredit.Infrastructure.Sources.Projection.PayrollProjector(
            SourceTestData.Source(tables).Scanner.Mapping, strict).Project(dataset));
        var authored = new LookupResolver(new LookupDouble
        {
            Values = [new("pay_code_category", 7, "code", "REG", "Regular")],
        }, options: new SourceLookupOptions(CustomerClassified: true));
        Assert.Equal("Regular", authored.PayCode(7, "REG").Category);
        Assert.Equal("override", authored.PayCode(7, "REG").Provider);
    }

    private static SourceLookupEntry FiscalOverride(long client, string begin, string end) =>
        new("entity_fiscal_year_rules", client, "rule", "default",
            "{\"fiscal_year_begin\":\"" + begin + "\",\"fiscal_year_end\":\"" + end + "\"}");

    private sealed class RuleReader : IFiscalRuleReader
    {
        internal IReadOnlyList<FiscalRule>? Rules { get; set; }
        internal Exception? Failure { get; init; }
        internal int Calls { get; private set; }
        public bool IsConfigured => true;
        public IReadOnlyList<FiscalRule>? Read(long accountId)
        {
            Calls++;
            if (Failure is not null) { throw Failure; }
            return Rules;
        }
    }
    private sealed class LookupDouble : ISourceLookupReader
    {
        internal IReadOnlyList<SourceLookupEntry> Values { get; init; } = [];
        internal Exception? Failure { get; init; }
        internal int Calls { get; private set; }
        public IReadOnlyList<SourceLookupEntry> Entries(string lookup, long accountId)
        {
            Calls++;
            if (Failure is not null) { throw Failure; }
            return Values;
        }
    }
}
