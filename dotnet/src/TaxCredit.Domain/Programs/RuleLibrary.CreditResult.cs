using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

public sealed partial class RuleLibrary
{
    // Put the benefit step into the active calculation trail, when one is recording.
    private static void RecordStep(PyDict pack, double average, double prior, double threshold, (double Qualifying, object Annual, object Lifetime) figures)
    {
        var recorder = TrailContext.Current;
        if (recorder is null)
        {
            return;
        }

        var credit = RuleTree.Sub(pack, "credit");
        var step = $"Apply One/Zero Average Headcount to {RuleTree.Str(RuleTree.Sub(credit, "name"))} benefit math";
        var citation = RuleTree.Sub(credit, "statutory_citation") as string
            ?? throw new PyUnsupportedException("a statutory citation that is not text is not modelled in the trail");
        recorder.Record(
            step,
            new PyDict().Add("average_headcount", average).Add("prior_period_average_headcount", prior).Add("threshold", threshold),
            "qualifying = max(0, avg_headcount - prior_avg_headcount - threshold)",
            new PyDict().Add("qualifying_jobs", figures.Qualifying).Add("annual_credit_usd", figures.Annual).Add("lifetime_credit_usd", figures.Lifetime),
            citation);
    }

    // The structured credit answer every caller reads (key order is the contract).
    private static PyDict Result(PyDict pack, string state, (double Average, double Prior, double Threshold, double Qualifying) inputs, (object PerJob, object Annual, object Years) money) => new PyDict()
        .Add("state", state)
        .Add("no_state_pack", false)
        .Add("credit_code", RuleTree.Sub(RuleTree.Sub(pack, "credit"), "code"))
        .Add("credit_name", RuleTree.Sub(RuleTree.Sub(pack, "credit"), "name"))
        .Add("jurisdiction", RuleTree.Sub(RuleTree.Sub(pack, "jurisdiction"), "code"))
        .Add("citation", RuleTree.Sub(RuleTree.Sub(pack, "credit"), "statutory_citation"))
        .Add("threshold", inputs.Threshold)
        .Add("qualifying_jobs", inputs.Qualifying)
        .Add("amount_per_job_usd", money.PerJob)
        .Add("annual_credit_usd", money.Annual)
        .Add("benefit_period_years", money.Years)
        .Add("lifetime_credit_usd", RuleTree.Int(RuleTree.Big(money.Annual) * RuleTree.Big(money.Years)))
        .Add("basis", "one_zero")
        .Add("average_headcount", inputs.Average)
        .Add("prior_period_average_headcount", inputs.Prior);

    // Python `credit_math._no_state_pack_result`: a state with no rule pack (for example TX) answers honestly instead of running the wrong math.
    private PyDict NoStatePackResult(string state)
    {
        var stateUpper = PyStr.Upper(state);
        var result = new PyDict()
            .Add("state", stateUpper)
            .Add("no_state_pack", true)
            .Add("credit_code", null)
            .Add("credit_name", null)
            .Add("jurisdiction", stateUpper)
            .Add("citation", null)
            .Add("threshold", null)
            .Add("qualifying_jobs", 0L)
            .Add("amount_per_job_usd", 0L)
            .Add("annual_credit_usd", 0L)
            .Add("benefit_period_years", 0L)
            .Add("lifetime_credit_usd", 0L)
            .Add("message", $"No state-level rule pack for {stateUpper} in our library (have: {string.Join(", ", StateToPack.SortedKeys())}). "
                + "Federal credits like WOTC may still apply \u2014 try the portfolio or discovery question.");
        var recorder = TrailContext.Current;
        if (recorder is not null)
        {
            // The only place a tool renames the active trail: when its title is still empty or "Pending".
            if (recorder.Title.Length == 0 || recorder.Title == "Pending")
            {
                recorder.Title = $"{stateUpper}: no state pack";
            }

            recorder.Record(
                $"Look up state rule pack for {stateUpper}",
                new PyDict().Add("state", stateUpper).Add("library", StateToPack.SortedKeys().Cast<object?>().ToList()),
                "STATE_TO_PACK[state]",
                new PyDict().Add("pack", null).Add("fallback", "federal only"),
                "backend/rules/");
        }

        return result;
    }
}
