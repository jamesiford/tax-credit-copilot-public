using System.Globalization;
using System.Text.Json;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Infrastructure.Sources.Lookups;

/// <summary>Seed values carry authored provenance and never masquerade as customer-authored mappings.</summary>
public sealed record LookupSeed(int Version, bool Inferred, string Basis, string AuthoredBy,
    string AuthoredOn, IReadOnlyDictionary<string, string> Entries);

/// <summary>Lookup policy is injected/resettable; customer mode defaults to strict and rejects inferred seed truth.</summary>
public sealed record SourceLookupOptions(bool CustomerClassified = false, string? PayCodePolicy = null,
    string FiscalPolicy = "assume")
{
    /// <summary>Resolved default appropriate to data classification.</summary>
    public string EffectivePayCodePolicy => PayCodePolicy ?? (CustomerClassified ? "strict" : "assume");
}

/// <summary>Resolved pay-code category with its actual provider.</summary>
public sealed record PayCodeResolution(string? Category, string Provider, bool Inferred);

/// <summary>Read-only Persistence bridge. No local database, writes, or configuration globals are introduced.</summary>
public sealed class LookupResolver
{
    private readonly ISourceLookupReader? _reader;
    private readonly LookupSeed? _seed;
    private readonly TimeProvider _clock;
    private string? _seedIdentity;
    /// <summary>The policy for this source instance.</summary>
    public SourceLookupOptions Options { get; }

    /// <summary>Failed lookup reads propagate; no catch converts an unavailable store into an inferred answer.</summary>
    public LookupResolver(ISourceLookupReader? reader = null, LookupSeed? payCodeSeed = null,
        SourceLookupOptions? options = null, TimeProvider? clock = null)
    {
        _reader = reader;
        _seed = payCodeSeed;
        _clock = clock ?? TimeProvider.System;
        Options = options ?? new SourceLookupOptions();
        if (Options.EffectivePayCodePolicy is not ("assume" or "strict") || Options.FiscalPolicy is not ("assume" or "strict"))
        {
            throw new ArgumentException("Unknown lookup policy.");
        }
    }

    /// <summary>Code then category within client, before code then category within global, then permitted seed.</summary>
    public PayCodeResolution PayCode(long accountId, string? code, long? categoryId = null)
    {
        var entries = Entries("pay_code_category", accountId);
        var normalized = (code ?? "").Trim().ToUpperInvariant();
        foreach (var client in new[] { accountId, 0L }.Distinct())
        {
            foreach (var (kind, key) in new[] { ("code", normalized),
                         ("category", categoryId?.ToString(CultureInfo.InvariantCulture) ?? "") })
            {
                var found = entries.LastOrDefault(e => e.ClientId == client && e.Kind == kind
                    && string.Equals(e.Key.Trim(), key, StringComparison.OrdinalIgnoreCase) && key.Length > 0);
                if (found is not null) { return new PayCodeResolution(found.Value, "override", found.Inferred); }
            }
        }
        if (_seed is not null && (!Options.CustomerClassified || Options.EffectivePayCodePolicy == "assume")
            && _seed.Entries.TryGetValue(normalized, out var value))
        {
            return new PayCodeResolution(value, "seed", _seed.Inferred);
        }
        return new PayCodeResolution(null, "none", false);
    }

    /// <summary>
    /// A digest of what decides a pay code's category today for this client: the active override entries (client and global) and the seed.
    /// The projection cache compares it, because an operator's lookup edit changes a projection without touching the source.
    /// </summary>
    public string PayCodeDigest(long accountId)
    {
        var lines = Entries("pay_code_category", accountId).OrderBy(e => e.ClientId).ThenBy(e => e.Kind, StringComparer.Ordinal)
            .ThenBy(e => e.Key, StringComparer.Ordinal).ThenBy(e => e.Value, StringComparer.Ordinal)
            .Select(e => string.Join('\u001f', e.ClientId.ToString(CultureInfo.InvariantCulture), e.Kind, e.Key, e.Value, e.Inferred ? "1" : "0"));
        return Sha256(SeedIdentity + "\n" + string.Join('\n', lines));
    }

