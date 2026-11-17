using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using static TaxCredit.Application.Features.ReadsCalc.ReadValues;

namespace TaxCredit.Application.Features.ReadsCalc.Ingestion;

public sealed partial class IngestionViews
{
    private static readonly Dictionary<string, (string Field, bool Numeric)> Sorts =
        new Dictionary<string, (string, bool)>(StringComparer.Ordinal)
        {
            ["employee"] = ("Employee_ID", false),
            ["worksite"] = ("Worksite_ID", false),
            ["fein"] = ("Entity_FEIN", false),
            ["pps"] = ("Pay_Period_Start", false),
            ["ppe"] = ("Pay_Period_End", false),
            ["pay_date"] = ("Pay_Date", false),
            ["tax_year"] = ("Tax_Year", true),
            ["hours"] = ("Hours_Worked", true),
            ["wages"] = ("Gross_Wages", true),
            ["pay_code"] = ("Pay_Code", false),
        };

    private static readonly string[] SearchFields = ["Employee_ID", "Worksite_ID", "Entity_FEIN", "Pay_Date", "Pay_Code"];

    /// <summary>Cash-basis source browsing sorts and searches before paging; it never claims to be the run population.</summary>
    public object Rows(ReadArguments args)
    {
        ArgumentNullException.ThrowIfNull(args);
        var client = args.Client();
        var year = args.WholeNumber("tax_year");
        var state = args.Text("state", "GA")!.ToUpperInvariant();
        var search = args.Text("q", "")!.Trim().ToLowerInvariant();
        var rows = PayrollRows.RequirePayPeriods(source, annotations.Resolutions(client), accountId: client)
            .Where(row => row.PayDateText().StartsWith(Text(year), StringComparison.Ordinal)
                && Text(row.Get("Worksite_ID")).StartsWith(state + "_", StringComparison.Ordinal)
                && (search.Length == 0 || SearchFields
                    .Any(field => Text(row.Get(field)).Contains(search, StringComparison.OrdinalIgnoreCase)))).ToArray();
        var sort = args.Text("sort", "employee")!;
        var order = args.Text("order", "asc")!.ToLowerInvariant();
        var sorted = Sort(rows, sort, order);
        var limit = Math.Clamp(args.WholeNumber("limit", 25), 1, 200);
        var offset = Math.Max(0, args.WholeNumber("offset"));
        return Map(("tax_year", year), ("state", state), ("q", search), ("total", rows.Length), ("offset", offset), ("limit", limit),
            ("sort", sort), ("order", order), ("rows", sorted.Skip(offset).Take(limit).Select(row =>
            {
                var output = Raw(row);
                output["Worksite_Name"] = SiteLabels.Name(Text(row.Get("Worksite_ID")));
                return output;
            }).ToArray()));
    }

    private static IEnumerable<PayRow> Sort(PayRow[] rows, string sort, string order)
    {
        if (!Sorts.TryGetValue(sort, out var spec))
        {
            return rows.OrderBy(row => Text(row.Get("Employee_ID")), PyStr.Comparer).ThenBy(row => row.PayDateText(), PyStr.Comparer);
        }
        var comparison = Comparer<PayRow>.Create((left, right) =>
        {
            var a = Text(left.Get(spec.Field));
            var b = Text(right.Get(spec.Field));
            var primary = spec.Numeric ? Number(left.Get(spec.Field)).CompareTo(Number(right.Get(spec.Field)))
                : (a.Length == 0).CompareTo(b.Length == 0);
            if (primary == 0 && !spec.Numeric)
            {
                primary = PyStr.Comparer.Compare(a, b);
            }
            if (primary == 0)
            {
                primary = PyStr.Comparer.Compare(spec.Numeric ? Text(left.Get("Employee_ID")) : left.PayDateText(),
                    spec.Numeric ? Text(right.Get("Employee_ID")) : right.PayDateText());
            }
            return order == "desc" ? -primary : primary;
        });
        return rows.Order(comparison);
    }

    private static readonly object[] FieldMap =
    [
        Field("Employee_ID", "employee_id", "surrogate key (PII-minimal)"),
        Field("Worksite_ID", "worksite_id", "unit granularity + worksite join (DATA-04)"),
        Field("Entity_FEIN", "legal_entity_fein", "legal entity / cost centre"),
        Field("Pay_Period_Start", "pay_period_start", "true-weeks basis"),
        Field("Pay_Period_End", "pay_period_end", "measuring-date anchor"),
        Field("Pay_Date", "pay_date", "cash-basis fiscal-year anchor (DATA-06)"),
        Field("Hours_Worked", "hours_worked", "weekly-hours floor input"),
        Field("Gross_Wages", "gross_wages", "weekly-wage floor input"),
        Field("Pay_Code", "pay_code / includable", "wage-basis classification (DATA-05 / CALC-11)"),
    ];

    private static Dictionary<string, object?> Field(string source, string canonical, string note) =>
        Map(("source", source), ("canonical", canonical), ("note", note));
}
