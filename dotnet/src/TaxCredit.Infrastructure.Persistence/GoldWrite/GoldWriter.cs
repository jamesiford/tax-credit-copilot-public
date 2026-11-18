using TaxCredit.Application.Hosting;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence;

/// <summary>Persists certified projections, never recomputes them, and atomically publishes the recalculated client-program series.</summary>
public sealed class GoldWriter : IGoldWriter
{
    /// <summary>The contract counts section 9 checks, not supplementary publication integrity queries.</summary>
    public static int Section9QueryCount => GoldValidation.Section9QueryCount;

    private readonly PersistenceDatabase _database;
    private readonly IReadOnlyDictionary<string, IReadOnlyList<StorageColumn>> _schema;
    private readonly Action<string>? _checkpoint;

    /// <summary>Uses the deployed column contract and an optional fault-injection checkpoint.</summary>
    public GoldWriter(PersistenceDatabase database, string repositoryRoot, Action<string>? checkpoint = null)
    {
        ArgumentNullException.ThrowIfNull(database);
        _database = database;
        _schema = PersistenceSchema.Read(repositoryRoot);
        _checkpoint = checkpoint;
    }

    /// <inheritdoc />
    public IReadOnlyList<KeyValuePair<string, long>> WriteRun(GoldRunPayload payload)
    {
        ArgumentNullException.ThrowIfNull(payload);
        ValidateShape(payload);
        var manifest = payload.ManifestRow.Select((v, i) => _schema["tcc_ops.run_manifest"][i].ConvertValue(v)).ToArray();
        _database.Transact(session =>
        {
            if (session.Query(payload.ClientId, "SELECT run_id FROM tcc_ops.run_manifest WHERE {tenant} AND run_id=?", payload.RunId).Count > 0)
            {
                throw new InvalidOperationException("A run identity cannot be reused.");
            }

            using (RunSpans.Start("persist.manifest")) { session.Insert(payload.ClientId, "tcc_ops.run_manifest", payload.ManifestColumns, [manifest]); }
            return 0;
        });
        try
        {
            return _database.Transact(session => Publish(session, payload));
        }
        catch (AmbiguousCommitException)
        {
            // A committed run must not be marked failed after an uncertain acknowledgement.
            throw;
        }
        catch
        {
            _database.Transact(session => session.Execute(payload.ClientId,
                "UPDATE tcc_ops.run_manifest SET run_status='failed' WHERE {tenant} AND run_id=? AND run_status='running'", payload.RunId));
            throw;
        }
    }

    private List<KeyValuePair<string, long>> Publish(SqlSession session, GoldRunPayload payload)
    {
        var counts = new List<KeyValuePair<string, long>> { new("run_manifest", 1) };
        using (RunSpans.Start("persist.retire"))
        {
            RetirePrior(session, payload);
        }

        _checkpoint?.Invoke("prior-current-retired");
        foreach (var (table, rows) in payload.Tables)
        {
            var columns = GoldColumns.All[table];
            var storage = _schema["tcc_gold." + table];
            IReadOnlyList<object?>[] values;
            using (var prepare = RunSpans.Start("gold.prepare"))
            {
                prepare?.SetTag("table", table);
                values = rows.Select(row => (IReadOnlyList<object?>)row.Cells
                    .Select((cell, i) => storage[i].ConvertValue(cell)).ToArray()).ToArray();
            }

            int written;
            using (var insert = RunSpans.Start("persist.insert"))
            {
                insert?.SetTag("table", table);
                insert?.SetTag("rows", values.Length);
                written = session.Insert(payload.ClientId, "tcc_gold." + table, columns, values);
            }

            counts.Add(new(table, written));
            _checkpoint?.Invoke(table);
        }

        using (RunSpans.Start("persist.validate"))
        {
            var failures = GoldValidation.Check(session, payload.RunId);
            if (failures.Count > 0)
            {
                throw new GoldWriteFailed("Gold invariant violation: " + string.Join("; ", failures.Select(f => f.Query)));
            }
        }

        using (RunSpans.Start("persist.supersede"))
        {
            Supersede(session, payload);
        }

        return counts;
    }

    private static void RetirePrior(SqlSession session, GoldRunPayload payload)
    {
        foreach (var table in new[] { "unit_year_master", "unit_credit_installment" })
        {
            session.Execute(payload.ClientId, "UPDATE tcc_gold." + table
                + " SET is_current=0 WHERE {tenant} AND program_code=? AND is_current=1", payload.ProgramCode);
        }
    }

    private static void Supersede(SqlSession session, GoldRunPayload payload)
    {
        session.Execute(payload.ClientId,
            "UPDATE tcc_ops.run_manifest SET run_status='superseded',superseded_by_run_id=? WHERE {tenant} AND program_code=? AND run_status='success' AND run_id<>?",
            payload.RunId, payload.ProgramCode, payload.RunId);
        session.Execute(payload.ClientId,
            "UPDATE tcc_ops.run_manifest SET run_status='success',run_completed_at=? WHERE {tenant} AND run_id=? AND run_status='running'",
            payload.RunCompletedAt, payload.RunId);
    }
    private static void ValidateShape(GoldRunPayload payload)
    {
        if (!payload.ManifestColumns.SequenceEqual(WarehouseVocabulary.RunManifestColumns) || payload.ManifestRow.Count != payload.ManifestColumns.Count ||
            payload.ManifestRow[0] as string != payload.RunId || payload.ManifestRow[1] is not long client || client != payload.ClientId ||
            payload.ManifestRow[3] as string != payload.ProgramCode || payload.ManifestRow[17] as string != "running")
        {
            throw new GoldWriteFailed("Manifest does not match its run identity or columns.");
        }

        foreach (var (table, rows) in payload.Tables)
        {
            foreach (var row in rows)
            {
                if (row.Table != table || !row.Columns.SequenceEqual(GoldColumns.All[table]) ||
                    row["client_id"].AsInt != payload.ClientId || row["run_id"].AsText != payload.RunId ||
                    (row.Columns.Contains("program_code") && row["program_code"].AsText != payload.ProgramCode))
                {
                    throw new GoldWriteFailed("Gold row does not match its run identity or columns.");
                }
            }
        }
    }

    /// <inheritdoc />
    public IReadOnlyList<(string Query, long RowCount)> Validate()
    {
        using var span = RunSpans.Start("gold.validate");
        using var session = _database.Open();
        return GoldValidation.Check(session);
    }

    /// <summary>Marks abandoned running manifests failed without inventing a completion timestamp.</summary>
    public int ReapStranded(DateTime cutoffUtc) => _database.Transact(session => session.ExecuteExempt(SqlExemption.Worker,
        "UPDATE tcc_ops.run_manifest SET run_status='failed' WHERE run_status='running' AND run_completed_at IS NULL AND run_started_at<?",
        cutoffUtc.ToString("yyyy-MM-dd HH:mm:ss", System.Globalization.CultureInfo.InvariantCulture)));
}
