using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Packages;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using static TaxCredit.Application.Features.Ai.Capabilities.Bindings.CapabilityBindingValues;

namespace TaxCredit.Application.Features.Ai.Capabilities.Bindings;

/// <summary>Authorized bytes retain their owner for gateway attribution; no storage address crosses this seam.</summary>
public sealed record CapabilityPackageDownload(ApiPrincipal Owner, ArtifactDownload Download);

/// <summary>Durable hashed tickets survive request scopes and spend atomically before accessing bytes.</summary>
public sealed class CapabilityPackageTickets(IChannelStateRepository confirmations, IArtifactRepository artifacts,
    IMediator mediator, TimeProvider clock, IIdSource ids, ISecretSource secrets)
{
    private const string TicketTool = "claim_package_download";
    private const int LifetimeMinutes = 15;

    internal CapabilityRead Link(JsonObject args, ApiPrincipal principal)
    {
        if (string.IsNullOrEmpty(principal.EffectiveOid))
        {
            throw new CapabilityException(403, "not_authorized", "A download link needs a named user.");
        }
        var live = artifacts.Live(Client(args), "claim_package", Year(args));
        var artifact = live.Count > 0 ? live[0]
            : throw NotCalculated("No claim package has been built for this client-year; build one first.");
        var ticket = Convert.ToBase64String(secrets.NextBytes(32)).TrimEnd('=').Replace('+', '-').Replace('/', '_');
        var now = clock.GetUtcNow();
        var owner = Owner(principal);
        var context = new TicketContext(Client(args), artifact.ArtifactId, owner,
            principal.ActingFor?.Channel, principal.ActingFor?.ConversationId, principal.ActingFor?.Assurance);
        var row = confirmations.Create(new Confirmation(ids.NewId().ToString("N"), Hash(ticket), owner.Oid!,
            TicketTool, Hash($"{Client(args)}:{artifact.ArtifactId}"), Time(now), Time(now.AddMinutes(LifetimeMinutes)),
            ResultJson: JsonSerializer.Serialize(context)));
        var facts = new JsonObject
        {
            ["client_id"] = Client(args),
            ["tax_year"] = Year(args),
            ["file_name"] = artifact.FileName,
            ["sha256"] = artifact.Sha256,
            ["size_bytes"] = artifact.SizeBytes,
            ["download_path"] = "/channel/v1/downloads/" + ticket,
            ["expires_at"] = row.ExpiresAt.IsoFormat(),
            ["ticket_minutes"] = LifetimeMinutes,
            ["single_use"] = true,
        };
        var provenance = CapabilityResult.Evidence(source: "artifact store");
        provenance["run_id"] = artifact.RunId;
        return new(facts, provenance);
    }

    internal CapabilityRead Redeem(JsonObject args) => Redeem(Text(args, "ticket") ?? "", Text(args, "expected_user_oid"));

    /// <summary>Internal gateway redemption needs possession of the ticket, not an invented service person.</summary>
    public CapabilityRead Redeem(string ticket, string? expectedUserOid = null)
    {
        var (row, context) = Spend(ticket, expectedUserOid);
        return new(new JsonObject
        {
            ["user_oid"] = row.UserOid,
            ["tenant_id"] = context.Owner.TenantId,
            ["client_id"] = context.ClientId,
            ["artifact_id"] = context.ArtifactId,
            ["name"] = context.Owner.Name,
            ["channel"] = context.Channel,
            ["conversation_id"] = context.ConversationId,
            ["assurance"] = context.Assurance,
        }, CapabilityResult.Evidence(source: "download ticket; spent"));
    }

    /// <summary>Wrong-person checks happen before spend; missing bytes or lost rights never make a spent ticket reusable.</summary>
    public async Task<CapabilityPackageDownload> DownloadAsync(string ticket, string? expectedUserOid = null,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var (_, context) = Spend(ticket, expectedUserOid);
        var download = await mediator.Send(new DownloadArtifact(context.ClientId, context.ArtifactId, context.Owner),
            cancellationToken).ConfigureAwait(false);
        return new CapabilityPackageDownload(context.Owner, download);
    }

    private (Confirmation Row, TicketContext Context) Spend(string ticket, string? expected)
    {
        if (ticket.Length > 500) { throw CapabilityException.Invalid("Download ticket is too long."); }
        var row = confirmations.FindByTokenHash(Hash(ticket));
        if (row is null || row.ToolName != TicketTool) { throw CapabilityException.Invalid("That download link is not recognised."); }
        if (!string.IsNullOrEmpty(expected) && !string.Equals(expected, row.UserOid, StringComparison.OrdinalIgnoreCase))
        {
            throw new CapabilityException(403, "confirmation_wrong_user", "That download link belongs to another person.");
        }
        if (row.ConsumedAt is not null) { throw Gone("replayed"); }
        if (DateTimeOffset.Parse(row.ExpiresAt.IsoFormat(), System.Globalization.CultureInfo.InvariantCulture) <= clock.GetUtcNow())
        {
            throw Gone("expired");
        }
        var context = JsonSerializer.Deserialize<TicketContext>(row.ResultJson ?? "")
            ?? throw new InvalidOperationException("The stored ticket has no context.");
        if (context.Owner.Oid != row.UserOid || context.ClientId <= 0) { throw new InvalidOperationException("Invalid stored ticket binding."); }
        if (!confirmations.Consume(row.ConfirmationId, row.UserOid, row.ArgsSha256, Time(clock.GetUtcNow())))
        {
            throw Gone("replayed");
        }
        confirmations.RecordResult(row.ConfirmationId, "redeemed", row.ResultJson);
        return (row, context);
    }

    private static ApiPrincipal Owner(ApiPrincipal principal) => new(principal.EffectiveOid,
        principal.IsAgent ? principal.ActingFor?.Upn : principal.Upn,
        principal.IsAgent ? principal.ActingFor?.Name : principal.Name,
        principal.IsAgent ? principal.ActingFor?.TenantId ?? principal.TenantId : principal.TenantId,
        Authenticated: true);
    private static CapabilityException Gone(string reason) => new(410, "confirmation_" + reason, "That download link has " + reason + ".");
    private static string Hash(string value) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
    private static PyDateTime Time(DateTimeOffset now) => new(DateOnly.FromDateTime(now.UtcDateTime),
        now.Hour, now.Minute, now.Second, (int)(now.Ticks % TimeSpan.TicksPerSecond / 10), 0);
    private sealed record TicketContext(long ClientId, string ArtifactId, ApiPrincipal Owner,
        string? Channel, string? ConversationId, string? Assurance);
}
