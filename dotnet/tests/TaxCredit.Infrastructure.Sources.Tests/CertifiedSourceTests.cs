using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure.Payroll;
using TaxCredit.Infrastructure.Rules;
using TaxCredit.Infrastructure.Sources.Fiscal;
using TaxCredit.Infrastructure.Sources.Fixtures;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Projection;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Infrastructure.Sources.Tests;

public sealed class CertifiedSourceTests
{
    [Fact]
    public void CommittedCsvUsesCertifiedParserAndTenantIsolationWithOriginalDomainPort()
    {
        var path = Path.Combine(SourceTestData.Root, "backend", "data", "payroll_pay_periods.csv");
        var source = new CsvClientSource(path, 7, new FiscalRuleAdapter(SourceTestData.Library(),
            new AbsentFiscalReader(), SourceTestData.Lookups(), holdsClientRules: false));
        Assert.Equal(9477, ReadCertified(source, 7).Count);
        Assert.Empty(ReadCertified(source, 8));
        Assert.Equal(source.Footprint()[7], source.Footprint([7L])[7]);
        Assert.Empty(source.Footprint([8L]));
        Assert.Equal(ReadCertified(source, null), source.LoadPortfolioPayPeriods()[7]);
        Assert.True(source.ClientFiscalWindow(7, 2024, "begins").Assumed);
        using var scope = source.SharedScope();
        var services = new ServiceCollection();
        services.AddTaxCreditCsvSources(path, 7);
        Assert.Contains(services, s => s.ServiceType == typeof(IPayrollSource));
        Assert.Contains(services, s => s.ServiceType == typeof(IFiscalRuleSource));
        Assert.DoesNotContain(services, s => s.ServiceType == typeof(IAnalyticsTransport));
        var unnamed = new CsvClientSource(path, null, new FiscalRuleAdapter(SourceTestData.Library(),
            new AbsentFiscalReader(), SourceTestData.Lookups(), holdsClientRules: false));
        Assert.Null(unnamed.FixtureAccountId);
        Assert.Empty(unnamed.LoadPayPeriods(7));
        Assert.Empty(unnamed.LoadPortfolioPayPeriods());
        Assert.Empty(unnamed.ListAccounts());
        Assert.Contains(2024L, source.PayrollScope(7).TaxYears);
    }

    [Fact]
    public void CanonicalCsvGoldenCasesStillUseTheExistingParserNotAnotherStateMachine()
    {
        using var file = File.OpenRead(Path.Combine(SourceTestData.Root, "parity", "goldens", "canonical.jsonl.gz"));
        using var gzip = new GZipStream(file, CompressionMode.Decompress);
        using var reader = new StreamReader(gzip);
        var compared = 0;
        var path = Path.Combine(SourceTestData.Root, "dotnet", "tests", "TaxCredit.Infrastructure.Sources.Tests",
            "csv-golden-" + Guid.NewGuid().ToString("N") + ".csv");
        try
        {
            while (reader.ReadLine() is { } line)
            {
                if (!line.Contains("\"csv_rows\"", StringComparison.Ordinal)) { continue; }
                using var record = JsonDocument.Parse(line);
                var root = record.RootElement;
                if (!root.TryGetProperty("fn", out var fn) || fn.GetString() != "csv_rows") { continue; }
                if (!root.TryGetProperty("args", out var args)) { continue; }
                if (args.TryGetProperty("missing", out _)) { File.Delete(path); }
                else { File.WriteAllText(path, args.GetProperty("text").GetString(), new UTF8Encoding(false)); }
                if (!root.TryGetProperty("out", out var expected)) { continue; }
                var actual = PyJson.Dumps(new PayPeriodCsvAdapter(path).Rows().ToList());
                Assert.True(System.Text.Json.Nodes.JsonNode.DeepEquals(
                    System.Text.Json.Nodes.JsonNode.Parse(actual), System.Text.Json.Nodes.JsonNode.Parse(expected.GetRawText())));
                compared++;
            }
        }
        finally { File.Delete(path); }
        Assert.Equal(47, compared);
    }

    [Fact]
    public void DeferredProgramWageSourceFeedsRuleLibraryNyExcelsiorWithoutCreditReimplementation()
    {
        var rules = new JsonRulePackSource(new RulePackOptions { RulesDirectory = Path.Combine(SourceTestData.Root, "backend", "rules") });
        var baseLibrary = new RuleLibrary(rules);
        var wages = new ProgramWageSource(Path.Combine(SourceTestData.Root, "backend", "data", "payroll.csv"),
            key => baseLibrary.ProgramForCode(key)?.State ?? key);
        Assert.Equal(101528.16666666667, wages.AverageProgramWage("NY_EXCELSIOR"));
        var library = new RuleLibrary(rules, wages: wages);
        Assert.Equal(6599L, library.ApplyOneZeroProgramCredit("NY_EXCELSIOR", 20.0)["amount_per_job_usd"]);
    }

