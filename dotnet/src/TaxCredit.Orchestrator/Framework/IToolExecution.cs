using System.Text.Json.Nodes;

namespace TaxCredit.Orchestrator.Framework;

/// <summary>Per-turn state is supplied to shared framework definitions through invocation context.</summary>
public interface IToolExecution
{
    /// <summary>The one settling pipeline surrounds the generated function's logic-free forwarder.</summary>
    Task<object?> InvokeAsync(string name, JsonObject proposed,
        Func<JsonObject, CancellationToken, Task<object?>> forward, CancellationToken cancellationToken);

    /// <summary>Forwards the settled call without interpreting its figures.</summary>
    Task<object?> ForwardAsync(string name, JsonObject arguments, CancellationToken cancellationToken);

    /// <summary>Unknown names must count even when the SDK cannot find a registered function.</summary>
    void RefuseUnknown(string name);
}
