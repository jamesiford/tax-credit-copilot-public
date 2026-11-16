using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.Ai.Numeric;

namespace TaxCredit.Orchestrator.Composition;

/// <summary>The single boundary between a narrator's words and the reader's checked answer.</summary>
public static class GuardedReplyComposer
{
    /// <summary>Safe failure text is deterministic and contains no unverified figures.</summary>
    public const string VerificationNotice =
        "The figures in this answer could not be verified against the engine's output, so none are shown.";

    /// <summary>Compose evidence first, screen raw narration, substitute trusted formatting, then independently check output.</summary>
    public static ComposedReply ComposeReply(string question, IReadOnlyList<CompositionRun> runs, string? narration,
        IReadOnlyList<string>? allowedHosts = null, ReferenceContext? reference = null)
    {
        var result = ComposeCore(question, runs, narration, allowedHosts);
        if (!result.NarrationUsed || reference is null)
        {
            return result;
        }
        var full = CompositionProjection.Index(FactsOf(runs));
        var shown = CompositionProjection.Index(ModelFactsOf(runs));
        var references = reference.ReaderText(CompositionProjection.HiddenText(full, shown).Concat(CompositionProjection.Secrets(runs)));
        return result with { Text = Join(result.Body, references, result.Footer), ReferenceText = references };
    }

    private static ComposedReply ComposeCore(string question, IReadOnlyList<CompositionRun> runs, string? narration,
        IReadOnlyList<string>? allowedHosts)
    {
        ArgumentNullException.ThrowIfNull(runs);
        var violations = new List<NumericViolation>();
        try
        {
            var full = CompositionProjection.Index(CompositionProjection.Facts(runs, model: false));
            var shown = CompositionProjection.Index(CompositionProjection.Facts(runs, model: true));
            var context = CompositionProjection.Context(question, runs);
            var blocks = BlockRendering.Render(runs);
            var fallback = Join(blocks, CapabilityResult.Disclaimer);
            var secrets = CompositionProjection.Secrets(runs);
            if (CompositionProjection.ContainsHiddenText(fallback, secrets))
            {
                return Unverified([Violation("private_confirmation_in_evidence", "blocks")], runs);
            }
            var blockGuard = NumericGuard.Check(fallback, full, context, "blocks");
            if (!blockGuard.Passed)
            {
                return Unverified(SafeViolations(blockGuard), runs);
            }
            if (string.IsNullOrWhiteSpace(narration))
            {
                return Finish(fallback, runs, violations, narrationUsed: false);
            }
            if (CompositionProjection.ContainsHiddenText(narration, secrets))
            {
                violations.Add(Violation("private_confirmation"));
                return Finish(fallback, runs, violations, narrationUsed: false);
            }
            var expanded = Screen(narration, full, shown, context, allowedHosts ?? [], violations);
            if (expanded is not null && violations.Count == 0)
            {
                var body = Join(expanded.Text.Trim(), fallback);
                var final = NumericGuard.Check(body, expanded.Index, context);
                if (final.Passed)
                {
                    return Finish(body, runs, violations, narrationUsed: true);
                }
                violations.AddRange(SafeViolations(final));
            }
            return Finish(fallback, runs, violations, narrationUsed: false);
        }
        catch (Exception exception) when (exception is ArgumentException or InvalidOperationException or FormatException or OverflowException)
        {
            violations.Add(Violation("invalid_capability_evidence", "blocks"));
            return Unverified(violations, runs);
        }
    }

    /// <summary>Alternate argument order for runner call sites.</summary>
    public static ComposedReply ComposeReply(IReadOnlyList<CompositionRun> runs, string? narration,
        string question = "", IReadOnlyList<string>? allowedHosts = null, ReferenceContext? reference = null) =>
        ComposeReply(question, runs, narration, allowedHosts, reference);

    /// <summary>The reader's full, confirmation-free facts. Never send this object to a model.</summary>
    public static JsonObject FactsOf(IReadOnlyList<CompositionRun> runs) => CompositionProjection.Facts(runs, model: false);

    /// <summary>Only lane-projected, bounded facts may cross the model boundary.</summary>
    public static JsonObject ModelFactsOf(IReadOnlyList<CompositionRun> runs) => CompositionProjection.Facts(runs, model: true);

