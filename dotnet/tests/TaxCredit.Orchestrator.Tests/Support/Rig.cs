using Microsoft.Extensions.AI;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Orchestrator.Boundary;
using TaxCredit.Orchestrator.Framework;
using TaxCredit.Orchestrator.Hosting;
using TaxCredit.Orchestrator.Planning;
using TaxCredit.Orchestrator.Turns;

namespace TaxCredit.Orchestrator.Tests.Support;

internal sealed class Rig
{
    internal const string Tenant = "00000000-0000-0000-0000-0000000000aa";
    internal const string Oid = "bbbbbbbb-0000-4000-8000-000000000002";
    internal const string OtherOid = "cccccccc-0000-4000-8000-000000000003";
    internal FakeGateway Gateway { get; }
    internal TurnPipeline Pipeline { get; }
    internal ChannelHost Host { get; }
    internal ConversationStore Store { get; }

    internal Rig(IChatClient? model = null, bool supportsTools = true, bool debug = false,
        FakeGateway? gateway = null, TimeProvider? clock = null, int maxCalls = 8)
    {
        Gateway = gateway ?? new FakeGateway();
        var catalog = new ModelToolCatalog(new CapabilityCatalog());
        var loop = new FrameworkToolLoop(catalog);
        var planner = new TurnPlanner(catalog, loop, model, supportsTools);
        Store = new ConversationStore(TimeSpan.FromMinutes(30), clock);
        var workflow = new WorkflowBridge(Gateway, catalog, clock);
        Pipeline = new TurnPipeline(Gateway, catalog, planner, Store, workflow, new TurnOptions(maxCalls, AgentVersion: "7"));
        var identity = new IdentityOptions(Tenant, debugWhoami: debug, agentVersion: "7");
        Host = new ChannelHost(identity, Pipeline, Store, new DebugCommandHandler(identity), ["gateway"], model is not null, model is not null && supportsTools);
    }

    internal static ActingIdentity Person(string oid = Oid, string conversation = "conv-1", string correlation = "corr-1") =>
        IdentityResolver.Resolve(new IdentityContext(OriginalSubject: new PlatformOriginalSubject(oid, Tenant, "user"),
            ConversationId: conversation, ResponseId: correlation), new IdentityOptions(Tenant)).Identity!;

    internal Task<TurnReply> SayAsync(string text, ActingIdentity? person = null) =>
        Pipeline.HandleAsync(text, person ?? Person());
}
