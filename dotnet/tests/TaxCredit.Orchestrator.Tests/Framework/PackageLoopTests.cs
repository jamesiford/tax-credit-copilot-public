using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Orchestrator.Framework;

namespace TaxCredit.Orchestrator.Tests.Framework;

public sealed class PackageLoopTests
{
    [Fact]
    public async Task Scripted_call_crosses_real_agent_function_middleware_and_generated_body()
    {
        var catalog = new ModelToolCatalog(new CapabilityCatalog());
        var loop = new FrameworkToolLoop(catalog);
        var turn = new ProbeTurn();
        await loop.RunOneAsync(turn, "book_rank", new JsonObject { ["limit"] = 2 }, CancellationToken.None);
        Assert.Equal(["middleware", "body"], turn.Trace);
        Assert.Equal(2, turn.Arguments?["limit"]?.GetValue<int>());
        Assert.Equal(25, catalog.Definitions.Count);
        Assert.DoesNotContain(catalog.Definitions, definition => definition.Name.EndsWith("_commit", StringComparison.Ordinal));
    }

    [Fact]
    public async Task Unlisted_name_never_executes_a_body()
    {
        var turn = new ProbeTurn();
        await new FrameworkToolLoop(new ModelToolCatalog(new CapabilityCatalog()))
            .RunOneAsync(turn, "finding_resolve_commit", [], CancellationToken.None);
        Assert.Equal(["refused"], turn.Trace);
    }

    private sealed class ProbeTurn : IToolExecution
    {
        public List<string> Trace { get; } = [];
        public JsonObject? Arguments { get; private set; }
        public Task<object?> InvokeAsync(string name, JsonObject proposed,
            Func<JsonObject, CancellationToken, Task<object?>> forward, CancellationToken cancellationToken)
        {
            Trace.Add("middleware");
            return forward(proposed, cancellationToken);
        }

        public Task<object?> ForwardAsync(string name, JsonObject arguments, CancellationToken cancellationToken)
        {
            Trace.Add("body");
            Arguments = arguments;
            return Task.FromResult<object?>(new JsonObject { ["ok"] = true });
        }

        public void RefuseUnknown(string name) => Trace.Add("refused");
    }
}
