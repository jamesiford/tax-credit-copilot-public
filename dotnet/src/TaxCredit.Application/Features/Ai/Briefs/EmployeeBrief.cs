using System.Globalization;
using System.Text.Json.Nodes;
using static TaxCredit.Application.Features.Ai.Briefs.BriefValues;

namespace TaxCredit.Application.Features.Ai.Briefs;

/// <summary>An employee brief reads each recorded verdict without re-deciding eligibility.</summary>
public static class EmployeeBrief
{
    /// <summary>The person-facing facts are never supplied to a model.</summary>
    public static PageBrief Build(JsonObject drill, bool placeholder = false)
    {
        ArgumentNullException.ThrowIfNull(drill);
        var year = drill["tax_year"];
        var employee = Text(drill["employee_id"]);
        var thresholds = Object(drill["thresholds"]);
        var floorHours = Number(thresholds["minimum_average_weekly_hours"]);
        var floorWages = thresholds["minimum_average_weekly_wages_usd"];
        var rows = Rows(drill["raw_source_rows"]).ToArray();
        var included = rows.Count(r => Text(r["selection_decision"]) == "included");
        var facts = new List<string>
        {
            string.Create(CultureInfo.InvariantCulture, $"Employee {employee}, TY{year}: {Plural(rows.Length, "pay period")} on record, {included} included.")
        };
        foreach (var (key, label) in new[] { ("min_max", "Min-Max"), ("pay_period", "Pay Period") })
        {
            if (Object(drill["step1"])[key] is not JsonObject method) { continue; }
            var verdict = True(method["eligible"]) ? "eligible" : "not eligible";
            var hours = Number(method["rounded_avg_weekly_hours"]) ?? Number(method["avg_weekly_hours"]);
            var wages = method["rounded_avg_weekly_wages"] ?? method["avg_weekly_wages"];
            facts.Add(hours is { } h && Number(wages) is not null && floorHours is { } f
                ? $"{label}: {verdict} \u2014 {Fixed(h, 2)} hrs/week against {General(f)}, {Usd(wages)}/week against {Usd(floorWages)}."
                : $"{label}: {verdict}.");
        }
        AddAllocation(drill, facts);
        var caveats = placeholder
            ? new[] { string.Create(CultureInfo.InvariantCulture, $"TY{year}'s wage floor is a placeholder carried forward from TY{Integer(year) - 1}.") }
            : [];
        return new("employee", $"employee {employee}", facts[0], facts, caveats, new JsonObject
        {
            ["employee_id"] = employee,
            ["tax_year"] = year?.DeepClone(),
            ["periods"] = rows.Length,
            ["included"] = included
        });
    }

    private static void AddAllocation(JsonObject drill, List<string> facts)
    {
        var onezero = Object(drill["onezero"]);
        if (onezero["months"] is not JsonArray months || months.Count == 0) { return; }
        var matrix = Rows(onezero["min_max"]).ToArray();
        if (matrix.Length == 0) { return; }
        var reached = Enumerable.Range(0, months.Count).Count(index => matrix.Any(row =>
            row["months"] is JsonArray values && index < values.Count && Number(values[index]) is > 0));
        var units = matrix.Select(r => Text(r["unit_id"])).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal);
        facts.Add(string.Create(CultureInfo.InvariantCulture, $"Counted in {reached} of {months.Count} measuring months under Min-Max, at {string.Join(", ", units)}."));
    }
}
