using System.Text.Json;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Sources.Fiscal;
using TaxCredit.Infrastructure.Sources.Lookups;

namespace TaxCredit.Infrastructure.Sources.Tests;

public sealed class FiscalOverrideBoundaryTests
{
    [Theory]
    [InlineData(7, "not-date", "2024-12-31")]
    [InlineData(0, "not-date", "2024-12-31")]
    [InlineData(7, "2024-01-01", "2024-02-30")]
    [InlineData(0, "2024-01-01", "2024-02-30")]
    [InlineData(7, "2023-02-29", "2024-12-31")]
    [InlineData(0, "2024-01-01", "2024-12-31T00:00:00")]
    [InlineData(7, null, "2024-12-31")]
    [InlineData(0, "2024-01-01", null)]
    public void MalformedClientOrGlobalOverrideDatesRefuseBeforeCalendarSubstitutionUnderAssume(
        long client, string? begin, string? end)
    {
        var library = SourceTestData.Library();
        var lookups = new LookupResolver(new LookupReader([Override(client, begin, end)]));
        Assert.Equal("assume", lookups.Options.FiscalPolicy);
        var fiscal = new FiscalRuleAdapter(library, new RuleReader([]), lookups);
        var failure = Assert.Throws<FiscalRulesMissing>(() => new FiscalSource(library, fiscal).ClientFiscalWindow(7, 2024, "begins"));
        Assert.Equal("fiscal_rules_missing", failure.Code);
        Assert.Null(failure.InnerException);
    }

    [Theory]
    [InlineData(7)]
    [InlineData(0)]
    public void PresentSourceRulesWinWithoutReadingMalformedClientOrGlobalOverrides(long client)
    {
        var library = SourceTestData.Library();
        var lookup = new LookupReader([Override(client, "junk", "2024-12-31")]);
        var fiscal = new FiscalRuleAdapter(library,
            new RuleReader([new FiscalRule("synthetic source", null, "2023-07-01", "2024-06-30")]),
            new LookupResolver(lookup));
        var window = new FiscalSource(library, fiscal).ClientFiscalWindow(7, 2024, "begins");
        Assert.False(window.Assumed);
        Assert.Equal(new DateOnly(2024, 7, 1), window.Begin);
        Assert.Equal(0, lookup.Reads);
    }

    [Theory]
    [InlineData(7)]
    [InlineData(0)]
    public void AValidOtherOverrideDoesNotConcealMalformedStoredDates(long malformedClient)
    {
        var other = malformedClient == 7 ? 0 : 7;
        var lookups = new LookupResolver(new LookupReader([
            Override(malformedClient, "junk", "2024-12-31"), Override(other, "2024-01-01", "2024-12-31")]));
        Assert.Throws<FiscalRulesMissing>(() => lookups.FiscalOverrides(7));
    }

    [Theory]
    [InlineData("2024-01-01", "2024-12-31")]
    [InlineData("20240101", "20241231")]
    [InlineData("2024-W01-1", "2024-W52-7")]
    public void ValidPythonIsoDateFormsAreMaterializedAtTheLookupBoundary(string begin, string end)
    {
        var lookups = new LookupResolver(new LookupReader([Override(7, begin, end)]));
        var rule = Assert.Single(lookups.FiscalOverrides(7));
        Assert.Equal(new DateOnly(2024, 1, 1), Assert.IsType<DateOnly>(rule.FiscalYearBegin));
        Assert.IsType<DateOnly>(rule.FiscalYearEnd);
    }

    private static SourceLookupEntry Override(long client, string? begin, string? end) =>
        new("entity_fiscal_year_rules", client, "rule", "synthetic", JsonSerializer.Serialize(new
        {
            fiscal_year_begin = begin,
            fiscal_year_end = end,
        }));

    private sealed class RuleReader(IReadOnlyList<FiscalRule> rules) : IFiscalRuleReader
    {
        public bool IsConfigured => true;
        public IReadOnlyList<FiscalRule>? Read(long accountId) => rules;
    }
    private sealed class LookupReader(IReadOnlyList<SourceLookupEntry> entries) : ISourceLookupReader
    {
        internal int Reads { get; private set; }
        public IReadOnlyList<SourceLookupEntry> Entries(string lookup, long accountId) { Reads++; return entries; }
    }
}
