using System.Numerics;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Parity.Tests;

/// <summary>Replays one helper call of <c>gold_payload.jsonl.gz</c> (program defaults, payroll rows, QC resolutions) against the C# port.</summary>
internal static partial class PayloadHelperInvoke
{
    private static PayloadWorld World => PayloadWorld.Instance;

    private static ProgramDefaults Defaults { get; } = World.DefaultsOver(World.Csv);

    private static PayrollRows Rows { get; } = new(World.Library, Defaults);

    public static object? Invoke(PyDict call)
    {
        var a = (PyDict)GoldReplay.Decode(call["args"])!;
        return (string)call["fn"]! switch
        {
            "calculable_states" => Strings(Defaults.CalculableStates(MaybeLong(a["tax_year"]))),
            "calculable_programs_for_state" => Strings(Defaults.CalculableProgramsForState((string)a["state"]!, MaybeLong(a["tax_year"]))),
            "pick_state" => Defaults.PickState(((List<object?>)a["client_states"]!).Select(s => (string)s!).ToList(), MaybeLong(a["tax_year"])),
            "derive_run_state" => Defaults.DeriveRunState(MaybeLong(a["client_id"]), MaybeLong(a["tax_year"]), (string?)a["requested"]),
            "derive_run_programs" => Strings(Defaults.DeriveRunPrograms(MaybeLong(a["client_id"]), MaybeLong(a["tax_year"]))),
            "state_for_location" => Defaults.StateForLocation(MaybeLong(a["client_id"]), (string)a["worksite_id"]!, MaybeLong(a["tax_year"]), (string?)a["requested"]),
            "check_program_state" => CheckState(a),
            "program_state" => Defaults.ProgramState((string)a["program_code"]!),
            "location_state" => Defaults.LocationState(MaybeLong(a["client_id"]), (string)a["worksite_id"]!, (string?)a["state"], (string?)a["program_code"]),
            "resolve_program" => Resolved(a),
            "priced_program" => Priced(a),
            "run_state" => Defaults.RunState(MaybeLong(a["client_id"]), MaybeLong(a["tax_year"]), (string?)a["state"], (string?)a["program_code"]),
            "programs_to_price" => Strings(Defaults.ProgramsToPrice((string)a["state"]!)),
            "program_code_for_state" => Defaults.ProgramCodeForState((string)a["state"]!),
            "state_programs" => Defaults.StatePrograms().Select(p => (object?)new List<object?> { p.State, p.Code }).ToList(),
            "rows_of_program" => ProgramDefaults.RowsOfProgram(GoldReplay.Rows(a["rows"]), (string?)a["program_code"]).Select(r => (object?)r).ToList(),
            "ProgramChoiceRequired" => Choice(a),
            "program_rows" => Digest(PayrollRows.ProgramRows(RowsOf((string)a["rows"]!), (string)a["program_state"]!)),
            "states_present" => Strings(PayrollRows.StatesPresent(RowsOf((string)a["rows"]!))),
            "row_state_digest" => RowsOf((string)a["rows"]!).Take(50).Select(r => (object?)Headcount.RowState(r.Row)).ToList(),
            "require_pay_periods" => Digest(PayrollRows.RequirePayPeriods(World.Csv, new QcResolutionStore(), (bool)a["drop_qc"]!, MaybeLong(a["account_id"]))),
            "unauthored_state_years" => Rows.UnauthoredStateYears(((List<object?>)a["tax_years"]!).Select(y => (long)y!).ToList(), (string?)a["state"]),
            "iter_state_packs" => PackItems(a),
            "apply_calc_drops" => Drops(a),
            "exception_id" => QcResolutions.ExceptionId((PyDict)a["anomaly"]!),
            _ => Fiscal(call, a),
        };
    }

    internal static IReadOnlyList<PayRow> RowsOf(string spec)
    {
        var parts = spec.Split(':');
        var all = parts[0] == "csv" ? World.Csv.LoadPayPeriods(1001) : World.Synthetic[long.Parse(parts[1], System.Globalization.CultureInfo.InvariantCulture)];
        var count = parts.Length > (parts[0] == "csv" ? 1 : 2) ? int.Parse(parts[^1], System.Globalization.CultureInfo.InvariantCulture) : (int?)null;
        return count is { } n ? all.Take(n).ToList() : all;
    }

