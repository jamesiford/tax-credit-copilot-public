using System.Globalization;
using System.Text.Json;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Prices in-memory proposed statute on the designated synthetic dataset, writing nothing.</summary>
public sealed record PreviewDraftQuery(string DraftId, JsonElement? Body) : IQuery<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

internal sealed class PreviewDraftHandler(DraftLifecycle lifecycle, DraftValidation validation, SyntheticPreviewSample sample, RuleLibrary rules)
    : IRequestHandler<PreviewDraftQuery, object>
{
    public ValueTask<object> Handle(PreviewDraftQuery request, CancellationToken cancellationToken)
    {
        var draft = lifecycle.Load(request.DraftId);
        if (draft.Years.Count == 0) { throw new PreviewRefused("Add a year pack to preview a calculation."); }
        if (validation.Validate(draft)["valid"] is not true) { throw new PreviewRefused("Validate and fix the draft before previewing it."); }
        var body = FeatureValues.Document(request.Body);
        var dataset = FeatureValues.Text(body, "dataset", "synthetic_sample");
        if (dataset == "client" && body.TryGetValue("client_id", out var client) && client is not null) { throw new CustomerDataRefused("A preview reads only the committed synthetic sample, never client payroll."); }
        if (dataset != "synthetic_sample") { throw new PreviewRefused("The supported dataset is synthetic_sample."); }
        var rows = sample.Load(draft.State!);
        var averages = new Dictionary<long, (double Average, int Rows, int Months)>();
        var declined = new List<object?>();
        foreach (var (key, document) in draft.Years.OrderBy(p => p.Key, PyStr.Comparer))
        {
            cancellationToken.ThrowIfCancellationRequested();
            var year = long.Parse(key, CultureInfo.InvariantCulture);
            var selected = Headcount.RowsForStateYear(rows, draft.State!, year);
            var months = selected.Select(r => r.PayDate.Text![..7]).Distinct(StringComparer.Ordinal).Count();
            if (selected.Count < ClientAssessment.MinRowsToAssess) { declined.Add(new PyDict().Add("tax_year", year).Add("reason", "no_payroll").Add("detail", $"the sample holds {selected.Count} row(s) for {draft.State} in {year}")); }
            else if (months < ClientAssessment.MinMonthsToAssess) { declined.Add(new PyDict().Add("tax_year", year).Add("reason", "payroll_too_thin").Add("detail", $"payroll covers {months} month(s) of {year}")); }
            else { averages[year] = (Headcount.AverageHeadcount(rows, draft.State!, year, OneZeroPackBuilder.FromDocument((PyDict)document!, year)), selected.Count, months); }
        }
        var wanted = FeatureValues.Years(body, "tax_years");
        var years = new List<object?>();
        foreach (var (year, current) in averages.OrderBy(p => p.Key).Where(p => wanted.Count == 0 || wanted.Contains(p.Key)))
        {
            var hasPrior = averages.TryGetValue(year - 1, out var prior);
            var credit = rules.CreditFromPack((PyDict)draft.Years[year.ToString(CultureInfo.InvariantCulture)]!,
                (draft.ProposedCode, draft.State!, DraftViews.FileName(draft)), current.Average, hasPrior ? prior.Average : current.Average, null);
            years.Add(new PyDict().Add("tax_year", year).Add("average_headcount", PyRound.Round(current.Average, 2))
                .Add("prior_average_headcount", hasPrior ? PyRound.Round(prior.Average, 2) : null).Add("is_base_year", !hasPrior)
                .Add("threshold_jobs", credit["threshold"]).Add("qualifying_jobs", credit["qualifying_jobs"]).Add("per_job_usd", credit["amount_per_job_usd"])
                .Add("annual_credit_usd", credit["annual_credit_usd"]).Add("benefit_period_years", credit["benefit_period_years"])
                .Add("window", "calendar year (assumed for the sample)").Add("rows_used", (long)current.Rows).Add("months_with_payroll", (long)current.Months));
        }
        return ValueTask.FromResult<object>(new PyDict().Add("label", "Preview, not verified, not for filing").Add("draft_id", draft.DraftId)
            .Add("proposed_code", draft.ProposedCode).Add("state", draft.State).Add("dataset", new PyDict().Add("kind", "synthetic_sample")
                .Add("description", "Committed synthetic sample payroll (generated; not a client's data), relabelled to the draft's state").Add("client_id", null))
            .Add("unverified", true).Add("unverified_flags", DraftDocuments.All(draft).Sum(d => Flags(d.Document))).Add("years", years)
            .Add("declined", declined).Add("persisted", false).Add("wrote_nothing", true));
    }

    private static long Flags(object? node) => node switch
    {
        PyDict map => (map.TryGetValue("_prototype_verify", out var flag) && flag is true ? 1 : 0) + map.Sum(p => Flags(p.Value)),
        IReadOnlyList<object?> list => list.Sum(Flags),
        _ => 0,
    };
}
