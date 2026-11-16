using System.Text.RegularExpressions;

namespace TaxCredit.Orchestrator.Composition;

internal static partial class NarrationPolicy
{
    private static readonly HashSet<string> Hedges = new(StringComparer.Ordinal)
    {
        "about", "around", "roughly", "approximately", "approx", "approximate", "approximated",
        "nearly", "almost", "circa", "rounded", "rounding", "round", "ballpark",
    };
    private static readonly HashSet<string> Rounding = new(StringComparer.Ordinal)
    {
        "rounded", "rounding", "round", "approximate", "approximately", "approximated", "approx",
    };
    private static readonly string[][] Phrases =
    [
        ["up", "to"], ["close", "to"], ["or", "so"], ["more", "or", "less"], ["give", "or", "take"],
        ["in", "the", "region", "of"], ["on", "the", "order", "of"], ["just", "over"], ["just", "under"],
        ["just", "above"], ["just", "below"], ["a", "little", "over"], ["a", "little", "under"],
        ["somewhere", "around"], ["in", "the", "ballpark"],
    ];

    internal static IReadOnlyList<string> Review(string substituted, string masked, IReadOnlyList<string> allowedHosts)
    {
        var codes = new List<string>();
        if (UrlPattern().Matches(substituted).Any(match => !Allowed(match.Value, allowedHosts)) ||
            MarkdownLinkPattern().Matches(substituted).Any(match => !Allowed(match.Groups[1].Value, allowedHosts)) ||
            UnsafeSchemePattern().IsMatch(substituted))
        {
            codes.Add("output_policy_url");
        }
        foreach (var (code, pattern) in new (string, Regex)[]
        {
            ("output_policy_email", EmailPattern()), ("output_policy_phone", PhonePattern()),
            ("output_policy_ssn_shape", SsnPattern()), ("output_policy_ein_shape", EinPattern()),
            ("output_policy_code_fence", FencePattern()), ("output_policy_legal_advice", LegalPattern()),
        })
        {
            if (pattern.IsMatch(substituted))
            {
                codes.Add(code);
            }
        }
        if (Hedged(masked))
        {
            codes.Add("narration_approximation");
        }
        return codes;
    }

    private static bool Allowed(string url, IReadOnlyList<string> hosts)
    {
        if (!Uri.TryCreate(url.Contains("://", StringComparison.Ordinal) ? url : "https://" + url,
            UriKind.Absolute, out var uri) || uri.Scheme is not ("https" or "http") || uri.UserInfo.Length != 0)
        {
            return false;
        }
        return hosts.Any(allowed =>
        {
            var host = allowed.TrimStart('.');
            return host.Length != 0 && (uri.IdnHost.Equals(host, StringComparison.OrdinalIgnoreCase) ||
                uri.IdnHost.EndsWith("." + host, StringComparison.OrdinalIgnoreCase));
        });
    }

    private static bool Hedged(string masked)
    {
        var tokens = TokenPattern().Matches(masked).Select(match => EdgePattern().Replace(match.Value.ToLowerInvariant(), "")).ToArray();
        if (tokens.Any(Rounding.Contains))
        {
            return true;
        }
        var hedges = tokens.Select((token, index) => (token, index))
            .Where(item => Hedges.Contains(item.token) || item.token.StartsWith('~')).Select(item => item.index).ToHashSet();
        foreach (var phrase in Phrases)
        {
            for (var start = 0; start <= tokens.Length - phrase.Length; start++)
            {
                if (tokens.AsSpan(start, phrase.Length).SequenceEqual(phrase))
                {
                    hedges.UnionWith(Enumerable.Range(start, phrase.Length));
                }
            }
        }
        return tokens.Select((token, index) => (token, index))
            .Any(item => (item.token.Contains('█') || item.token.Any(char.IsDigit)) &&
                hedges.Any(position => Math.Abs(position - item.index) <= 3));
    }

    [GeneratedRegex("""\b(?:https?://|www\.)[^\s<>()\[\]"']+""", RegexOptions.IgnoreCase)]
    private static partial Regex UrlPattern();

    [GeneratedRegex(@"!?\[[^\]\r\n]*\]\(\s*<?([^\s)>]+)>?(?:\s+[^)]*)?\)")]
    private static partial Regex MarkdownLinkPattern();

    [GeneratedRegex(@"\b(?:javascript|data|file|vbscript):", RegexOptions.IgnoreCase)]
    private static partial Regex UnsafeSchemePattern();

    [GeneratedRegex(@"[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+", RegexOptions.IgnoreCase)]
    private static partial Regex EmailPattern();

    [GeneratedRegex(@"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")]
    private static partial Regex PhonePattern();

    [GeneratedRegex(@"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")]
    private static partial Regex SsnPattern();

    [GeneratedRegex(@"(?<!\d)\d{2}-\d{7}(?!\d)")]
    private static partial Regex EinPattern();

    [GeneratedRegex("```|~~~")]
    private static partial Regex FencePattern();

    [GeneratedRegex(@"\b(?:as your (?:tax |legal )?(?:attorney|lawyer|advis[eo]r|cpa|accountant)|(?:this|that|it) (?:is|constitutes) (?:formal )?(?:legal|tax) advice|i (?:advise|recommend) (?:that )?you (?:to )?(?:file|claim|amend)|you (?:should|must|need to) (?:file|claim|amend)\b|you (?:are|will be) (?:legally )?(?:entitled|guaranteed)|(?:guarantee[sd]?|guaranteed) (?:the |a |your )?(?:credit|refund|approval|outcome)|(?:safe|protected) from (?:an )?audit|(?:will|can)(?: not|'t|not) be audited|no (?:risk|chance) of (?:an )?audit)", RegexOptions.IgnoreCase)]
    private static partial Regex LegalPattern();

    [GeneratedRegex(@"\S+")]
    private static partial Regex TokenPattern();

    [GeneratedRegex(@"^[^\w~█]+|[^\w~█]+$")]
    private static partial Regex EdgePattern();
}
