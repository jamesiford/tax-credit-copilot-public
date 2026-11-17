using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.Ai.Numeric;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Infrastructure.Auth;

namespace TaxCredit.Gateway.Execution;

internal sealed class ChannelState(IRuntimeConfiguration settings, TimeProvider clock)
{
    private static readonly string[][] ViolationHeader = [["Figure", "Position", "Why"]];
    private readonly object _gate = new();
    private readonly Dictionary<(string Person, string Conversation), LedgerEntry> _ledger = [];
    private sealed record LedgerEntry(long Stamp, List<JsonElement> Facts);
    private ApiRateLimiter? _limiter;
    private int? _profileRate;
    private int _rate;

    internal RateLimitDecision Spend(string person)
    {
        lock (_gate)
        {
            var rate = ChannelConfiguration.Rate(settings, _profileRate ?? 60);
            if (_limiter is null || _rate != rate) { _limiter = new(new(rate), clock); _rate = rate; }
            return _limiter.Check("channel", new ApiPrincipal(person, Authenticated: true));
        }
    }

    internal void Record(Trust.ChannelCaller caller, string tool, JsonObject facts)
    {
        if (tool is "verify_figures" or "channel_ping" or "claim_package_link" or "claim_package_redeem") { return; }
        lock (_gate)
        {
            Expire();
            var key = Key(caller);
            var scrubbed = new JsonObject(facts.Where(pair => pair.Key is not ("confirmation" or "ticket"))
                .Select(pair => KeyValuePair.Create(pair.Key, pair.Value?.DeepClone())));
            var held = _ledger.Remove(key, out var previous) ? previous.Facts : [];
            held.Add(JsonSerializer.SerializeToElement(scrubbed));
            if (held.Count > 200) { held.RemoveAt(0); }
            _ledger.Add(key, new(clock.GetTimestamp(), held));
            if (_ledger.Count > 1000) { _ledger.Remove(_ledger.MinBy(p => p.Value.Stamp).Key); }
        }
    }

    internal JsonObject Verify(Trust.ChannelCaller caller, JsonObject args)
    {
        JsonElement[] facts;
        lock (_gate) { Expire(); facts = _ledger.TryGetValue(Key(caller), out var entry) ? entry.Facts.ToArray() : []; }
        var draft = args["draft_text"]!.GetValue<string>();
        var context = AllowedContext.Build((args["allowed_context"] as JsonArray ?? []).Select(v => v!.GetValue<string>()));
        // Namespace each result so conflicting dotted paths cannot discard earlier trusted values.
        var index = FactIndex.FromFacts(facts, Enumerable.Range(0, facts.Length).Select(i => "result" + i).ToArray());
        var check = NumericGuard.Check(draft, index, context);
        var count = NumeralExtractor.Extract(draft).Count(n => n.Kind != "structural");
        var violations = new JsonArray(check.Violations.Select(v => (JsonNode)new JsonObject
        {
            ["token"] = v.Numeral.Text,
            ["position"] = v.Numeral.Start,
            ["reason"] = v.Reason,
        }).ToArray());
        var blocks = new JsonArray(CapabilityResult.Block("heading", "Figure check"), CapabilityResult.Block("paragraph",
            check.Passed ? $"Every figure in the draft was found in this conversation's results ({count} checked)." :
            $"{violations.Count} of {count} figures in the draft are not in this conversation's results."));
        if (violations.Count != 0)
        {
            blocks.Add(CapabilityResult.Block("table", rows: ViolationHeader.Concat(
                check.Violations.Select(v => new[] { v.Numeral.Text, v.Numeral.Start.ToString(System.Globalization.CultureInfo.InvariantCulture), v.Reason }))));
        }
        return new CapabilityResult("verify_figures", new JsonObject
        {
            ["status"] = check.Status,
            ["violations"] = violations,
            ["violation_count"] = violations.Count,
            ["checked_numerals"] = count,
        })
        { Blocks = blocks, Provenance = CapabilityResult.Evidence(source: "numeric guard over this conversation's tool facts") }.ToJson();
    }

    private void Expire()
    {
        foreach (var key in _ledger.Where(pair => clock.GetElapsedTime(pair.Value.Stamp) >= TimeSpan.FromHours(8)).Select(p => p.Key).ToArray())
        { _ledger.Remove(key); }
    }
    private static (string, string) Key(Trust.ChannelCaller caller) =>
        (caller.Acting.TenantId + ":" + caller.Acting.Oid, caller.Acting.ConversationId ?? "user:" + caller.Acting.Oid);
    internal void Reset(int? profileRate = null)
    {
        lock (_gate) { _ledger.Clear(); _limiter = null; _profileRate = profileRate; }
    }
    internal void ClearRateLimits() { lock (_gate) { _limiter = null; } }
}
