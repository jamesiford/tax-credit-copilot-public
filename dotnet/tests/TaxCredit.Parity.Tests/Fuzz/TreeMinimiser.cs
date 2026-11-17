using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Delta-debugging over an argument tree: lists lose elements (ddmin chunks) and mappings lose keys while the call still diverges, recursively,
/// so a failing scenario shrinks to the rows, inputs and fields that matter. Tagged scalars (<c>{"$date": ...}</c>) are atomic.
/// </summary>
internal static class TreeMinimiser
{
    /// <summary>Shrinks <paramref name="args"/>; <paramref name="stillFails"/> is asked at most <paramref name="budget"/> times.</summary>
    public static PyDict Minimise(PyDict args, Func<PyDict, bool> stillFails, int budget = 400)
    {
        var asked = 0;
        bool Fails(PyDict candidate)
        {
            if (asked >= budget)
            {
                return false;
            }

            asked++;
            return stillFails(candidate);
        }

        var current = args;
        PyDict previous;
        do
        {
            previous = current;
            current = (PyDict)Reduce(current, node => Fails((PyDict)node!))!;
        }
        while (asked < budget && PyJson.Dumps(previous, false, true) != PyJson.Dumps(current, false, true));
        return current;
    }

    private static bool IsTag(PyDict d) => d.Count == 1 && d.Keys.First().StartsWith('$');

    /// <summary>Returns a reduced copy of <paramref name="node"/>; <paramref name="accepts"/> says whether the whole tree, with this node replaced, still diverges.</summary>
    private static object? Reduce(object? node, Func<object?, bool> accepts)
    {
        switch (node)
        {
            case List<object?> list:
                return ReduceList(list, accepts);
            case PyDict d when !IsTag(d):
                return ReduceDict(d, accepts);
            default:
                return node;
        }
    }

    private static List<object?> ReduceList(List<object?> original, Func<object?, bool> accepts)
    {
        var current = original.ToList();
        var chunk = Math.Max(1, current.Count / 2);
        while (chunk >= 1 && current.Count > 0)
        {
            var removed = false;
            for (var start = 0; start < current.Count;)
            {
                var candidate = current.Take(start).Concat(current.Skip(start + chunk)).ToList();
                if (accepts(candidate))
                {
                    current = candidate;
                    removed = true;
                }
                else
                {
                    start += chunk;
                }
            }

            if (!removed)
            {
                chunk /= 2;
            }
        }

        for (var i = 0; i < current.Count; i++)
        {
            var index = i;
            var snapshot = current;
            current[index] = Reduce(snapshot[index], e => accepts(snapshot.Select((x, j) => j == index ? e : x).ToList()));
        }

        return current;
    }

    private static PyDict ReduceDict(PyDict original, Func<object?, bool> accepts)
    {
        var current = original;
        foreach (var key in original.Keys.ToList())
        {
            var candidate = Without(current, key);
            if (accepts(candidate))
            {
                current = candidate;
            }
        }

        foreach (var key in current.Keys.ToList())
        {
            var snapshot = current;
            var reduced = Reduce(snapshot[key], v => accepts(With(snapshot, key, v)));
            current = With(current, key, reduced);
        }

        return current;
    }

    private static PyDict Without(PyDict d, string key) => d.Where(kv => kv.Key != key).Aggregate(new PyDict(), (acc, kv) => acc.Add(kv.Key, kv.Value));

    private static PyDict With(PyDict d, string key, object? value) => d.Aggregate(new PyDict(), (acc, kv) => acc.Add(kv.Key, kv.Key == key ? value : kv.Value));
}
