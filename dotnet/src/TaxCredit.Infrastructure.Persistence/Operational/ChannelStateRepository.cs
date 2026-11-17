using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>Durable person-bound grants and hashed single-use confirmations. Expired tokens cannot acquire a command lease.</summary>
public sealed class ChannelStateRepository(PersistenceDatabase database) : IChannelStateRepository
{
    private static readonly string[] GrantColumns = ["user_oid", "display_name", "role", "added_by", "added_at", "removed_at"];
    private static readonly string[] ConfirmationColumns =
    [
        "confirmation_id", "token_sha256", "user_oid", "tool_name", "args_sha256", "idempotency_key", "created_at", "expires_at",
        "consumed_at", "outcome", "result_json",
    ];
    private static string ConfirmationSelect => "SELECT " + string.Join(", ", ConfirmationColumns) + " FROM tcc_ops.channel_confirmation";

    /// <inheritdoc />
    public WriterGrant Grant(WriterGrant grant)
    {
        ArgumentNullException.ThrowIfNull(grant);
        if (grant.Role != "writer" || grant.RemovedAt is not null)
        {
            throw new ArgumentException("A new live grant must carry the writer role.", nameof(grant));
        }

        return database.Transact(session =>
        {
            session.ExecuteExempt(SqlExemption.ChannelIdentity, "UPDATE tcc_ops.channel_user SET removed_at = ? WHERE user_oid = ? AND removed_at IS NULL",
                OpsRow.Clock(session, grant.AddedAt), grant.UserOid);
            session.InsertExempt(SqlExemption.ChannelIdentity, "tcc_ops.channel_user", GrantColumns,
                [new object?[] { grant.UserOid, grant.DisplayName, grant.Role, grant.AddedBy, OpsRow.Clock(session, grant.AddedAt), null }]);
            return grant;
        });
    }

    /// <inheritdoc />
    public bool Revoke(string userOid, PyDateTime at) => database.Transact(session =>
        session.ExecuteExempt(SqlExemption.ChannelIdentity, "UPDATE tcc_ops.channel_user SET removed_at = ? WHERE user_oid = ? AND removed_at IS NULL",
            OpsRow.Clock(session, at), userOid) > 0);

    /// <inheritdoc />
    public bool IsWriter(string userOid)
    {
        using var session = database.Open();
        return session.QueryExempt(SqlExemption.ChannelIdentity,
            "SELECT user_oid FROM tcc_ops.channel_user WHERE user_oid = ? AND role = 'writer' AND removed_at IS NULL", userOid).Count > 0;
    }

    /// <inheritdoc />
    public IReadOnlyList<WriterGrant> Live()
    {
        using var session = database.Open();
        return session.QueryExempt(SqlExemption.ChannelIdentity, "SELECT " + string.Join(", ", GrantColumns)
            + " FROM tcc_ops.channel_user WHERE removed_at IS NULL ORDER BY added_at, user_oid").Select(values =>
            {
                var r = new OpsRow(values);
                return new WriterGrant(r.Required("user_oid"), r.Text("display_name"), r.Required("role"), r.Required("added_by"),
                    r.Instant("added_at")!.Value, r.Instant("removed_at"));
            }).ToArray();
    }

