using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Pipeline;
using static TaxCredit.Application.Features.ReadsCalc.ReadValues;

namespace TaxCredit.Application.Features.ReadsCalc.Stored;

/// <summary>Reads the accepted population; display floors never replace a stored eligibility verdict.</summary>
public sealed class StoredEligibility(IGoldReadPort gold, ReadStatutes resolver)
{
    /// <summary>Returns both methods and whole-population counts independently of the page's narrowing.</summary>
    public object Read(ReadArguments args)
    {
        ArgumentNullException.ThrowIfNull(args);
        var client = args.Client();
        var year = args.WholeNumber("tax_year");
        var resolved = resolver.ResolveStatute(client, args.Text("state"), year, args.Text("program_code"), true);
        if (client is null)
        {
            throw new ReadRefusalException(404, "Select a client to read its eligibility population.");
        }
        var options = Options(args, resolved.ProgramCode);
        using var scope = gold.Scope();
        var read = gold.EligibilityPopulation(client.Value, year, Number(resolved.Floors.MinWeeklyHours),
            Number(resolved.Floors.MinWeeklyWages), options);
        var output = Map(("account_id", client), ("state", resolved.State), ("program_code", resolved.ProgramCode),
            ("tax_year", year), ("thresholds", resolved.Floors.AsDict()), ("fiscal", resolved.Window.AsDict()),
            ("run", read["run"]));
        var summary = Child(read, "summary");
        if (summary is null)
        {
            output["calculation_state"] = "not_calculated";
            output["message"] = $"TY{year} has not been calculated for this client. It carries no figure - not a zero.";
            foreach (var key in new[] { "employees_evaluated", "min_max_eligible", "pay_period_eligible", "near_floor", "eligible_either_method", "total" })
            {
                output[key] = 0;
            }
            output["reconciliation"] = Map();
            output["rows"] = Array.Empty<object>();
            return output;
        }
        output["calculation_state"] = "calculated";
        output["statute_matches_run"] = Map(("matches", Count(summary.GetValueOrDefault("verdict_disagreements")) == 0),
            ("verdict_disagreements", Count(summary.GetValueOrDefault("verdict_disagreements"))),
            ("resolved_rule_pack_source", resolved.Floors.AsDict()["source"]));
        foreach (var key in new[] { "employees_evaluated", "min_max_eligible", "pay_period_eligible", "near_floor" })
        {
            output[key] = Count(summary[key]);
        }
        output["eligible_either_method"] = Count(summary["eligible_either"]);
        output["reconciliation"] = Map(("eligible_both", Count(summary["eligible_both"])),
            ("min_max_only", Count(summary["min_max_only"])), ("pay_period_only", Count(summary["pay_period_only"])),
            ("neither", Count(summary["neither"])));
        output["total"] = read["matching"];
        output["rows"] = Rows(read, "rows").Select(row => Map(("record_token", row["record_token"]),
            ("employee_id", row["employee_id"]), ("status", row["status"]), ("near_floor", Bool(row["near_floor"])),
            ("totals", Map(("hours", Number(row.GetValueOrDefault("total_hours"))), ("wages", Number(row.GetValueOrDefault("total_wages"))))),
            ("min_max", Verdict(row, "mm", resolved.Floors)), ("pay_period", Verdict(row, "pp", resolved.Floors)))).ToArray();
        return output;
    }

    private static EligibilityOptions Options(ReadArguments args, string program)
    {
        var status = args.Text("status", "all")!;
        var sort = args.Text("sort", "employee_id")!;
        var order = args.Text("order", "asc")!.ToLowerInvariant();
        if (status is not ("all" or "both" or "min_max_only" or "pay_period_only" or "neither")
            || sort is not ("employee_id" or "status" or "near_floor" or "total_hours" or "total_wages" or "mm_weeks" or "mm_hours" or "pp_weeks" or "pp_hours")
            || order is not ("asc" or "desc"))
        {
            throw new ReadRefusalException(422, "Unsupported eligibility status or ordering.");
        }
        return new EligibilityOptions
        {
            Status = status,
            Sort = sort,
            Order = order,
            NearFloor = args.Flag("near_floor"),
            Q = args.Text("q", "")!,
            Limit = args.WholeNumber("limit", 50),
            Offset = args.WholeNumber("offset"),
            ProgramCode = program
        };
    }

    private static Dictionary<string, object?> Verdict(IReadOnlyDictionary<string, object?> row, string prefix, StatutoryFloors floors)
    {
        var hours = row.GetValueOrDefault(prefix + "_hours");
        if (hours is null)
        {
            return Map(("weeks", null), ("avg_hours", null), ("avg_wages", null),
                ("passed_hours", false), ("passed_wages", false), ("eligible", false));
        }
        var wages = Number(row.GetValueOrDefault(prefix + "_wages"));
        return Map(("weeks", Number(row.GetValueOrDefault(prefix + "_weeks"))), ("avg_hours", Number(hours)),
            ("avg_wages", wages), ("passed_hours", Number(hours) >= Number(floors.MinWeeklyHours)),
            ("passed_wages", wages >= Number(floors.MinWeeklyWages)),
            ("eligible", Bool(row.GetValueOrDefault(prefix + "_eligible"))));
    }
}
