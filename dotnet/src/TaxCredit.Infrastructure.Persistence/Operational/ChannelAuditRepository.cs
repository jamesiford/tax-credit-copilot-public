using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>Insert-only audit adapters with a closed column catalogue; caller data never becomes SQL syntax.</summary>
public sealed class ChannelAuditRepository(PersistenceDatabase database) : IChannelAuditRepository
{
    private static readonly string[] EventColumns =
    [
        "audit_id", "event_seq", "phase", "correlation_id", "occurred_at", "elapsed_ms", "channel", "user_oid", "tenant_id",
        "user_display_name", "user_upn", "identity_assurance", "conversation_id", "tool_name", "action_kind", "client_id", "tax_year",
        "request_summary", "request_sha256", "confirmation_ref", "outcome", "error", "run_id", "trail_sha256", "numeric_guard", "is_deterministic_path",
    ];
    private static readonly string[] ActionColumns =
    [
        "action_id", "run_id", "client_id", "agent_name", "agent_version", "model_deployment", "prompt_hash", "tool_calls",
        "input_summary", "output_summary", "user_upn", "occurred_at", "is_deterministic_path",
    ];

    /// <inheritdoc />
    public void Append(ChannelAuditEvent auditEvent)
    {
        ArgumentNullException.ThrowIfNull(auditEvent);
        var r = new OpsRow(auditEvent.Fields);
        if (r.Required("phase") is not ("begin" or "end" or "single")
            || r.Required("numeric_guard") is not ("pass" or "rejected" or "n/a")
            || r.Required("outcome") is not ("pending" or "ok" or "error" or "refused" or "rejected_by_guard"))
        {
            throw new ArgumentException("Invalid channel event vocabulary.", nameof(auditEvent));
        }

        database.Transact(session =>
        {
            if (session.QueryExempt(SqlExemption.ChannelIdentity, "SELECT audit_id FROM tcc_ops.channel_audit WHERE audit_id = ? AND event_seq = ?",
                r.Required("audit_id"), r.Long("event_seq")).Count != 0)
            {
                throw new InvalidOperationException("The channel event identity and sequence are already recorded.");
            }

            Insert(session, "tcc_ops.channel_audit", EventColumns, auditEvent.Fields);
            return true;
        });
    }

    /// <inheritdoc />
    public IReadOnlyList<ChannelAuditEvent> ForUser(string userOid, PyDateTime? since = null, PyDateTime? until = null, string? tool = null, int limit = 200)
    {
        BoundLimit(limit);
        using var session = database.Open();
        var sql = "SELECT " + string.Join(", ", EventColumns) + " FROM tcc_ops.channel_audit WHERE user_oid = ?";
        var args = new List<object?> { userOid };
        if (since is { } begin)
        {
            sql += " AND occurred_at >= ?";
            args.Add(OpsRow.Clock(session, begin));
        }

        if (until is { } end)
        {
            sql += " AND occurred_at < ?";
            args.Add(OpsRow.Clock(session, end));
        }

        if (tool is not null)
        {
            sql += " AND tool_name = ?";
            args.Add(tool);
        }

        return session.QueryExempt(SqlExemption.ChannelIdentity,
            session.Dialect.Page(sql + " ORDER BY occurred_at DESC, event_seq DESC, audit_id", limit, 0), args.ToArray())
            .Select(row => new ChannelAuditEvent(row)).ToArray();
    }

    /// <inheritdoc />
    public IReadOnlyList<ChannelAuditEvent> ByCorrelation(string correlationId)
    {
        using var session = database.Open();
        return session.QueryExempt(SqlExemption.ChannelIdentity, "SELECT " + string.Join(", ", EventColumns)
            + " FROM tcc_ops.channel_audit WHERE correlation_id = ? ORDER BY occurred_at, event_seq, audit_id", correlationId)
            .Select(row => new ChannelAuditEvent(row)).ToArray();
    }

    /// <inheritdoc />
    public void Append(AgentActionAudit action)
    {
        ArgumentNullException.ThrowIfNull(action);
        database.Transact(session =>
        {
            var id = new OpsRow(action.Fields).Required("action_id");
            if (session.QueryExempt(SqlExemption.ChannelIdentity, "SELECT action_id FROM tcc_ops.agent_action_audit WHERE action_id = ?", id).Count != 0)
            {
                throw new InvalidOperationException("The agent action identity is already recorded.");
            }

            Insert(session, "tcc_ops.agent_action_audit", ActionColumns, action.Fields);
            return true;
        });
    }

    /// <inheritdoc />
    public IReadOnlyList<AgentActionAudit> Recent(string? agentName = null, int limit = 100)
    {
        BoundLimit(limit);
        using var session = database.Open();
        var sql = "SELECT " + string.Join(", ", ActionColumns) + " FROM tcc_ops.agent_action_audit"
            + (agentName is null ? "" : " WHERE agent_name = ?") + " ORDER BY occurred_at DESC, action_id";
        return session.QueryExempt(SqlExemption.ChannelIdentity, session.Dialect.Page(sql, limit, 0), agentName is null ? [] : [agentName])
            .Select(row => new AgentActionAudit(row)).ToArray();
    }

    private static void Insert(SqlSession session, string table, string[] columns, IReadOnlyDictionary<string, object?> fields)
    {
        if (fields.Keys.Except(columns, StringComparer.Ordinal).Any())
        {
            throw new ArgumentException("Unknown audit column.", nameof(fields));
        }

        var row = new OpsRow(fields);
        var values = columns.Select(column => column == "occurred_at"
            ? OpsRow.Clock(session, row.Instant(column) ?? throw new ArgumentException("An audit event requires an instant.", nameof(fields)))
            : row[column]).ToArray();
        if (row.OptionalLong("client_id") is { } clientId)
        {
            values[Array.IndexOf(columns, "client_id")] = clientId;
            session.Insert(clientId, table, columns, [values]);
        }
        else
        {
            session.InsertExempt(SqlExemption.ChannelIdentity, table, columns, [values]);
        }
    }

    private static void BoundLimit(int limit)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(limit);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(limit, 1000);
    }
}
