using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using TaxCredit.Application.Ports.Sources;

namespace TaxCredit.Application.Features.Ai.Capabilities;

internal static class CapabilityClientResolver
{
    internal static CapabilityResult Resolve(IReadOnlyList<SourceAccount> accounts, JsonObject args)
    {
        var text = args["name_or_text"]!.GetValue<string>();
        var named = Named(accounts, text);
        var current = args["current_client_id"] is { } selected ? CapabilityJson.Integer(selected) : (long?)null;
        var chosen = named.Length == 1 ? named[0].AccountId : (long?)null;
        var reason = named.Length > 1 ? "more than one client is named" : (string?)null;
        if (named.Length == 0)
        {
            chosen = Historical(accounts, args["history"] as JsonArray, current);
        }
        var candidates = named.Length > 1 ? named : chosen is null ? accounts : [];
        var facts = new JsonObject
        {
            ["resolved"] = chosen is not null,
            ["client_id"] = chosen,
            ["client_name"] = accounts.FirstOrDefault(account => account.AccountId == chosen)?.Name,
            ["clarify"] = chosen is null,
            ["reason"] = chosen is null ? reason ?? "no client is selected or named" : null,
            ["named"] = new JsonArray(named.Select(account => (JsonNode?)JsonValue.Create(account.AccountId)).ToArray()),
            ["candidates"] = new JsonArray(candidates.Select(account => (JsonNode)new JsonObject
            {
                ["client_id"] = account.AccountId,
                ["name"] = account.Name,
            }).ToArray()),
        };
        var blocks = chosen is null
            ? new JsonArray(CapabilityResult.Block("paragraph", $"Which client do you mean? ({facts["reason"]!.GetValue<string>()})"),
                CapabilityResult.Block("bullets", rows: candidates.Select(account => new[] { account.Name })))
            : new JsonArray(CapabilityResult.Block("paragraph", $"Answering for {facts["client_name"]!.GetValue<string>()}."));
        return new CapabilityResult("client_resolve", facts) { Blocks = blocks, Provenance = CapabilityResult.Evidence(source: "client book") };
    }

    private static long? Historical(IReadOnlyList<SourceAccount> accounts, JsonArray? history, long? current)
    {
        if (current is not null && accounts.Any(account => account.AccountId == current))
        {
            return current;
        }
        foreach (var entry in (history ?? []).Reverse())
        {
            var names = Named(accounts, entry!["text"]!.GetValue<string>());
            if (names.Length != 0)
            {
                return names.Length == 1 ? names[0].AccountId : null;
            }
        }
        return null;
    }

    private static SourceAccount[] Named(IReadOnlyList<SourceAccount> accounts, string text)
    {
        var complete = accounts.Where(account => Contains(text, account.Name.Trim())).ToArray();
        if (complete.Length == 1)
        {
            var remainder = Regex.Replace(text, $@"\b{Regex.Escape(complete[0].Name.Trim())}\b", " ",
                RegexOptions.IgnoreCase | RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1));
            if (!accounts.Any(account => account.AccountId != complete[0].AccountId && Contains(remainder, account.Name.Split(' ')[0])))
            {
                return complete;
            }
        }
        return accounts.Where(account => Contains(text, account.Name.Trim()) || Contains(text, account.Name.Split(' ')[0])).ToArray();
    }

    private static bool Contains(string text, string name) => name.Length > 0 &&
        Regex.IsMatch(text, $@"\b{Regex.Escape(name)}\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1));
}