    /// <summary>The seed's version, provenance flag and a hash of its entries, or <c>none</c>; constant for the life of the resolver.</summary>
    public string SeedIdentity => _seedIdentity ??= _seed is null ? "none" : string.Join('|', _seed.Version.ToString(CultureInfo.InvariantCulture),
        _seed.Inferred ? "inferred" : "authored", Sha256(string.Join('\n', _seed.Entries.OrderBy(e => e.Key, StringComparer.Ordinal).Select(e => e.Key + "=" + e.Value))));

    private static string Sha256(string text) =>
        Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(text)));

    /// <summary>Client rules precede global rules; malformed authored dates fail at the boundary even under assume policy.</summary>
    public IReadOnlyList<FiscalRule> FiscalOverrides(long accountId)
    {
        return Entries("entity_fiscal_year_rules", accountId).Where(e => e.Kind == "rule")
            .OrderBy(e => e.ClientId == 0).Select(ParseFiscalOverride).ToArray();
    }

    /// <summary>Latest committed version wins and all seed provenance fields are required.</summary>
    public static LookupSeed? LoadSeed(string directory, string lookup = "pay_code_category")
    {
        var found = Directory.EnumerateFiles(directory, lookup + ".v*.json")
            .Select(path => (Path: path, Version: int.TryParse(Path.GetFileNameWithoutExtension(path)[(lookup.Length + 2)..],
                NumberStyles.None, CultureInfo.InvariantCulture, out var v) ? v : -1)).Where(p => p.Version >= 0)
            .OrderByDescending(p => p.Version).FirstOrDefault();
        if (found.Path is null) { return null; }
        using var doc = JsonDocument.Parse(File.ReadAllText(found.Path));
        var root = doc.RootElement;
        if (root.GetProperty("lookup").GetString() != lookup || root.GetProperty("version").GetInt32() != found.Version)
        {
            throw new InvalidDataException("Seed lookup/version mismatch.");
        }
        var entries = root.GetProperty("entries").EnumerateObject()
            .ToDictionary(p => p.Name, p => p.Value.GetString()!, StringComparer.Ordinal);
        return new LookupSeed(found.Version, root.GetProperty("inferred").GetBoolean(), root.GetProperty("basis").GetString()!,
            root.GetProperty("authored_by").GetString()!, root.GetProperty("authored_on").GetString()!, entries);
    }

    private SourceLookupEntry[] Entries(string lookup, long accountId)
    {
        var today = DateOnly.FromDateTime(_clock.GetUtcNow().UtcDateTime);
        return (_reader?.Entries(lookup, accountId) ?? []).Where(e => e.Lookup == lookup
            && (e.ClientId == accountId || e.ClientId == 0)
            && (e.EffectiveFrom is null || today >= e.EffectiveFrom)
            && (e.EffectiveTo is null || today <= e.EffectiveTo)).ToArray();
    }

    private static FiscalRule ParseFiscalOverride(SourceLookupEntry entry)
    {
        try
        {
            using var doc = JsonDocument.Parse(entry.Value);
            var begin = ParseOverrideDate(doc.RootElement.GetProperty("fiscal_year_begin").GetString());
            var end = ParseOverrideDate(doc.RootElement.GetProperty("fiscal_year_end").GetString());
            var expression = doc.RootElement.TryGetProperty("rule_expression", out var expr) ? expr.GetString() : null;
            return new FiscalRule("override:" + entry.Key, expression, begin, end);
        }
        catch (Exception error) when (error is JsonException or KeyNotFoundException or InvalidOperationException)
        {
            throw new FiscalRulesMissing();
        }
    }

    private static DateOnly ParseOverrideDate(string? value) =>
        value is not null && PyDate.TryFromIsoFormat(value, out var date) ? date : throw new FiscalRulesMissing();
}
