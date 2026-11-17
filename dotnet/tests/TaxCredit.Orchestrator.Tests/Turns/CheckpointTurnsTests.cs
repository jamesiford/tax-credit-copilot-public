using System.Text.Json.Nodes;
using TaxCredit.Orchestrator.Tests.Support;

namespace TaxCredit.Orchestrator.Tests.Turns;

public sealed class CheckpointTurnsTests
{
    [Fact]
    public async Task Actual_agent_prepare_pauses_then_confirm_resumes_once_with_current_attribution()
    {
        using var model = PrepareModel();
        var rig = new Rig(model);
        var preview = await rig.SayAsync("Set Cascade GA_JTC in scope.");
        Assert.Contains("Nothing has changed yet", preview.Text, StringComparison.Ordinal);
        Assert.Contains("**confirm**", preview.Text, StringComparison.Ordinal);
        Assert.Equal(0, rig.Gateway.Mutations);
        var reply = await rig.SayAsync("confirm", Rig.Person(correlation: "confirm-correlation"));
        Assert.Equal("commit", reply.Kind);
        Assert.Equal(1, rig.Gateway.Mutations);
        var commit = Assert.Single(rig.Gateway.Calls, call => call.Tool.EndsWith("_commit", StringComparison.Ordinal));
        Assert.Equal("confirm-correlation", commit.Identity.CorrelationId);
        Assert.False(string.IsNullOrEmpty(commit.Key));
        Assert.DoesNotContain("synthetic-confirmation", preview.Text + reply.Text, StringComparison.Ordinal);
        Assert.All(model.VisibleRequests(), request => Assert.DoesNotContain("synthetic-confirmation", request, StringComparison.Ordinal));
        await rig.SayAsync("confirm");
        Assert.Equal(1, rig.Gateway.Mutations);
        Assert.Single(rig.Gateway.Calls, call => call.Tool.EndsWith("_commit", StringComparison.Ordinal));
    }

