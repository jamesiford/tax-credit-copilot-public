using TaxCredit.Domain.DataMap;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Findings;
using TaxCredit.Application.Features.DraftsRuns;
using TaxCredit.Application.Features.ReadsCalc;
using TaxCredit.Application.Features.ReadsCalc.Portfolio;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Programs;
using static TaxCredit.Application.Features.Ai.Capabilities.Bindings.CapabilityBindingValues;

namespace TaxCredit.Application.Features.Ai.Capabilities.Bindings;

/// <summary>Capability projections reuse the same scoped application features as the portal.</summary>
public sealed class ApplicationCapabilityReads(CanonicalCapabilityReads canonical, IMediator mediator,
    CapabilityRiskReads risk, ReadsDiscoveryService discovery,
    RuleLibrary rules, CapabilityPackageTickets packages) : ICapabilityReadBridge
{
    /// <inheritdoc />
    public async Task<CapabilityRead> ReadAsync(string capability, JsonObject arguments, ApiPrincipal principal,
        CancellationToken cancellationToken)
    {
        return capability switch
        {
            "book_rank" or "client_eligibility" => await canonical.ReadAsync(capability, arguments, principal, cancellationToken).ConfigureAwait(false),
            "client_at_risk" => risk.Read(arguments),
            "client_discovery" => Discovery(arguments),
            "calc_walkthrough" => await canonical.WalkthroughAsync(arguments, cancellationToken).ConfigureAwait(false),
            "simulate" => await Simulation(arguments, cancellationToken).ConfigureAwait(false),
            "employee_drill" => await Employee(arguments, cancellationToken).ConfigureAwait(false),
            "findings_list" => new(await Query(new ListFindings(Client(arguments), Year(arguments),
                Text(arguments, "state"), Text(arguments, "program_code")), cancellationToken).ConfigureAwait(false),
                CapabilityResult.Evidence(source: "payroll exception detection, run live")),
            "program_catalog" => await Programs(arguments, cancellationToken).ConfigureAwait(false),
            "run_batch_list" => await Batches(arguments, cancellationToken).ConfigureAwait(false),
            "run_batch_status" => await Batch(arguments, cancellationToken).ConfigureAwait(false),
            "claim_package_link" => packages.Link(arguments, principal),
            "claim_package_redeem" => packages.Redeem(arguments),
            _ => throw CapabilityException.Missing(CapabilityDependencies.Read(capability).Owner, CapabilityDependencies.Read(capability).Service),
        };
    }

    private CapabilityRead Discovery(JsonObject args)
    {
        var excluded = args["exclude_codes"] is JsonArray codes ? codes.Select(code => code!.GetValue<string>()).ToArray()
            : rules.LoadRegistry().ForState(Text(args, "state") ?? "").Select(entry => entry.Code).ToArray();
        var recorder = new TrailRecorder("Pending");
        using var trail = TrailContext.Use(recorder);
        var facts = Object(discovery.DiscoverCredits(excluded, Client(args), args["tax_year"] is null ? null : Year(args)));
        var evidence = CapabilityResult.Evidence(source: "rule-pack library scan");
        evidence["trail_sha256"] = recorder.Steps.Count == 0 ? null : ((string)recorder.ToDict()["evidence_hash"]!)[7..];
        return new(facts, evidence, ["Rule packs other than the Georgia Jobs Tax Credit are illustrative. Do not rely on a figure from one."]);
    }

    private async Task<CapabilityRead> Employee(JsonObject args, CancellationToken token)
    {
        var facts = await Query(new StoredReadQuery("drill", Arguments(args)), token).ConfigureAwait(false);
        return new(facts, CapabilityDirectReads.RunEvidence(facts["run"] as JsonObject, PhysicalNames.Active.Map.GoldSchema));
    }

    private async Task<CapabilityRead> Simulation(JsonObject args, CancellationToken token)
    {
        var facts = await Query(new CalculateViewQuery("POST /api/simulate/unit", Arguments(args)), token).ConfigureAwait(false);
        return new(facts, CapabilityResult.Evidence(runId: Text(facts, "run_id"), source: PhysicalNames.Active.Map.GoldSchema));
    }

    private async Task<CapabilityRead> Programs(JsonObject args, CancellationToken token)
    {
        var facts = await Query(new ProgramCatalogueQuery(Text(args, "program_code")), token).ConfigureAwait(false);
        if (facts["programs"] is JsonArray programs)
        {
            facts["calculable"] = programs.Count(program => program?["calculable"]?.GetValue<bool>() == true);
        }
        facts["verification_note"] = "Not verified. A rule pack that validates is well-formed, not legally correct: a person must verify each value against the primary source.";
        return new(facts);
    }

    private async Task<CapabilityRead> Batches(JsonObject args, CancellationToken token)
    {
        var facts = await Query(new ListBatchesQuery(args["limit"] is { } limit ? CapabilityJson.SmallInteger(limit) : 5,
            Status: Text(args, "status")), token).ConfigureAwait(false);
        if (facts["items"] is not JsonArray { Count: > 0 }) { throw NotCalculated("No run batch has been started yet."); }
        return new(facts, CapabilityResult.Evidence(source: "run batch queue"));
    }

    private async Task<CapabilityRead> Batch(JsonObject args, CancellationToken token)
    {
        var id = Text(args, "batch_id");
        if (string.IsNullOrEmpty(id))
        {
            var latest = await Batches(new JsonObject { ["limit"] = 1 }, token).ConfigureAwait(false);
            id = latest.Facts["items"]![0]!["batch_id"]!.GetValue<string>();
        }
        var facts = await Query(new GetBatchQuery(id), token).ConfigureAwait(false);
        var failures = new JsonArray();
        if (facts["counts"]?["failed"]?.GetValue<long>() > 0)
        {
            var page = await Query(new ListBatchItemsQuery(id, "failed", 50), token).ConfigureAwait(false);
            foreach (var group in page["items"]!.AsArray().GroupBy(item => item!["error_dependency"]?.GetValue<string>() ?? "unknown").OrderByDescending(group => group.Count()))
            {
                failures.Add(new JsonObject { ["dependency"] = group.Key, ["count"] = group.Count(), ["message"] = group.First()!["error_message"]?.DeepClone() });
            }
        }
        facts["failures"] = failures;
        var warnings = (facts["degraded"] as JsonArray ?? []).Select(item => $"{item!["dependency"]}: {item["impact"]} {item["remedy"]}").ToArray();
        return new(facts, CapabilityResult.Evidence(source: "run batch queue"), warnings);
    }

    private async Task<JsonObject> Query(IRequest<object> request, CancellationToken token) =>
        Object(await mediator.Send(request, token).ConfigureAwait(false));
}
