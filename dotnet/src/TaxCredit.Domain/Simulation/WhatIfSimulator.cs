using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Domain.Simulation;

/// <summary>
/// Python <c>tools/simulation.py</c> <c>simulate_hiring</c>: "what if we hired N more people in &lt;city&gt;?". Projects how a net change in
/// headcount at a location changes the statutory credit, both sides running through the One/Zero net-new credit math.
/// </summary>
/// <param name="library">The rule library behind the credit math.</param>
/// <param name="stateCredit">The baseline credit source (Python <c>portfolio.chat_state_credit</c>, whose payroll read is a port).</param>
public sealed class WhatIfSimulator(RuleLibrary library, StateCreditCalculator stateCredit)
{
    private const string NoPackCitation = "n/a \u2014 no state rule pack (federal WOTC still applies)";

    /// <summary>Python <c>simulate_hiring</c>.</summary>
    /// <param name="location">A city name or a two-letter state code (<c>null</c> is accepted as Python <c>None</c>).</param>
    /// <param name="newHires">The net change in headcount (negative = layoff or closure); zero is refused.</param>
    /// <returns>Baseline credit, projected credit and the USD delta.</returns>
    /// <exception cref="PyValueError">When <paramref name="newHires"/> is zero.</exception>
    public PyDict SimulateHiring(string? location, long newHires)
    {
        if (newHires == 0)
        {
            throw new PyValueError("new_hires must be non-zero");
        }

        var resolved = LocationResolver.Resolve(location);
        var state = resolved.State;
        var baseline = stateCredit.ChatStateCredit(state);
        var noPack = baseline.TryGetValue("no_state_pack", out var np) && ProximityCoerce.Truthy(np);
        double baselineAvg, priorAvg, projectedNetNew;
        PyDict baselineCredit, projectedCredit;
        if (noPack)
        {
            (baselineAvg, priorAvg, projectedNetNew) = (0.0, 0.0, 0.0);
            baselineCredit = new PyDict().Add("annual_credit_usd", 0L).Add("lifetime_credit_usd", 0L).Add("citation", NoPackCitation);
            projectedCredit = RuleTree.Copy(baselineCredit);
        }
        else
        {
            baselineAvg = ProximityCoerce.ToFloat(baseline.TryGetValue("average_headcount", out var ah) ? ah : 0.0);
            priorAvg = ProximityCoerce.ToFloat(baseline.TryGetValue("prior_period_average_headcount", out var pa) ? pa : 0.0);
            baselineCredit = baseline;
            var projectedAvg = PyRound.Round(PyArith.Max(0.0, baselineAvg + newHires), 2);
            projectedCredit = library.ApplyOneZeroStateCredit(state, projectedAvg, priorAvg, null);
            projectedNetNew = PyRound.Round(PyArith.Max(0.0, projectedAvg - priorAvg), 2);
        }

        var baselineNetNew = PyRound.Round(PyArith.Max(0.0, baselineAvg - priorAvg), 2);
        var deltaAnnual = Diff(projectedCredit, baselineCredit, "annual_credit_usd");
        var deltaLifetime = Diff(projectedCredit, baselineCredit, "lifetime_credit_usd");
        var result = new PyDict()
            .Add("location_city_or_state", location)
            .Add("resolved_state", state)
            .Add("resolved_county", resolved.County)
            .Add("new_hires", newHires)
            .Add("baseline", new PyDict()
                .Add("net_new_headcount", baselineNetNew)
                .Add("average_headcount", PyRound.Round(baselineAvg, 2))
                .Add("annual_credit_usd", baselineCredit["annual_credit_usd"])
                .Add("lifetime_credit_usd", baselineCredit["lifetime_credit_usd"]))
            .Add("projected", new PyDict()
                .Add("net_new_headcount", projectedNetNew)
                .Add("average_headcount", PyRound.Round(PyArith.Max(0.0, baselineAvg + newHires), 2))
                .Add("annual_credit_usd", projectedCredit["annual_credit_usd"])
                .Add("lifetime_credit_usd", projectedCredit["lifetime_credit_usd"]))
            .Add("delta", new PyDict().Add("annual_credit_usd", deltaAnnual).Add("lifetime_credit_usd", deltaLifetime))
            .Add("citation", baselineCredit["citation"]);
        if (TrailContext.Current is { } recorder)
        {
            RecordTrail(recorder, (location, resolved, newHires), (baselineAvg, priorAvg, projectedNetNew), (baselineCredit, projectedCredit), (deltaAnnual, deltaLifetime));
        }

        return result;
    }

    // projected - baseline of an int field, as the tree value Python's int subtraction gives.
    private static object Diff(PyDict projected, PyDict baseline, string key) => RuleTree.Int(RuleTree.Big(projected[key]!) - RuleTree.Big(baseline[key]!));

    private static void RecordTrail(TrailRecorder recorder, (string? Location, ResolvedLocation Resolved, long NewHires) ask, (double BaselineAvg, double PriorAvg, double ProjectedNetNew) avg, (PyDict Baseline, PyDict Projected) credits, (object Annual, object Lifetime) delta)
    {
        var (location, resolved, newHires) = ask;
        var verb = newHires > 0 ? "Add" : "Remove";
        var magnitude = Math.Abs(newHires);
        var citation = credits.Baseline["citation"] as string ?? throw new PyUnsupportedException("a trail citation that is not text is not modelled");
        recorder.Title = $"What-if: {(newHires > 0 ? "+" : "-")}{magnitude} headcount in {location ?? "None"}";
        recorder.Citation = citation;
        recorder.Record(
            "Resolve location",
            new PyDict().Add("input", location),
            "city -> (state, county) lookup",
            new PyDict().Add("state", resolved.State).Add("county", resolved.County),
            "prototype city map");
        recorder.Record(
            "Baseline statutory credit (as-is)",
            new PyDict().Add("average_headcount", PyRound.Round(avg.BaselineAvg, 2)).Add("prior_period_average_headcount", PyRound.Round(avg.PriorAvg, 2)),
            "apply_one_zero_state_credit(baseline avg headcount, prior avg)",
            new PyDict().Add("lifetime_credit_usd", credits.Baseline["lifetime_credit_usd"]),
            citation);
        var projectedAvg = PyRound.Round(PyArith.Max(0.0, avg.BaselineAvg + newHires), 2);
        recorder.Record(
            $"{verb} {magnitude} to current-year Average Monthly Headcount",
            new PyDict().Add("baseline_average_headcount", PyRound.Round(avg.BaselineAvg, 2)).Add("delta", newHires),
            "projected_avg = max(0, baseline_avg + delta)",
            new PyDict().Add("projected_average_headcount", projectedAvg).Add("projected_net_new_headcount", avg.ProjectedNetNew),
            "straight-line model; assumes the change persists across the year");
        recorder.Record(
            "Projected statutory credit",
            new PyDict().Add("projected_net_new_headcount", avg.ProjectedNetNew),
            "apply_one_zero_state_credit(projected avg headcount, prior avg)",
            new PyDict().Add("lifetime_credit_usd", credits.Projected["lifetime_credit_usd"]),
            citation);
        recorder.Record(
            "Delta",
            new PyDict().Add("baseline_lifetime", credits.Baseline["lifetime_credit_usd"]).Add("projected_lifetime", credits.Projected["lifetime_credit_usd"]),
            "projected_lifetime - baseline_lifetime",
            new PyDict().Add("delta_annual_usd", delta.Annual).Add("delta_lifetime_usd", delta.Lifetime),
            citation);
    }
}
