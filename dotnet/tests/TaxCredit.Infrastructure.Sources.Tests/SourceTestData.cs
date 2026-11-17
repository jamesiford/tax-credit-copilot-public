using System.Diagnostics;
using System.Text.Json;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure.Rules;
using TaxCredit.Infrastructure.Sources.Fiscal;
using TaxCredit.Infrastructure.Sources.Fixtures;
using TaxCredit.Infrastructure.Sources.Lookups;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Projection;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Infrastructure.Sources.Tests;

internal static class SourceTestData
{
    internal static string Root
    {
        get
        {
            var path = new DirectoryInfo(AppContext.BaseDirectory);
            while (path is not null && !Directory.Exists(Path.Combine(path.FullName, "backend", "rules"))) { path = path.Parent; }
            return path?.FullName ?? throw new InvalidOperationException("Repository root not found.");
        }
    }
    internal static RuleLibrary Library() => new(new JsonRulePackSource(new RulePackOptions
    {
        RulesDirectory = Path.Combine(Root, "backend", "rules"),
    }));
    internal static LookupResolver Lookups(SourceLookupOptions? options = null) => new(payCodeSeed:
        LookupResolver.LoadSeed(Path.Combine(Root, "backend", "rules", "lookups")), options: options);

    internal static Dictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>> MiniTables(SourceMapping? mapping = null)
    {
        var active = mapping ?? SourceMapping.Load();
        var tables = active.Tables.Values.ToDictionary(t => t.Physical,
            _ => (IReadOnlyList<IReadOnlyDictionary<string, object?>>)Array.Empty<IReadOnlyDictionary<string, object?>>(), StringComparer.Ordinal);
        Set("Account", Row(("account_id", 7L), ("name", "Synthetic One")), Row(("account_id", 8L), ("name", "Synthetic Two")));
        Set("Entity", Row(("entity_id", 70L), ("account_id", 7L), ("federal_tax_id", "SYNTHETIC"), ("fiscal_year_rules_id", 1L)),
            Row(("entity_id", 80L), ("account_id", 8L), ("federal_tax_id", "SYNTHETIC"), ("fiscal_year_rules_id", 2L)));
        Set("Location", Row(("location_id", 700L), ("account_id", 7L), ("address_id", 1L), ("client_location_id", "site")),
            Row(("location_id", 800L), ("account_id", 8L), ("address_id", 2L), ("client_location_id", "GA_existing")));
        Set("Address", Row(("address_id", 1L), ("state_county_zip_id", 1L), ("state_original", "sc")),
            Row(("address_id", 2L), ("state_county_zip_id", 2L)));
        Set("StateCountyZip", Row(("state_county_zip_id", 1L), ("state_abbr", ""), ("county_name", "Synthetic County")),
            Row(("state_county_zip_id", 2L), ("state_abbr", "GA"), ("county_name", "Synthetic County")));
        Set("PayCode", Row(("pay_code_id", 1L), ("account_id", 7L), ("pay_code", "REG")),
            Row(("pay_code_id", 2L), ("account_id", 8L), ("pay_code", "OT")));
        Set("Employment", Row(("employee_id", 101L), ("job_title", "Synthetic role")), Row(("employee_id", 201L)));
        Set("PayFrequency", Row(("pay_frequency_id", 77L), ("name", "Untrusted label")));
        Set("EntityFiscalYearRules", Row(("fiscal_year_rules_id", 1L), ("name", "Synthetic rule"),
                ("fiscal_year_begin", "2023-07-01"), ("fiscal_year_end", "2024-06-30"), ("inferred", true)),
            Row(("fiscal_year_rules_id", 2L), ("fiscal_year_begin", "2023-01-01"), ("fiscal_year_end", "2023-12-31")));
        Set("Payroll", Payroll(7, 1), Payroll(7, 2, null), Payroll(8, 3));
        return tables;

        void Set(string logical, params Dictionary<string, object?>[] rows)
        {
            var table = active.Tables[logical];
            tables[table.Physical] = rows.Select(row => (IReadOnlyDictionary<string, object?>)table.Fields.ToDictionary(
                f => f.Value.Column, f => row.TryGetValue(f.Key, out var value) ? value : null, StringComparer.Ordinal)).ToArray();
        }
    }

