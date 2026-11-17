using System.Globalization;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Sources.Lookups;
using TaxCredit.Infrastructure.Sources.Mapping;

namespace TaxCredit.Infrastructure.Sources.Projection;

/// <summary>Logical source to certified engine rows. Fiscal trimming, short-period filtering and collapse belong to the engine, never here.</summary>
public sealed partial class PayrollProjector(SourceMapping mapping, LookupResolver lookups)
{
    /// <summary>Projects every source row with a usable span/effective date, retaining lineage and assumption controls.</summary>
    public PayrollProjection Project(SourceDataset dataset)
    {
        ArgumentNullException.ThrowIfNull(dataset);
        var entities = Index(dataset.Rows("Entity"), "entity_id");
        var employment = Index(dataset.Rows("Employment"), "employee_id");
        var locations = Dimensions(dataset);
        var codes = Index(dataset.Rows("PayCode"), "pay_code_id");
        var resolved = codes.ToDictionary(c => c.Key, c => lookups.PayCode(dataset.AccountId,
            SourceValues.Text(c.Value, "pay_code"), SourceValues.Id(c.Value, "pay_code_category_id")));
        var unmappedRows = dataset.Rows("Payroll").Count(p => SourceValues.Id(p, "pay_code_id") is { } id
            && resolved.TryGetValue(id, out var code) && code.Category is null);
        var distinctUnmapped = dataset.Rows("Payroll").Select(p => SourceValues.Id(p, "pay_code_id"))
            .OfType<long>().Distinct().Count(id => resolved.TryGetValue(id, out var code) && code.Category is null);
        if (lookups.Options.EffectivePayCodePolicy == "strict" && unmappedRows > 0)
        {
            throw new UnmappedPayCodes(unmappedRows, distinctUnmapped);
        }
        var rows = new List<PayRow>();
        var counters = new Counters();
        var context = new ProjectionDimensions(entities, employment, locations, codes, resolved);
        foreach (var payroll in dataset.Rows("Payroll"))
        {
            AddRow(payroll, dataset.AccountId, rows, counters, context);
        }
        var providers = resolved.Values.GroupBy(r => r.Provider).ToDictionary(g => g.Key, g => g.Count(), StringComparer.Ordinal);
        var controls = new ProjectionControls(dataset.Rows("Payroll").Count, rows.Count, counters.NoSpan,
            counters.NullDates, counters.Imputed, counters.Excluded, counters.NullHours, counters.NullWages,
            counters.WorksiteFallbacks, unmappedRows, counters.Defaulted, resolved.Values.Count(r => r.Inferred),
            providers, rows.Count(r => string.IsNullOrEmpty((string?)r.Get("Work_County"))),
            rows.Select(r => r.Get("Employee_ID")).Distinct().Count(), rows.Select(r => r.Get("Worksite_ID")).Distinct().Count(),
            rows.Select(r => r.Get("Entity_FEIN")).Distinct().Count());
        return new PayrollProjection(rows, controls, dataset.MissingTables, "logical-source-to-silver");
    }

    /// <summary>Span-derived frequency, never a surrogate-key multiplier.</summary>
    public static string FrequencyLabel(DateOnly start, DateOnly end)
    {
        var days = end.DayNumber - start.DayNumber + 1;
        return days switch
        {
            1 => "daily",
            >= 5 and <= 8 => "weekly",
            >= 13 and <= 14 => "biweekly",
            >= 15 and <= 16 => "semimonthly",
            >= 27 and <= 31 => "monthly",
            _ => days.ToString(CultureInfo.InvariantCulture) + "d",
        };
    }

    private static long RequiredId(IReadOnlyDictionary<string, object?> row, string key) =>
        SourceValues.Id(row, key) ?? throw new SourceSchemaMismatch("Payroll", [key]);
    private static string Iso(DateOnly date) => date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    private static Dictionary<long, IReadOnlyDictionary<string, object?>> Index(
        IEnumerable<IReadOnlyDictionary<string, object?>> rows, string key)
    {
        var output = new Dictionary<long, IReadOnlyDictionary<string, object?>>();
        foreach (var row in rows)
        {
            if (SourceValues.Id(row, key) is { } id) { output[id] = row; }
        }
        return output;
    }
    private static Dictionary<long, LocationDimension> Dimensions(SourceDataset dataset)
    {
        var addresses = Index(dataset.Rows("Address"), "address_id");
        var counties = Index(dataset.Rows("StateCountyZip"), "state_county_zip_id");
        var output = new Dictionary<long, LocationDimension>();
        foreach (var loc in dataset.Rows("Location"))
        {
            var id = SourceValues.Id(loc, "location_id");
            if (id is null) { continue; }
            var addressId = SourceValues.Id(loc, "address_id");
            var address = addressId is { } a && addresses.TryGetValue(a, out var addr) ? addr : null;
            var countyId = address is null ? null : SourceValues.Id(address, "state_county_zip_id");
            var county = countyId is { } c && counties.TryGetValue(c, out var co) ? co : null;
            var state = county is null ? "" : SourceValues.Text(county, "state_abbr");
            if (state.Length == 0 && address is not null) { state = SourceValues.Text(address, "state_original"); }
            state = state.ToUpperInvariant();
            var unit = SourceValues.Text(loc, "client_location_id");
            if (unit.Length == 0) { unit = id.Value.ToString(CultureInfo.InvariantCulture); }
            if (state.Length > 0 && !unit.StartsWith(state + "_", StringComparison.Ordinal)) { unit = state + "_" + unit; }
            output[id.Value] = new LocationDimension(unit, state, county is null ? "" : SourceValues.Text(county, "county_name"));
        }
        return output;
    }
    private sealed record LocationDimension(string Unit, string State, string County);
    private sealed class Counters
    {
        internal long NoSpan, NullDates, Imputed, Excluded, NullHours, NullWages, WorksiteFallbacks, Defaulted;
    }
}
