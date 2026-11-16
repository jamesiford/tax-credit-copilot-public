using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Orchestrator.Framework;
using TaxCredit.Orchestrator.Planning;

namespace TaxCredit.Orchestrator.Tests.Planning;

public sealed class ReaderWordsTests
{
    [Theory]
    [InlineData("What is the credit for 2024?", "both")]
    [InlineData("credit for 2024 pay period", "pay_period")]
    [InlineData("credit TY2024 min-max", "min_max")]
    [InlineData("compare min max and pay period 2024", "both")]
    public void Reader_overrides_model_year_and_method(string question, string method)
    {
        var spec = new ModelToolCatalog(new CapabilityCatalog()).Find("client_eligibility")!;
        var arguments = new JsonObject { ["tax_year"] = 2025, ["method"] = "min_max" };
        Assert.Null(ReaderWords.Settle(spec, arguments, question, null));
        Assert.Equal(2024, arguments["tax_year"]!.GetValue<int>());
        Assert.Equal(method, arguments["method"]!.GetValue<string>());
    }

    [Fact]
    public void Write_year_cannot_come_from_conversation_state()
    {
        var spec = new ModelToolCatalog(new CapabilityCatalog()).Find("finding_resolve_prepare")!;
        Assert.Equal("year", ReaderWords.Settle(spec, new JsonObject { ["tax_year"] = 2024 }, "resolve it", 2024));
    }

    [Fact]
    public void Model_scenario_values_are_removed_and_missing_size_is_asked_not_inferred()
    {
        var spec = new ModelToolCatalog(new CapabilityCatalog()).Find("simulate")!;
        var args = new JsonObject { ["magnitude"] = 12, ["hire_weekly_hours"] = 40, ["tax_year"] = 2024 };
        Assert.Equal("detail", ReaderWords.Settle(spec, args, "What if we hire five in 2024?", null));
        Assert.False(args.ContainsKey("magnitude"));
        Assert.False(args.ContainsKey("hire_weekly_hours"));
        args["magnitude"] = 5;
        Assert.Null(ReaderWords.Settle(spec, args, "What if we hire five in 2024?", null));
    }

    [Fact]
    public void Data_years_keep_only_the_reader_and_never_a_neighbor()
    {
        var spec = new ModelToolCatalog(new CapabilityCatalog()).Find("data_query")!;
        var args = new JsonObject { ["tax_years"] = new JsonArray(2024, 2025) };
        ReaderWords.Settle(spec, args, "compare TY2023 to TY2024", null);
        Assert.Equal("[2024]", args["tax_years"]!.ToJsonString());
    }
}
