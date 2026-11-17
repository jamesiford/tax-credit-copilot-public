using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Orchestrator.Boundary;

namespace TaxCredit.Orchestrator.Tests.Support;

internal sealed class FakeGateway : IGatewayClient
{
    internal static readonly (int Id, string Name)[] Book =
        [(2001, "Cascade Retail Partners"), (2002, "Northwind Care Systems"), (2003, "Ironbridge Logistics")];
    internal readonly List<(string Tool, JsonObject Arguments, ActingIdentity Identity, string? Key)> Calls = [];
    internal readonly List<JsonObject> Narrations = [];
    internal readonly Dictionary<string, Func<JsonObject, GatewayReply>> Overrides = new(StringComparer.Ordinal);
    internal readonly HashSet<string> Writers = new(StringComparer.Ordinal) { Rig.Oid };
    private readonly Dictionary<string, (string Person, string Tool, JsonObject Args, bool Used)> _prepared = new(StringComparer.Ordinal);
    private readonly HashSet<string> _committed = new(StringComparer.Ordinal);
    internal int Mutations { get; private set; }
    internal bool LoseCommitResponse { get; set; }
    internal int AuditStatus { get; set; } = 200;

    public Task<GatewayReply> CallToolAsync(ActingIdentity identity, string tool, JsonObject arguments,
        string? idempotencyKey = null, string? confirmationToken = null, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        Calls.Add((tool, (JsonObject)arguments.DeepClone(), identity, idempotencyKey));
        if (Overrides.TryGetValue(tool, out var answer)) { return Task.FromResult(answer(arguments)); }
        var spec = new CapabilityCatalog().Resolve(tool);
        if (spec is null) { return Task.FromResult(Error("unknown_tool", 404)); }
        if (spec["kind"]!.ToString() != "write_commit")
        {
            try { CapabilitySchema.Validate(spec["schema"]!.AsObject(), arguments); }
            catch (CapabilityException error) { return Task.FromResult(new GatewayReply(error.StatusCode, error.Body())); }
        }
        var kind = spec["kind"]!.ToString();
        var reply = kind == "write_prepare" ? Prepare(identity, tool, arguments) :
            kind == "write_commit" ? Commit(identity, tool, arguments, idempotencyKey, confirmationToken) :
            tool == "client_resolve" ? Resolve(arguments) : new GatewayReply(200, FakeEnvelopes.Read(tool, arguments).ToJson());
        return Task.FromResult(reply);
    }

    public Task<GatewayReply> ReportNarrationAsync(ActingIdentity identity, JsonObject report,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        Narrations.Add((JsonObject)report.DeepClone());
        return Task.FromResult(AuditStatus == 200 ? new GatewayReply(200, new JsonObject { ["audit_id"] = "audit" }) : Error("audit_unavailable", AuditStatus));
    }

    private GatewayReply Prepare(ActingIdentity who, string name, JsonObject args)
    {
        if (!Writers.Contains(who.Oid)) { return Error("not_authorized", 403); }
        var token = "synthetic-confirmation-" + (_prepared.Count + 1);
        var command = name[..^"_prepare".Length];
        _prepared[token] = (who.Oid, command, (JsonObject)args.DeepClone(), false);
        var after = args["scope"]?.ToString() ?? "in_scope";
        var result = new CapabilityResult(name, new JsonObject
        {
            ["tool"] = command,
            ["preview"] = new JsonObject
            {
                ["before"] = new JsonObject { ["scope"] = "prospective" },
                ["after"] = new JsonObject { ["scope"] = after },
            },
            ["confirmation"] = new JsonObject { ["confirmation_id"] = "id-" + token, ["token"] = token, ["expires_at"] = "later" },
        })
        {
            Blocks = new JsonArray(CapabilityResult.Block("heading", "Preview: " + command.Replace('_', ' ')),
                CapabilityResult.Block("table", rows: [new[] { "Field", "Now", "After" }, new[] { "scope", "prospective", after }]),
                CapabilityResult.Block("callout", "Nothing has changed yet. It is only written when you confirm.")),
            Provenance = CapabilityResult.Evidence(source: "prepared change; nothing written"),
            Warnings = ["Prepared only: no change is made until the confirmation is committed."],
        };
        return new GatewayReply(200, result.ToJson());
    }

