using System.Globalization;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Sources.Lookups;

namespace TaxCredit.Infrastructure.Sources.Projection;

public sealed partial class PayrollProjector
{
    private void AddRow(IReadOnlyDictionary<string, object?> p, long accountId, List<PayRow> output,
        Counters count, ProjectionDimensions context)
    {
        var facts = ReadFacts(p, count);
        if (facts is null) { return; }
        var rawLocation = RequiredId(p, "location_id");
        var worksite = SourceValues.Id(p, "worksite_location_id");
        var selected = mapping.WorksiteMode switch
        {
            "location_only" => rawLocation,
            "worksite_only" => worksite,
            _ => worksite is not null and not 0 ? worksite : rawLocation,
        };
        var dimension = selected is { } loc && context.Locations.TryGetValue(loc, out var d) ? d : null;
        output.Add(BuildRow(p, accountId, facts, context, ResolveCode(p, context, count), dimension, selected));
    }

    private RowFacts? ReadFacts(IReadOnlyDictionary<string, object?> p, Counters count)
    {
        var start = SourceValues.Date(p, "pay_period_start");
        var end = SourceValues.Date(p, "pay_period_end");
        var actualPaid = SourceValues.Date(p, "pay_date");
        var hours = SourceValues.Number(p, "hours");
        var wages = SourceValues.Number(p, "wages");
        if (hours is null) { count.NullHours++; }
        if (wages is null) { count.NullWages++; }
        if (actualPaid is null) { count.NullDates++; }
        if (SourceValues.Id(p, "worksite_location_id") is null) { count.WorksiteFallbacks++; }
        if (start is null || end is null) { count.NoSpan++; return null; }
        var paid = actualPaid ?? (mapping.NullPayDateMode == "period_end" ? end : null);
        if (paid is null) { count.Excluded++; return null; }
        if (actualPaid is null) { count.Imputed++; }
        return new RowFacts(start.Value, end.Value, actualPaid, paid.Value, hours ?? 0.0, wages ?? 0.0);
    }

    private static CodeDetail ResolveCode(IReadOnlyDictionary<string, object?> p, ProjectionDimensions context, Counters count)
    {
        var codeId = SourceValues.Id(p, "pay_code_id");
        var known = codeId is { } id && context.Resolved.ContainsKey(id);
        var category = known ? context.Resolved[codeId!.Value].Category : "Regular";
        var text = codeId is { } cid && context.Codes.TryGetValue(cid, out var sourceCode) ? SourceValues.Text(sourceCode, "pay_code") : "";
        if (!known) { count.Defaulted++; }
        return new CodeDetail(category, text, known);
    }

    private static PayRow BuildRow(IReadOnlyDictionary<string, object?> p, long accountId, RowFacts facts,
        ProjectionDimensions context, CodeDetail code, LocationDimension? dimension, long? selected)
    {
        var employee = RequiredId(p, "employee_id");
        var entity = RequiredId(p, "entity_id");
        var row = new PyDict().Set("Tax_Year", (long)facts.Paid.Year).Set("Employee_ID", employee.ToString(CultureInfo.InvariantCulture))
            .Set("Job_Title", context.Employment.TryGetValue(employee, out var job) ? SourceValues.Text(job, "job_title") : "")
            .Set("Worksite_ID", dimension?.Unit ?? selected?.ToString(CultureInfo.InvariantCulture) ?? "None")
            .Set("Work_State", dimension?.State ?? "").Set("Work_County", dimension?.County ?? "")
            .Set("Entity_FEIN", context.Entities.TryGetValue(entity, out var ent) ? SourceValues.Text(ent, "federal_tax_id") : "")
            .Set("Pay_Period_Start", Iso(facts.Start)).Set("Pay_Period_End", Iso(facts.End)).Set("Pay_Date", Iso(facts.Paid))
            .Set("_Pay_Date_Imputed", facts.ActualPaid is null).Set("Pay_Frequency", FrequencyLabel(facts.Start, facts.End))
            .Set("_Source_Pay_Frequency_Id", SourceValues.Id(p, "pay_frequency_id"))
            .Set("Pay_Code", code.Category ?? code.Text.Trim()).Set("_Source_Pay_Code", code.Text)
            .Set("_Pay_Code_Unmapped", code.Known && code.Category is null).Set("_Pay_Code_Defaulted", !code.Known)
            .Set("Hours_Worked", facts.Hours).Set("Gross_Wages", facts.Wages)
            .Set("_Source_Payroll_Id", SourceValues.Id(p, "payroll_id")).Set("_Source_Account_Id", accountId);
        return PayRow.Of(row);
    }

    private sealed record RowFacts(DateOnly Start, DateOnly End, DateOnly? ActualPaid, DateOnly Paid, double Hours, double Wages);
    private sealed record CodeDetail(string? Category, string Text, bool Known);
    private sealed record ProjectionDimensions(Dictionary<long, IReadOnlyDictionary<string, object?>> Entities,
        Dictionary<long, IReadOnlyDictionary<string, object?>> Employment, Dictionary<long, LocationDimension> Locations,
        Dictionary<long, IReadOnlyDictionary<string, object?>> Codes, Dictionary<long, PayCodeResolution> Resolved);
}
