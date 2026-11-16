using System.Text.Json;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Pipeline;
using static TaxCredit.Application.Features.ReadsCalc.ReadValues;

namespace TaxCredit.Application.Features.ReadsCalc.Stored;

/// <summary>The matrix and its counts are the run's stored answer, not an engine replay.</summary>
public sealed class StoredMatrix(IGoldReadPort gold, ReadStatutes resolver)
{
    /// <summary>Shapes the accepted allocation while naming a year the run has never reached.</summary>
    public object Read(ReadArguments args)
    {
        ArgumentNullException.ThrowIfNull(args);
        var client = args.Client() ?? throw new ReadRefusalException(404, "Select a client to read its One/Zero matrix.");
        var year = args.WholeNumber("tax_year");
        var method = args.Method();
        var statute = resolver.ResolveStatute(client, args.Text("state", "GA"), year, args.Text("program_code"), true);
        using var scope = gold.Scope();
        var read = gold.OnezeroMatrix(client, year, method, statute.ProgramCode);
        var output = Map(("account_id", client), ("state", statute.State), ("program_code", statute.ProgramCode),
            ("tax_year", year), ("method", method), ("thresholds", statute.Floors.AsDict()), ("fiscal", statute.Window.AsDict()),
            ("run", read["run"]), ("flags", Array.Empty<object>()));
        var summary = Child(read, "summary");
        if (summary is null)
        {
            output["calculation_state"] = "not_calculated";
            output["message"] = $"TY{year} has not been calculated for this client. It carries no figure - not a zero.";
            foreach (var key in new[] { "units", "matrix_rows", "eligible_employees", "annual_average", "contested_months" })
            {
                output[key] = 0;
            }
            foreach (var key in new[] { "months", "summary", "matrix" })
            {
                output[key] = Array.Empty<object>();
            }
            return output;
        }
        output["calculation_state"] = "calculated";
        output["months"] = JsonSerializer.Deserialize<string[]>(Text(summary["month_ends"]));
        output["units"] = Count(summary["unit_fein_rows"]);
        output["matrix_rows"] = Count(summary["matrix_rows"]);
        output["eligible_employees"] = Count(summary["eligible_employees"]);
        output["annual_average"] = Number(summary["annual_average"]);
        output["contested_months"] = Count(summary["contested_months"]);
        output["summary"] = Rows(read, "units").Select(row => Map(("unit_id", row["worksite_id"]), ("fein", row["entity_fein"]),
            ("month_totals", Months(row)), ("total", Number(row["total"])), ("average_headcount", Number(row["average_headcount"])))).ToArray();
        output["matrix"] = Rows(read, "matrix").Select(row => Map(("record_token", row["record_token"]), ("employee_id", row["employee_id"]),
            ("unit_id", row["worksite_id"]), ("fein", row["entity_fein"]), ("months", Months(row)),
            ("weight", Number(row["weight"]) is 0 ? 1.0 : Number(row["weight"])))).ToArray();
        return output;
    }

    internal static double[] Months(IReadOnlyDictionary<string, object?> row) =>
        Enumerable.Range(1, 12).Select(i => Number(row.GetValueOrDefault(FormattableString.Invariant($"month_{i:00}")))).ToArray();
}
