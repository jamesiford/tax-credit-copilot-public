using System.Security.Cryptography;
using System.Text;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Forecast;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Simulation;
using TaxCredit.Infrastructure.Rules;

namespace TaxCredit.Parity.Tests;

/// <summary>The payroll the C# side serves to <see cref="IPayPeriodSource"/>: the rows the golden's first call carries.</summary>
internal sealed class GoldenPayroll(IReadOnlyList<PayrollRow> rows) : IPayPeriodSource
{
    public IReadOnlyList<PayrollRow> LoadPayPeriods(long? accountId) => rows;
}

/// <summary>Decoding of <c>parity/goldens/forecast.jsonl.gz</c> arguments and the dispatch of each recorded function to the C# port.</summary>
internal sealed partial class ForecastGolden
{
    public const string File = "forecast.jsonl.gz";

    private static readonly string[] Columns = [.. EngineRunner.KnownColumns, "Job_Title"];
    private readonly RecordedWages _wages = new();
    private readonly RuleLibrary _library;
    private readonly Lazy<List<PayrollRow>> _payroll;
    private readonly Lazy<StateCreditCalculator> _credit;

    public ForecastGolden()
    {
        _library = new RuleLibrary(new JsonRulePackSource(new RulePackOptions { RulesDirectory = CreditMathHarness.RulesDirectory }), null, _wages);
        _payroll = new Lazy<List<PayrollRow>>(() => Rows(Payroll()));
        _credit = new Lazy<StateCreditCalculator>(() => new StateCreditCalculator(_library, new GoldenPayroll(_payroll.Value)));
    }

    public RuleLibrary Library => _library;

    public static IEnumerable<PyDict> Calls() => ClaimGolden.Calls(File);

    public object? Invoke(PyDict call)
    {
        try
        {
            return InvokeCore(call);
        }
        catch (PyUnsupportedException e)
        {
            // A gap in the port is reported as a divergence of this call, so one run lists every gap.
            throw new NormalisedException("UNSUPPORTED", e.Message);
        }
    }

    private PyDict InvokeCore(PyDict call)
    {
        var fn = (string)call["fn"]!;
        var a = (PyDict)call["args"]!;
        _wages.Values.Clear();
        if (a.TryGetValue("wage_calls", out var wc))
        {
            foreach (var pair in ((List<object?>)wc!).Cast<List<object?>>())
            {
                _wages.Values[(string)pair[0]!] = (double)pair[1]!;
            }
        }

        if (a.TryGetValue("trail", out var spec) && spec is PyDict t)
        {
            var recorder = new TrailRecorder((string)t["title"]!, (string)t["citation"]!);
            object? result;
            using (TrailContext.Use(recorder))
            {
                result = Dispatch(fn, a, call);
            }

            return new PyDict().Add("result", result).Add("trail", recorder.ToDict());
        }

        return new PyDict().Add("result", Dispatch(fn, a, call));
    }

    private object? Dispatch(string fn, PyDict a, PyDict call) => fn switch
    {
        "_payroll" => RowsTree(_payroll.Value),
        "_months_elapsed" => ForecastProjection.MonthsElapsed(Date(a["analysis_start"]), Date(a["as_of"])),
        "_ytd_average_headcount" => ForecastProjection.YtdAverageHeadcount(Summary(a["summary"]), (long)a["months_elapsed"]!),
        "project_state_year_end" => Project(a),
        "_resolve_location" => Resolve((string?)a["city_or_state"]),
        "simulate_hiring" => new WhatIfSimulator(_library, _credit.Value).SimulateHiring((string?)a["location"], (long)a["new_hires"]!),
        "chat_state_credit" => _credit.Value.ChatStateCredit((string)a["state"]!, StateOptions(a)),
        "latest_tax_year" => _credit.Value.LatestTaxYear((long)a["fy_end_month"]!),
        "onezero_snapshot" => Snapshot(a),
        "describe_role" => OneZeroSimulation.DescribeRole(Opt(a["weekly_hours"]), Opt(a["hourly_rate"]), Pack(a["pack"])),
        "apply_onezero_lever" => Lever(a),
        "str.lower" => PyStrCase.Lower((string)a["s"]!),
        "str.lower.table" => LowerTable(),
        _ => throw new PyUnsupportedException("unknown function " + fn + " in call " + call["id"]),
    };

