using TaxCredit.Application.Features.Ai.Numeric;

namespace TaxCredit.Api.Tests.Ai.Numeric;

public sealed class NumeralExtractorTests
{
    [Theory]
    [InlineData("$1,234.56", "money", "1234.56")]
    [InlineData(".5", "number", "0.5")]
    [InlineData("-3", "number", "-3")]
    [InlineData("(3)", "number", "-3")]
    [InlineData("($3,500)", "money", "-3500")]
    [InlineData("-$3,500", "money", "-3500")]
    [InlineData("12 percent", "percent", "12")]
    [InlineData("12 per cent", "percent", "12")]
    [InlineData("$1.2M", "abbreviated", "1200000")]
    [InlineData("2.5 billion", "abbreviated", "2500000000")]
    [InlineData("TY2025", "year", "2025")]
    [InlineData("FY 2025", "year", "2025")]
    [InlineData("2024-07-26", "date", null)]
    [InlineData("2024-07-26T09:30:00Z", "date", null)]
    public void Shapes_are_recognized_whole(string text, string kind, string? value)
    {
        var numeral = Assert.Single(NumeralExtractor.Extract("It is " + text + " today"));
        Assert.Equal(text, numeral.Text);
        Assert.Equal(kind, numeral.Kind);
        Assert.Equal(value, numeral.Value);
    }

    [Theory]
    [InlineData("3-5", "3", "5")]
    [InlineData("3–5", "3", "5")]
    [InlineData("Q3-24", "3", "24")]
    [InlineData("12.67 FTE and 14 jobs", "12.67", "14")]
    public void Ranges_and_units_do_not_hide_figures(string text, string first, string second)
    {
        Assert.Equal([first, second], NumeralExtractor.Extract(text).Select(n => n.Value));
    }

    [Fact]
    public void Words_are_not_guessed_and_code_fences_are_not_a_bypass()
    {
        Assert.Empty(NumeralExtractor.Extract("twelve jobs and one hundred hours"));
        Assert.False(NumericGuard.CheckRaw("```\n46\n```").Passed);
        Assert.Equal("3", Assert.Single(NumeralExtractor.Extract("(see 3 below)")).Value);
    }

    [Theory]
    [InlineData("3640", "compact_money", "$3.64K")]
    [InlineData("3640.5", "money", "$3,640.50")]
    [InlineData("14", "headcount", "14.00")]
    [InlineData("0.125", "percent", "12.5%")]
    [InlineData("-3640", "compact_money", "-$3.64K")]
    public void Formatting_is_lossless_and_accepted(string value, string formatter, string expected)
    {
        Assert.Equal(expected, NumericFormatting.Format(value, formatter));
        var facts = FactIndex.FromFacts(System.Text.Json.JsonSerializer.SerializeToElement(new { value }), ["value"]);
        Assert.True(NumericGuard.Check(expected, facts).Passed);
    }
}
