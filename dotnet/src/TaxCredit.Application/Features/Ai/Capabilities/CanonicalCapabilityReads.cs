using System.Globalization;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Briefs;
using TaxCredit.Application.Features.ReadsCalc;
using TaxCredit.Application.Features.ReadsCalc.Portfolio;
using TaxCredit.Application.Features.ReadsCalc.Stored;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Domain.Calculation;

namespace TaxCredit.Application.Features.Ai.Capabilities;

/// <summary>Canonical feature collaborators supply figures; this bridge only shapes their capability contracts.</summary>
public sealed class CanonicalCapabilityReads(IMediator mediator, ReadStatutes statutes,
    ReadsStoredPortfolioBriefs stored, ReadsPortfolioService portfolio)
    : ICapabilityReadBridge
{
    /// <inheritdoc />
    public async Task<CapabilityRead> ReadAsync(string capability, JsonObject arguments, ApiPrincipal principal,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(arguments);
        cancellationToken.ThrowIfCancellationRequested();
        return capability switch
        {
            "book_rank" => new(CanonicalPageReads.Object(
                await mediator.Send(CanonicalPageReads.Portfolio(), cancellationToken).ConfigureAwait(false))),
            "client_eligibility" => Eligibility(arguments),
            _ => throw Missing(capability),
        };
    }

    private CapabilityRead Eligibility(JsonObject args)
    {
        var client = args["client_id"]!.GetValue<long>();
        var year = args["tax_year"]!.GetValue<int>();
        var asked = args["program_code"]?.GetValue<string>();
        var statute = statutes.ResolveStatute(client, args["state"]?.GetValue<string>(), year, asked, true);
        var method = args["method"]?.GetValue<string>() ?? "min_max";
        if (method == "both") { method = "pay_period"; }
        IReadOnlyDictionary<string, object?>? run = null;
        var recorder = TrailContext.Current ?? new TrailRecorder("Pending");
        using var trail = TrailContext.Use(recorder);
        var context = CanonicalPageReads.Object(stored.ClientContext(client, year, method, statute.ProgramCode, row => run = row));
        var snapshot = Snapshot(client, year, statute.State, context, statute.Window.Begin, statute.Window.End);
        var credit = CanonicalPageReads.Object(portfolio.StateCredit(statute.State, year, client,
            context["current_average"]?.GetValue<double>(), context["prior_average"]?.GetValue<double>(), statute.ProgramCode));
        var facts = new JsonObject { ["snapshot"] = snapshot, ["credit"] = credit };
        if (asked is not null) { facts["program_code"] = statute.ProgramCode; }
        var evidence = CapabilityDirectReads.RunEvidence(run is null ? null : CanonicalPageReads.Object(run), "tcc_gold");
        evidence["trail_sha256"] = recorder.Steps.Count == 0 ? null
            : ((string)recorder.ToDict()["evidence_hash"]!)[7..];
        return new(facts, evidence);
    }

    private static JsonObject Snapshot(long client, int year, string state, JsonObject context, DateOnly begin, DateOnly end)
    {
        var snapshot = new JsonObject
        {
            ["source"] = "tcc_gold \u2014 read from the run that computed it",
            ["selected_client_id"] = client,
            ["selected_tax_year"] = year,
            ["state"] = state,
            ["calculated"] = context["calculated"]?.DeepClone(),
            ["average_headcount"] = context["current_average"]?.DeepClone(),
            ["prior_year_average_headcount"] = context["prior_average"]?.DeepClone(),
            ["run_id"] = context["run_id"]?.DeepClone(),
            ["fiscal_window"] = new JsonObject
            {
                ["begin"] = begin.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                ["end"] = end.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
            },
        };
        if (context["calculated"]?.GetValue<bool>() != true)
        {
            snapshot["note"] = $"No calculated run holds TY{year} for this client. That is not a zero \u2014 say so rather than reporting a figure.";
        }
        return snapshot;
    }

    private static CapabilityException Missing(string capability)
    {
        var (owner, service) = CapabilityDependencies.Read(capability);
        return CapabilityException.Missing(owner, service);
    }
}