    [Theory]
    [InlineData("confirm!")]
    [InlineData("YES, APPLY.")]
    [InlineData(" yes apply...! ")]
    public async Task Source_confirmation_punctuation_resumes_the_same_checkpoint(string command)
    {
        using var model = PrepareModel();
        var rig = new Rig(model);
        await rig.SayAsync("Set Cascade GA_JTC in scope.");
        var result = await rig.SayAsync(command);
        Assert.Equal("commit", result.Kind);
        Assert.Equal(1, rig.Gateway.Mutations);
        Assert.Single(rig.Gateway.Calls, call => call.Tool.EndsWith("_commit", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Wrong_person_cannot_consume_the_preview_even_with_the_same_conversation()
    {
        using var model = PrepareModel();
        var rig = new Rig(model);
        await rig.SayAsync("Set Cascade GA_JTC in scope.");
        var wrong = await rig.SayAsync("confirm", Rig.Person(Rig.OtherOid));
        Assert.Equal("commit_refused", wrong.Kind);
        Assert.Equal(0, rig.Gateway.Mutations);
        await rig.SayAsync("confirm");
        Assert.Equal(1, rig.Gateway.Mutations);
    }

    [Theory]
    [InlineData("cancel")]
    [InlineData("cancel.")]
    [InlineData("yes")]
    [InlineData("no")]
    [InlineData("How has Cascade trended?")]
    public async Task Non_confirmation_never_applies_a_preview(string command)
    {
        using var model = new ScriptedModel(ScriptedModel.Tools(("engagement_set_prepare", Args())),
            ScriptedModel.Text("The preview is shown."), ScriptedModel.Tools(("client_trend", new())), ScriptedModel.Text("The trend is shown."));
        var rig = new Rig(model);
        await rig.SayAsync("Set Cascade GA_JTC in scope.");
        await rig.SayAsync(command);
        await rig.SayAsync("confirm");
        Assert.Equal(0, rig.Gateway.Mutations);
        Assert.DoesNotContain(rig.Gateway.Calls, call => call.Tool.EndsWith("_commit", StringComparison.Ordinal));
    }

    [Fact]
    public async Task At_the_expiry_boundary_a_checkpoint_cannot_dispatch()
    {
        var clock = new MovingClock();
        using var model = PrepareModel();
        var rig = new Rig(model, clock: clock);
        await rig.SayAsync("Set Cascade GA_JTC in scope.");
        clock.Advance(TimeSpan.FromMinutes(5));
        var expired = await rig.SayAsync("confirm");
        Assert.Contains("expired", expired.Text, StringComparison.Ordinal);
        Assert.Equal(0, rig.Gateway.Mutations);
    }

    [Fact]
    public async Task Concurrent_confirms_serialize_the_whole_turn_and_make_one_mutation()
    {
        using var model = PrepareModel();
        var rig = new Rig(model);
        await rig.SayAsync("Set Cascade GA_JTC in scope.");
        var answers = await Task.WhenAll(rig.SayAsync("confirm"), rig.SayAsync("confirm"), rig.SayAsync("confirm"));
        Assert.Equal(1, rig.Gateway.Mutations);
        Assert.Single(answers, reply => reply.Kind == "commit");
        Assert.Single(rig.Gateway.Calls, call => call.Tool.EndsWith("_commit", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Lost_commit_response_is_unknown_and_cannot_reconfirm_or_retry()
    {
        using var model = PrepareModel();
        var rig = new Rig(model, gateway: new FakeGateway { LoseCommitResponse = true });
        await rig.SayAsync("Set Cascade GA_JTC in scope.");
        var unknown = await rig.SayAsync("confirm");
        Assert.Contains("can't say whether", unknown.Text, StringComparison.Ordinal);
        Assert.DoesNotContain("Nothing was changed", unknown.Text, StringComparison.Ordinal);
        await rig.SayAsync("confirm");
        Assert.Equal(1, rig.Gateway.Mutations);
        Assert.Single(rig.Gateway.Calls, call => call.Tool.EndsWith("_commit", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Reader_authorization_is_enforced_by_the_gateway_before_a_checkpoint_can_commit()
    {
        using var model = PrepareModel();
        var gateway = new FakeGateway();
        gateway.Writers.Clear();
        var rig = new Rig(model, gateway: gateway);
        var preview = await rig.SayAsync("Set Cascade GA_JTC in scope.");
        Assert.DoesNotContain("**confirm**", preview.Text, StringComparison.Ordinal);
        await rig.SayAsync("confirm");
        Assert.DoesNotContain(gateway.Calls, call => call.Tool.EndsWith("_commit", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Model_failure_after_prepare_keeps_the_preview_without_preparing_again()
    {
        using var model = new ScriptedModel(ScriptedModel.Tools(("engagement_set_prepare", Args())), ScriptedModel.Error());
        var rig = new Rig(model);
        var preview = await rig.SayAsync("Set Cascade GA_JTC in scope.");
        Assert.Contains("**confirm**", preview.Text, StringComparison.Ordinal);
        await rig.SayAsync("confirm");
        Assert.Equal(1, rig.Gateway.Mutations);
        Assert.Single(rig.Gateway.Calls, call => call.Tool.EndsWith("_prepare", StringComparison.Ordinal));
    }

    private static ScriptedModel PrepareModel() =>
        new(ScriptedModel.Tools(("engagement_set_prepare", Args())), ScriptedModel.Text("The proposed scope is shown."));
    private static JsonObject Args() => new() { ["program_code"] = "GA_JTC", ["scope"] = "in_scope" };

    private sealed class MovingClock : TimeProvider
    {
        private DateTimeOffset _now = DateTimeOffset.Parse("2030-01-01T00:00:00Z", global::System.Globalization.CultureInfo.InvariantCulture);
        private long _ticks;
        public override DateTimeOffset GetUtcNow() => _now;
        public override long GetTimestamp() => _ticks;
        public override long TimestampFrequency => TimeSpan.TicksPerSecond;
        internal void Advance(TimeSpan amount) { _now += amount; _ticks += amount.Ticks; }
    }
}