    internal static Dictionary<string, object?> Row(params (string Key, object? Value)[] values) =>
        values.ToDictionary(p => p.Key, p => p.Value, StringComparer.Ordinal);
    internal static Dictionary<string, object?> Payroll(long account, long id, string? paid = "2024-01-20") =>
        Row(("payroll_id", id), ("account_id", account), ("employee_id", account == 7 ? 101L : 201L),
            ("entity_id", account == 7 ? 70L : 80L), ("location_id", account == 7 ? 700L : 800L),
            ("pay_frequency_id", 77L), ("pay_period_start", "2024-01-01"), ("pay_period_end", "2024-01-14"),
            ("pay_date", paid), ("hours", "$80.00"), ("wages", "1,600.00"),
            ("pay_code_id", account == 7 ? 1L : 2L), ("worksite_location_id", account == 7 ? null : 800L),
            ("modify_date", "2024-02-01T03:04:05"));

    internal static (SqlClientSource Source, SourceScanner Scanner, RecordingTransport Transport) Source(
        Dictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>>? tables = null,
        SourceMapping? mapping = null, long limit = 10000, FootprintGuard? guard = null)
    {
        var active = mapping ?? SourceMapping.Load();
        var transport = new RecordingTransport(new MaterializedAnalyticsTransport(active, tables ?? MiniTables(active)));
        var scanner = new SourceScanner(transport, active, maximumRows: limit);
        var lookups = Lookups();
        return (new SqlClientSource(scanner, new PayrollProjector(active, lookups),
            new FiscalRuleAdapter(Library(), new SqlFiscalRuleReader(scanner), lookups), guard), scanner, transport);
    }

    internal static JsonDocument Oracle(string mode, object input)
    {
        var python = Environment.GetEnvironmentVariable("TCC_PYTHON") ?? throw new InvalidOperationException("TCC_PYTHON must select CPython 3.12.");
        var start = new ProcessStartInfo(python)
        {
            WorkingDirectory = Root,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        };
        start.ArgumentList.Add(Path.Combine(Root, "dotnet", "tests", "TaxCredit.Infrastructure.Sources.Tests", "source_oracle.py"));
        start.ArgumentList.Add(mode);
        start.Environment["PYTHONPATH"] = Path.Combine(Root, "backend");
        start.Environment["DATA_CLASSIFICATION"] = "synthetic";
        start.Environment["PAY_CODE_POLICY"] = "assume";
        start.Environment["LOOKUP_STORE"] = "none";
        using var process = Process.Start(start)!;
        process.StandardInput.Write(JsonSerializer.Serialize(input));
        process.StandardInput.Close();
        var stdout = process.StandardOutput.ReadToEndAsync();
        var stderr = process.StandardError.ReadToEndAsync();
        Assert.True(process.WaitForExit(180000), "Source oracle exceeded its bounded test deadline.");
        Assert.Equal(0, process.ExitCode);
        _ = stderr.GetAwaiter().GetResult();
        return JsonDocument.Parse(stdout.GetAwaiter().GetResult());
    }
}

internal sealed class RecordingTransport(IAnalyticsTransport inner) : IAnalyticsTransport
{
    public string SourceProvenance => inner.SourceProvenance;
    internal List<AnalyticsQuery> Queries { get; } = [];
    internal int DiscoveryCalls { get; private set; }
    internal int RowsSent { get; private set; }
    internal int DisposedStreams { get; private set; }
    internal Exception? Failure { get; set; }
    /// <summary>What the catalogue estimate query answers; null means the endpoint has no estimate.</summary>
    internal long? Estimate { get; set; }
    /// <summary>Statement kinds the server cancels at their own timeout.</summary>
    internal HashSet<string> TimeOut { get; } = [];
    public bool IsConfigured { get; set; } = true;
    public IReadOnlyList<string> Columns(string schema, string physicalTable, CancellationToken cancellationToken = default)
    {
        DiscoveryCalls++;
        if (Failure is not null) { throw Failure; }
        return inner.Columns(schema, physicalTable, cancellationToken);
    }
    public IEnumerable<IReadOnlyDictionary<string, object?>> Read(AnalyticsQuery query, CancellationToken cancellationToken = default)
    {
        Queries.Add(query);
        if (Failure is not null) { throw Failure; }
        if (TimeOut.Contains(query.Kind)) { throw new SourceTimedOut(query.TimeoutSeconds ?? 0); }
        if (query.Kind == "estimate")
        {
            if (Estimate is { } rows) { yield return new Dictionary<string, object?> { ["rows"] = rows }; }
            yield break;
        }
        try
        {
            foreach (var row in inner.Read(query, cancellationToken)) { RowsSent++; yield return row; }
        }
        finally { DisposedStreams++; }
    }
    public IDisposable SharedScope() => inner.SharedScope();
}
