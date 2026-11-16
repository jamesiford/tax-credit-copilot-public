using System.Text.Json;
using TaxCredit.Application.Features.Ai.Numeric;

namespace TaxCredit.Api.Tests.Ai.Numeric;

public sealed class NumericGuardTests
{
    private static FactIndex Facts() => FactIndex.FromFacts(JsonSerializer.SerializeToElement(new
    {
        annual_credit_usd = "3640.50",
        average_headcount = "14.73",
        owed_usd = "-1220",
        share_ratio = "0.125",
        citation = "Code 48-7-40.26",
        window = "2024-07-26",
    }), ["share_ratio"]);

    [Theory]
    [InlineData("$3,640.50")]
    [InlineData("3640.5000")]
    [InlineData("14.730")]
    [InlineData("-$1,220")]
    [InlineData("($1,220)")]
    [InlineData("12.5%")]
    [InlineData("2024-07-26")]
    [InlineData("Code 48-7-40.26")]
    public void Final_gate_accepts_exact_facts(string text) => Assert.True(NumericGuard.Check(text, Facts()).Passed);

    [Theory]
    [InlineData("$3,640.51")]
    [InlineData("$3,604.50")]
    [InlineData("14.7")]
    [InlineData("14.731")]
    [InlineData("1220")]
    [InlineData("13%")]
    [InlineData("2024-07-27")]
    [InlineData("Code 48-7-40.27")]
    public void Final_gate_rejects_changed_figures(string text) => Assert.False(NumericGuard.Check(text, Facts()).Passed);

    [Fact]
    public void Raw_digits_are_refused_even_when_final_facts_would_accept_them()
    {
        Assert.True(NumericGuard.Check("$3,640.50", Facts()).Passed);
        var result = NumericGuard.CheckRaw("$3,640.50");
        Assert.False(result.Passed);
        Assert.Equal("narration", Assert.Single(result.Violations).Stage);
    }

    [Fact]
    public void Raw_gate_does_not_mask_placeholder_paths_on_behalf_of_the_composer()
    {
        Assert.False(NumericGuard.CheckRaw("Value {{facts.rows.42.amount}}.").Passed);
        Assert.True(NumericGuard.CheckRaw("Value █.").Passed);
        Assert.False(NumericGuard.CheckRaw("Value 19.3000000001.",
            AllowedContext.Build(["19.3"])).Passed);
    }

    [Fact]
    public void Reader_context_allows_only_supplied_values_dates_and_years()
    {
        var context = AllowedContext.Build(["What about 6 hires on 2025-08-03 at 7%?"], [2025], [2101]);
        Assert.True(NumericGuard.CheckRaw("For 6 hires in TY2025, client 2101, on 2025-08-03 at 7%.", context).Passed);
        Assert.False(NumericGuard.CheckRaw("For 8 hires in TY2025", context).Passed);
        Assert.False(NumericGuard.CheckRaw("2025-08-04", context).Passed);
        Assert.False(NumericGuard.CheckRaw("7", context).Passed);
        Assert.False(NumericGuard.CheckRaw("TY2026", context).Passed);
    }

    [Fact]
    public void Percentage_requires_a_hint_and_is_a_separate_lane()
    {
        var facts = FactIndex.FromFacts(JsonSerializer.SerializeToElement(new { share_ratio = "0.125", employees = 12 }));
        Assert.False(NumericGuard.Check("12.5%", facts).Passed);
        Assert.True(NumericGuard.Check("12.5%", facts.WithPercent("share_ratio")).Passed);
        Assert.False(NumericGuard.Check("12%", facts).Passed);
        Assert.True(NumericGuard.Check("0.125", facts).Passed);
    }

    [Theory]
    [InlineData("$3.64K", true)]
    [InlineData("3.64 thousand", true)]
    [InlineData("$3.6K", false)]
    [InlineData("$3.64k", false)]
    [InlineData("$0.00364 million", false)]
    [InlineData("$3.640K", false)]
    public void Abbreviation_must_be_an_exact_formatter_spelling(string text, bool passes)
    {
        var facts = FactIndex.FromFacts(JsonSerializer.SerializeToElement(new { amount = 3640 }));
        Assert.Equal(passes, NumericGuard.Check(text, facts).Passed);
    }

