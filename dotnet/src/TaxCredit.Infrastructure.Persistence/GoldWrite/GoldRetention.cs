using System.Globalization;
using TaxCredit.Application.Hosting;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence;

/// <summary>
/// How many superseded runs keep their employee-grain Gold rows. Every healthy-path read resolves the one current run of a client-program and
/// selects by that <c>run_id</c>; the employee-grain tables of older runs serve nothing but forensics, and each run writes a full copy.
/// The manifest and the unit-level tables (<c>unit_year_master</c>, <c>unit_credit_installment</c>, which keep their history through
/// <c>is_current</c>) are never touched.
/// </summary>
/// <param name="KeepSuperseded">The newest superseded runs per client-program that keep their rows; null keeps every run.</param>
/// <param name="MaximumRunsPerPass">Bounds the work one publication can trigger, so a backlog drains over several publications.</param>
public sealed record GoldRetention(int? KeepSuperseded, int MaximumRunsPerPass = 5)
{
    /// <summary>Nothing is removed: the behaviour before retention existed.</summary>
    public static GoldRetention Off { get; } = new(KeepSuperseded: null);

    /// <summary>The conservative default: the current run plus the two before it.</summary>
    public static GoldRetention Default { get; } = new(2);

    /// <summary>Reads <c>RETAIN_SUPERSEDED_RUNS</c>: a whole number of superseded runs to keep (at least 1), or <c>all</c> to prune nothing.</summary>
    public static GoldRetention FromSettings(Func<string, string?> setting)
    {
        ArgumentNullException.ThrowIfNull(setting);
        var text = setting("RETAIN_SUPERSEDED_RUNS")?.Trim().ToLowerInvariant();
        if (string.IsNullOrEmpty(text))
        {
            return Default;
        }

        if (text is "all" or "off")
        {
            return Off;
        }

        // At least one: a reader that resolved the current run an instant before a newer publish supersedes it must still find its rows.
        return int.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out var keep) && keep >= 1
            ? new GoldRetention(keep)
            : throw new InvalidOperationException("Invalid setting RETAIN_SUPERSEDED_RUNS: a whole number of runs (at least 1), or all.");
    }

    // Deleted in this order. employee_eligibility goes last because it is the marker: a run that still has eligibility rows still has
    // something to prune, and a pass that stopped part-way is finished by the next one.
    private static readonly string[] Tables = ["employee_period_fact", "onezero_matrix", "employee_eligibility"];

    /// <summary>Removes the employee-grain rows of superseded runs beyond the newest <see cref="KeepSuperseded" />; returns the runs pruned.</summary>
    internal int Prune(PersistenceDatabase database, long clientId, string programCode)
    {
        if (KeepSuperseded is not { } keep)
        {
            return 0;
        }

        using var span = RunSpans.Start("persist.prune");
        var candidates = database.Transact(session =>
        {
            var superseded = session.Query(clientId, "SELECT run_id FROM {ops.run_manifest} WHERE {tenant} AND program_code=? AND run_status='superseded' "
                + "ORDER BY run_started_at DESC, run_id DESC", programCode).Select(r => (string)r["run_id"]!).Skip(keep).ToArray();
            if (superseded.Length == 0)
            {
                return [];
            }

            var pending = new List<string>();
            foreach (var chunk in Enumerable.Reverse(superseded).Chunk(500))
            {
                var holding = session.Query(clientId, "SELECT DISTINCT run_id FROM {gold.employee_eligibility} WHERE {tenant} AND run_id IN ("
                    + string.Join(",", chunk.Select(_ => "?")) + ")", chunk.Cast<object?>().ToArray()).Select(r => (string)r["run_id"]!).ToHashSet(StringComparer.Ordinal);
                pending.AddRange(chunk.Where(holding.Contains));
                if (pending.Count >= MaximumRunsPerPass)
                {
                    break;
                }
            }

            return pending.Take(MaximumRunsPerPass).ToArray();
        });
        foreach (var run in candidates)
        {
            database.Transact(session =>
            {
                // Re-checked inside the deleting transaction: only a run that is still superseded is ever pruned.
                if (session.Query(clientId, "SELECT run_status FROM {ops.run_manifest} WHERE {tenant} AND run_id=?", run) is not [{ } row]
                    || (string?)row["run_status"] != "superseded")
                {
                    return 0;
                }

                foreach (var table in Tables)
                {
                    session.Execute(clientId, "DELETE FROM {gold." + table + "} WHERE {tenant} AND run_id=?", run);
                }

                return 1;
            });
        }

        span?.SetTag("runs", candidates.Length);
        return candidates.Length;
    }
}
