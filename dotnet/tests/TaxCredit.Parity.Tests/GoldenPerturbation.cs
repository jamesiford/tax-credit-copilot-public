using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// The in-process half of a mutation self-test for the golden replays: the same <see cref="ClaimGolden.Compare"/>, fed outputs with one
/// deliberate defect (an ulp, an int where Python has a float, a flipped bool, a reversed list, reordered keys), must disagree.
/// </summary>
internal static class GoldenPerturbation
{
    private static readonly (string Name, Func<object?, object?> Apply)[] All =
    [
        ("ulp", t => Map(t, v => v is double d && double.IsFinite(d) && d != 0 ? BitConverter.Int64BitsToDouble(BitConverter.DoubleToInt64Bits(d) + 1) : v)),
        ("int-as-float", t => Map(t, v => v is long l ? (double)l : v)),
        ("float-as-int", t => Map(t, v => v is double d && double.IsFinite(d) && Math.Floor(d) == d && Math.Abs(d) < 1e15 ? (long)d : v)),
        ("bool-flip", t => Map(t, v => v is bool b ? !b : v)),
        ("tie-order", t => Map(t, v => v is List<object?> { Count: > 1 } list ? list.AsEnumerable().Reverse().ToList() : v)),
        ("key-order", t => Map(t, v => v is PyDict { Count: > 1 } d ? Reorder(d) : v)),
    ];

    /// <summary>Asserts every perturbation named in <paramref name="required"/> is caught more than five times over the first <paramref name="take"/> successful calls.</summary>
    public static void AssertDetected(string file, Func<PyDict, object?> invoke, string[] required, int take = 6000)
    {
        var detected = All.ToDictionary(p => p.Name, _ => 0);
        foreach (var call in ClaimGolden.Calls(file).Where(c => !c.ContainsKey("err")).Take(take))
        {
            var actual = invoke(call);
            foreach (var (name, apply) in All)
            {
                var perturbed = apply(Map(actual, v => v));
                if (ClaimGolden.Compare(call["out"], perturbed, "$") is not null)
                {
                    detected[name]++;
                }
            }
        }

        foreach (var name in required)
        {
            Assert.True(detected[name] > 5, $"the comparison cannot fail for '{name}' ({detected[name]} detections)");
        }
    }

    private static PyDict Reorder(PyDict d)
    {
        var reversed = new PyDict();
        foreach (var kv in d.Reverse())
        {
            reversed.Add(kv.Key, kv.Value);
        }

        return reversed;
    }

    private static object? Map(object? t, Func<object?, object?> f) => t switch
    {
        PyDict d => f(d.Aggregate(new PyDict(), (acc, kv) => acc.Add(kv.Key, Map(kv.Value, f)))),
        List<object?> l => f(l.Select(x => Map(x, f)).ToList()),
        _ => f(t),
    };
}
