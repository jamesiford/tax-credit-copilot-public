using System.Text.Json;
using TaxCredit.Application.Features.Ai.Numeric;

namespace TaxCredit.Api.Tests.Ai.Numeric;

public sealed class SummaryNumericGuardTests
{
    private static JsonElement Brief => JsonSerializer.SerializeToElement(new
    {
        facts = new[] { "$548,730 claimable since TY2021; 4.71 net-new jobs." },
    });

    [Fact]
    public void Summary_precision_is_distinct_from_strict_channel_equality()
    {
        Assert.Empty(SummaryNumericGuard.UnsupportedFigures("About $549k; 4.7 jobs since TY2021.", Brief));
        Assert.False(NumericGuard.Check("$549K", Brief).Passed);
        Assert.Equal(["2.5", "$12,000", "2019"],
            SummaryNumericGuard.UnsupportedFigures("2.5 jobs and $12,000 since TY2019.", Brief));
    }

    [Fact]
    public void Summary_ignores_small_whole_counts_and_deduplicates_violations()
    {
        Assert.Empty(SummaryNumericGuard.UnsupportedFigures("4 of 6 locations.", JsonSerializer.SerializeToElement(new { })));
        Assert.Equal(["$73"], SummaryNumericGuard.UnsupportedFigures("$73 and $73.", Brief));
    }

    [Theory]
    [InlineData("19.3", "19.249999999999999999999999999999", true)]
    [InlineData("19.3", "19.2499999995", true)]
    [InlineData("19.3", "19.249999998", false)]
    [InlineData("19.3000000001", "19.3", true)]
    [InlineData("19.300000002", "19.3", false)]
    [InlineData("9007199254740993", "9007199254740992", true)]
    public void Precision_boundary_preserves_python_binary64_and_epsilon(string text, string known, bool supported)
    {
        // tools/page_brief.py _values uses float; unsupported_figures uses abs(value-k) <= precision/2 + 1e-9.
        var brief = JsonSerializer.SerializeToElement(new { value = known });
        var missing = SummaryNumericGuard.UnsupportedFigures(text, brief);
        Assert.Equal(supported, missing.Count == 0);
        if (!supported)
        {
            Assert.Equal([text], missing);
        }
    }

    [Fact]
    public void Json_escaping_does_not_authorize_digits_inside_unicode_escape_sequences()
    {
        var brief = JsonSerializer.SerializeToElement(new { facts = "TY2021–TY2025" });
        Assert.Equal(["2013"], PageFigureCheck.UnsupportedFigures("TY2013", brief));
    }
}
