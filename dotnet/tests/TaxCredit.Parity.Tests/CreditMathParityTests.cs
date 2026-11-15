using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application;
using TaxCredit.Application.Rules;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure;
using TaxCredit.Infrastructure.Rules;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate DS7 (rule packs): replays <c>parity/goldens/credit_math.jsonl.gz</c>, recorded from the production <c>tools/credit_math.py</c>,
/// <c>tools/program_credit.py</c>, <c>tools/program_registry.py</c>, <c>tools/pack_lookup.py</c> and <c>tools/one_zero_pack.py</c> on CPython 3.12 over the real
/// <c>backend/rules</c> (read through the Infrastructure adapter, never copied) and the invented worlds the exporter overlays on it. Every result is
/// compared by type (int, float, bool), key order, double bits and exception type plus message; the calculation trail (with its SHA-256) and the
/// payroll-wage lookups of each credit call are compared too.
/// </summary>
public sealed class CreditMathParityTests
{
    [Fact]
    public void Every_golden_call_matches_python_bit_for_bit()
    {
        var harness = new CreditMathHarness();
        var counts = new Dictionary<string, int>();
        var failures = new List<string>();
        var total = 0;
        var errors = 0;
        foreach (var call in ClaimGolden.Calls(CreditMathHarness.File))
        {
            total++;
            var fn = (string)call["fn"]!;
            counts[fn] = counts.GetValueOrDefault(fn) + 1;
            bool wasError;
            string? mismatch;
            try
            {
                mismatch = ClaimGolden.Replay(call, harness.Invoke, out wasError);
            }
            catch (Exception e)
            {
                // A port that takes a different path (a mutant, or a real regression) can ask for an input the replay cannot serve or fail outside Python's
                // exception types; that is a divergence too.
                mismatch = $"the port left the recorded path: {e.GetType().Name}: {e.Message}";
                wasError = call.ContainsKey("err");
            }

            errors += wasError ? 1 : 0;
            mismatch ??= WageMismatch(call, harness);
            if (mismatch is not null)
            {
                failures.Add(failures.Count < 8 ? $"#{call["id"]} {fn}: {mismatch}" : string.Empty);
            }
        }

        Assert.True(failures.Count == 0, $"{failures.Count}/{total} calls of {CreditMathHarness.File} diverged:\n" + string.Join("\n", failures.Where(f => f.Length > 0)));
        Assert.True(total >= 90000 && errors >= 15000, $"corpus too thin: {total} calls, {errors} errors");
        foreach (var fn in new[]
                 {
                     "parse_registry", "load_registry", "registry_views", "registry_get", "registry_for_state", "programs_for_state", "program_for_code", "view_lookup", "pack_file_for",
                     "state_of", "credit_key", "registry_sequence", "authored_years", "is_year_scoped", "load_pack_flat", "load_year_pack", "resolve_statutory_floors",
                     "resolve_tax_year_convention", "load_pack_one_zero", "ingested_one_zero", "pack_from_document", "build_one_zero_pack", "from_pack_json",
                     "apply_one_zero_program_credit", "apply_one_zero_state_credit", "program_per_job_usd", "state_per_job_usd", "combine_program_entity_credits",
                     "combine_entity_credits", "credit_from_pack",
                 })
        {
            Assert.True(counts.GetValueOrDefault(fn) > 4, fn + " is barely covered");
        }
    }

    [Fact]
    public void A_perturbed_output_is_detected_by_the_comparison()
    {
        var harness = new CreditMathHarness();
        GoldenPerturbation.AssertDetected(CreditMathHarness.File, harness.Invoke, ["ulp", "int-as-float", "float-as-int", "bool-flip", "tie-order", "key-order"], take: 6000);
    }

    [Fact]
    public void Without_an_ingestion_hook_the_port_answers_what_python_answered_with_the_hook_replaced_by_none()
    {
        var harness = new CreditMathHarness();
        var checkedCalls = 0;
        foreach (var call in ClaimGolden.Calls(CreditMathHarness.File).Where(c => (string)c["fn"]! == "load_pack_one_zero" && !c.ContainsKey("err")))
        {
            var args = (PyDict)call["args"]!;
            if (args["ingestion"] is not PyDict spec || !spec.ContainsKey("none") || (string)args["world"]! is "nomanifest" or "badjson")
            {
                continue;
            }

            var library = new RuleLibrary(harness.Source((string)args["world"]!));
            var pack = library.LoadPackOneZero((string)args["key"]!, (long?)args["tax_year"]);
            Assert.Null(ClaimGolden.Compare(((PyDict)call["out"]!)["pack"], pack is null ? null : CreditMathHarness.PackTree(pack), "$.pack"));
            checkedCalls++;
        }

        Assert.True(checkedCalls > 100);
    }

