using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.Ai.Numeric;
using TaxCredit.Orchestrator.Composition;

namespace TaxCredit.Orchestrator.Tests.Composition;

public sealed class ExactnessTests
{
    [Fact]
    public void Many_scripted_narrators_cannot_change_exact_synthetic_figures()
    {
        var random = new Random(20240625);
        for (var trial = 0; trial < 80; trial++)
        {
            var dollars = random.Next(1000, 1_000_000);
            var cents = random.Next(1, 100);
            var canonical = dollars.ToString(CultureInfo.InvariantCulture) + "." + cents.ToString("D2", CultureInfo.InvariantCulture);
            var rendered = CapabilityFormat.Render(JsonValue.Create(canonical), "money");
            var run = new CompositionRun("synthetic_credit", [], new CapabilityResult("synthetic_credit", new JsonObject
            {
                ["annual_credit_usd"] = canonical,
            })
            {
                Blocks = [CapabilityResult.Block("paragraph", "Annual credit: " + rendered)],
            }, "q");
            var index = FactIndex.FromFacts(JsonSerializer.SerializeToElement(GuardedReplyComposer.FactsOf([run])));
            foreach (var (narration, survives) in new[]
            {
                ("Narrator says {{facts.q.annual_credit_usd|money}}.", true),
                ("Narrator says " + rendered + ".", false),
                ("Narrator says " + rendered + " and 987654321 jobs.", false),
                ("Narrator says roughly {{facts.q.annual_credit_usd|money}}.", false),
            })
            {
                var reply = GuardedReplyComposer.ComposeReply("", [run], narration);
                Assert.Equal(survives, reply.NarrationUsed);
                Assert.Equal(survives ? "pass" : "rejected", reply.Guard.Status);
                Assert.Equal(survives, reply.Text.Contains("Narrator says", StringComparison.Ordinal));
                Assert.Contains(rendered, reply.Body, StringComparison.Ordinal);
                Assert.True(NumericGuard.Check(reply.Body, index).Passed, reply.Body);
            }
        }
    }

    [Fact]
    public void Arbitrary_precision_figures_survive_without_decimal_or_double_conversion()
    {
        const string canonical = "123456789012345678901234567890.123456789";
        var run = new CompositionRun("synthetic_credit", [], new CapabilityResult("synthetic_credit", new JsonObject
        {
            ["annual_credit_usd"] = canonical,
        }), "q");
        var reply = GuardedReplyComposer.ComposeReply("", [run], "Credit {{facts.q.annual_credit_usd|money}}.");
        Assert.True(reply.NarrationUsed);
        Assert.Contains("$123,456,789,012,345,678,901,234,567,890.123456789", reply.Text, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("fr-FR")]
    [InlineData("de-DE")]
    public void Rendering_remains_invariant_without_localized_grouping_or_decimal_marks(string cultureName)
    {
        var prior = CultureInfo.CurrentCulture;
        try
        {
            CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo(cultureName);
            var reply = GuardedReplyComposer.ComposeReply("", [CompositionFixture.Credit()],
                "Credit " + CompositionFixture.Placeholder("credit.annual_credit_usd"));
            Assert.True(reply.NarrationUsed);
            Assert.Contains("$3,640.50", reply.Text, StringComparison.Ordinal);
        }
        catch (CultureNotFoundException)
        {
            // The production SDK explicitly enables invariant globalization.
            Assert.True(CultureInfo.CurrentCulture.Equals(CultureInfo.InvariantCulture));
        }
        finally
        {
            CultureInfo.CurrentCulture = prior;
        }
    }
}
