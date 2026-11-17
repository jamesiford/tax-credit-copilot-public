using System.Text.Json.Nodes;

namespace TaxCredit.Gateway.Execution;

internal static class ChannelRender
{
    internal static string Text(ChannelOutcome outcome, HttpRequest request)
    {
        var envelope = outcome.Body;
        if (outcome.Status != 200) { return $"The request did not go through ({envelope["error"]?["code"]}): {envelope["error"]?["message"]}"; }
        var parts = new List<string> { "VERBATIM — quote figures exactly as written.", Blocks(envelope["blocks"] as JsonArray ?? []) };
        if (envelope["facts"]?["confirmation"]?["token"] is { } token)
        { parts.Add($"Confirmation token (pass it to the matching commit tool only after the user confirms): {token}"); }
        if (envelope["facts"]?["download_path"]?.GetValue<string>() is { } path && path.StartsWith("/channel/", StringComparison.Ordinal))
        { parts.Add($"Download (single use, for this user only): {request.Scheme}://{request.Host}{request.PathBase}{path}"); }
        var evidence = envelope["provenance"];
        var proof = new[] { ("run_id", "run"), ("rule_pack_version", "rule pack"), ("assumption_set_id", "assumptions"), ("trail_sha256", "trail hash") }
            .Where(pair => evidence?[pair.Item1] is { } value && value.ToString().Length != 0)
            .Select(pair => pair.Item2 + " " + evidence![pair.Item1]).ToArray();
        if (proof.Length != 0) { parts.Add("Provenance: " + string.Join("; ", proof) + "."); }
        parts.Add(envelope["disclaimer"]?.GetValue<string>() ?? Application.Features.Ai.Capabilities.CapabilityResult.Disclaimer);
        return string.Join("\n\n", parts.Where(p => p.Length != 0));
    }

    internal static string Blocks(JsonArray blocks) => string.Join("\n\n", blocks.OfType<JsonObject>().Select(block =>
    {
        var text = block["text"]?.GetValue<string>() ?? "";
        var rows = block["rows"] as JsonArray ?? [];
        return block["kind"]?.GetValue<string>() switch
        {
            "heading" => "### " + text,
            "paragraph" => text,
            "callout" => string.Join("\n", text.Split('\n').Select(line => "> " + line)),
            "bullets" => string.Join("\n", rows.Select(row => "- " + row![0])),
            "table" when rows.Count != 0 => string.Join("\n", rows.Take(1).Select(Row)
                .Concat(["| " + string.Join(" | ", rows[0]!.AsArray().Select(_ => "---")) + " |"]).Concat(rows.Skip(1).Select(Row))),
            _ => "",
        };
    }).Where(part => part.Length != 0));
    private static string Row(JsonNode? row) => "| " + string.Join(" | ", row!.AsArray().Select(cell =>
        cell!.GetValue<string>().Replace("|", "\\|", StringComparison.Ordinal).Replace("\n", " ", StringComparison.Ordinal))) + " |";
}
