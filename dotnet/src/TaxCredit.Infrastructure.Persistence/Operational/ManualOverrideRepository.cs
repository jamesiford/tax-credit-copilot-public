using System.Globalization;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>Durable human adjustments; clearing a choice appends a null value instead of erasing its history.</summary>
public sealed class ManualOverrideRepository(PersistenceDatabase database) : IManualOverrideRepository, IBaseYearOverrides
{
    private static readonly string[] Columns =
    [
        "override_id", "run_id", "client_id", "scope", "target_key", "field_changed", "value_before", "value_after",
        "reason_code", "justification_text", "created_by", "created_at", "approved_by", "approved_at",
    ];

    /// <inheritdoc />
    public bool IsDurable { get; } = true;

    /// <inheritdoc />
    public ManualOverride Record(ManualOverride overrideRow)
    {
        ArgumentNullException.ThrowIfNull(overrideRow);
        return database.Transact(session =>
        {
            if (session.Query(overrideRow.ClientId, "SELECT override_id FROM tcc_ops.manual_override WHERE {tenant} AND override_id = ?", overrideRow.OverrideId).Count != 0)
            {
                throw new InvalidOperationException("The override identity is already recorded.");
            }

            var order = OverrideOrder.Next(session);
            session.Insert(overrideRow.ClientId, "tcc_ops.manual_override", [.. Columns, "write_order"],
                [new object?[] { overrideRow.OverrideId, overrideRow.RunId, overrideRow.ClientId, overrideRow.Scope, overrideRow.TargetKey,
                    overrideRow.FieldChanged, overrideRow.ValueBefore, overrideRow.ValueAfter, overrideRow.ReasonCode, overrideRow.JustificationText,
                    overrideRow.CreatedBy, OpsRow.Timestamp(session, overrideRow.CreatedAt), overrideRow.ApprovedBy, OpsRow.Timestamp(session, overrideRow.ApprovedAt), order }]);
            return overrideRow;
        });
    }

    /// <inheritdoc />
    public IReadOnlyDictionary<string, long> BaseYears(long clientId, string programCode)
    {
        var result = new Dictionary<string, long>(StringComparer.Ordinal);
        var prefix = programCode + ":";
        foreach (var row in History(clientId))
        {
            if (row.FieldChanged != "base_year" || !row.TargetKey.StartsWith(prefix, StringComparison.Ordinal))
            {
                continue;
            }

            var key = row.TargetKey[prefix.Length..];
            result.Remove(key);
            if (long.TryParse(row.ValueAfter, NumberStyles.Integer, CultureInfo.InvariantCulture, out var year))
            {
                result[key] = year;
            }
        }

        return result;
    }

    /// <inheritdoc />
    public IReadOnlyList<ManualOverride> History(long clientId)
    {
        using var session = database.Open();
        return session.Query(clientId, "SELECT " + string.Join(", ", Columns)
            + " FROM tcc_ops.manual_override WHERE {tenant} ORDER BY write_order").Select(Hydrate).ToArray();
    }

    private static ManualOverride Hydrate(IReadOnlyDictionary<string, object?> values)
    {
        var r = new OpsRow(values);
        return new ManualOverride(r.Required("override_id"), r.Required("run_id"), r.Long("client_id"), r.Required("scope"),
            r.Required("target_key"), r.Required("field_changed"), r.Text("value_before"), r.Text("value_after"), r.Text("reason_code"),
            r.Text("justification_text"), r.Required("created_by"), r.Instant("created_at")!.Value, r.Text("approved_by"), r.Instant("approved_at"));
    }
}
