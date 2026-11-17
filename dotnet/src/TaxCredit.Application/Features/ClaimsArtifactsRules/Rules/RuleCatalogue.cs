using System.Globalization;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Rules;

/// <summary>File timestamps describe deployed assets, not an invented statutory publication date.</summary>
public interface IRuleFileMetadata
{
    /// <summary>The actual modification time of one known flat file.</summary>
    DateTimeOffset ModifiedAt(string fileName);
}

internal sealed class RuleCatalogue(IRulePackSource source, RuleLibrary rules, ILookupStore lookups)
{
    internal IReadOnlyList<(string File, PyDict Pack)> Packs() => source.ListJsonStems("").Order(StringComparer.Ordinal)
        .Select(stem => (File: stem + ".json", Pack: rules.LoadPack(stem + ".json"))).ToArray();

    internal PyDict? Verification(string? code)
    {
        if (code is null) { return null; }
        var stored = lookups.Entries("rule_verification", 0).LastOrDefault(e => e.Key == code);
        if (stored is not null) { return (PyDict)PyJson.Loads(stored.ValueJson)!; }
        return code switch
        {
            "GA_JTC" => new PyDict().Add("verified_by", "K. Wallace, JD (External tax counsel)").Add("verified_at", "2026-03-22")
                .Add("note", "Tier 1 GA county designations re-verified against current DOR guidance."),
            "FED_WOTC" => new PyDict().Add("verified_by", "K. Wallace, JD (External tax counsel)").Add("verified_at", "2026-04-02")
                .Add("note", "WOTC target group caps + flat $2,400 simplified amount confirmed against IRS Form 5884."),
            _ => null,
        };
    }

    internal void Verify(string code, PyDict verification, string actor, PyDateTime now) =>
        lookups.Put(new LookupEntry("rule_verification", 0, "program", code, PyJson.Dumps(verification), actor), now);

    internal static object? Get(PyDict? map, string key) => map is not null && map.TryGetValue(key, out var value) ? value : null;
    internal static PyDict? Map(PyDict? map, string key) => Get(map, key) as PyDict;

    internal PyDict Row(string file, PyDict pack)
    {
        var credit = Map(pack, "credit");
        var jurisdiction = Map(pack, "jurisdiction");
        var code = Get(credit, "code") as string;
        var verification = Verification(code);
        return new PyDict().Add("file", file).Add("code", code).Add("name", Get(credit, "name"))
            .Add("jurisdiction", Get(jurisdiction, "code")).Add("jurisdiction_level", Get(jurisdiction, "level"))
            .Add("citation", Get(credit, "statutory_citation")).Add("threshold", Get(Map(pack, "thresholds"), "minimum_new_jobs"))
            .Add("benefit_period_years", Get(Map(pack, "benefit"), "benefit_period_years"))
            .Add("prototype_verification", Get(pack, "_prototype_verification")).Add("effective_date", Get(pack, "effective_date"))
            .Add("version", Get(pack, "rule_pack_version")).Add("filing", Get(pack, "filing"))
            .Add("pinned_claims", LegacyPinnedCount(code)).Add("verified", verification is not null).Add("verification", verification)
            .Add("one_zero", Get(pack, "one_zero"));
    }

    // Display-only legacy catalogue pins from backend/data/claims.py, not operational filing assertions.
    private static int LegacyPinnedCount(string? code) => code is "GA_JTC" or "SC_JTC" or "FED_WOTC" or "TN_JTC" or "VA_MBJF" ? 1 : 0;

    internal static PyDict Recent(string file, PyDict pack, DateTimeOffset modified)
    {
        var credit = Map(pack, "credit");
        var name = Get(credit, "name") as string ?? Path.GetFileNameWithoutExtension(file);
        var version = Get(pack, "rule_pack_version") as string ?? "0.1.0";
        var window = Get(Map(pack, "filing"), "window") as string ?? "\u2014";
        return new PyDict().Add("timestamp_utc", modified.UtcDateTime.ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture))
            .Add("citation", Get(credit, "statutory_citation") ?? Path.GetFileNameWithoutExtension(file)).Add("credit_code", Get(credit, "code"))
            .Add("title", name + " \u2014 prototype pack pinned").Add("detail", $"Filing: {window} \u00b7 pinned as v{version}")
            .Add("version", "v" + version).Add("status", "ok");
    }
}
