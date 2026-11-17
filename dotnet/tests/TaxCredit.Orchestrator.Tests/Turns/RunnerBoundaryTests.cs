using System.Collections.Concurrent;
using System.Diagnostics;
using TaxCredit.Orchestrator.Tests.Support;

namespace TaxCredit.Orchestrator.Tests.Turns;

public sealed class RunnerBoundaryTests
{
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Unknown_arguments_reach_the_common_schema_refusal_not_the_gateway(bool tools)
    {
        using var model = tools
            ? new ScriptedModel(ScriptedModel.Tools(("client_trend", new() { ["surprise"] = "not-a-column" })), ScriptedModel.Text("The call was refused."))
            : new ScriptedModel(ScriptedModel.Text("""{"tools":[{"tool":"client_trend","args":{"surprise":"not-a-column"}}]}"""));
        var rig = new Rig(model, supportsTools: tools);
        var reply = await rig.SayAsync("How has Cascade trended?");
        Assert.Equal("failure", reply.Kind);
        Assert.Equal(["client_resolve"], rig.Gateway.Calls.Select(call => call.Tool));
        Assert.Empty(reply.Runs!);
        Assert.Contains("surprise", reply.Text, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Naming_another_client_overrides_the_same_persons_existing_selection()
    {
        using var model = new ScriptedModel(ScriptedModel.Tools(("client_trend", new())), ScriptedModel.Text("The trend is shown."),
            ScriptedModel.Tools(("client_trend", new())), ScriptedModel.Text("The other trend is shown."));
        var rig = new Rig(model);
        await rig.SayAsync("How has Cascade trended?");
        await rig.SayAsync("How has Northwind trended?");
        Assert.Equal([2001, 2002], rig.Gateway.Calls.Where(call => call.Tool == "client_trend")
            .Select(call => call.Arguments["client_id"]!.GetValue<int>()));
    }

    [Fact]
    public async Task An_unrelated_message_cannot_become_a_pending_review_packs_year_answer()
    {
        var rig = new Rig();
        await rig.SayAsync("Give Cascade a review pack.");
        await rig.SayAsync("How has Northwind trended in 2024?");
        var unrelated = await rig.SayAsync("2023");
        Assert.Equal("keywords", unrelated.Mode);
        Assert.Equal(["client_resolve", "client_resolve", "client_trend", "client_resolve", "client_eligibility", "client_eligibility"],
            rig.Gateway.Calls.Select(call => call.Tool));
        Assert.All(rig.Gateway.Calls.Where(call => call.Tool == "client_eligibility"), call =>
        {
            Assert.Equal(2002, call.Arguments["client_id"]!.GetValue<int>());
            Assert.Equal(2023, call.Arguments["tax_year"]!.GetValue<int>());
        });
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Tool_spans_report_controlled_outcomes_without_reader_text_arguments_or_person_fields(bool failure)
    {
        var stopped = new ConcurrentBag<Activity>();
        using var root = new Activity("synthetic-test-root").Start();
        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source.Name == "TaxCredit.Orchestrator.Tools",
            Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllData,
            ActivityStopped = activity => { if (activity.TraceId == root.TraceId) { stopped.Add(activity); } },
        };
        ActivitySource.AddActivityListener(listener);
        using var model = new ScriptedModel(ScriptedModel.Tools(("client_trend", new())), ScriptedModel.Text("The available evidence is shown."));
        var gateway = new FakeGateway();
        if (failure) { gateway.Overrides["client_trend"] = _ => FakeGateway.Error("dependency_unavailable"); }
        var rig = new Rig(model, gateway: gateway);
        await rig.SayAsync("How has Cascade trended?");
        var span = Assert.Single(stopped);
        Assert.Equal("client_trend", span.GetTagItem("tcc.tool"));
        Assert.Equal(failure ? "error" : "ok", span.GetTagItem("tcc.outcome"));
        Assert.Equal(failure ? "dependency_unavailable" : null, span.GetTagItem("tcc.error_code"));
        Assert.All(span.TagObjects, tag => Assert.Contains(tag.Key, new[] { "tcc.tool", "tcc.outcome", "tcc.error_code", "tcc.channel" }));
        Assert.DoesNotContain("Cascade", string.Join(";", span.TagObjects), StringComparison.Ordinal);
        Assert.DoesNotContain(Rig.Oid, string.Join(";", span.TagObjects), StringComparison.Ordinal);
    }
}
