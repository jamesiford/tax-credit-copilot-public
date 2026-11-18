using TaxCredit.Domain.DataMap;
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
        var client = CapabilityJson.Integer(args["client_id"]!);
        var year = checked((int)CapabilityJson.Integer(args["tax_year"]!));
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
        var evidence = CapabilityDirectReads.RunEvidence(run is null ? null : CanonicalPageReads.Object(run), PhysicalNames.Active.Map.GoldSchema);
        evidence["trail_sha256"] = recorder.Steps.Count == 0 ? null
            : ((string)recorder.ToDict()["evidence_hash"]!)[7..];
        return new(facts, evidence);
    }

    /// <summary>Captures the canonical stored-result credit explanation, not a payroll replay.</summary>
    public Task<CapabilityRead> WalkthroughAsync(JsonObject args, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var recorder = new TrailRecorder("Pending");
        using var trail = TrailContext.Use(recorder);
        var read = Eligibility(args);
        if (read.Facts["snapshot"]?["calculated"]?.GetValue<bool>() != true)
        {
            throw new CapabilityException(409, "not_calculated", "No calculated run holds this client-year. That is not a zero.");
        }
        var credit = read.Facts["credit"]!;
        if (credit["no_state_pack"]?.GetValue<bool>() == true)
        {
            throw new CapabilityException(404, "year_not_authored", credit["message"]!.GetValue<string>());
        }
        recorder.Title = $"{credit["credit_name"]} · TY{args["tax_year"]}";
        recorder.Citation = credit["citation"]?.GetValue<string>() ?? "";
        var facts = CanonicalPageReads.Object(recorder.ToDict());
        if (args["program_code"] is not null) { facts["program_code"] = read.Facts["program_code"]?.DeepClone(); }
        var evidence = read.Provenance!;
        evidence["trail_sha256"] = ((string)recorder.ToDict()["evidence_hash"]!)[7..];
        return Task.FromResult(new CapabilityRead(facts, evidence));
    }

    private static JsonObject Snapshot(long client, int year, string state, JsonObject context, DateOnly begin, DateOnly end)
    {
        var snapshot = new JsonObject
        {
            ["source"] = PhysicalNames.Active.Map.GoldSchema + " \u2014 read from the run that computed it",
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
