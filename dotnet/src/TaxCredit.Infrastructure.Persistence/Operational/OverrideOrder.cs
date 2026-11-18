using System.Globalization;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>A conflicting counter update aborts the transaction on both providers and is retried with the append.</summary>
internal static class OverrideOrder
{
    internal static long Next(SqlSession session)
    {
        var changed = session.ExecuteExempt(SqlExemption.OperationalSequence,
            "UPDATE {ops.write_sequence} SET last_value = last_value + 1 WHERE sequence_name = ?", "manual_override");
        if (changed != 1)
        {
            throw new InvalidOperationException("The manual override sequence must have exactly one provisioned row.");
        }

        var rows = session.QueryExempt(SqlExemption.OperationalSequence,
            "SELECT last_value FROM {ops.write_sequence} WHERE sequence_name = ?", "manual_override");
        return Convert.ToInt64(rows.Single()["last_value"], CultureInfo.InvariantCulture);
    }

    internal static void UpgradeLocal(SqlSession session)
    {
        session.ExecuteExempt(SqlExemption.Schema, "CREATE TABLE IF NOT EXISTS {ops.write_sequence} "
            + "(sequence_name TEXT PRIMARY KEY NOT NULL, last_value INTEGER NOT NULL) STRICT");
        session.ExecuteExempt(SqlExemption.Schema, "INSERT INTO {ops.write_sequence} (sequence_name,last_value) "
            + "SELECT 'manual_override',0 WHERE NOT EXISTS (SELECT 1 FROM {ops.write_sequence} WHERE sequence_name='manual_override')");
        var columns = session.QueryExempt(SqlExemption.Schema, "PRAGMA table_info(" + session.Dialect.Name("ops.manual_override") + ")");
        if (!columns.Any(c => (string)c["name"]! == "write_order"))
        {
            session.ExecuteExempt(SqlExemption.Schema, "ALTER TABLE {ops.manual_override} ADD COLUMN write_order INTEGER NULL");
        }

        var rows = session.QueryExempt(SqlExemption.Schema, "SELECT client_id,override_id FROM {ops.manual_override} "
            + "WHERE write_order IS NULL ORDER BY created_at,override_id,client_id");
        foreach (var row in rows)
        {
            var order = Next(session);
            session.Execute(Convert.ToInt64(row["client_id"], CultureInfo.InvariantCulture),
                "UPDATE {ops.manual_override} SET write_order=? WHERE {tenant} AND override_id=? AND write_order IS NULL",
                order, row["override_id"]);
        }
    }
}
