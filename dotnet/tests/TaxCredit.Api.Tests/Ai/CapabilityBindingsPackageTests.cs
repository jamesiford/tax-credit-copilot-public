using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Api.Tests.Contract;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.Ai.Capabilities.Bindings;
using TaxCredit.Application.Features.ClaimsArtifactsRules;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using static TaxCredit.Api.Tests.Ai.CapabilityBindingsFixture;

namespace TaxCredit.Api.Tests.Ai;

public sealed class CapabilityBindingsPackageTests
{
    [Fact]
    public async Task Internal_redeem_returns_stored_owner_context_and_wrong_person_cannot_spend_it()
    {
        await using var fixture = await Start();
        await Create(fixture);
        var caller = new ApiPrincipal("00000000-0000-0000-0000-0000000000b1", PrincipalType: "agent",
            Authenticated: true, ActingFor: new ActingUser(Writer.Oid!, Writer.TenantId, Writer.Name,
                Writer.Upn, Channel: "teams", ConversationId: "synthetic-conversation"));
        var linked = await fixture.Invoke("claim_package_link", Args("claim_package_create"), caller);
        var ticket = Ticket(linked);
        var wrong = await Assert.ThrowsAsync<CapabilityException>(() => fixture.Invoke("claim_package_redeem",
            new JsonObject { ["ticket"] = ticket, ["expected_user_oid"] = Other.Oid }));
        Assert.Equal("confirmation_wrong_user", wrong.Code);
        using var scope = fixture.Host.App.Services.CreateScope();
        var redeemed = scope.ServiceProvider.GetRequiredService<CapabilityPackageTickets>().Redeem(ticket, Writer.Oid);
        var facts = redeemed.Facts;
        Assert.Equal(Writer.Oid, facts["user_oid"]!.GetValue<string>());
        Assert.Equal(Writer.TenantId, facts["tenant_id"]!.GetValue<string>());
        Assert.Equal(1001, facts["client_id"]!.GetValue<long>());
        Assert.NotEmpty(facts["artifact_id"]!.GetValue<string>());
        Assert.Equal("teams", facts["channel"]!.GetValue<string>());
        Assert.Equal("synthetic-conversation", facts["conversation_id"]!.GetValue<string>());
        Assert.Equal("channel-asserted", facts["assurance"]!.GetValue<string>());
        Assert.Equal(Writer.Name, facts["name"]!.GetValue<string>());
        var service = new ApiPrincipal(Guid.Empty.ToString(), PrincipalType: "agent", Authenticated: true);
        var replay = await Assert.ThrowsAsync<CapabilityException>(() => fixture.Invoke("claim_package_redeem",
            new JsonObject { ["ticket"] = ticket }, service));
        Assert.Equal("confirmation_replayed", replay.Code);
        Assert.Equal(410, replay.StatusCode);
    }

