using System.Globalization;
using TaxCredit.Infrastructure.Sources.Fixtures;
using TaxCredit.Infrastructure.Sources.Mapping;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Api.Tests.Bench;

/// <summary>
/// An in-memory stand-in for the SQL endpoint that serves one synthetic client of a chosen payroll size in the real source shape.
/// Small dimension tables come from the committed materialized fixture; payroll is generated lazily so a million rows never sits in memory twice.
/// </summary>
internal sealed class SyntheticAnalyticsTransport : IAnalyticsTransport
{
    internal const long AccountId = 5001;
    private const int Locations = 100;
    private const int PeriodsPerYear = 26;
    private const int FirstYear = 2022;
    private const int Years = 3;
    private readonly SourceMapping _mapping;
    private readonly MaterializedAnalyticsTransport _dimensions;
    private readonly long _employees;

    internal SyntheticAnalyticsTransport(long payrollRows)
    {
        _mapping = SourceMapping.Load();
        // A third of the staff are hired in each year, so headcount grows and a base year, net-new jobs and a credit all exist.
        _employees = Math.Max(1, payrollRows / (PeriodsPerYear * 2));
        RowCount = Enumerable.Range(0, (int)_employees).Sum(e => (long)(Years - HireIndex(e)) * PeriodsPerYear);
        _dimensions = new MaterializedAnalyticsTransport(_mapping, Dimensions());
    }

    /// <summary>The number of payroll rows this client holds.</summary>
    internal long RowCount { get; }

    /// <summary>Counts each logical Payroll scan so a harness can report how often the source is read.</summary>
    internal int PayrollScans { get; private set; }

    public string SourceProvenance => "synthetic-bench-transport";

    public bool IsConfigured => true;

    public IReadOnlyList<string> Columns(string schema, string physicalTable, CancellationToken cancellationToken = default) =>
        _dimensions.Columns(schema, physicalTable, cancellationToken);

    public IEnumerable<IReadOnlyDictionary<string, object?>> Read(AnalyticsQuery query, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(query);
        if (query.Table != "Payroll") { return _dimensions.Read(query, cancellationToken); }
        if (query.Kind == "fingerprint")
        {
            return [new Dictionary<string, object?> { ["row_count"] = RowCount, ["maximum_modified"] = "2025-02-01T03:04:05" }];
        }
        if (query.Kind != "scan") { return _dimensions.Read(query, cancellationToken); }
        PayrollScans++;
        return Payroll(query, cancellationToken);
    }

    public IDisposable SharedScope() => _dimensions.SharedScope();

    private IEnumerable<IReadOnlyDictionary<string, object?>> Payroll(AnalyticsQuery query, CancellationToken cancellationToken)
    {
        long id = 0;
        for (var year = 0; year < Years; year++)
        {
            var first = new DateOnly(FirstYear + year, 1, 1);
            for (var period = 0; period < PeriodsPerYear; period++)
            {
                var start = first.AddDays(period * 14);
                for (long employee = 0; employee < _employees; employee++)
                {
                    if (HireIndex(employee) > year) { continue; }
                    cancellationToken.ThrowIfCancellationRequested();
                    var hours = 64 + ((employee * 7 + period * 3) % 25);
                    var rate = 10 + (employee % 15);
                    var location = employee % Locations;
                    var row = new Dictionary<string, object?>
                    {
                        ["payroll_id"] = ++id,
                        ["account_id"] = AccountId,
                        ["employee_id"] = 100_000 + employee,
                        ["entity_id"] = 70L,
                        ["location_id"] = 7000 + location,
                        ["pay_frequency_id"] = 77L,
                        ["pay_period_start"] = Iso(start),
                        ["pay_period_end"] = Iso(start.AddDays(13)),
                        ["pay_date"] = Iso(start.AddDays(18)),
                        ["hours"] = hours.ToString("0.00", CultureInfo.InvariantCulture),
                        ["wages"] = (hours * rate).ToString("0.00", CultureInfo.InvariantCulture),
                        ["pay_code_id"] = 1L,
                        ["worksite_location_id"] = null,
                        ["modify_date"] = "2025-02-01T03:04:05",
                    };
                    yield return query.Columns.ToDictionary(p => p.Key, p => row[p.Key], StringComparer.Ordinal);
                }
            }
        }
    }

    private static int HireIndex(long employee) => (int)(employee % Years);
    private static string Iso(DateOnly date) => date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    private Dictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>> Dimensions()
    {
        var tables = _mapping.Tables.Values.ToDictionary(t => t.Physical,
            _ => (IReadOnlyList<IReadOnlyDictionary<string, object?>>)[], StringComparer.Ordinal);
        Set("Account", Row(("account_id", AccountId), ("name", "Synthetic Bench Client")));
        Set("Entity", Row(("entity_id", 70L), ("account_id", AccountId), ("federal_tax_id", "SYNTHETIC"), ("fiscal_year_rules_id", 1L)));
        Set("Location", Enumerable.Range(0, Locations).Select(i => Row(("location_id", 7000L + i), ("account_id", AccountId),
            ("address_id", 1L + i), ("client_location_id", "site-" + i.ToString(CultureInfo.InvariantCulture)))).ToArray());
        Set("Address", Enumerable.Range(0, Locations).Select(i => Row(("address_id", 1L + i), ("state_county_zip_id", 1L))).ToArray());
        Set("StateCountyZip", Row(("state_county_zip_id", 1L), ("state_abbr", "GA"), ("county_name", "Synthetic County")));
        Set("PayCode", Row(("pay_code_id", 1L), ("account_id", AccountId), ("pay_code", "REG")));
        Set("Employment", Enumerable.Range(0, (int)_employees).Select(i => Row(("employee_id", 100_000L + i),
            ("job_title", "Synthetic role"))).ToArray());
        Set("PayFrequency", Row(("pay_frequency_id", 77L), ("name", "Biweekly")));
        Set("EntityFiscalYearRules", Row(("fiscal_year_rules_id", 1L), ("name", "Synthetic rule"),
            ("fiscal_year_begin", "2024-01-01"), ("fiscal_year_end", "2024-12-31"), ("inferred", false)));
        return tables;

        void Set(string logical, params Dictionary<string, object?>[] rows)
        {
            var table = _mapping.Tables[logical];
            tables[table.Physical] = rows.Select(row => (IReadOnlyDictionary<string, object?>)table.Fields.ToDictionary(
                f => f.Value.Column, f => row.TryGetValue(f.Key, out var value) ? value : null, StringComparer.Ordinal)).ToArray();
        }
    }

    private static Dictionary<string, object?> Row(params (string Key, object? Value)[] values) =>
        values.ToDictionary(p => p.Key, p => p.Value, StringComparer.Ordinal);
}
