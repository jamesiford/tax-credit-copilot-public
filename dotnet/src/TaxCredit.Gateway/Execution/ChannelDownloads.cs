using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.Ai.Capabilities.Bindings;
using TaxCredit.Application.Features.ClaimsArtifactsRules;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Packages;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Gateway.Trust;

namespace TaxCredit.Gateway.Execution;

internal sealed class ChannelDownloads(CapabilityPackageTickets tickets, IApiPrincipalAccessor principals, IMediator mediator,
    ChannelState state, ChannelAudit audit, IIdSource ids)
{
    internal async Task<IResult> ServeAsync(string ticket, ChannelCaller? caller, HttpContext http)
    {
        var correlation = ids.NewId().ToString("N");
        var limit = state.Spend("download:" + (http.Connection.RemoteIpAddress?.ToString() ?? "unknown"));
        if (!limit.Allowed)
        {
            http.Response.Headers.RetryAfter = limit.RetryAfterSeconds.ToString(System.Globalization.CultureInfo.InvariantCulture);
            return ChannelEndpoints.Json(429, new ChannelFailure(429, "rate_limited", "Too many download attempts.").Body(correlation));
        }
        JsonObject facts;
        try
        {
            facts = tickets.Redeem(ticket, caller?.Acting.Oid).Facts;
        }
        catch (CapabilityException error)
        {
            var status = error.Code is "confirmation_replayed" or "confirmation_expired" ? 410 :
                error.StatusCode is 403 or 404 or 409 ? error.StatusCode : 502;
            return ChannelEndpoints.Json(status, new ChannelFailure(status, error.Code, "That download link cannot be used.").Body(correlation));
        }
        var acting = new ActingUser(facts["user_oid"]!.GetValue<string>(), facts["tenant_id"]?.GetValue<string>(),
            facts["name"]?.GetValue<string>(), Assurance: facts["assurance"]?.GetValue<string>() ?? "channel-asserted",
            Channel: facts["channel"]?.GetValue<string>() ?? "teams", ConversationId: facts["conversation_id"]?.GetValue<string>(), CorrelationId: correlation);
        var owner = new ApiPrincipal(acting.Oid, Name: acting.Name, TenantId: acting.TenantId, Authenticated: true, ActingFor: acting);
        var ownerCaller = new ChannelCaller(owner, acting, "delegated", "ticket", null);
        var handle = audit.Begin(ownerCaller, "claim_package_download", "read", new JsonObject { ["artifact_id"] = facts["artifact_id"]!.DeepClone() });
        try
        {
            ArtifactDownload download;
            using (principals.Push(owner))
            {
                download = await mediator.Send(new DownloadArtifact(facts["client_id"]!.GetValue<long>(),
                    facts["artifact_id"]!.GetValue<string>(), owner), http.RequestAborted).ConfigureAwait(false);
            }
            if (download.Data.Length > 25 * 1024 * 1024) { throw new ChannelFailure(502, "download_failed", "The package exceeds its delivery limit."); }
            http.Response.Headers.CacheControl = "no-store";
            http.Response.Headers["X-Correlation-Id"] = correlation;
            http.Response.Headers["X-Content-Sha256"] = download.Sha256;
            http.Response.Headers.ContentDisposition = $"attachment; filename=\"{download.FileName}\"";
            audit.Finish(handle, "ok");
            return Results.Bytes(download.Data, download.ContentType);
        }
        catch (FeatureRefusalException error)
        {
            audit.Finish(handle, error.Status == 403 ? "refused" : "error", "download_failed");
            var status = error.Status == 404 ? 404 : 502;
            return ChannelEndpoints.Json(status, new ChannelFailure(status, "download_failed", "The package could not be served.").Body(correlation));
        }
        catch (OperationCanceledException) { audit.Finish(handle, "error", "cancelled"); throw; }
        catch (ChannelFailure) { audit.Finish(handle, "error", "download_failed"); throw; }
#pragma warning disable CA1031 // Close the durable opening audit; the outer boundary safely reports and logs the unexpected failure.
        catch (Exception) { audit.Finish(handle, "error", "download_failed"); throw; }
#pragma warning restore CA1031
    }
}
