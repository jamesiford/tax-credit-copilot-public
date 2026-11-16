using System.Text.Json.Nodes;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Designations;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure.Rules;
using TaxCredit.Infrastructure.Sources.Fiscal;
using TaxCredit.Infrastructure.Sources.Lookups;

namespace TaxCredit.Infrastructure.Sources.Tests;

public sealed class FiscalPipelineBridgeTests
{
    [Theory]
    [InlineData("missing")]
    [InlineData("unreadable")]
    [InlineData("unconfigured")]
    [InlineData("malformed")]
    public void StrictFailuresSurviveCertifiedRunResolverAndCalculationBeforePayrollOrWrites(string state)
    {
        var library = SourceTestData.Library();
        var reader = new RuleReader(state);
        var adapter = StrictAdapter(library, reader);
        var boundary = new ExecutionBoundary();
        var (resolver, calculation) = Pipeline(library, adapter, boundary);
        var failure = Assert.Throws<FiscalRulesMissing>(() => resolver.ResolveClientRun(7, "GA", 2024, programCode: "GA_JTC"));
        Assert.Equal("fiscal_rules_missing", failure.Code);
        Assert.Equal("lookup:entity_fiscal_year_rules", failure.Dependency);
        Assert.Null(failure.InnerException);
        Assert.Throws<FiscalRulesMissing>(() => calculation.Run(new RunClientCalculationCommand(7, 2024, "GA", "GA_JTC")));
        Assert.Equal(0, boundary.Attempts);
        Assert.Equal(state == "unconfigured" ? 0 : 2, reader.Reads);
    }

