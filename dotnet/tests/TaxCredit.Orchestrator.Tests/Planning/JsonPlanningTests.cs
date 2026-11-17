using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Orchestrator.Boundary;
using TaxCredit.Orchestrator.Planning;
using TaxCredit.Orchestrator.Tests.Support;

namespace TaxCredit.Orchestrator.Tests.Planning;

public sealed class JsonPlanningTests
{
    [Fact]
    public async Task Lookup_only_plan_gets_one_replan_then_a_shared_placeholder_brief()
    {
        using var model = new ScriptedModel(ScriptedModel.Text("""{"tools":[{"tool":"data_catalog"}]}"""),
            ScriptedModel.Text("""{"tools":[{"tool":"data_query","args":{"dataset":"payroll","measures":[{"column":"*","agg":"count","as":"periods"}]}}]}"""),
            ScriptedModel.Text("The data answers your question."));
        var rig = new Rig(model, supportsTools: false);
        rig.Gateway.Overrides["data_catalog"] = _ => Catalog();
        var answer = await rig.SayAsync("Count the periods for Cascade.");
        Assert.Equal("json", answer.Mode);
        Assert.Equal(["data_catalog", "client_resolve", "data_query"], rig.Gateway.Calls.Select(call => call.Tool));
        Assert.Equal(3, model.Seen.Count);
        var requests = model.VisibleRequests().ToArray();
        Assert.Contains("LOOKUP RESULTS", requests[1], StringComparison.Ordinal);
        Assert.Contains("payroll", requests[1], StringComparison.Ordinal);
        Assert.Contains("{{facts.", requests[2], StringComparison.Ordinal);
        Assert.DoesNotContain("31500.00", requests[2], StringComparison.Ordinal);
        Assert.DoesNotContain("### Data Catalog", answer.Text, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("""{"tools":[{"tool":"data_catalog"},{"tool":"data_query","args":{"dataset":"payroll"}}]}""", 2)]
    [InlineData("""{"tools":[{"tool":"client_trend"}]}""", 2)]
    [InlineData("""{"tools":[]}""", 1)]
    [InlineData("""not valid json""", 1)]
    public async Task A_query_or_nonlookup_plan_is_not_replanned(string plan, int requests)
    {
        using var model = new ScriptedModel(ScriptedModel.Text(plan), ScriptedModel.Text("The answer is shown."));
        var rig = new Rig(model, supportsTools: false);
        await rig.SayAsync("How has Cascade trended?");
        Assert.Equal(requests, model.Seen.Count);
    }

    [Fact]
    public async Task A_second_lookup_only_plan_cannot_create_an_unbounded_replan_loop()
    {
        using var model = new ScriptedModel(ScriptedModel.Text("""{"tools":["data_catalog"]}"""),
            ScriptedModel.Text("""{"tools":["data_catalog"]}"""), ScriptedModel.Text("The catalog is shown."));
        var rig = new Rig(model, supportsTools: false);
        await rig.SayAsync("What data is held for Cascade?");
        Assert.Equal(3, model.Seen.Count);
        Assert.Single(rig.Gateway.Calls, call => call.Tool == "data_catalog");
    }

    [Fact]
    public void Malformed_plan_elements_do_not_hide_unknown_names_from_the_shared_refusal()
    {
        var steps = TurnPlanner.Parse("""prefix {"tools":["unknown",null,{"tool":12},{"tool":"book_rank","args":[]},{"tool":"client_trend"}]} suffix""", 2);
        Assert.Equal(["unknown", "book_rank"], steps.Select(step => step.Name));
        Assert.Empty(steps[1].Arguments);
        Assert.Empty(TurnPlanner.Parse("[]", 8));
    }

    [Fact]
    public async Task An_invented_or_commit_tool_is_not_dispatched_in_json_mode()
    {
        using var model = new ScriptedModel(ScriptedModel.Text("""{"tools":["engagement_set_commit","invented","client_trend"]}"""),
            ScriptedModel.Text("The trend is shown."));
        var rig = new Rig(model, supportsTools: false, maxCalls: 2);
        await rig.SayAsync("How has Cascade trended?");
        Assert.Empty(rig.Gateway.Calls);
    }

    private static GatewayReply Catalog() => new(200, new CapabilityResult("data_catalog", new JsonObject
    {
        ["datasets"] = new JsonArray(new JsonObject
        {
            ["name"] = "payroll",
            ["columns"] = new JsonArray("hours_worked", "worksite_id"),
            ["grain"] = "one pay period",
        }),
    })
    {
        Blocks = new JsonArray(CapabilityResult.Block("heading", "Data Catalog")),
    }.ToJson());
}