    [Theory]
    [InlineData("３６４０")]
    [InlineData("٣٦٤٠")]
    [InlineData("½")]
    [InlineData("²")]
    [InlineData("𝟛")]
    [InlineData("3\u2009640")]
    [InlineData("3\u00a0640")]
    [InlineData("3\u202f640")]
    [InlineData("3\u200b640")]
    public void Non_ascii_evasion_is_not_normalized_even_when_reader_supplies_it(string text)
    {
        var result = NumericGuard.Check(text, Facts(), AllowedContext.Build([text]));
        Assert.False(result.Passed);
        Assert.All(result.Violations, v => Assert.Equal("non_ascii", v.Numeral.Kind));
    }

    [Fact]
    public void Structural_allow_list_is_narrow()
    {
        Assert.True(NumericGuard.CheckRaw("1. First\n2) Second\n - 3. Third\nstep 20, the 1st through 10th.").Passed);
        Assert.False(NumericGuard.CheckRaw("100. Claim\nstep 21 and 11th").Passed);
        Assert.False(NumericGuard.CheckRaw("the count is 2.").Passed);
        Assert.False(NumericGuard.CheckRaw("The 1.5th figure").Passed);
    }

    [Fact]
    public void Exact_decimal_primitive_does_not_round_large_or_tiny_values()
    {
        var facts = FactIndex.FromFacts(JsonSerializer.SerializeToElement(new
        {
            large = "123456789012345678901234567890.123456789",
            tiny = "0.000000000000000000000000000000001",
        }));
        Assert.True(NumericGuard.Check("123456789012345678901234567890.1234567890", facts).Passed);
        Assert.False(NumericGuard.Check("123456789012345678901234567890.123456788", facts).Passed);
        Assert.True(NumericGuard.Check("0.000000000000000000000000000000001", facts).Passed);
    }

    [Fact]
    public void Audit_result_uses_decimal_strings_and_nearest_fact()
    {
        var result = NumericGuard.Check("$3,640.51", Facts());
        var violation = Assert.Single(result.Violations);
        Assert.Equal("3640.5", violation.NearestFact);
        using var json = JsonDocument.Parse(JsonSerializer.Serialize(result));
        Assert.Equal("rejected", json.RootElement.GetProperty("status").GetString());
        Assert.Equal(JsonValueKind.String, json.RootElement.GetProperty("violations")[0].GetProperty("numeral").GetProperty("value").ValueKind);
    }

    [Fact]
    public void Model_lane_does_not_get_employee_row_values()
    {
        var full = FactIndex.FromFacts(JsonSerializer.SerializeToElement(new { row_count = 2, rows = new[] { new { wage = "613.47" } } }));
        var shown = FactIndex.FromFacts(JsonSerializer.SerializeToElement(new { row_count = 2 }));
        Assert.True(NumericGuard.Check("613.47", full).Passed);
        Assert.False(NumericGuard.Check("613.47", shown).Passed);
        Assert.False(NumericGuard.CheckRaw("613.47").Passed);
        Assert.True(NumericGuard.CheckRaw("613.47", AllowedContext.Build(["Is 613.47 correct?"])).Passed);
    }

    [Fact]
    public void Ambiguous_paths_are_marked_and_can_be_namespaced()
    {
        var first = JsonSerializer.SerializeToElement(new { amount = 28 });
        var second = JsonSerializer.SerializeToElement(new { amount = 39 });
        Assert.Contains("amount", FactIndex.FromFacts([first, second]).Ambiguous);
        var named = FactIndex.FromFacts([first, second], ["a", "b"]);
        Assert.Empty(named.Ambiguous);
        Assert.True(named.Leaves.ContainsKey("b.amount"));
    }

    [Fact]
    public void Every_single_digit_perturbation_is_refused()
    {
        const string valid = "Credit $3,640.50; headcount 14.73; date 2024-07-26.";
        Assert.True(NumericGuard.Check(valid, Facts()).Passed);
        var mutations = 0;
        foreach (var numeral in NumeralExtractor.Extract(valid))
        {
            for (var position = numeral.Start; position < numeral.End; position++)
            {
                if (!char.IsAsciiDigit(valid[position]))
                {
                    continue;
                }

                var replacement = valid[position] == '9' ? '8' : (char)(valid[position] + 1);
                var mutated = valid[..position] + replacement + valid[(position + 1)..];
                Assert.False(NumericGuard.Check(mutated, Facts()).Passed, mutated);
                mutations++;
            }
        }

        Assert.True(mutations > 15);
    }
}
