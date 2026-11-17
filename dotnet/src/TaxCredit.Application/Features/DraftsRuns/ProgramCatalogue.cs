using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Reads installed registry/pack files, never proposals, for the catalogue and its calculation coverage.</summary>
public sealed record ProgramCatalogueQuery(string? Code = null) : IQuery<object>;

internal sealed class ProgramCatalogueHandler(RuleLibrary rules, IRulePackSource source, PackValidator validator, ISourceReader book, IClaimRepository claims)
    : IRequestHandler<ProgramCatalogueQuery, object>
{
    private const string Note = "Not verified. A rule pack that validates is well-formed, not legally correct: a person must verify each statutory value against the primary source. [ADR-005]";

    public ValueTask<object> Handle(ProgramCatalogueQuery request, CancellationToken cancellationToken)
    {
        var entries = rules.LoadRegistry().Entries;
        var counts = book.ListAccounts().SelectMany(c => claims.Engagements(c.AccountId)).GroupBy(e => e.ProgramCode)
            .ToDictionary(g => g.Key, g => g.GroupBy(e => e.Scope.Value()).ToDictionary(s => s.Key, s => s.LongCount()), StringComparer.Ordinal);
        if (request.Code is not null)
        {
            var entry = rules.LoadRegistry().Get(request.Code) ?? throw new DraftsRunsRefusalException(404, "Unknown program.");
            return ValueTask.FromResult<object>(Detail(entry, counts.GetValueOrDefault(entry.Code) ?? []));
        }
        return ValueTask.FromResult<object>(new PyDict().Add("programs", entries.Select(e => (object?)Row(e, counts.GetValueOrDefault(e.Code) ?? [])).ToList())
            .Add("total", (long)entries.Count).Add("engagement_available", true).Add("verification_note", Note));
    }

    private PyDict Row(ProgramEntry entry, Dictionary<string, long> engagement)
    {
        var years = source.IsFile(entry.PackFile) ? rules.AuthoredYears(entry.PackFile) : [];
        var status = entry.Status(years);
        var calculable = status == "calculable" && entry.Level != "federal";
        return new PyDict().Add("code", entry.Code).Add("name", entry.Name).Add("state", entry.State)
            .Add("jurisdiction", new PyDict().Add("level", entry.Level).Add("code", entry.JurisdictionCode)).Add("lifecycle", status)
            .Add("authored_years", years.Cast<object?>().ToList()).Add("unverified_years", years.Where(y => Unverified(entry, y)).Cast<object?>().ToList())
            .Add("verification", "not_verified").Add("calculable", calculable).Add("not_calculable_reason", calculable ? "" : Reason(entry, status))
            .Add("engagement", new PyDict().Add("in_scope", engagement.GetValueOrDefault("in_scope")).Add("out_of_scope", engagement.GetValueOrDefault("out_of_scope"))
                .Add("prospective", engagement.GetValueOrDefault("prospective")).Add("clients", engagement.Values.Sum()));
    }

    private PyDict Detail(ProgramEntry entry, Dictionary<string, long> engagement)
    {
        var row = Row(entry, engagement);
        var present = source.IsFile(entry.PackFile);
        var pack = present ? rules.LoadPack(entry.PackFile) : new PyDict();
        var years = rules.AuthoredYears(entry.PackFile).Select(year =>
        {
            var path = entry.PackFile[..^5] + "/" + year + ".json";
            var document = rules.LoadYearPack(entry.PackFile, year).Pack;
            return new PyDict().Add("tax_year", year).Add("rule_pack_version", FeatureValues.Text(document, "rule_pack_version"))
                .Add("unverified", Unverified(entry, year)).Add("source", FeatureValues.Map(document, "_year_provenance").TryGetValue("source", out var value) ? value : null)
                .Add("issues", Issues(path, true));
        }).ToArray();
        var issues = present ? Issues(entry.PackFile, years.Length > 0) : [];
        var errors = issues.Concat(years.SelectMany(y => (List<object?>)y["issues"]!)).Cast<PyDict>().LongCount(i => Equals(i["severity"], "error"));
        var blockers = new List<object?>();
        if (row["not_calculable_reason"] is string { Length: > 0 } reason) { blockers.Add(reason); }
        if (errors > 0) { blockers.Add($"{errors} validation error(s) in the pack files: see the validation results."); }
        var credit = FeatureValues.Map(pack, "credit");
        return row.Add("pack", new PyDict().Add("file", entry.PackFile).Add("present", present)
            .Add("rule_pack_version", FeatureValues.Text(pack, "rule_pack_version")).Add("credit_name", FeatureValues.Text(credit, "name"))
            .Add("citation", FeatureValues.Text(credit, "statutory_citation")).Add("engine_profile", new PyDict()
                .Add("credit_model", entry.EngineProfile.CreditModel).Add("headcount_model", entry.EngineProfile.HeadcountModel)).Add("notes", entry.Notes))
            .Add("years", years.Cast<object?>().ToList()).Add("validation", new PyDict().Add("pack", issues).Add("error_count", errors).Add("valid", errors == 0))
            .Add("blockers", blockers);
    }

    private List<object?> Issues(string path, bool authored) => validator.ValidatePack(path, authored).Issues.Select(i => (object?)new PyDict()
        .Add("severity", i.Severity).Add("code", i.Code).Add("path", i.Path).Add("message", i.Message)).ToList();
    private bool Unverified(ProgramEntry entry, long year) => rules.ResolveStatutoryFloors(entry.Code, year).PrototypeVerify;
    private static string Reason(ProgramEntry entry, string status) => entry.Level == "federal"
        ? "A federal program has no state, and a run prices a state's payroll rows: federal programs are described, not calculable."
        : status == "retired" ? "Retired: the engine no longer resolves this program."
        : status == "draft" ? "Draft: registered for authoring only. It becomes calculable when a human commits an authored year pack and sets it described."
        : $"No year-scoped rule packs authored for {entry.Code}. ADR-005: statute is not inherited across years.";
}
