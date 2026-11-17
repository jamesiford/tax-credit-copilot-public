using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate CAP (helpers): replays every helper call of <c>gold_payload.jsonl.gz</c> (the production <c>program_defaults</c>, <c>payroll_rows</c>, <c>qc_resolutions</c>,
/// <c>_client_run</c>, <c>runs/fingerprint</c> and <c>fiscal_source</c> on CPython 3.12) against the C# port, with exceptions compared by type and message.
/// </summary>
[Trait("Category", "heavy")]
public sealed class PayloadHelperParityTests
{
    private static readonly string[] Functions =
    [
        "calculable_states", "calculable_programs_for_state", "pick_state", "derive_run_state", "check_program_state", "resolve_program", "priced_program", "program_rows",
        "iter_state_packs", "apply_calc_drops", "client_fiscal_window", "_window_from_rule", "client_fiscal_window_rules", "resolve_statute", "resolve_client_run",
        "run_identity", "client_data_fingerprint", "authored_windows", "unauthored_state_years", "state_for_location",
    ];

    [Fact]
    public void Every_helper_call_matches_python_bit_for_bit()
    {
        var counts = new Dictionary<string, int>();
        var failures = new List<string>();
        var total = 0;
        var errors = 0;
        foreach (var line in PayloadGolden.Lines(PayloadGolden.Main, "call"))
        {
            var call = (PyDict)PyJson.Loads(line)!;
            total++;
            var fn = (string)call["fn"]!;
            counts[fn] = counts.GetValueOrDefault(fn) + 1;
            var mismatch = ClaimGolden.Replay(call, PayloadHelperInvoke.Invoke, out var wasError);
            errors += wasError ? 1 : 0;
            if (mismatch is not null)
            {
                failures.Add(failures.Count < 10 ? $"#{call["id"]} {fn} {PyJson.Dumps(call["args"])[..Math.Min(160, PyJson.Dumps(call["args"]).Length)]}: {mismatch}" : string.Empty);
            }
        }

        Assert.True(failures.Count == 0, $"{failures.Count}/{total} helper calls diverged:\n" + string.Join("\n", failures.Where(f => f.Length > 0)));
        Assert.True(total >= 1500 && errors >= 300, $"corpus too thin: {total} calls, {errors} errors");
        foreach (var fn in Functions)
        {
            Assert.True(counts.GetValueOrDefault(fn) >= 5, fn + " is barely covered");
        }
    }

    [Fact]
    public void A_state_with_several_calculable_programs_asks_which()
    {
        var e = new Domain.Pipeline.ProgramChoiceRequired("GA", ["GA_JTC", "GA_X"]);
        Assert.IsAssignableFrom<Domain.Pipeline.ProgramNotRunnableError>(e);
        Assert.Equal("ProgramChoiceRequired", e.PythonType);
        Assert.Equal("state GA has several calculable programs (GA_JTC, GA_X): pass program_code to choose one", e.Message);
    }
}
