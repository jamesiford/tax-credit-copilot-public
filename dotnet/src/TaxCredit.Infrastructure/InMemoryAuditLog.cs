using System.Collections.Concurrent;
using TaxCredit.Application.Pipeline;

namespace TaxCredit.Infrastructure;

/// <summary>Bounded in-memory audit trail: a support aid, not the destination (the durable trail is an operational table).</summary>
public sealed class InMemoryAuditLog : IAuditLog
{
    private const int Capacity = 1000;
    private readonly ConcurrentQueue<AuditRecord> _records = new();

    /// <summary>The most recent records, oldest first.</summary>
    /// <returns>A snapshot copy.</returns>
    public IReadOnlyList<AuditRecord> Snapshot() => [.. _records];

    /// <inheritdoc />
    public void Record(AuditRecord record)
    {
        _records.Enqueue(record);
        while (_records.Count > Capacity && _records.TryDequeue(out _))
        {
        }
    }
}
