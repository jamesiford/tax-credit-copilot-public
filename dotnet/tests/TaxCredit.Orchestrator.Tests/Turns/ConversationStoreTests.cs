using TaxCredit.Orchestrator.Tests.Support;
using TaxCredit.Orchestrator.Turns;

namespace TaxCredit.Orchestrator.Tests.Turns;

public sealed class ConversationStoreTests
{
    [Fact]
    public async Task Exact_idle_expiry_drops_selection_without_retaining_a_second_pending_command()
    {
        var clock = new Clock();
        var store = new ConversationStore(TimeSpan.FromMinutes(1), clock);
        using (var first = await store.AcquireAsync("verified-person:conversation", CancellationToken.None))
        {
            first.State.ClientId = 2003;
            first.State.TaxYear = 2023;
            Assert.True(first.IsNew);
        }
        clock.Advance(TimeSpan.FromMinutes(1));
        using var expired = await store.AcquireAsync("verified-person:conversation", CancellationToken.None);
        Assert.True(expired.IsNew);
        Assert.Null(expired.State.ClientId);
        Assert.Null(expired.State.TaxYear);
        Assert.Empty(expired.State.History);
    }

    [Fact]
    public async Task An_active_or_waiting_turn_is_not_evicted_and_same_key_turns_are_serialized()
    {
        var clock = new Clock();
        var store = new ConversationStore(TimeSpan.FromSeconds(1), clock);
        var first = await store.AcquireAsync("person:conversation", CancellationToken.None);
        first.State.ClientId = 2003;
        var waiting = store.AcquireAsync("person:conversation", CancellationToken.None).AsTask();
        clock.Advance(TimeSpan.FromMinutes(2));
        using (await store.AcquireAsync("other-person:conversation", CancellationToken.None))
        {
            Assert.False(waiting.IsCompleted);
            Assert.Equal(2, store.Count);
        }
        first.Dispose();
        using var second = await waiting;
        Assert.False(second.IsNew);
        Assert.Equal(2003, second.State.ClientId);
        Assert.Same(first.State, second.State);
    }

    [Fact]
    public async Task Cancelling_a_waiter_releases_its_borrow_without_unlocking_the_active_turn()
    {
        var clock = new Clock();
        var store = new ConversationStore(TimeSpan.FromSeconds(1), clock);
        var first = await store.AcquireAsync("person:conversation", CancellationToken.None);
        using var cancel = new CancellationTokenSource();
        var waiting = store.AcquireAsync("person:conversation", cancel.Token).AsTask();
        await cancel.CancelAsync();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => waiting);
        first.Dispose();
        clock.Advance(TimeSpan.FromSeconds(1));
        using var expired = await store.AcquireAsync("person:conversation", CancellationToken.None);
        Assert.True(expired.IsNew);
    }

    [Fact]
    public async Task A_reused_response_chain_cannot_share_a_selected_client_between_verified_people()
    {
        using var model = new ScriptedModel(ScriptedModel.Tools(("client_trend", new())), ScriptedModel.Text("The trend is shown."),
            ScriptedModel.Tools(("client_trend", new())), ScriptedModel.Text("A client is needed."));
        var rig = new Rig(model);
        await rig.SayAsync("How has Cascade trended?");
        var other = await rig.SayAsync("How have they trended?", Rig.Person(Rig.OtherOid));
        Assert.Equal("clarify", other.Kind);
        Assert.DoesNotContain(rig.Gateway.Calls, call => call.Tool == "client_trend" && call.Identity.Oid == Rig.OtherOid);
        Assert.Single(rig.Gateway.Calls, call => call.Tool == "client_trend" && call.Identity.Oid == Rig.Oid);
    }

    [Fact]
    public void Routing_history_is_bounded_and_never_treated_as_numeric_authority()
    {
        var state = new ConversationState();
        for (var turn = 0; turn < 10; turn++) { state.Remember("user", new string('x', 600)); }
        Assert.Equal(6, state.History.Count);
        Assert.All(state.History, entry => Assert.Equal(500, entry["text"]!.ToString().Length));
    }

    private sealed class Clock : TimeProvider
    {
        private long _ticks;
        public override long GetTimestamp() => _ticks;
        public override long TimestampFrequency => TimeSpan.TicksPerSecond;
        internal void Advance(TimeSpan amount) => _ticks += amount.Ticks;
    }
}
