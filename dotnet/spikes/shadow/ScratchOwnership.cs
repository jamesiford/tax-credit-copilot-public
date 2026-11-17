namespace TaxCredit.Shadow;

/// <summary>Recovery retains only acknowledged invocation-owned identities, never a schema-wide sweep.</summary>
public sealed class ScratchOwnership(Guid invocation, IEnumerable<string> preExisting)
{
    private readonly HashSet<string> _preExisting = new(preExisting, StringComparer.Ordinal);
    private readonly Dictionary<string, long> _created = new(StringComparer.Ordinal);
    private readonly HashSet<string> _reserved = new(StringComparer.Ordinal);
    private int _ordinal;

    public string Reserve()
    {
        var name = $"w4_{invocation:N}_{++_ordinal}";
        if (_preExisting.Contains(name))
        {
            throw new InvalidOperationException("Scratch collision refused.");
        }

        _reserved.Add(name);
        return name;
    }

    public void AcknowledgeCreated(string name, long objectId)
    {
        if (!_reserved.Contains(name) || _preExisting.Contains(name) || objectId <= 0 || !_created.TryAdd(name, objectId))
        {
            throw new InvalidOperationException("Scratch ownership refused.");
        }
    }

    public int Cleanup(Func<string, long?> currentIdentity, Action<string> dropOwnedTable)
    {
        ArgumentNullException.ThrowIfNull(currentIdentity);
        ArgumentNullException.ThrowIfNull(dropOwnedTable);
        var removed = 0;
        foreach (var (name, identity) in _created.ToArray())
        {
            var current = currentIdentity(name);
            if (current is null)
            {
                _created.Remove(name);
            }
            else if (current == identity)
            {
                dropOwnedTable(name);
                _created.Remove(name);
                removed++;
            }
            else
            {
                throw new InvalidOperationException("Scratch identity changed; recovery refused.");
            }
        }

        return removed;
    }

    public IReadOnlyDictionary<string, long> RecoveryLedger => new Dictionary<string, long>(_created, StringComparer.Ordinal);

    public static ScratchOwnership Recover(Guid invocation, IEnumerable<string> preExisting, IReadOnlyDictionary<string, long> ledger)
    {
        ArgumentNullException.ThrowIfNull(ledger);
        var result = new ScratchOwnership(invocation, preExisting);
        var prefix = $"w4_{invocation:N}_";
        foreach (var (name, identity) in ledger)
        {
            if (!name.StartsWith(prefix, StringComparison.Ordinal)
                || !int.TryParse(name.AsSpan(prefix.Length), out var ordinal) || ordinal <= 0)
            {
                throw new InvalidOperationException("Scratch recovery ownership refused.");
            }

            result._reserved.Add(name);
            result.AcknowledgeCreated(name, identity);
            result._ordinal = Math.Max(result._ordinal, ordinal);
        }

        return result;
    }
}
