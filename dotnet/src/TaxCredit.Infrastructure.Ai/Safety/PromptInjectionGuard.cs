using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace TaxCredit.Infrastructure.Ai.Safety;

/// <summary>Pattern screening is deliberately conservative; it complements, not replaces, numeric validation.</summary>
public sealed class PromptInjectionGuard
{
    private const string Object = @"(?:instructions?|rules?|prompts?|directions?|guidelines?|constraints?|restrictions?|programming)";
    private static readonly IReadOnlyDictionary<string, string> Patterns = new Dictionary<string, string>
    {
        ["override_instructions"] = $@"\b(?:ignore|disregard|forget|override|bypass|discard|drop|skip)\b(?: \w+){{0,3}} {Object}\b",
        ["override_facts"] = @"\b(?:ignore|disregard|override|replace|contradict)\b(?: \w+){0,3} (?:json|facts?|figures?|numbers?|data|brief|engine)\b",
        ["persona_switch"] = @"\b(?:you are now|from now on,? you|you will now act|pretend (?:to be|you are|that you)|roleplay as|simulate being)|(?:^|[.!?:] |\bplease |\byou (?:must|should|will|can|could) |\bnow |\bjust )act as (?:if|though|an?|the|my)\b",
        ["reveal_prompt"] = $@"\b(?:reveal|print|show|repeat|output|display|leak|tell me|what (?:is|are|was|were))\b(?: \w+){{0,4}} (?:system|hidden|initial|original|your|the above|above) (?:prompt|message|{Object})\b",
        ["role_markers"] = @"<\|[a-z_]+\|>|\[/?inst\]|<</?sys>>",
        ["fence_spoof"] = @"<<<\s*untrusted|end untrusted\s*>>>",
        ["jailbreak"] = @"\b(?:jailbreak|developer mode|dan mode|do anything now|no restrictions|without (?:any )?(?:restrictions|limits|filters))\b",
        ["new_instructions"] = $@"\b(?:new|updated|real|actual|additional) {Object}\b ?[:\-]",
        ["exfiltrate"] = @"\b(?:send|post|upload|forward|email|exfiltrate|transmit)\b(?: \w+){0,6} (?:to|at) (?:https?://|www\.|[\w.-]+@)",
        ["encoding_evasion"] = @"\b(?:base64|rot13|hex)\b(?: \w+){0,4} (?:encode|decode|encoded|decoded)|\b(?:encode|decode)\b(?: \w+){0,4} (?:in|as|into|using) (?:base64|rot13|hex)\b"
    };
    private static readonly IReadOnlyDictionary<string, string[]> Compact = new Dictionary<string, string[]>
    {
        ["override_instructions"] = ["ignorepreviousinstructions", "ignoreallinstructions", "disregardpreviousinstructions",
            "ignoreyourinstructions", "ignoretheabove", "forgetyourinstructions"],
        ["persona_switch"] = ["youarenow", "pretendtobe"],
        ["reveal_prompt"] = ["revealyoursystemprompt", "printyoursystemprompt", "showyoursystemprompt", "repeatyoursystemprompt"]
    };
    private static readonly TimeSpan RegexTimeout = TimeSpan.FromSeconds(1);
    /// <summary>Returns controlled rule names, never the matching text.</summary>
    public static IReadOnlyList<string> Scan(string text)
    {
        try { return ScanCore(text); }
        catch (RegexMatchTimeoutException) { return ["screening_limit"]; }
        catch (ArgumentException) { return ["invalid_unicode"]; }
    }
    private static IReadOnlyList<string> ScanCore(string text)
    {
        string clean = string.Concat(UnicodeFold.Normalize(UntrustedText.Unwrap(text))
            .Where(ch => CharUnicodeInfo.GetUnicodeCategory(ch) != UnicodeCategory.Format)).ToLowerInvariant();
        string spaced = Regex.Replace(clean, @"\s+", " ", RegexOptions.None, RegexTimeout).Trim();
        string compact = Regex.Replace(clean, "[^a-z]", "", RegexOptions.None, RegexTimeout);
        var hits = new SortedSet<string>(StringComparer.Ordinal);
        foreach (var (code, pattern) in Patterns)
        {
            if (Regex.IsMatch(spaced, pattern, RegexOptions.CultureInvariant, RegexTimeout))
            {
                hits.Add(code);
            }
        }

        foreach (var (code, phrases) in Compact)
        {
            if (phrases.Any(p => compact.Contains(p, StringComparison.Ordinal)))
            {
                hits.Add(code);
            }
        }

        if (Regex.IsMatch(clean, @"^[ \t>*#-]*(?:system|assistant|developer)(?: (?:prompt|message))?[ \t]*:",
            RegexOptions.Multiline, RegexTimeout))
        {
            hits.Add("forged_role");
        }

        return [.. hits];
    }
}
