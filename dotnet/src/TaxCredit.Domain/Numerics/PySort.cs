namespace TaxCredit.Domain.Numerics;

/// <summary>Python's <c>sorted()</c> / <c>list.sort()</c> contract: stable, with <c>reverse</c> preserving input order of equals.</summary>
/// <remarks>
/// Why not <see cref="List{T}.Sort()"/> or <c>Array.Sort</c>: they are unstable introsorts. The contract is enforced
/// here with an explicit input-index tie-break (ascending for both directions: Python's <c>reverse=True</c> keeps
/// equal elements in their original order), so the result does not depend on the sort algorithm.
/// </remarks>
public static class PySort
{
    /// <summary>Python <c>sorted(items, key=key, reverse=reverse)</c>.</summary>
    public static List<T> Sorted<T, TKey>(IEnumerable<T> items, Func<T, TKey> key, IComparer<TKey> comparer, bool reverse = false)
    {
        ArgumentNullException.ThrowIfNull(items);
        ArgumentNullException.ThrowIfNull(key);
        ArgumentNullException.ThrowIfNull(comparer);
        var decorated = items.Select((item, index) => (Item: item, Key: key(item), Index: index)).ToList();
        try
        {
            decorated.Sort((x, y) =>
            {
                var c = comparer.Compare(x.Key, y.Key);
                if (c != 0)
                {
                    return reverse ? -c : c;
                }

                return x.Index.CompareTo(y.Index);
            });
        }
        catch (InvalidOperationException e) when (e.InnerException is PyException inner)
        {
            // List.Sort wraps a comparer's exception; Python lets a TypeError from "<" propagate unchanged.
            System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(inner).Throw();
        }

        return decorated.Select(d => d.Item).ToList();
    }

    /// <summary>Python <c>min(items, key=key)</c>: the first minimal element.</summary>
    public static T MinBy<T, TKey>(IReadOnlyList<T> items, Func<T, TKey> key, IComparer<TKey> comparer)
    {
        ArgumentNullException.ThrowIfNull(items);
        if (items.Count == 0)
        {
            throw new PyValueError("min() iterable argument is empty");
        }

        var best = items[0];
        var bestKey = key(best);
        for (var i = 1; i < items.Count; i++)
        {
            var k = key(items[i]);
            if (comparer.Compare(k, bestKey) < 0)
            {
                best = items[i];
                bestKey = k;
            }
        }

        return best;
    }

    /// <summary>Python <c>max(items, key=key)</c>: the first maximal element.</summary>
    public static T MaxBy<T, TKey>(IReadOnlyList<T> items, Func<T, TKey> key, IComparer<TKey> comparer)
    {
        ArgumentNullException.ThrowIfNull(items);
        if (items.Count == 0)
        {
            throw new PyValueError("max() iterable argument is empty");
        }

        var best = items[0];
        var bestKey = key(best);
        for (var i = 1; i < items.Count; i++)
        {
            var k = key(items[i]);
            if (comparer.Compare(k, bestKey) > 0)
            {
                best = items[i];
                bestKey = k;
            }
        }

        return best;
    }

    /// <summary>Python float ordering for keys that are not NaN (so <c>0.0</c> and <c>-0.0</c> are equal).</summary>
    public static IComparer<double> FloatComparer { get; } = Comparer<double>.Create((a, b) => a < b ? -1 : (a > b ? 1 : 0));
}
