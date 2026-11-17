using System.Text.Json;
using System.Text.Json.Nodes;
using ModelContextProtocol;
using ModelContextProtocol.Protocol;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.Gateway.Execution;

internal sealed class ChannelCatalog(CapabilityCatalog catalog, IRuntimeConfiguration settings)
{
    private const string Preview = "Returns a preview — nothing is changed until the matching commit tool is called with the returned token after the user confirms.";
    private const string Commit = "Call only after the user has confirmed the preview from the matching prepare tool.";

    internal JsonArray Offered()
    {
        var tools = catalog.Offered();
        if (settings.Get("CHANNEL_DEBUG_WHOAMI") is "1" or "true" or "on")
        {
            tools.Add(new JsonObject
            {
                ["name"] = "channel_ping",
                ["description"] = "Diagnostics: the gateway's version, who it believes is calling and by which rule, and whether the API answers.",
                ["kind"] = "read",
                ["needs_client"] = false,
                ["needs_year"] = false,
                ["sensitive"] = false,
                ["implemented"] = true,
                ["tags"] = new JsonArray("gateway-local", "debug"),
                ["schema"] = new JsonObject
                {
                    ["type"] = "object",
                    ["properties"] = new JsonObject(),
                    ["required"] = new JsonArray(),
                    ["additionalProperties"] = false
                },
            });
        }
        return tools;
    }

    internal JsonObject? Find(string name) => Offered().OfType<JsonObject>().FirstOrDefault(s => s["name"]!.GetValue<string>() == name);

    internal IList<Tool> McpTools() => Offered().OfType<JsonObject>().Select(spec =>
    {
        var name = spec["name"]!.GetValue<string>();
        var kind = spec["kind"]!.GetValue<string>();
        var description = spec["description"]!.GetValue<string>();
        var shape = new JsonObject
        {
            ["name"] = name,
            ["title"] = char.ToUpperInvariant(name[0]) + name[1..].Replace('_', ' '),
            ["description"] = description + (kind == "write_prepare" ? " " + Preview : kind == "write_commit" ? " " + Commit : ""),
            ["inputSchema"] = spec["schema"]!.DeepClone(),
            ["annotations"] = new JsonObject
            {
                ["readOnlyHint"] = kind == "read",
                ["destructiveHint"] = kind == "write_commit",
                ["idempotentHint"] = kind == "read",
                ["openWorldHint"] = false
            },
        };
        return JsonSerializer.Deserialize<Tool>(shape.ToJsonString(), McpJsonUtilities.DefaultOptions)!;
    }).ToList();
}
