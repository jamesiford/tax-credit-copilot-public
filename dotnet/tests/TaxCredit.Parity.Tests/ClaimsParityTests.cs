using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate DS4 (claims family): replays every call of <c>parity/goldens/claims.jsonl.gz</c> (production <c>domain/claims.py</c> and raw
/// <c>decimal</c> arithmetic on CPython 3.12) against <see cref="ProgramClaim"/>, <see cref="ClaimReadings"/>,
/// <see cref="ProgramEngagement"/>, <see cref="ClaimMoney"/> and <see cref="PyDecimalOps"/>. Trees are compared by type, key order,
/// double bit pattern, exact decimal text, and exception type plus message.
/// </summary>
public sealed class ClaimsParityTests
{
    private const string File = "claims.jsonl.gz";

    [Fact]
    public void Every_golden_call_matches_python_bit_for_bit() =>
        ClaimGolden.AssertAllMatch(
            File,
            Invoke,
            ["claim", "transition", "declining_reading", "_money", "engagement", "dec_add", "dec_sub", "dec_cmp", "dec_max0", "dec_neg", "dec_abs", "dec_sum", "dec_sum_neg"],
            minimumCalls: 30000,
            minimumErrors: 200);

    [Fact]
    public void A_perturbed_output_is_detected_by_the_comparison()
    {
        // Mutation self-test (in process): the comparison fed outputs with one deliberate defect must disagree.
        var detected = new Dictionary<string, int> { ["ulp"] = 0, ["int-as-float"] = 0, ["decimal-text"] = 0, ["key-order"] = 0, ["bool-flip"] = 0 };
        foreach (var call in ClaimGolden.Calls(File).Where(c => (string)c["fn"]! == "claim" && !c.ContainsKey("err")).Take(2500))
        {
            var actual = (PyDict)Invoke(call)!;
            var wire = (PyDict)actual["wire"]!;
            Perturb(call["out"], wire, detected);
        }

        foreach (var (name, n) in detected)
        {
            Assert.True(n > 5, $"the comparison cannot fail for '{name}' ({n} detections)");
        }
    }

    [Fact]
    public void A_claim_without_an_id_or_time_gets_a_fresh_guid_and_the_current_utc_instant()
    {
        var spec = new ClaimSpec { ClientId = 1, ProgramCode = "ga_jtc", TaxYear = 2023 };
        var a = ProgramClaim.Create(spec);
        var b = ProgramClaim.Create(spec);
        Assert.NotEqual(a.ClaimId, b.ClaimId);
        Assert.Matches("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", a.ClaimId!);
        Assert.Equal(0, a.EffectiveFrom.OffsetMinutes);
        Assert.Equal("GA_JTC", a.ProgramCode);
        var next = a.TransitionTo(ClaimStatus.Assessed, new TransitionOptions { DecidedBy = "x" });
        Assert.Equal(ClaimStatus.NotAssessed, a.Status);
        Assert.NotEqual(a.ClaimId, next.ClaimId);
        Assert.Null(next.EffectiveTo);
    }

    [Fact]
    public void A_transition_does_not_mutate_its_predecessor()
    {
        var original = ProgramClaim.Create(new ClaimSpec { ClientId = 1, ProgramCode = "GA_JTC", TaxYear = 2023, Status = ClaimStatus.Assessed });
        var before = original.ToDict();
        var next = original.TransitionTo(ClaimStatus.Proposed, new TransitionOptions { DecidedBy = "lead@example.com" });
        Assert.Null(ClaimGolden.Compare(before, original.ToDict(), "$"));
        Assert.NotEqual(original.ClaimId, next.ClaimId);
    }

    private static readonly (string Name, Func<object?, object?> Apply)[] Perturbations =
    [
        ("ulp", t => Map(t, v => v is double d && double.IsFinite(d) && d != 0 ? BitConverter.Int64BitsToDouble(BitConverter.DoubleToInt64Bits(d) + 1) : v)),
        ("int-as-float", t => Map(t, v => v is long l ? (double)l : v)),
        ("decimal-text", t => Map(t, v => v is string s && s.Length > 0 && char.IsAsciiDigit(s[^1]) && s.Contains('.', StringComparison.Ordinal) ? s + "0" : v)),
        ("bool-flip", t => Map(t, v => v is bool b ? !b : v)),
        ("key-order", t => Map(t, v => v is PyDict { Count: > 1 } d ? Reverse(d) : v)),
    ];

    private static void Perturb(object? expectedOut, PyDict wire, Dictionary<string, int> detected)
    {
        var expectedWire = ((PyDict)expectedOut!)["wire"];
        foreach (var (name, apply) in Perturbations)
        {
            if (ClaimGolden.Compare(expectedWire, apply(Map(wire, v => v)), "$") is not null)
            {
                detected[name]++;
            }
        }
    }

    private static PyDict Reverse(PyDict d)
    {
        var reversed = new PyDict();
        foreach (var kv in d.Reverse())
        {
            reversed.Add(kv.Key, kv.Value);
        }

        return reversed;
    }

    private static object? Map(object? t, Func<object?, object?> f) => t switch
    {
        PyDict d => f(d.Aggregate(new PyDict(), (acc, kv) => acc.Add(kv.Key, Map(kv.Value, f)))),
        List<object?> l => f(l.Select(x => Map(x, f)).ToList()),
        _ => f(t),
    };

    private static object? Invoke(PyDict call)
    {
        var a = (PyDict)call["args"]!;
        return (string)call["fn"]! switch
        {
            "enums" => Enums(),
            "claim" => ClaimOut(ProgramClaim.Create(ClaimGolden.Spec(a["spec"]))),
            "transition" => Transition(a),
            "declining_reading" => ClaimReadings.DecliningReading(((List<object?>)a["claims"]!).Select(s => ProgramClaim.Create(ClaimGolden.Spec(s))).ToList()),
            "_money" => ClaimMoney.Of(ClaimGolden.Untag(a["value"])).ToString(),
            "engagement" => Engagement((PyDict)a["spec"]!),
            "dec_add" => PyDecimalOps.Add(ClaimGolden.Decimal(a["a"]), ClaimGolden.Decimal(a["b"])).ToString(),
            "dec_sub" => PyDecimalOps.Subtract(ClaimGolden.Decimal(a["a"]), ClaimGolden.Decimal(a["b"])).ToString(),
            "dec_cmp" => Cmp(ClaimGolden.Decimal(a["a"]), ClaimGolden.Decimal(a["b"])),
            "dec_max0" => (PyDecimalOps.Compare(ClaimGolden.Decimal(a["a"]), PyDecimalOps.Zero) > 0 ? ClaimGolden.Decimal(a["a"]) : PyDecimalOps.Zero).ToString(),
            "dec_neg" => PyDecimalOps.Negate(ClaimGolden.Decimal(a["a"])).ToString(),
            "dec_abs" => PyDecimalOps.Abs(ClaimGolden.Decimal(a["a"])).ToString(),
            "dec_sum" => PyDecimalOps.Sum(Decimals(a["xs"])).ToString(),
            "dec_sum_neg" => PyDecimalOps.Sum(Decimals(a["xs"]).Select(PyDecimalOps.Negate)).ToString(),
            _ => throw new PyUnsupportedException("unknown function " + call["fn"]),
        };
    }

    private static List<PyDecimal> Decimals(object? xs) => ((List<object?>)xs!).Select(ClaimGolden.Decimal).ToList();

    private static PyDict Cmp(PyDecimal a, PyDecimal b)
    {
        var c = PyDecimalOps.Compare(a, b);
        return new PyDict().Add("lt", c < 0).Add("le", c <= 0).Add("eq", c == 0).Add("gt", c > 0).Add("ge", c >= 0);
    }

    private static PyDict ClaimOut(ProgramClaim c)
    {
        var props = new PyDict()
            .Add("cell_key", new List<object?> { c.CellKey.ClientId, c.CellKey.ProgramCode, c.CellKey.TaxYear })
            .Add("is_current", c.IsCurrent)
            .Add("status_is_claimed", c.Status.IsClaimed())
            .Add("verified", c.Provenance.Verified())
            .Add("variance_usd", c.VarianceUsd.ToString())
            .Add("variance_is_computable", c.VarianceIsComputable)
            .Add("outcome", c.Outcome.Value())
            .Add("is_exposure", c.IsExposure)
            .Add("opportunity_usd", c.OpportunityUsd.ToString())
            .Add("net_new_jobs", c.NetNewJobs)
            .Add("jobs_to_threshold", c.JobsToThreshold)
            .Add("jobs_margin", c.JobsMargin)
            .Add("near_threshold", c.NearThreshold)
            .Add("priority_band", c.PriorityBand.Value())
            .Add("priority_rank", c.PriorityBand.Rank());
        return new PyDict().Add("props", props).Add("wire", c.ToDict());
    }

    private static PyDict Transition(PyDict a)
    {
        var t = (PyDict)a["transition"]!;
        var newId = (string)a["new_claim_id"]!;
        var now = PyDateTime.FromIsoFormat((string)((PyDict)a["now"]!)["$dt"]!);
        var options = new TransitionOptions
        {
            DecidedBy = ClaimGolden.Get<string>(t, "decided_by"),
            DeclineReason = ClaimGolden.Get<string>(t, "decline_reason"),
            ClaimedUsd = ClaimGolden.Raw(t, "claimed_usd"),
            CertifiedUsd = ClaimGolden.Raw(t, "certified_usd"),
            FiledOn = ClaimGolden.Date(t, "filed_on"),
            FilingReference = ClaimGolden.Get<string>(t, "filing_reference"),
            Provenance = t.TryGetValue("provenance", out var p) && p is string ps ? ClaimEnumExtensions.ProvenanceFromValue(ps) : null,
            At = ClaimGolden.DateTimeOf(t, "at"),
        };
        var claim = ProgramClaim.Create(ClaimGolden.Spec(a["spec"]));
        return claim.TransitionTo(ClaimEnumExtensions.StatusFromValue((string)t["status"]!), options, new ClaimClock(() => newId, () => now)).ToDict();
    }

    private static PyDict Engagement(PyDict s) => new ProgramEngagement
    {
        ClientId = (long)s["client_id"]!,
        ProgramCode = (string)s["program_code"]!,
        Scope = s.TryGetValue("scope", out var sc) ? ClaimEnumExtensions.ScopeFromValue((string)sc!) : EngagementScope.Prospective,
        EffectiveFrom = ClaimGolden.DateTimeOf(s, "effective_from")!.Value,
        EffectiveTo = ClaimGolden.DateTimeOf(s, "effective_to"),
        Note = ClaimGolden.Get<string>(s, "note"),
        SetBy = ClaimGolden.Get<string>(s, "set_by"),
        SetAt = ClaimGolden.DateTimeOf(s, "set_at"),
    }.ToDict();

    private static PyDict Enums()
    {
        var status = new PyDict();
        foreach (var s in Enum.GetValues<ClaimStatus>())
        {
            var allowed = PySort.Sorted(s.AllowedTransitions().Select(t => t.Value()), v => v, PyStr.Comparer);
            status.Add(s.Value(), new PyDict().Add("is_claimed", s.IsClaimed()).Add("allowed", allowed.Cast<object?>().ToList()));
        }

        var provenance = new PyDict();
        foreach (var p in Enum.GetValues<Provenance>())
        {
            provenance.Add(p.Value(), p.Verified());
        }

        var band = new PyDict();
        foreach (var b in Enum.GetValues<PriorityBand>())
        {
            band.Add(b.Value(), b.Rank());
        }

        return new PyDict()
            .Add("status", status)
            .Add("provenance", provenance)
            .Add("band", band)
            .Add("outcome", Enum.GetValues<Outcome>().Select(o => (object?)o.Value()).ToList())
            .Add("scope", Enum.GetValues<EngagementScope>().Select(o => (object?)o.Value()).ToList())
            .Add("materiality_usd", ClaimMoney.Materiality.ToString())
            .Add("on_the_line_jobs", ProgramClaim.OnTheLineJobs);
    }
}
