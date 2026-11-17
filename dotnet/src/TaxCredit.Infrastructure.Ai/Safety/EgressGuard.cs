using System.Text.Json;
using System.Text.RegularExpressions;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Safety;

/// <summary>External-provider policy never weakens the identifier invariant.</summary>
public enum EgressPolicy
{
    /// <summary>Permits clean prompts.</summary>
    AllowAll,
    /// <summary>Requires an aggregate brief for external providers.</summary>
    AggregatesOnly,
    /// <summary>Disables all external-provider egress.</summary>
    BlockExternal
}

/// <summary>The identifier invariant applies even to internal providers, independent of operator policy.</summary>
public sealed partial class EgressGuard(EgressPolicy policy = EgressPolicy.AllowAll) : IModelGuard
{
    /// <inheritdoc/>
    public GuardDecision Evaluate(NarrationRequest request, string provider)
    {
        string text = request.Spec.Instructions + "\n" + request.Prompt + "\n" + request.TrustedFacts?.GetRawText();
        var rules = IdentifierRules(text);
        if (rules.Count != 0)
        {
            return new(false, rules);
        }

        if (provider is not ("gateway" or "foundry_connection"))
        {
            return new(true, []);
        }

        if (policy == EgressPolicy.BlockExternal)
        {
            return new(false, ["external_blocked"]);
        }

        if (policy == EgressPolicy.AggregatesOnly && !Aggregate(request))
        {
            return new(false, ["aggregates_required"]);
        }

        return new(true, []);
    }
    /// <summary>Identifies forbidden identifier shapes, excluding trail hashes.</summary>
    public static IReadOnlyList<string> IdentifierRules(string text)
    {
        var rules = new List<string>();
        if (RecordToken().IsMatch(text))
        {
            rules.Add("record_token");
        }

        if (Ssn().IsMatch(text))
        {
            rules.Add("ssn");
        }

        if (IdentifierKey().IsMatch(text))
        {
            rules.Add("identifier_field");
        }

        return rules;
    }
    private static bool Aggregate(NarrationRequest request)
    {
        if (request.TrustedFacts is { } trusted)
        {
            return !HasRows(trusted) && !RowGrainJsonKey().IsMatch(request.Prompt);
        }

        string prompt = request.Prompt;
        int marker = prompt.LastIndexOf("JSON:", StringComparison.Ordinal);
        if (marker < 0)
        {
            return false;
        }

        try
        {
            using var doc = JsonDocument.Parse(prompt[(marker + 5)..]);
            return !HasRows(doc.RootElement);
        }
        catch (JsonException) { return false; }
    }
    private static bool HasRows(JsonElement node) => node.ValueKind switch
    {
        JsonValueKind.Object => node.EnumerateObject().Any(p => RowKey().IsMatch(p.Name) || HasRows(p.Value)),
        JsonValueKind.Array => node.EnumerateArray().Any(HasRows),
        _ => false
    };
    [GeneratedRegex(@"(?<![0-9a-fA-F])[0-9a-f]{24}(?![0-9a-fA-F])")]
    private static partial Regex RecordToken();
    [GeneratedRegex(@"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")]
    private static partial Regex Ssn();
    [GeneratedRegex("\"(?:employee_ids?|employee_id_hash|record_tokens?|ssn)\"\\s*:", RegexOptions.IgnoreCase)]
    private static partial Regex IdentifierKey();
    [GeneratedRegex("employee|record_token|ssn|worksite|unit_id|evidence|person", RegexOptions.IgnoreCase)]
    private static partial Regex RowKey();
    [GeneratedRegex("\"[^\"]*(?:employee|record_token|ssn|worksite|unit_id|evidence|person)[^\"]*\"\\s*:", RegexOptions.IgnoreCase)]
    private static partial Regex RowGrainJsonKey();
}