    internal static long? MaybeLong(object? v) => v is null ? null : (long)v;

    internal static List<object?> Strings(IEnumerable<string> items) => items.Select(s => (object?)s).ToList();

    /// <summary>Python <c>row_digest</c>: SHA-256 of the compact JSON of ten fields of each row (the exporter's identity of a row set).</summary>
    internal static string RowDigest(IEnumerable<PayRow> rows)
    {
        string[] fields = ["Employee_ID", "Worksite_ID", "Entity_FEIN", "Pay_Period_Start", "Pay_Period_End", "Pay_Date", "Hours_Worked", "Gross_Wages", "Pay_Code", "Work_State"];
        var table = rows.Select(r => (object?)fields.Select(f => r.Get(f)).ToList()).ToList();
        return Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.ASCII.GetBytes(PyJson.Dumps(table, sortKeys: false, compact: true))));
    }

    private static PyDict Digest(IReadOnlyList<PayRow> rows) => new PyDict().Add("n", (long)rows.Count).Add("digest", RowDigest(rows));

    private static object? CheckState(PyDict a)
    {
        Defaults.CheckProgramState((string?)a["state"], (string?)a["program_code"]);
        return null;
    }

    private static List<object?> Resolved(PyDict a)
    {
        var (state, code) = Defaults.ResolveProgram(MaybeLong(a["client_id"]), (string?)a["state"], (string?)a["program_code"], MaybeLong(a["tax_year"]), (bool)a["require_program"]!);
        return new List<object?> { state, code };
    }

    private static List<object?> Priced(PyDict a)
    {
        var (state, code, pack) = Defaults.PricedProgram(MaybeLong(a["client_id"]), (string?)a["state"], (string?)a["program_code"], MaybeLong(a["tax_year"]));
        return new List<object?> { state, code, pack };
    }

    private static PyDict Choice(PyDict a)
    {
        var e = new ProgramChoiceRequired((string)a["state"]!, ((List<object?>)a["candidates"]!).Select(c => (string)c!).ToList());
        return new PyDict().Add("message", e.Message).Add("candidates", Strings(e.Candidates)).Add("is_not_runnable", true);
    }

    private static List<object?> PackItems(PyDict a) =>
        Rows.IterStatePacks(RowsOf((string)a["rows"]!).ToList(), (long)a["tax_year"]!, (string?)a["state"], (string)a["on_unauthored"]!)
            .Select(p => (object?)new PyDict().Add("state", p.State).Add("program_code", p.ProgramCode).Add("n", (long)p.Rows.Count).Add("pack", PackTree(p.Pack))).ToList();

    internal static PyDict PackTree(OneZeroPack p) => new PyDict()
        .Add("min_weekly_hours", TrailValues.Of(p.MinWeeklyHours))
        .Add("min_weekly_wages", TrailValues.Of(p.MinWeeklyWages))
        .Add("wage_basis", p.WageBasis)
        .Add("tax_year", p.TaxYear)
        .Add("citation", p.Citation)
        .Add("measuring_date", p.MeasuringDate)
        .Add("entity_combination", p.EntityCombination)
        .Add("pt_weight", p.PtWeight is { } w ? TrailValues.Of(w) : null)
        .Add("geographic_granularity", p.GeographicGranularity);

    private static PyDict Drops(PyDict a)
    {
        var store = new QcResolutionStore();
        foreach (var (id, resolution) in (PyDict)a["resolutions"]!)
        {
            store.Set(id, (PyDict)resolution!);
        }

        var rows = RowsOf((string)a["rows"]!);
        var kept = QcResolutions.ApplyCalcDrops(store, rows);
        return new PyDict().Add("n", (long)kept.Count).Add("digest", RowDigest(kept)).Add("same_list", ReferenceEquals(kept, rows));
    }

    internal static BigInteger Big(long v) => v;
}