    [Theory]
    [InlineData("begins", 2024, 2024)]
    [InlineData("ends", 2024, 2023)]
    public void CertifiedResolverRetainsSourceWindowProvenanceAndBothConventions(string convention, long year, int beginYear)
    {
        var library = LibraryWithConvention(convention);
        var adapter = StrictAdapter(library, new RuleReader("present"));
        var (resolver, _) = Pipeline(library, adapter, new ExecutionBoundary());
        var statute = resolver.ResolveStatute(7, "GA", year, "GA_JTC");
        Assert.Equal(new DateOnly(beginYear, 7, 1), statute.Window.Begin);
        Assert.Equal(new DateOnly(beginYear + 1, 6, 30), statute.Window.End);
        Assert.Equal("client_rules", statute.Window.Basis);
        Assert.Equal(convention, statute.Window.LabelConvention);
        Assert.False(statute.Window.Assumed);
        Assert.Contains("EntityFiscalYearRules", statute.Window.Note, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("begins", 2024)]
    [InlineData("ends", 2025)]
    public void RepresentableLeapWindowSurvivesCertifiedResolverUnchanged(string convention, long year)
    {
        var library = LibraryWithConvention(convention);
        var adapter = StrictAdapter(library, new RuleReader("leap"));
        var (resolver, _) = Pipeline(library, adapter, new ExecutionBoundary());
        var statute = resolver.ResolveStatute(7, "GA", year, "GA_JTC");
        Assert.Equal(new DateOnly(2024, 2, 29), statute.Window.Begin);
        Assert.Equal(new DateOnly(2025, 2, 28), statute.Window.End);
        Assert.False(statute.Window.Assumed);
    }

    [Theory]
    [InlineData("begins", 2025)]
    [InlineData("ends", 2024)]
    public void NeedsHumanOriginalDomainSeamSubstitutesCalendarForUnrepresentableLeapShift(string convention, long year)
    {
        var library = LibraryWithConvention(convention);
        var reader = new RuleReader("leap");
        var adapter = StrictAdapter(library, reader);
        var boundary = new ExecutionBoundary();
        var (resolver, calculation) = Pipeline(library, adapter, boundary);
        Assert.Null(FiscalSource.WindowFromRule(reader.Rules![0], 7, year, convention));
        Assert.Throws<FiscalRulesMissing>(() => adapter.ClientFiscalWindow(7, year, convention));
        var statute = resolver.ResolveStatute(7, "GA", year, "GA_JTC");
        // Evidence of the unmet gate, not acceptance: the old seam has no year/convention argument.
        Assert.True(statute.Window.Assumed);
        Assert.Equal("assumed_calendar", statute.Window.Basis);
        Assert.Equal(new DateOnly((int)year, 1, 1), statute.Window.Begin);
        Assert.Equal(new DateOnly((int)year, 12, 31), statute.Window.End);
        Assert.Throws<ExecutionBoundaryReachedException>(() => calculation.Run(new RunClientCalculationCommand(7, year, "GA", "GA_JTC")));
        Assert.Equal(1, boundary.Attempts);
    }

    [Fact]
    public void CertifiedResolverRetainsOverrideOriginInsteadOfClaimingSourceRules()
    {
        var library = SourceTestData.Library();
        var lookup = new OverrideReader();
        var adapter = new FiscalRuleAdapter(library, new RuleReader("missing"),
            new LookupResolver(lookup, options: new SourceLookupOptions(FiscalPolicy: "strict")));
        var (resolver, _) = Pipeline(library, adapter, new ExecutionBoundary());
        var statute = resolver.ResolveStatute(7, "GA", 2024, "GA_JTC");
        Assert.False(statute.Window.Assumed);
        Assert.Contains("app-owned override", statute.Window.Note, StringComparison.Ordinal);
        Assert.Equal("override", adapter.ReadWithDiagnostic(7).Diagnostic.Provider);
        Assert.False(adapter.ReadWithDiagnostic(7).Diagnostic.FallbackUsed);
    }

    [Fact]
    public void CertifiedResolverNamesMaterializedFallbackInWindowProvenance()
    {
        var library = SourceTestData.Library();
        var adapter = new FiscalRuleAdapter(library, new RuleReader("unreadable"),
            new LookupResolver(options: new SourceLookupOptions(FiscalPolicy: "strict")),
            allowFixtureFallback: true, fixtureFallback: new RuleReader("present"));
        var (resolver, _) = Pipeline(library, adapter, new ExecutionBoundary());
        var statute = resolver.ResolveStatute(7, "GA", 2024, "GA_JTC");
        Assert.False(statute.Window.Assumed);
        Assert.Contains("Materialized offline fiscal fixture fallback", statute.Window.Note, StringComparison.Ordinal);
        var diagnostic = adapter.ReadWithDiagnostic(7).Diagnostic;
        Assert.Equal("unreadable", diagnostic.SourceState);
        Assert.Equal("materialized_fixture", diagnostic.Provider);
        Assert.True(diagnostic.FallbackUsed);
    }

    private static FiscalRuleAdapter StrictAdapter(RuleLibrary library, RuleReader reader) =>
        new(library, reader, new LookupResolver(options: new SourceLookupOptions(FiscalPolicy: "strict")));

    private static (ClientRunResolver Resolver, ClientCalculation Calculation) Pipeline(
        RuleLibrary library, FiscalRuleAdapter adapter, ExecutionBoundary boundary)
    {
        var defaults = new ProgramDefaults(library, _ => ["GA"]);
        var fiscal = new FiscalSource(library, adapter);
        var resolver = new ClientRunResolver(library, defaults, fiscal, boundary);
        var today = new DateOnly(2026, 1, 1);
        static PyDateTime Clock() => PyDateTime.FromIsoFormat("2026-01-01T00:00:00");
        var parts = new ClientCalculationParts(library, defaults, resolver, new RunFingerprint(library, fiscal),
            new DesignationRegistry([], [], [], () => true), boundary, boundary,
            new ClientAssessment(library, fiscal, () => today, Clock, () => "synthetic-claim"), boundary, boundary);
        return (resolver, new ClientCalculation(parts, new ClientCalculationConfig("synthetic", [], 0,
            () => today, Clock, () => "synthetic-run")));
    }

    private static RuleLibrary LibraryWithConvention(string convention) => new(new ConventionSource(
        new JsonRulePackSource(new RulePackOptions { RulesDirectory = Path.Combine(SourceTestData.Root, "backend", "rules") }), convention));

    private sealed class RuleReader(string state) : IFiscalRuleReader
    {
        internal int Reads { get; private set; }
        internal IReadOnlyList<FiscalRule>? Rules => state switch
        {
            "missing" => [],
            "unreadable" => null,
            "malformed" => [new("synthetic", null, "junk", "2024-01-01")],
            "leap" => [new("synthetic leap", null, "2024-02-29", "2025-02-28")],
            _ => [new("synthetic source", null, "2023-07-01", "2024-06-30")],
        };
        public bool IsConfigured => state != "unconfigured";
        public IReadOnlyList<FiscalRule>? Read(long accountId)
        {
            Assert.Equal(7, accountId);
            Reads++;
            if (state == "unreadable") { throw new SourceUnavailable(); }
            return Rules;
        }
    }

    private sealed class OverrideReader : ISourceLookupReader
    {
        public IReadOnlyList<SourceLookupEntry> Entries(string lookup, long accountId) =>
            [new(lookup, accountId, "rule", "synthetic",
                "{\"fiscal_year_begin\":\"2023-07-01\",\"fiscal_year_end\":\"2024-06-30\"}")];
    }

    private sealed class ExecutionBoundaryReachedException() : Exception("Unexpected payroll or persistence reached.");
    private sealed class ExecutionBoundary : IPayrollSource, IBaseYearOverrides, IClaimSink, IGoldWriter
    {
        internal int Attempts { get; private set; }
        private ExecutionBoundaryReachedException Refuse() { Attempts++; return new ExecutionBoundaryReachedException(); }
        public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId) => throw Refuse();
        public IReadOnlyDictionary<string, long> BaseYears(long clientId, string programCode) => throw Refuse();
        public ProgramClaim? Current(long clientId, string programCode, long taxYear) => throw Refuse();
        public void Record(ProgramClaim claim) => throw Refuse();
        public IReadOnlyList<KeyValuePair<string, long>> WriteRun(GoldRunPayload payload) => throw Refuse();
        public IReadOnlyList<(string Query, long RowCount)> Validate() => throw Refuse();
    }

    // Only the in-memory test pack is changed; no authored statute or Domain code is edited.
    private sealed class ConventionSource(IRulePackSource source, string convention) : IRulePackSource
    {
        public string RulesDirectory => source.RulesDirectory;
        public string RegistryFile => source.RegistryFile;
        public bool Exists(string relativePath) => source.Exists(relativePath);
        public bool IsFile(string relativePath) => source.IsFile(relativePath);
        public bool IsDirectory(string relativePath) => source.IsDirectory(relativePath);
        public IReadOnlyList<string> ListJsonStems(string relativeFolder) => source.ListJsonStems(relativeFolder);
        public long? RegistryStamp() => source.RegistryStamp();
        public string ReadRegistryText() => source.ReadRegistryText();
        public string ReadText(string relativePath)
        {
            var root = JsonNode.Parse(source.ReadText(relativePath))!;
            if (root["tax_year_convention"] is JsonObject label) { label["label"] = convention; }
            return root.ToJsonString();
        }
    }
}
