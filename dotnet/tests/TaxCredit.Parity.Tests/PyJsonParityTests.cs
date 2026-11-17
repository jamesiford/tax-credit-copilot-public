using System.Text.Json;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>Gate DS2: <c>PyJson.Loads</c>/<c>Dumps</c> against <c>json.loads</c>/<c>json.dumps</c> on CPython 3.12.</summary>
public sealed class PyJsonParityTests
{
    private const string File = "json.jsonl.gz";

    [Fact]
    public void Loads_and_dumps_match_python_for_every_vector()
    {
        var errors = 0;
        var accepted = 0;
        PrimitiveParityTests.Run("json", v =>
        {
            var input = v.GetProperty("in").GetString()!;
            if (v.TryGetProperty("err", out var errType))
            {
                errors++;
                try
                {
                    var tree = PyJson.Loads(input);
                    return $"Python raised {errType.GetString()} but C# parsed {PyJson.Dumps(tree)}";
                }
                catch (PyException e)
                {
                    var type = errType.GetString();
                    var typeOk = e.PythonType == type || (type == "JSONDecodeError" && e is PyJsonDecodeError);
                    return typeOk && e.Message == v.GetProperty("msg").GetString()
                        ? null
                        : $"error: got {e.PythonType} '{e.Message}' expected {type} '{v.GetProperty("msg").GetString()}'";
                }
            }

            accepted++;
            object? parsed;
            try
            {
                parsed = PyJson.Loads(input);
            }
            catch (PyException e)
            {
                return $"C# raised {e.PythonType} '{e.Message}' but Python parsed";
            }

            var plain = PyJson.Dumps(parsed, sortKeys: false, compact: false);
            var sorted = PyJson.Dumps(parsed);
            return plain != v.GetProperty("plain").GetString() ? "plain dumps differs: " + Head(plain)
                : sorted != v.GetProperty("sorted").GetString() ? "sorted dumps differs: " + Head(sorted)
                : null;
        }, File);
        Assert.True(errors > 500 && accepted > 500, $"corpus too thin: {errors} errors, {accepted} accepted");
    }

    [Fact]
    public void A_perturbed_reader_is_detected_by_the_comparison()
    {
        // Mutation self-test: the same comparison, fed a reader that reads every integer lexeme as a float, must disagree.
        var diverged = 0;
        foreach (var v in GoldenFiles.Read(File, "json").Take(400))
        {
            if (v.TryGetProperty("err", out _))
            {
                continue;
            }

            var input = v.GetProperty("in").GetString()!;
            var perturbed = PyJson.Dumps(IntsAsFloats(PyJson.Loads(input)), false, false);
            if (perturbed != v.GetProperty("plain").GetString())
            {
                diverged++;
            }
        }

        Assert.True(diverged > 10, "the int/float comparison cannot fail");
    }

    private static object? IntsAsFloats(object? v) => v switch
    {
        long l => (double)l,
        List<object?> list => list.Select(IntsAsFloats).ToList(),
        PyDict d => d.Aggregate(new PyDict(), (acc, kv) => acc.Set(kv.Key, IntsAsFloats(kv.Value))),
        _ => v,
    };

    private static string Head(string s) => s.Length <= 160 ? s : s[..160] + "…";

    [Fact]
    public void Duplicate_keys_keep_the_last_value_at_the_first_position()
    {
        var d = (PyDict)PyJson.Loads("{\"a\":1,\"b\":2,\"a\":3}")!;
        Assert.Equal(["a", "b"], d.Keys);
        Assert.Equal((object)3L, d["a"]);
    }

    [Fact]
    public void Integer_and_float_lexemes_keep_their_type()
    {
        var l = (List<object?>)PyJson.Loads("[35, 35.0, 1e2, 9223372036854775808]")!;
        Assert.IsType<long>(l[0]);
        Assert.IsType<double>(l[1]);
        Assert.IsType<double>(l[2]);
        Assert.IsType<System.Numerics.BigInteger>(l[3]);
    }
}