    /// <inheritdoc />
    public Confirmation Create(Confirmation confirmation)
    {
        ArgumentNullException.ThrowIfNull(confirmation);
        if (!IsDigest(confirmation.TokenSha256) || !IsDigest(confirmation.ArgsSha256))
        {
            throw new ArgumentException("Confirmation token and argument digests must be SHA-256 hex, never cleartext tokens.", nameof(confirmation));
        }

        if (string.CompareOrdinal(OpsRow.Clock(confirmation.ExpiresAt), OpsRow.Clock(confirmation.CreatedAt)) <= 0
            || confirmation.ConsumedAt is not null || confirmation.Outcome is not null)
        {
            throw new ArgumentException("A new confirmation must be unconsumed and expire after creation.", nameof(confirmation));
        }

        return database.Transact(session =>
        {
            if (session.QueryExempt(SqlExemption.ChannelIdentity, "SELECT confirmation_id FROM tcc_ops.channel_confirmation WHERE confirmation_id = ? OR token_sha256 = ?",
                confirmation.ConfirmationId, confirmation.TokenSha256).Count != 0)
            {
                throw new InvalidOperationException("The confirmation identity or token digest is already recorded.");
            }

            session.InsertExempt(SqlExemption.ChannelIdentity, "tcc_ops.channel_confirmation", ConfirmationColumns,
                [new object?[] { confirmation.ConfirmationId, confirmation.TokenSha256, confirmation.UserOid, confirmation.ToolName, confirmation.ArgsSha256,
                    confirmation.IdempotencyKey, OpsRow.Clock(session, confirmation.CreatedAt), OpsRow.Clock(session, confirmation.ExpiresAt), null, null, confirmation.ResultJson }]);
            return confirmation;
        });
    }

    /// <inheritdoc />
    public Confirmation? FindByTokenHash(string tokenSha256)
    {
        using var session = database.Open();
        return session.QueryExempt(SqlExemption.ChannelIdentity, ConfirmationSelect + " WHERE token_sha256 = ?", tokenSha256).Select(Hydrate).SingleOrDefault();
    }

    /// <inheritdoc />
    public Confirmation? FindByIdempotencyKey(string userOid, string key)
    {
        using var session = database.Open();
        return session.QueryExempt(SqlExemption.ChannelIdentity, session.Dialect.Page(ConfirmationSelect
            + " WHERE user_oid = ? AND idempotency_key = ? AND outcome IS NOT NULL ORDER BY created_at, confirmation_id", 1, 0),
            userOid, key).Select(Hydrate).SingleOrDefault();
    }

    /// <inheritdoc />
    public bool Consume(string confirmationId, string userOid, string argsSha256, PyDateTime at, string? idempotencyKey = null) =>
        database.Transact(session => session.ExecuteExempt(SqlExemption.ChannelIdentity,
            "UPDATE tcc_ops.channel_confirmation SET consumed_at = ?, idempotency_key = ? WHERE confirmation_id = ? AND user_oid = ? "
            + "AND args_sha256 = ? AND consumed_at IS NULL AND expires_at > ?", OpsRow.Clock(session, at), idempotencyKey,
            confirmationId, userOid, argsSha256, OpsRow.Clock(session, at)) == 1);

    /// <inheritdoc />
    public void RecordResult(string confirmationId, string outcome, string? resultJson)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(outcome);
        database.Transact(session =>
        {
            var changed = session.ExecuteExempt(SqlExemption.ChannelIdentity, "UPDATE tcc_ops.channel_confirmation SET outcome = ?, result_json = ? "
                + "WHERE confirmation_id = ? AND consumed_at IS NOT NULL AND outcome IS NULL", outcome, resultJson, confirmationId);
            if (changed == 0)
            {
                var existing = session.QueryExempt(SqlExemption.ChannelIdentity, ConfirmationSelect + " WHERE confirmation_id = ?", confirmationId).Select(Hydrate).SingleOrDefault();
                if (existing is null || existing.ConsumedAt is null || existing.Outcome != outcome || existing.ResultJson != resultJson)
                {
                    throw new InvalidOperationException("Only one matching result can be recorded for a consumed confirmation.");
                }
            }

            return true;
        });
    }

    private static Confirmation Hydrate(IReadOnlyDictionary<string, object?> values)
    {
        var r = new OpsRow(values);
        return new Confirmation(r.Required("confirmation_id"), r.Required("token_sha256").Trim(), r.Required("user_oid"), r.Required("tool_name"),
            r.Required("args_sha256").Trim(), r.Instant("created_at")!.Value, r.Instant("expires_at")!.Value,
            r.Text("idempotency_key"), r.Instant("consumed_at"), r.Text("outcome"), r.Text("result_json"));
    }

    private static bool IsDigest(string value) => value.Length == 64 && value.All(char.IsAsciiHexDigit);
}
