using System.Text.RegularExpressions;
using TaxCredit.Application.Features.Ai.Numeric;

namespace TaxCredit.Gateway.Execution;

internal static class NarrationPolicy
{
    private static readonly HashSet<string> Qualifiers = new(StringComparer.Ordinal)
    { "about", "around", "roughly", "approximately", "approx", "approximate", "approximated", "nearly", "almost", "circa", "rounded", "rounding", "round", "ballpark" };
    private static readonly HashSet<string> Rounding = new(StringComparer.Ordinal)
    { "rounded", "rounding", "round", "approximate", "approximately", "approximated", "approx" };
    private static readonly string[][] Phrases =
    [
        ["up", "to"], ["close", "to"], ["or", "so"], ["more", "or", "less"], ["give", "or", "take"],
        ["in", "the", "region", "of"], ["on", "the", "order", "of"], ["just", "over"], ["just", "under"],
        ["just", "above"], ["just", "below"], ["a", "little", "over"], ["a", "little", "under"],
        ["somewhere", "around"], ["in", "the", "ballpark"],
    ];
    private static readonly Regex Token = Pattern(@"\S+");
    private static readonly Regex Edge = Pattern(@"^[^\w~\u2588]+|[^\w~\u2588]+$");
    private static readonly (string Code, Regex Rule)[] Rules =
    [
        ("url", Pattern("""\b(?:https?://|www\.)[^\s<>()\[\]"']+""")),
        ("email", Pattern(@"[a-z0-9._%+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+")),
        ("phone", Pattern(@"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")),
        ("ssn_shape", Pattern(@"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
        ("ein_shape", Pattern(@"(?<!\d)\d{2}-\d{7}(?!\d)")),
        ("code_fence", Pattern(@"```|~~~")),
        ("legal_advice", Pattern(@"\b(?:as your (?:tax |legal )?(?:attorney|lawyer|advis[eo]r|cpa|accountant)"
            + @"|(?:this|that|it) (?:is|constitutes) (?:formal )?(?:legal|tax) advice"
            + @"|i (?:advise|recommend) (?:that )?you (?:to )?(?:file|claim|amend)"
            + @"|you (?:should|must|need to) (?:file|claim|amend)\b"
            + @"|you (?:are|will be) (?:legally )?(?:entitled|guaranteed)"
            + @"|(?:guarantee[sd]?|guaranteed) (?:the |a |your )?(?:credit|refund|approval|outcome)"
            + @"|(?:safe|protected) from (?:an )?audit|(?:will|can)(?: not|'t|not) be audited|no (?:risk|chance) of (?:an )?audit)")),
    ];

    internal static IEnumerable<NumericViolation> Review(string masked, string rendered)
    {
        var tokens = Token.Matches(masked).Select(match => Edge.Replace(match.Value.ToLowerInvariant(), "")).ToArray();
        var qualifiers = tokens.Select((token, index) => (token, index))
            .Where(item => Qualifiers.Contains(item.token) || item.token.StartsWith('~')).Select(item => item.index).ToHashSet();
        foreach (var phrase in Phrases)
        {
            for (var start = 0; start + phrase.Length <= tokens.Length; start++)
            {
                if (!tokens.AsSpan(start, phrase.Length).SequenceEqual(phrase)) { continue; }
                for (var offset = 0; offset < phrase.Length; offset++) { qualifiers.Add(start + offset); }
            }
        }
        for (var i = 0; i < tokens.Length; i++)
        {
            if ((tokens[i].Contains('\u2588') || tokens[i].Any(char.IsDigit)) && qualifiers.Any(position => Math.Abs(i - position) <= 3))
            { yield return Violation("approximation", "narration style: an approximation qualifier next to a figure", "narration"); }
            if (Rounding.Contains(tokens[i]))
            { yield return Violation("approximation", "narration style: the wording says a figure was rounded or approximated", "narration"); }
        }
        foreach (var (code, rule) in Rules)
        {
            if (rule.IsMatch(rendered)) { yield return Violation("output_policy", "output policy: " + code, "output_policy"); }
        }
    }

    private static NumericViolation Violation(string kind, string code, string stage) => new(new(code, 0, 0, kind), code, stage, null);
    private static Regex Pattern(string pattern) => new(pattern, RegexOptions.IgnoreCase | RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1));
}