    private static List<object?> Resolve(string? city)
    {
        var r = LocationResolver.Resolve(city);
        return [r.State, r.County];
    }

    private PyDict? Project(PyDict a)
    {
        var options = new ForecastOptions(
            a.TryGetValue("fiscal_year_end_month", out var fy) ? (long)fy! : 12,
            a.TryGetValue("months_elapsed", out var me) ? (long?)me : null,
            a.TryGetValue("ytd_average_headcount", out var ytd) ? Opt(ytd) : null,
            a.TryGetValue("prior_average_headcount", out var prior) ? Opt(prior) : null);
        return new ForecastProjection(_library).ProjectStateYearEnd((string)a["state"]!, (long)a["tax_year"]!, Resolved(a["rows"]), Resolved(a["prior_rows"]), Date(a["as_of"]), options);
    }

    private static StateCreditOptions StateOptions(PyDict a) => new(
        a.TryGetValue("tax_year", out var ty) ? (long?)ty : null,
        a.TryGetValue("fy_end_month", out var fy) ? (long)fy! : 12,
        null,
        a.TryGetValue("current_average", out var cur) ? Opt(cur) : null,
        a.TryGetValue("prior_average", out var pr) ? Opt(pr) : null,
        a.TryGetValue("program_code", out var pc) ? (string?)pc : null);

    private PyDict Snapshot(PyDict a)
    {
        PyNumber? prior = a.TryGetValue("prior_average_headcount", out var p) ? (p is long l ? PyNumber.OfInt(l) : PyNumber.OfFloat((double)p!)) : null;
        return new OneZeroSimulation(_library).OneZeroSnapshot(Resolved(a["rows"]), (long)a["tax_year"]!, (string)a["state"]!, Pack(a["pack"]), prior);
    }

    private PyDict Lever(PyDict a)
    {
        var request = new LeverRequest(
            (string)a["action"]!, Opt(a["magnitude"])!.Value, Pack(a["pack"]), (string)a["state"]!,
            a.TryGetValue("fein", out var fein) ? (string?)fein : null,
            a.TryGetValue("hire_weekly_hours", out var hh) ? Opt(hh) : null,
            a.TryGetValue("hire_hourly_rate", out var hr) ? Opt(hr) : null);
        var (rows, detail) = OneZeroLever.Apply(Resolved(a["rows"]), request);
        var tree = RowsTree(rows);
        return new PyDict().Add("rows", a.TryGetValue("digest", out var d) && d is true ? Digest(tree) : tree).Add("detail", detail);
    }

    private static List<object?> LowerTable()
    {
        var table = new List<object?>();
        for (var cp = 0; cp < 0x110000; cp++)
        {
            if (cp is >= 0xD800 and <= 0xDFFF)
            {
                continue;
            }

            var text = char.ConvertFromUtf32(cp);
            var lowered = PyStrCase.Lower(text);
            if (lowered != text)
            {
                var points = new List<object?>();
                for (var i = 0; i < lowered.Length; i += char.IsSurrogatePair(lowered, i) ? 2 : 1)
                {
                    points.Add((long)char.ConvertToUtf32(lowered, i));
                }

                table.Add(new List<object?> { (long)cp, points });
            }
        }

        return table;
    }

    private static PyDict Digest(List<object?> rows) => new PyDict()
        .Add("$digest", Convert.ToHexStringLower(SHA256.HashData(Encoding.ASCII.GetBytes(PyJson.Dumps(rows, sortKeys: false, compact: true, ensureAscii: true)))))
        .Add("n", (long)rows.Count);
}
