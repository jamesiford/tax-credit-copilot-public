using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Briefs;
using TaxCredit.Application.Features.Ai.Streams;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Api.Tests.Ai;

internal sealed class StreamFacts : IPageFactSource, IPageScope
{
    internal JsonObject Portfolio { get; set; } = JsonNode.Parse("""
        {"total_clients":2,"assessed_clients":1,"items":[
          {"client_name":"Example Books","priority_band":"on_the_line","jobs_margin":-0.83,"program_code":"GA_JTC","tax_year":2025}
        ]}
        """)!.AsObject();
    public string ClientName(long clientId) => "Example Books";
    public IReadOnlyList<int> PlaceholderYears(string state) => [];
    public ValueTask<JsonObject> PortfolioAsync(CancellationToken cancellationToken) => ValueTask.FromResult(Portfolio.DeepClone().AsObject());
    public ValueTask<JsonObject> ClientAsync(SummaryQuery query, CancellationToken cancellationToken) =>
        ValueTask.FromResult(new JsonObject { ["items"] = new JsonArray() });
    public ValueTask<JsonObject> UnitAsync(SummaryQuery query, CancellationToken cancellationToken) =>
        ValueTask.FromResult(JsonNode.Parse("""
            {"year":2025,"unit":{"worksite_id":"UNIT-A","average_headcount":17.25,"base_average_headcount":9.17,
               "status":"above_minimum","net_new_vs_base":8.08,"threshold":2},
             "total_unfiltered":21,"thresholds":{"min_weekly_hours":35},
             "near_threshold":[{"employee_id":"SYNTHETIC-PERSON","avg_weekly_hours":34.76,"additional_weekly_hours":0.24}]}
            """)!.AsObject());
    public ValueTask<JsonObject> EmployeeAsync(SummaryQuery query, CancellationToken cancellationToken) =>
        ValueTask.FromResult(JsonNode.Parse("""
            {"employee_id":"SYNTHETIC-PERSON","tax_year":2025,
             "thresholds":{"minimum_average_weekly_hours":"35","minimum_average_weekly_wages_usd":"680"},
             "raw_source_rows":[{"selection_decision":"included"}],
             "step1":{"min_max":{"eligible":true,"avg_weekly_hours":40,"avg_weekly_wages":1000}}}
            """)!.AsObject());
}

internal sealed class StreamNarrator : IAiNarrator
{
    internal bool AvailableFlag { get; set; }
    internal string[] Tokens { get; set; } = ["Only 0.83 jobs short."];
    internal bool FailAfterFirst { get; set; }
    internal bool BlockAfterFirst { get; set; }
    internal bool Disposed { get; private set; }
    internal string? Prompt { get; private set; }
    internal TaskCompletionSource FirstEmitted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    internal TaskCompletionSource Released { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public bool Available(IEnumerable<string> agents) => AvailableFlag && !agents.Contains("OrchestratorAgent", StringComparer.Ordinal);

    public async IAsyncEnumerable<ModelEvent> StreamAsync(string agent, string prompt, string principal,
        JsonElement trustedFacts, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        Prompt = prompt;
        try
        {
            for (var index = 0; index < Tokens.Length; index++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                yield return new TextDelta(Tokens[index]);
                FirstEmitted.TrySetResult();
                if (index == 0 && BlockAfterFirst) { await Released.Task.WaitAsync(cancellationToken); }
                if (index == 0 && FailAfterFirst) { throw new IOException("synthetic upstream failure"); }
            }
            yield return new StreamEnd("scripted-test");
        }
        finally { Disposed = true; }
    }
}
