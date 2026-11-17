using TaxCredit.Orchestrator.Tests.Support;

namespace TaxCredit.Orchestrator.Tests.Planning;

public sealed class ReviewPackTests
{
    [Theory]
    [InlineData("review pack")]
    [InlineData("client review")]
    [InlineData("credit review")]
    [InlineData("client briefing")]
    public async Task Named_pack_has_fixed_read_only_order_and_its_own_six_call_budget(string phrase)
    {
        using var model = new ScriptedModel(ScriptedModel.Error());
        var rig = new Rig(model, maxCalls: 1);
        var answer = await rig.SayAsync($"{phrase} Cascade 2024");
        Assert.Equal("review_pack", answer.Mode);
        Assert.Empty(model.Seen);
        Assert.Equal(["client_resolve", "client_situation", "client_eligibility", "client_eligibility", "client_trend",
            "client_at_risk", "client_discovery"], rig.Gateway.Calls.Select(call => call.Tool));
        Assert.Contains("read-only position", answer.Text, StringComparison.Ordinal);
        Assert.DoesNotContain(rig.Gateway.Calls, call => call.Tool.Contains("prepare", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Bare_year_follow_up_reuses_the_original_named_pack()
    {
        var rig = new Rig();
        var ask = await rig.SayAsync("Review pack Cascade");
        Assert.Equal("Which tax year do you mean?", ask.Text);
        var answer = await rig.SayAsync("2024");
        Assert.Equal("review_pack", answer.Mode);
        Assert.Contains("643,125", answer.Text, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Numbered_choice_keeps_the_pack_and_uses_the_reader_selected_client()
    {
        var rig = new Rig();
        var ask = await rig.SayAsync("Client review Cascade and Northwind 2024");
        Assert.Contains("Reply with the number", ask.Text, StringComparison.Ordinal);
        var answer = await rig.SayAsync("2");
        Assert.Equal("review_pack", answer.Mode);
        Assert.All(rig.Gateway.Calls.Skip(1), call => Assert.Equal(2002, call.Arguments["client_id"]!.GetValue<int>()));
    }

    [Fact]
    public async Task A_partial_failure_does_not_hide_other_reads()
    {
        var rig = new Rig();
        rig.Gateway.Overrides["client_situation"] = _ => FakeGateway.Error("api_error");
        var answer = await rig.SayAsync("Review pack Cascade 2024");
        Assert.Contains("643,125", answer.Text, StringComparison.Ordinal);
        Assert.Contains("calculation service did not answer", answer.Text, StringComparison.Ordinal);
        Assert.Equal(7, rig.Gateway.Calls.Count);
    }

    [Fact]
    public async Task If_all_steps_fail_no_trusted_numeric_answer_is_invented()
    {
        var rig = new Rig();
        foreach (var name in new[] { "client_situation", "client_eligibility", "client_trend", "client_at_risk", "client_discovery" })
        {
            rig.Gateway.Overrides[name] = _ => FakeGateway.Error("api_error");
        }
        var answer = await rig.SayAsync("Review pack Cascade 2024");
        Assert.Equal("failure", answer.Kind);
        Assert.DoesNotContain(answer.Text, char.IsAsciiDigit);
        Assert.DoesNotContain("read-only position", answer.Text, StringComparison.Ordinal);
    }
}
