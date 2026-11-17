using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>One generated call: the function name and its arguments in the exporters' tagged encoding (see <c>parity/fuzz_ops.py</c>).</summary>
/// <param name="Id">A stable identifier (family, seed and index) used in logs and regression file names.</param>
/// <param name="Fn">The function the oracle and the port both run.</param>
/// <param name="Args">The argument tree; ints, floats, strings, bools, <c>null</c>, lists and <see cref="PyDict"/> with the <c>$date</c>, <c>$dt</c> and <c>$dec</c> tags.</param>
internal sealed record FamilyCase(string Id, string Fn, PyDict Args)
{
    /// <summary>The request line for <paramref name="family"/>: Python reads it with <c>json.loads</c>, so NaN and the infinities are legal.</summary>
    public string ToRequest(string family) => ToRequest(family, Args);

    /// <summary>The request line with other arguments (the minimiser's candidates).</summary>
    public string ToRequest(string family, PyDict args) => PyJson.Dumps(
        new PyDict().Add("id", Id).Add("op", "call").Add("family", family).Add("fn", Fn).Add("args", args), sortKeys: false, compact: true, ensureAscii: true);
}

/// <summary>A family of ported functions with a seeded scenario generator and the comparison of the port against the oracle's answer.</summary>
internal abstract class FuzzFamily
{
    /// <summary>The family name sent to the oracle (one of <c>fuzz_ops.FAMILIES</c>).</summary>
    public abstract string Name { get; }

    /// <summary>Mixes into each batch's seed so two families never draw the same stream (FNV-1a of the name: <c>string.GetHashCode</c> is randomised per process).</summary>
    public ulong Salt => Name.Aggregate(14695981039346656037UL, (h, c) => (h ^ c) * 1099511628211UL);

    /// <summary>The functions that must each appear in a run (coverage assertion).</summary>
    public abstract IReadOnlyList<string> Functions { get; }

    /// <summary>Draws one scenario.</summary>
    public abstract FamilyCase Generate(Rng rng, string id);

    /// <summary>A checker bound to a fresh port instance (some harnesses keep per-call state, so one per batch and thread).</summary>
    public abstract Func<PyDict, string?> CreateChecker();

    /// <summary>Compares the oracle's answer with the port's: <c>null</c> when identical in type, key order, bits and exception text.</summary>
    protected static string? Replay(PyDict call, Func<PyDict, object?> invoke)
    {
        try
        {
            return ClaimGolden.Replay(call, invoke, out _);
        }
        catch (Exception e) when (e is not PyException)
        {
            // A port that dies outside Python's exception types, or asks for an input it cannot model, is a divergence too.
            return $"the port left the recorded path: {e.GetType().Name}: {e.Message}";
        }
    }
}
