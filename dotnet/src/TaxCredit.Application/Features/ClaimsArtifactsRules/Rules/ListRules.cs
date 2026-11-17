using System.Globalization;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Rules;

/// <summary>Reads actual flat rule documents and their practitioner sign-offs.</summary>
public sealed record ListRules : IQuery<object>;

internal sealed class ListRulesHandler(RuleCatalogue catalogue, IRuleFileMetadata metadata, IClock clock) : IRequestHandler<ListRules, object>
{
    public ValueTask<object> Handle(ListRules request, CancellationToken cancellationToken)
    {
        var packs = catalogue.Packs();
        var rows = packs.Select(p => catalogue.Row(p.File, p.Pack)).ToArray();
        var recent = packs.Select(p => (p.File, p.Pack, Modified: metadata.ModifiedAt(p.File))).OrderByDescending(p => p.Modified).ToArray();
        var verified = rows.Count(r => (bool)r["verified"]!);
        return ValueTask.FromResult<object>(new PyDict().Add("as_of", clock.UtcNow.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture))
            .Add("rule_count", rows.Length).Add("summary", new PyDict().Add("programs_codified", rows.Length).Add("active_rule_versions", rows.Length)
                .Add("last_update_iso", recent.Length == 0 ? null : recent[0].Modified.ToString("yyyy-MM-dd'T'HH:mmzzz", CultureInfo.InvariantCulture))
                .Add("pending_review", rows.Length - verified).Add("verified_count", verified).Add("vision_program_count", "240+"))
            .Add("recent_changes", recent.Take(5).Select(p => RuleCatalogue.Recent(p.File, p.Pack, p.Modified)).ToArray()).Add("rules", rows));
    }
}