    private GatewayReply Commit(ActingIdentity who, string name, JsonObject args, string? key, string? token)
    {
        if (!Writers.Contains(who.Oid)) { return Error("not_authorized", 403); }
        if (token is null || !_prepared.TryGetValue(token, out var pending)) { return Error("confirmation_unknown", 404); }
        if (pending.Person != who.Oid) { return Error("confirmation_wrong_user", 403); }
        if (!JsonNode.DeepEquals(pending.Args, args["arguments"] ?? args)) { return Error("confirmation_wrong_args", 422); }
        if (pending.Used && (key is null || !_committed.Contains(key))) { return Error("confirmation_replayed", 409); }
        if (key is null) { return Error("idempotency_required", 422); }
        var replay = !_committed.Add(key);
        _prepared[token] = pending with { Used = true };
        if (!replay) { Mutations++; }
        if (LoseCommitResponse) { return Error("timeout", 0); }
        return new GatewayReply(200, new CapabilityResult(name, new JsonObject
        {
            ["tool"] = pending.Tool,
            ["replayed"] = replay,
            ["result"] = new JsonObject { ["status"] = "recorded" },
        })
        {
            Blocks = new JsonArray(CapabilityResult.Block("heading", pending.Tool.Replace('_', ' ')),
                CapabilityResult.Block("paragraph", replay ? "Already done earlier; nothing was repeated." : "Done. The change is recorded under your name.")),
            Provenance = CapabilityResult.Evidence(source: "mediator command; audited"),
        }.ToJson());
    }

    private static GatewayReply Resolve(JsonObject args)
    {
        var text = args["name_or_text"]!.GetValue<string>();
        var named = Named(text);
        var current = args["current_client_id"]?.GetValue<int>();
        var referent = Regex.IsMatch(text, @"\b(their|theirs|them|they|this client|that client)\b", RegexOptions.IgnoreCase, TimeSpan.FromSeconds(1));
        var prior = (args["history"] as JsonArray ?? []).Reverse().Select(node => Named(node?["text"]?.ToString() ?? ""))
            .FirstOrDefault(names => names.Length != 0) ?? [];
        int? chosen = named.Length == 1 ? named[0].Id : named.Length == 0 ? current : null;
        var reason = named.Length > 1 ? "names more than one client" :
            referent && (prior.Length == 0 || !prior.Select(row => row.Id).ToHashSet().SetEquals(current is { } id ? [id] : []))
            ? "does not say which client it means" : "no client is selected";
        if (named.Length == 0 && referent && prior.Length != 0 && !prior.Select(row => row.Id).ToHashSet().SetEquals(current is { } value ? [value] : []))
        {
            chosen = null;
        }
        var candidates = chosen is not null ? [] : named.Length > 1 ? named : prior.Length != 0 ? prior : Book;
        return new GatewayReply(200, new CapabilityResult("client_resolve", new JsonObject
        {
            ["client_id"] = chosen,
            ["clarify"] = chosen is null,
            ["reason"] = chosen is null ? reason : "",
            ["named"] = new JsonArray(named.Select(row => (JsonNode?)JsonValue.Create(row.Id)).ToArray()),
            ["candidates"] = new JsonArray(candidates.Select(row => (JsonNode)new JsonObject { ["client_id"] = row.Id, ["name"] = row.Name }).ToArray()),
        }).ToJson());
    }

    private static (int Id, string Name)[] Named(string text) => Book
        .Select(row => (Row: row, Position: Regex.Match(text, @"\b" + Regex.Escape(row.Name.Split(' ')[0]) + @"\b",
            RegexOptions.IgnoreCase, TimeSpan.FromSeconds(1))))
        .Where(item => item.Position.Success).OrderBy(item => item.Position.Index).Select(item => item.Row).ToArray();

    internal static GatewayReply Error(string code, int status = 503) => new(status,
        new JsonObject { ["error"] = new JsonObject { ["code"] = code, ["message"] = code.Replace('_', ' '), ["retryable"] = false } });
}
