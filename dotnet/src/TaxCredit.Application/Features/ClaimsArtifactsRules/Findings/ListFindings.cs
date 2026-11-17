using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Qc;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Findings;

/// <summary>Surfaces decisions at policy or employee-month grain without changing the certified writer.</summary>
public sealed record ListFindings(long ClientId, long TaxYear, string? State, string? ProgramCode) : IQuery<object>;

internal sealed class ListFindingsHandler(IClientPayrollSource payroll, IFindingRepository repository, ProgramDefaults defaults)
    : IRequestHandler<ListFindings, object>
{
    public ValueTask<object> Handle(ListFindings request, CancellationToken cancellationToken)
    {
        var state = request.State;
        if (!string.IsNullOrEmpty(request.ProgramCode))
        {
            try
            {
                defaults.CheckProgramState(state, request.ProgramCode);
                state = defaults.ProgramState(request.ProgramCode);
            }
            catch (ProgramStateConflict e) { throw new FeatureRefusalException(422, e.Message); }
            catch (ProgramNotRunnable e) { throw new FeatureRefusalException(404, e.Message); }
        }
        var rows = payroll.LoadPayPeriods(request.ClientId);
        if (rows.Count == 0) { throw new FeatureRefusalException(404, "No payroll for this client in the active data source."); }
        var scoped = rows.Where(r => string.IsNullOrEmpty(state) || Headcount.RowState(r.Row).Equals(state, StringComparison.OrdinalIgnoreCase)).Select(r => r.Dict).ToArray();
        var decisions = repository.Live(request.ClientId, request.TaxYear).ToDictionary(d => d.FindingId, StringComparer.Ordinal);
        var groups = new Dictionary<string, List<PyDict>>(StringComparer.Ordinal)
        {
            ["test_of_twos"] = QcDetector.DetectTestOfTwos(scoped, request.TaxYear, state),
            ["meaningful_pay_period"] = QcDetector.DetectScragglyPayPeriods(scoped, request.TaxYear, state),
        };
        var present = groups.Where(g => g.Value.Count > 0).ToArray();
        var items = present.SelectMany(g => FindingPresentation.Items(g.Key, g.Value, request.TaxYear, state, decisions))
            .OrderBy(i => !(bool)i["requires_decision"]!).ThenBy(i => (string)i["finding_id"]!, StringComparer.Ordinal).ToArray();
        var open = items.Count(i => (bool)i["requires_decision"]!);
        var result = new PyDict().Add("client_id", request.ClientId).Add("tax_year", request.TaxYear)
            .Add("state", string.IsNullOrEmpty(state) ? null : state.ToUpperInvariant()).Add("findings", items)
            .Add("summary", new PyDict().Add("total", items.Length).Add("requires_decision", open).Add("instances", present.Sum(g => g.Value.Count))
                .Add("all_decided", items.Length > 0 && open == 0).Add("none_found", items.Length == 0)
                .Add("by_kind", present.Aggregate(new PyDict(), (map, g) => map.Add(g.Key, g.Value.Count))));
        if (!string.IsNullOrEmpty(request.ProgramCode)) { result.Add("program_code", request.ProgramCode.Trim().ToUpperInvariant()); }
        return ValueTask.FromResult<object>(result);
    }
}
