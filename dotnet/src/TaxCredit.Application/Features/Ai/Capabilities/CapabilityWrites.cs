using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities.Bindings;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using static TaxCredit.Application.Features.Ai.Capabilities.CapabilityResult;

namespace TaxCredit.Application.Features.Ai.Capabilities;

internal sealed class CapabilityWrites(IChannelStateRepository repository, IChannelAuditRepository audit,
    IWriterPolicy writer, ICapabilityWriteBridge bridge, CapabilityOptions options, TimeProvider clock,
    IIdSource ids, ISecretSource secrets, CapabilityCommitLocks commitLocks)
{
    private static readonly Dictionary<string, string> Summaries = new(StringComparer.Ordinal)
    {
        ["finding_resolve"] = "Record a decision about a finding.",
        ["finding_reopen"] = "Withdraw a decision on a finding.",
        ["claim_transition"] = "Move a claim along its lifecycle.",
        ["claim_record"] = "Record an unverified claim.",
        ["engagement_set"] = "Set the engagement for a programme.",
        ["base_year_set"] = "Set a location's base year.",
        ["claim_package_create"] = "Build the claim package.",
        ["run_batch"] = "Run assessments or calculations for many clients.",
    };
    private static readonly string[][] ChangeHeader = [["Field", "Now", "After"]];

    internal async Task<CapabilityResult> InvokeAsync(string tool, JsonObject supplied, ApiPrincipal principal, CancellationToken cancellationToken)
    {
        var prepare = tool.EndsWith("_prepare", StringComparison.Ordinal);
        var change = tool[..^(prepare ? "_prepare".Length : "_commit".Length)];
        var arguments = (prepare ? supplied : supplied["arguments"]!.AsObject());
        var args = new JsonObject(arguments.Where(entry => entry.Value is not null)
            .Select(entry => KeyValuePair.Create(entry.Key, (JsonNode?)entry.Value!.DeepClone())));
        var auditId = ids.NewId().ToString("N");
        var started = clock.GetTimestamp();
        Audit(auditId, 0, "begin", "pending", tool, args, principal);
        try
        {
            if (string.IsNullOrEmpty(principal.EffectiveOid))
            {
                throw new CapabilityException(403, "not_authorized", "a confirmation needs a named user");
            }
            await writer.CheckAsync(principal, principal.Actor, true, cancellationToken).ConfigureAwait(false);
            var result = prepare
                ? await PrepareAsync(change, args, principal, cancellationToken).ConfigureAwait(false)
                : await CommitAsync(change, args, supplied, principal, cancellationToken).ConfigureAwait(false);
            Audit(auditId, 1, "end", "ok", tool, args, principal, clock.GetElapsedTime(started).TotalMilliseconds);
            return result;
        }
        catch (Exception error)
        {
            Audit(auditId, 1, "end", error is CapabilityException or ApiAuthException ? "refused" : "error",
                tool, args, principal, clock.GetElapsedTime(started).TotalMilliseconds);
            throw;
        }
    }

    private async Task<CapabilityResult> PrepareAsync(string change, JsonObject args, ApiPrincipal principal, CancellationToken cancellationToken)
    {
        var preview = await bridge.PreviewAsync(change, args, principal, cancellationToken).ConfigureAwait(false);
        if (preview["after"] is not JsonObject)
        {
            throw new InvalidOperationException("The command owner did not supply a valid preview.");
        }
        var token = Convert.ToBase64String(secrets.NextBytes(32)).TrimEnd('=').Replace('+', '-').Replace('/', '_');
        var now = clock.GetUtcNow();
        var row = repository.Create(new Confirmation(ids.NewId().ToString("N"), Hash(token), principal.EffectiveOid!,
            change, ArgsHash(args), Time(now), Time(now + options.ConfirmationLifetime)));
        var facts = new JsonObject
        {
            ["tool"] = change,
            ["preview"] = preview,
            ["confirmation"] = new JsonObject
            {
                ["confirmation_id"] = row.ConfirmationId,
                ["token"] = token,
                ["expires_at"] = row.ExpiresAt.IsoFormat(),
            },
        };
        var before = preview["before"] as JsonObject ?? [];
        return new CapabilityResult(change + "_prepare", facts)
        {
            Blocks =
            [
                Block("heading", Summaries[change]),
                Block("table", rows: ChangeHeader.Concat(preview["after"]!.AsObject()
                    .Select(entry => new[] { entry.Key.Replace('_', ' '), Show(entry.Key, before[entry.Key]), Show(entry.Key, entry.Value) }))),
                Block("callout", "Nothing has changed yet. It is only written when you confirm."),
            ],
            Provenance = Evidence(source: "prepared change; nothing written"),
            Warnings = ["Prepared only: no change is made until the confirmation is committed."],
        };
    }

    private async Task<CapabilityResult> CommitAsync(string change, JsonObject args, JsonObject supplied,
        ApiPrincipal principal, CancellationToken cancellationToken)
    {
        var key = supplied["idempotency_key"]!.GetValue<string>();
        if (string.IsNullOrWhiteSpace(key) || key.Length > 200)
        {
            throw CapabilityException.Invalid("an idempotency key of at most 200 characters is required");
        }
        using var commitLease = await commitLocks.EnterAsync(principal.EffectiveOid!, key, cancellationToken).ConfigureAwait(false);
        var token = supplied["confirmation_token"]!.GetValue<string>();
        if (token.Length > 500)
        {
            throw CapabilityException.Invalid("confirmation token is too long");
        }
        var row = repository.FindByTokenHash(Hash(token)) ?? throw Refusal("unknown", 404);
        CheckBinding(row, principal.EffectiveOid!, change, args);
        var earlier = repository.FindByIdempotencyKey(principal.EffectiveOid!, key);
        if (earlier is not null)
        {
            if (earlier.ConfirmationId != row.ConfirmationId)
            {
                throw Refusal("idempotency_conflict", 409);
            }
            return earlier.Outcome == "ok" && earlier.ResultJson is { Length: > 0 } json
                ? Committed(change, JsonNode.Parse(json)!.AsObject(), true)
                : throw Refusal("replayed", 409);
        }
        if (row.ConsumedAt is not null)
        {
            throw Refusal("replayed", 409);
        }
        if (DateTimeOffset.Parse(row.ExpiresAt.IsoFormat(), System.Globalization.CultureInfo.InvariantCulture) <= clock.GetUtcNow())
        {
            throw Refusal("expired", 409);
        }
        if (!repository.Consume(row.ConfirmationId, principal.EffectiveOid!, ArgsHash(args), Time(clock.GetUtcNow()), key))
        {
            throw Refusal("replayed", 409);
        }
        try
        {
            var result = await bridge.CommitAsync(change, args, principal, cancellationToken).ConfigureAwait(false);
            repository.RecordResult(row.ConfirmationId, "ok", result.ToJsonString());
            return Committed(change, result, false);
        }
        catch
        {
            repository.RecordResult(row.ConfirmationId, "error", null);
            throw;
        }
    }

    private static CapabilityResult Committed(string change, JsonObject result, bool replayed) => new(change + "_commit",
        new JsonObject { ["tool"] = change, ["result"] = result, ["replayed"] = replayed })
    {
        Blocks = [Block("heading", Summaries[change]), Block("paragraph", replayed ?
            "Already done earlier; nothing was repeated." : "Done. The change is recorded under your name.")],
        Provenance = Evidence(source: "mediator command; audited"),
    };

    private static void CheckBinding(Confirmation row, string oid, string change, JsonObject args)
    {
        if (row.UserOid != oid)
        {
            throw Refusal("wrong_user", 403);
        }
        if (row.ToolName != change)
        {
            throw Refusal("wrong_tool", 422);
        }
        if (row.ArgsSha256 != ArgsHash(args))
        {
            throw Refusal("wrong_args", 422);
        }
    }

    private void Audit(string id, int sequence, string phase, string outcome, string tool, JsonObject args,
        ApiPrincipal principal, double elapsed = 0) => audit.Append(new ChannelAuditEvent(new Dictionary<string, object?>
        {
            ["audit_id"] = id,
            ["event_seq"] = sequence,
            ["phase"] = phase,
            ["correlation_id"] = principal.ActingFor?.CorrelationId ?? id,
            ["occurred_at"] = Time(clock.GetUtcNow()),
            ["elapsed_ms"] = elapsed,
            ["channel"] = principal.ActingFor?.Channel ?? "api",
            ["user_oid"] = principal.EffectiveOid ?? "anonymous",
            ["tenant_id"] = principal.TenantId,
            ["user_display_name"] = principal.ActingFor?.Name ?? principal.Name,
            ["user_upn"] = principal.Actor,
            ["identity_assurance"] = principal.ActingFor?.Assurance ?? "delegated",
            ["tool_name"] = tool,
            ["action_kind"] = tool.EndsWith("_prepare", StringComparison.Ordinal) ? "write_prepare" : "write_commit",
            ["client_id"] = args["client_id"] is { } client ? CapabilityJson.Integer(client) : null,
            ["tax_year"] = args["tax_year"] is { } year ? CapabilityJson.Integer(year) : null,
            ["request_summary"] = "Capability change; arguments withheld",
            ["request_sha256"] = ArgsHash(args),
            ["outcome"] = outcome,
            ["numeric_guard"] = "n/a",
            ["is_deterministic_path"] = true,
        }));

    private static string Show(string name, JsonNode? value) => value is null ? "—" :
        name.EndsWith("_usd", StringComparison.Ordinal) ? CapabilityFormat.Render(value, "money") :
        value is JsonValue ? value.ToString() : value.ToJsonString();
    private static CapabilityException Refusal(string code, int status) => new(status, "confirmation_" + code,
        "The confirmation cannot be used: " + code.Replace('_', ' ') + ".");
    private static string Hash(string value) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
    private static string ArgsHash(JsonObject args) => Hash(PyJson.Dumps(PyJson.Loads(args.ToJsonString())));
    private static PyDateTime Time(DateTimeOffset now) => new(DateOnly.FromDateTime(now.UtcDateTime),
        now.Hour, now.Minute, now.Second, (int)(now.Ticks % TimeSpan.TicksPerSecond / 10), 0);
}