    [Fact]
    public void A_missing_year_fails_loudly_and_never_falls_back_to_a_neighbour()
    {
        var library = new RuleLibrary(new JsonRulePackSource(new RulePackOptions { RulesDirectory = CreditMathHarness.RulesDirectory }));
        Assert.Equal([2019L, 2020, 2021, 2022, 2023, 2024, 2025, 2026], library.AuthoredYears("ga_jtc.json"));
        var missing = Assert.Throws<PyFileNotFoundError>(() => library.LoadYearPack("ga_jtc.json", 2027));
        Assert.Equal(
            "no rule pack for ga_jtc tax year 2027. Authored years: 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026. ADR-005: statute is not inherited across years \u2014 author the year or decline to calculate it.",
            missing.Message);
        Assert.Throws<PyFileNotFoundError>(() => library.LoadYearPack("ga_jtc.json", 2018));
        Assert.Throws<PyFileNotFoundError>(() => library.ResolveStatutoryFloors("GA_JTC", 2027));
        Assert.True(library.LoadYearPack("ga_jtc.json", 2026).YearResolved);
        Assert.False(library.LoadYearPack("ga_jtc.json", null).YearResolved);
        // A flat program (no year folder) resolves its one pack and says it was not year-resolved.
        Assert.False(library.LoadYearPack("sc_jtc.json", 2023).YearResolved);
        Assert.Throws<PyValueError>(() => library.ResolveStatutoryFloors("SC_JTC", 2023));
    }

    [Fact]
    public void A_state_with_several_programs_prices_its_first_and_a_named_program_prices_itself()
    {
        var harness = new CreditMathHarness();
        var library = harness.Library("zz");
        Assert.Equal(["ZZ_ALPHA_JTC", "ZZ_BETA_JTC"], library.ProgramsForState("zz").Select(e => e.Code));
        var alpha = library.ApplyOneZeroProgramCredit("ZZ_ALPHA_JTC", 110.0, 100.0, null);
        var beta = library.ApplyOneZeroProgramCredit("ZZ_BETA_JTC", 110.0, 100.0, null);
        Assert.Equal(9000L, alpha["annual_credit_usd"]);
        Assert.Equal(17500L, beta["annual_credit_usd"]);
        Assert.Equal(alpha["annual_credit_usd"], library.ApplyOneZeroStateCredit("ZZ", 110.0, 100.0, null)["annual_credit_usd"]);
        Assert.Equal(1000.0, library.StatePerJobUsd("ZZ"));
        Assert.Equal(2500.0, library.ProgramPerJobUsd("zz_beta_jtc"));
    }

    [Fact]
    public void The_shipped_world_is_the_real_rules_folder_with_no_overlay()
    {
        var shipped = (PyDict)((PyDict)CreditMathHarness.Meta()["worlds"]!)["shipped"]!;
        Assert.Empty((PyDict)shipped["files"]!);
        Assert.EndsWith(Path.Combine("backend", "rules"), new JsonRulePackSource(new RulePackOptions { RulesDirectory = CreditMathHarness.RulesDirectory }).RulesDirectory, StringComparison.Ordinal);
    }

    [Fact]
    public void The_rules_adapter_and_the_library_are_wired_through_application_and_infrastructure()
    {
        var services = new ServiceCollection();
        services.AddApplication().AddRulePackSource(new RulePackOptions { RulesDirectory = CreditMathHarness.RulesDirectory, IngestedConfigDirectory = CreditMathHarness.IngestedDirectory });
        Assert.Contains(services, d => d.ServiceType == typeof(IRulePackSource) && d.ImplementationInstance is JsonRulePackSource);
        Assert.Contains(services, d => d.ServiceType == typeof(RuleLibrary));
        Assert.Contains(services, d => d.ServiceType == typeof(IIngestedOneZeroSource));
    }

    private static string? WageMismatch(PyDict call, CreditMathHarness harness)
    {
        if (call.ContainsKey("err") || !((PyDict)call["args"]!).TryGetValue("wage_calls", out var expected))
        {
            return null;
        }

        return ClaimGolden.Compare(expected, harness.LastWageCalls, "$.wage_calls");
    }
}