    [Fact]
    public async Task Simultaneous_redemption_across_application_scopes_serves_exactly_one_integrity_checked_download()
    {
        await using var fixture = await Start();
        await Create(fixture);
        var linked = await fixture.Invoke("claim_package_link", Args("claim_package_create"));
        var ticket = Ticket(linked);
        var results = await Task.WhenAll(Enumerable.Range(0, 8).Select(async _ =>
        {
            try { return await Download(fixture, ticket); }
            catch (CapabilityException error) { Assert.Equal("confirmation_replayed", error.Code); return null; }
        }));
        var served = Assert.Single(results.OfType<CapabilityPackageDownload>());
        Assert.Equal(Writer.Oid, served.Owner.Oid);
        Assert.Equal(linked["facts"]!["sha256"]!.GetValue<string>(), Convert.ToHexStringLower(SHA256.HashData(served.Download.Data)));
        Assert.Equal(linked["facts"]!["file_name"]!.GetValue<string>(), served.Download.FileName);
        Assert.Equal(linked["facts"]!["size_bytes"]!.GetValue<long>(), served.Download.Data.LongLength);
        Assert.Equal("served", Assert.Single(fixture.Read(provider => provider.GetRequiredService<IArtifactRepository>().Accesses(1001))).Outcome);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Missing_bytes_or_revoked_owner_access_leave_the_ticket_spent_and_audited(bool missing)
    {
        await using var fixture = await Start();
        await Create(fixture);
        if (missing)
        {
            fixture.Read(provider =>
            {
                var store = provider.GetRequiredService<IArtifactRepository>();
                var artifact = store.Live(1001, "claim_package", 2025)[0];
                return store.Record(artifact with { ArtifactId = "synthetic-missing", BlobPath = "1001/missing/package.xlsx" });
            });
        }
        var linked = await fixture.Invoke("claim_package_link", Args("claim_package_create"));
        var ticket = Ticket(linked);
        if (!missing)
        {
            await RuntimeRequests.Env(fixture.Host, new { CLIENT_ALLOWLIST = "{}" });
        }
        var error = await Assert.ThrowsAsync<FeatureRefusalException>(() => Download(fixture, ticket));
        Assert.Equal(missing ? 404 : 403, error.Status);
        var replay = await Assert.ThrowsAsync<CapabilityException>(() => Download(fixture, ticket));
        Assert.Equal("confirmation_replayed", replay.Code);
        Assert.Equal(missing ? "missing" : "denied", Assert.Single(fixture.Read(provider =>
            provider.GetRequiredService<IArtifactRepository>().Accesses(1001))).Outcome);
    }

    [Fact]
    public async Task Expiration_is_checked_before_spending_and_reset_removes_persisted_tickets()
    {
        await using var fixture = await Start();
        await Create(fixture);
        var linked = await fixture.Invoke("claim_package_link", Args("claim_package_create"));
        var ticket = Ticket(linked);
        var expired = "synthetic-expired-ticket";
        fixture.Read(provider =>
        {
            var repository = provider.GetRequiredService<IChannelStateRepository>();
            var original = repository.FindByTokenHash(Hash(ticket))!;
            return repository.Create(original with
            {
                ConfirmationId = "synthetic-expired",
                TokenSha256 = Hash(expired),
                CreatedAt = PyDateTime.FromIsoFormat("2026-01-14T10:00:00+00:00"),
                ExpiresAt = PyDateTime.FromIsoFormat("2026-01-14T10:15:00+00:00"),
            });
        });
        var refusal = await Assert.ThrowsAsync<CapabilityException>(() => Download(fixture, expired));
        Assert.Equal("confirmation_expired", refusal.Code);
        Assert.Null(fixture.Read(provider => provider.GetRequiredService<IChannelStateRepository>().FindByTokenHash(Hash(expired)))!.ConsumedAt);
        await RuntimeRequests.Reset(fixture.Host, "G1");
        var unknown = await Assert.ThrowsAsync<CapabilityException>(() => Download(fixture, ticket));
        Assert.Equal("invalid_arguments", unknown.Code);
    }

    private static async Task Create(CapabilityBindingsFixture fixture)
    {
        var args = Args("claim_package_create");
        var prepared = await fixture.Invoke("claim_package_create_prepare", args);
        var committed = await fixture.Invoke("claim_package_create_commit", Commit(args,
            prepared["facts"]!["confirmation"]!["token"]!.GetValue<string>(), "package-create"));
        var result = committed["facts"]!["result"]!.AsObject();
        Assert.Equal("/api/clients/1001/artifacts/" + result["artifact_id"]!.GetValue<string>(),
            result["download_path"]!.GetValue<string>());
        Assert.False(result.ContainsKey("content_type"));
        Assert.False(result.ContainsKey("created_by"));
    }

    private static string Ticket(JsonObject result) => result["facts"]!["download_path"]!.GetValue<string>().Split('/')[^1];
    private static string Hash(string value) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
    private static async Task<CapabilityPackageDownload> Download(CapabilityBindingsFixture fixture, string ticket)
    {
        using var scope = fixture.Host.App.Services.CreateScope();
        return await scope.ServiceProvider.GetRequiredService<CapabilityPackageTickets>().DownloadAsync(ticket, Writer.Oid);
    }
}
