using System.Globalization;
using System.Text.Json;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Parity.Tests;

/// <summary>JSON to comparison-tree conversion: ints stay <c>long</c>, floats <c>double</c> (decided by the token text), objects keep key order.</summary>
internal static class JsonTree
{
    public static object? Read(JsonElement e)
    {
        switch (e.ValueKind)
        {
            case JsonValueKind.Null:
                return null;
            case JsonValueKind.True:
                return true;
            case JsonValueKind.False:
                return false;
            case JsonValueKind.String:
                return e.GetString();
            case JsonValueKind.Number:
                var raw = e.GetRawText();
                return raw.AsSpan().IndexOfAny('.', 'e', 'E') >= 0
                    ? (object)double.Parse(raw, NumberStyles.Float, CultureInfo.InvariantCulture)
                    : (object)long.Parse(raw, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture);
            case JsonValueKind.Array:
                return e.EnumerateArray().Select(Read).ToList();
            case JsonValueKind.Object:
                var d = new PyDict();
                foreach (var p in e.EnumerateObject())
                {
                    d.Add(p.Name, Read(p.Value));
                }

                return d;
            default:
                throw new InvalidOperationException("Unexpected JSON " + e.ValueKind);
        }
    }

    /// <summary>First difference between two trees (strict: types, key order, double bits), or null when identical.</summary>
    public static string? Diff(object? expected, object? actual, string path = "$")
    {
        switch (expected)
        {
            case null:
                return actual is null ? null : $"{path}: expected null got {Describe(actual)}";
            case bool b:
                return actual is bool ab && ab == b ? null : $"{path}: expected {b} got {Describe(actual)}";
            case long l:
                return actual is long al && al == l ? null : $"{path}: expected int {l} got {Describe(actual)}";
            case double d:
                return actual is double ad && PyFloat.SameBits(ad, d) ? null : $"{path}: expected float {PyFloat.Repr(d)} got {Describe(actual)}";
            case string s:
                return actual is string a && string.Equals(a, s, StringComparison.Ordinal) ? null : $"{path}: expected \"{s}\" got {Describe(actual)}";
            case PyDict ed:
                if (actual is not PyDict adict)
                {
                    return $"{path}: expected object got {Describe(actual)}";
                }

                var ek = ed.ToList();
                var ak = adict.ToList();
                if (!ek.Select(k => k.Key).SequenceEqual(ak.Select(k => k.Key)))
                {
                    return $"{path}: keys [{string.Join(',', ak.Select(k => k.Key))}] expected [{string.Join(',', ek.Select(k => k.Key))}]";
                }

                for (var i = 0; i < ek.Count; i++)
                {
                    var r = Diff(ek[i].Value, ak[i].Value, path + "." + ek[i].Key);
                    if (r is not null)
                    {
                        return r;
                    }
                }

                return null;
            case IReadOnlyList<object?> el:
                if (actual is not IReadOnlyList<object?> al2)
                {
                    return $"{path}: expected list got {Describe(actual)}";
                }

                if (el.Count != al2.Count)
                {
                    return $"{path}: length {al2.Count} expected {el.Count}";
                }

                for (var i = 0; i < el.Count; i++)
                {
                    var r = Diff(el[i], al2[i], $"{path}[{i}]");
                    if (r is not null)
                    {
                        return r;
                    }
                }

                return null;
            default:
                return $"{path}: unsupported expected type {expected.GetType().Name}";
        }
    }

    private static string Describe(object? v) => v switch
    {
        null => "null",
        double d => "float " + PyFloat.Repr(d),
        long l => "int " + l.ToString(CultureInfo.InvariantCulture),
        string s => "\"" + s + "\"",
        _ => v.GetType().Name,
    };

    /// <summary>SHA-256 over the little-endian bits of every double in traversal order (the exporter's <c>float_digest</c>).</summary>
    public static string FloatDigest(object? tree)
    {
        using var sha = System.Security.Cryptography.IncrementalHash.CreateHash(System.Security.Cryptography.HashAlgorithmName.SHA256);
        Walk(tree, sha);
        return Convert.ToHexString(sha.GetHashAndReset()).ToLowerInvariant();
    }

    private static void Walk(object? x, System.Security.Cryptography.IncrementalHash sha)
    {
        switch (x)
        {
            case double d:
                Span<byte> buf = stackalloc byte[8];
                System.Buffers.Binary.BinaryPrimitives.WriteInt64LittleEndian(buf, PyFloat.ToBits(d));
                sha.AppendData(buf);
                break;
            case PyDict dict:
                foreach (var kv in dict)
                {
                    Walk(kv.Value, sha);
                }

                break;
            case IReadOnlyList<object?> list:
                foreach (var v in list)
                {
                    Walk(v, sha);
                }

                break;
        }
    }
}