    [Fact]
    public void CsvAdapterRetainsCommittedPublicCertifiedPopulationAndBothMethodCounts()
    {
        var source = new CsvClientSource(Path.Combine(SourceTestData.Root, "backend", "data", "payroll_pay_periods.csv"), 7,
            new FiscalRuleAdapter(SourceTestData.Library(), new AbsentFiscalReader(), SourceTestData.Lookups(), holdsClientRules: false));
        var rows = source.LoadPayPeriods(7).Where(r => SourceValues.ParseIdentifier(r.Get("Tax_Year"), "Tax_Year") == 2024L
            && ((string)r.Get("Worksite_ID")!).StartsWith("GA_", StringComparison.Ordinal)).Select(r => r.Row).ToList();
        var pack = new OneZeroPack
        {
            MinWeeklyHours = PyNumber.OfFloat(35.0),
            MinWeeklyWages = PyNumber.OfFloat(686.0),
            WageBasis = "all_remuneration",
            Citation = "O.C.G.A. 48-7-40",
            TaxYear = 2024,
        };
        var window = (new DateOnly(2024, 1, 1), new DateOnly(2024, 12, 31));
        var mm = MinMaxMethod.Run(rows, 2024, window.Item1, pack, fiscalWindow: window);
        var pp = PayPeriodMethod.Run(rows, 2024, window.Item1, pack, fiscalWindow: window);
        Assert.Equal(81, mm.TotalHoursAndWages.Count);
        Assert.Equal(81, pp.TotalHoursAndWages.Count);
        Assert.Equal(51, mm.EligibleEmployees.Count);
        Assert.Equal(49, pp.EligibleEmployees.Count);
    }

    [Fact]
    [Trait("Category", "heavy")]
    public void MaterializedP2AllRowsControlsAndSelectedCertifiedResultsMatchPython312()
    {
        var mapping = SourceMapping.Load();
        var transport = MaterializedAnalyticsTransport.LoadP2(Path.Combine(SourceTestData.Root, "contract", "seed", "P2", "source"));
        var scanner = new SourceScanner(transport, mapping);
        var lookups = SourceTestData.Lookups();
        var source = new SqlClientSource(scanner, new PayrollProjector(mapping, lookups),
            new FiscalRuleAdapter(SourceTestData.Library(), new SqlFiscalRuleReader(scanner), lookups));
        var accounts = source.ListAccounts().Select(a => a.AccountId).ToArray();
        Assert.Equal(4, accounts.Length);
        using var oracle = SourceTestData.Oracle("p2", new { accounts });
        long total = 0;
        foreach (var expected in oracle.RootElement.EnumerateArray())
        {
            var projection = source.LoadProjection(expected.GetProperty("account").GetInt64())!;
            total += projection.Controls.PayrollRowsIn;
            Assert.Equal(expected.GetProperty("rows").GetInt32(), projection.Rows.Count);
            var hash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(PyJson.Dumps(projection.Rows.Select(r => r.Dict).ToList()))));
            Assert.Equal(expected.GetProperty("hash").GetString(), hash);
            ProjectionTests.AssertControls(projection.Controls, expected.GetProperty("controls"));
            var selected = projection.Rows.Where(r => r.Get("Tax_Year") is 2024L && r.Get("Work_State") as string == "GA").Select(r => r.Row).ToList();
            CompareMethods(selected, expected.GetProperty("methods"));
            var scope = source.PayrollScope(expected.GetProperty("account").GetInt64());
            Assert.Equal(projection.Rows.Count, scope.TotalRows);
        }
        Assert.Equal(197094, total);
    }

    private static void CompareMethods(List<PayrollRow> rows, JsonElement expected)
    {
        var pack = SourceTestData.Library().LoadPackOneZero("GA", 2024)!;
        var window = (new DateOnly(2024, 1, 1), new DateOnly(2024, 12, 31));
        var mm = MinMaxMethod.Run(rows, 2024, window.Item1, pack, fiscalWindow: window);
        var pp = PayPeriodMethod.Run(rows, 2024, window.Item1, pack, fiscalWindow: window);
        foreach (var (result, index) in new[] { (mm, 0), (pp, 1) })
        {
            Assert.Equal(expected[index][0].GetDouble(), result.AnnualAverage);
            Assert.Equal(expected[index][1].EnumerateArray().Select(e => e.GetString()).ToArray(),
                result.EligibleEmployees.Select(r => r.EmployeeId).Order(StringComparer.Ordinal).ToArray());
        }
        var reversed = rows.AsEnumerable().Reverse().ToList();
        var reversedMm = MinMaxMethod.Run(reversed, 2024, window.Item1, pack, fiscalWindow: window);
        var reversedPp = PayPeriodMethod.Run(reversed, 2024, window.Item1, pack, fiscalWindow: window);
        Assert.Equal(mm.AnnualAverage, reversedMm.AnnualAverage);
        Assert.Equal(pp.AnnualAverage, reversedPp.AnnualAverage);
        Assert.Equal(mm.EligibleEmployees.Select(r => r.EmployeeId).Order(StringComparer.Ordinal),
            reversedMm.EligibleEmployees.Select(r => r.EmployeeId).Order(StringComparer.Ordinal));
        Assert.Equal(pp.EligibleEmployees.Select(r => r.EmployeeId).Order(StringComparer.Ordinal),
            reversedPp.EligibleEmployees.Select(r => r.EmployeeId).Order(StringComparer.Ordinal));
    }

    private sealed class AbsentFiscalReader : IFiscalRuleReader
    {
        public bool IsConfigured => false;
        public IReadOnlyList<FiscalRule>? Read(long accountId) => throw new InvalidOperationException("CSV must not read fiscal SQL.");
    }

    [System.Diagnostics.CodeAnalysis.SuppressMessage("Performance", "CA1859",
        Justification = "This regression explicitly compiles and calls the original Domain interface, rather than the richer concrete adapter.")]
    private static IReadOnlyList<PayRow> ReadCertified(IPayrollSource source, long? account) => source.LoadPayPeriods(account);
}
