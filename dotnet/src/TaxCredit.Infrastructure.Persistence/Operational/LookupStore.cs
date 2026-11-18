using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>Stores authored lookup facts; source precedence and effective-date resolution remain in Sources.</summary>
public sealed class LookupStore(PersistenceDatabase database, IIdSource? ids = null) : ILookupStore
{
    private static readonly string[] Columns =
    [
        "override_id", "lookup_name", "client_id", "key_kind", "key_value", "value_json", "effective_from", "effective_to",
        "authored_by", "authored_on", "basis", "inferred", "superseded_at",
    ];

    /// <inheritdoc />
    public IReadOnlyList<LookupEntry> Entries(string lookup, long clientId) => database.Transact(session =>
    {
        var rows = ReadEntries(session, lookup, clientId);
        if (clientId != 0)
        {
            rows.AddRange(ReadEntries(session, lookup, 0));
        }

        return (IReadOnlyList<LookupEntry>)rows;
    });

    /// <inheritdoc />
    public void Put(LookupEntry entry, PyDateTime at)
    {
        ArgumentNullException.ThrowIfNull(entry);
        database.Transact(session =>
        {
            var clock = OpsRow.Clock(session, at);
            session.Execute(entry.ClientId, "UPDATE {ops.lookup_override} SET superseded_at = ? "
                + "WHERE {tenant} AND lookup_name = ? AND key_kind = ? AND key_value = ? AND superseded_at IS NULL",
                clock, entry.Lookup, entry.KeyKind, entry.Key);
            session.Insert(entry.ClientId, "ops.lookup_override", Columns,
                [new object?[] { (ids?.NewId() ?? Guid.NewGuid()).ToString(), entry.Lookup, entry.ClientId, entry.KeyKind, entry.Key, entry.ValueJson,
                    entry.EffectiveFrom, entry.EffectiveTo, entry.AuthoredBy, clock, entry.Basis, entry.Inferred, null }]);
            AppendAudit(session, entry, "put", entry.AuthoredBy, clock);
            return true;
        });
    }

    /// <inheritdoc />
    public bool Remove(string lookup, long clientId, string keyKind, string key, string actor, PyDateTime at) =>
        database.Transact(session =>
        {
            var clock = OpsRow.Clock(session, at);
            var count = session.Execute(clientId, "UPDATE {ops.lookup_override} SET superseded_at = ? "
                + "WHERE {tenant} AND lookup_name = ? AND key_kind = ? AND key_value = ? AND superseded_at IS NULL", clock, lookup, keyKind, key);
            if (count > 0)
            {
                AppendAudit(session, new LookupEntry(lookup, clientId, keyKind, key, "", actor), "remove", actor, clock);
            }

            return count > 0;
        });

    /// <inheritdoc />
    public IReadOnlyList<IReadOnlyDictionary<string, object?>> Audit(long clientId, string? lookup = null)
    {
        using var session = database.Open();
        var sql = "SELECT audit_id, lookup_name, client_id, action, key_kind, key_value, value_json, actor, at, basis "
            + "FROM {ops.lookup_audit} WHERE {tenant}" + (lookup is null ? "" : " AND lookup_name = ?") + " ORDER BY at, audit_id";
        return session.Query(clientId, sql, lookup is null ? [] : [lookup]);
    }

    private static List<LookupEntry> ReadEntries(SqlSession session, string lookup, long clientId) =>
        session.Query(clientId, "SELECT " + string.Join(", ", Columns)
            + " FROM {ops.lookup_override} WHERE {tenant} AND lookup_name = ? AND superseded_at IS NULL ORDER BY key_kind, key_value", lookup)
            .Select(values =>
            {
                var r = new OpsRow(values);
                return new LookupEntry(r.Required("lookup_name"), r.Long("client_id"), r.Required("key_kind"), r.Required("key_value"),
                    r.Required("value_json"), r.Required("authored_by"), r.Text("basis") ?? "", r.Bool("inferred"), r.Day("effective_from"), r.Day("effective_to"));
            }).ToList();

    private void AppendAudit(SqlSession session, LookupEntry entry, string action, string actor, object? at) =>
        session.Insert(entry.ClientId, "ops.lookup_audit",
            ["audit_id", "lookup_name", "client_id", "action", "key_kind", "key_value", "value_json", "actor", "at", "basis"],
            [new object?[] { (ids?.NewId() ?? Guid.NewGuid()).ToString(), entry.Lookup, entry.ClientId, action, entry.KeyKind, entry.Key,
                action == "put" ? entry.ValueJson : null, actor, at, entry.Basis }]);
}