    /// <summary>Build the sole names-only model brief.</summary>
    public static JsonObject NarrationBrief(string question, IReadOnlyList<CompositionRun> runs, bool fenced = false) =>
        ModelBrief.Build(question, runs, fenced);

    /// <summary>Runner-friendly name for the shared brief builder.</summary>
    public static JsonObject Brief(string question, IReadOnlyList<CompositionRun> runs, bool fenced = false) =>
        NarrationBrief(question, runs, fenced);

    /// <summary>Project a completed call for a framework or degraded planner model request.</summary>
    public static JsonObject ModelAnswer(CompositionRun run, JsonObject brief) => ModelBrief.Answer(run, brief);

    private static PlaceholderExpansion? Screen(string narration, FactIndex facts, FactIndex shown,
        AllowedContext context, IReadOnlyList<string> hosts, List<NumericViolation> violations)
    {
        if (narration.Length > 65_536)
        {
            violations.Add(Violation("narration_too_large"));
            return null;
        }
        try
        {
            var expanded = FactPlaceholders.Expand(narration, facts, shown);
            if (CompositionProjection.ContainsHiddenText(expanded.Masked, CompositionProjection.HiddenText(facts, shown)))
            {
                violations.Add(Violation("outside_model_view"));
            }
            violations.AddRange(SafeViolations(NumericGuard.CheckRaw(expanded.Masked, context)));
            violations.AddRange(NarrationPolicy.Review(expanded.Text, expanded.Masked, hosts).Select(code => Violation(code)));
            return expanded;
        }
        catch (PlaceholderException exception)
        {
            violations.Add(Violation(exception.Message));
            return null;
        }
    }

    private static ComposedReply Unverified(IEnumerable<NumericViolation> violations, IReadOnlyList<CompositionRun> runs) =>
        Finish(Join(VerificationNotice, CapabilityResult.Disclaimer), runs, violations, narrationUsed: false,
            blocksVerified: false, notice: VerificationNotice);

    private static ComposedReply Finish(string body, IReadOnlyList<CompositionRun> runs,
        IEnumerable<NumericViolation> violations, bool narrationUsed, bool blocksVerified = true, string? notice = null)
    {
        var all = violations.ToArray();
        var footer = ProvenanceFooter(runs);
        return new(Join(body, footer), body, footer, new(all.Length == 0 ? "pass" : "rejected", all),
            narrationUsed, blocksVerified, notice);
    }

    private static IEnumerable<NumericViolation> SafeViolations(GuardResult guard) =>
        guard.Violations.Select(item => Violation("numeric_" + item.Numeral.Kind, item.Stage));

    private static NumericViolation Violation(string code, string stage = "narration") =>
        new(new(code, 0, 0, "rule"), code, stage, null);

    internal static string Join(params string[] parts) => string.Join("\n\n", parts.Where(part => part.Length != 0));

    /// <summary>Source identifiers are appended after guarding figures; the model never rewrites them.</summary>
    public static string ProvenanceFooter(IReadOnlyList<CompositionRun> runs)
    {
        var sources = new List<string>();
        var secrets = CompositionProjection.Secrets(runs);
        foreach (var run in runs)
        {
            var provenance = run.Result.Provenance;
            var runId = SafeSource(provenance["run_id"]);
            var rules = SafeSource(provenance["rule_pack_version"]);
            var trail = SafeSource(provenance["trail_sha256"]);
            var source = SafeSource(provenance["source"]);
            var line = string.Join(" · ", new[]
            {
                runId is null ? null : "run " + runId,
                rules is null ? null : "rules " + rules,
                trail is null ? null : "trail " + trail[..Math.Min(12, trail.Length)],
                runId is null ? source : null,
            }.OfType<string>());
            if (line.Length != 0 && !CompositionProjection.ContainsHiddenText(line, secrets) &&
                !sources.Contains(line, StringComparer.Ordinal))
            {
                sources.Add(line);
            }
        }
        return string.Join("\n", sources.Select(line => "_Source: " + line + "_"));
    }

    private static string? SafeSource(JsonNode? node)
    {
        var value = CompositionProjection.String(node);
        return string.IsNullOrEmpty(value) || value.Length > 2048 || value.Any(char.IsControl) ? null : value;
    }
}
