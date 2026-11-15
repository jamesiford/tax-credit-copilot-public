using System.Collections;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>
/// An insertion-ordered string-keyed mapping: the shape of a Python <c>dict</c> in the calculation trail and in
/// the golden comparison trees. Values are <c>null</c>, <c>bool</c>, <c>long</c>, <c>double</c>, <c>string</c>,
/// <c>IReadOnlyList&lt;object?&gt;</c> or another <see cref="PyDict"/>.
/// </summary>
public sealed class PyDict : IEnumerable<KeyValuePair<string, object?>>
{
    private readonly List<KeyValuePair<string, object?>> _items = [];

    /// <summary>The number of entries.</summary>
    public int Count => _items.Count;

    /// <summary>Appends an entry (Python dict literal order is preserved; keys are unique by construction).</summary>
    /// <param name="key">The key.</param>
    /// <param name="value">The value.</param>
    /// <returns>This dictionary, for chaining.</returns>
    public PyDict Add(string key, object? value)
    {
        _items.Add(new KeyValuePair<string, object?>(key, value));
        return this;
    }

    /// <inheritdoc />
    public IEnumerator<KeyValuePair<string, object?>> GetEnumerator() => _items.GetEnumerator();

    /// <inheritdoc />
    IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
}

/// <summary>
/// Python <c>json.dumps(value, sort_keys=True, separators=(',', ':'))</c> over <see cref="PyDict"/> trees.
/// </summary>
/// <remarks>
/// Why a port: the calculation trail's evidence hash is SHA-256 over these exact bytes, so every character matters.
/// <c>System.Text.Json</c> escapes differently and writes doubles with its own rules (<c>1E+16</c>). Python's default
/// <c>ensure_ascii</c> escapes everything outside 0x20-0x7E, including DEL, as lowercase <c>\uXXXX</c> per UTF-16
/// unit, and formats floats with <c>repr</c>. Source: CPython <c>Lib/json/encoder.py</c>.
/// </remarks>
public static class PyJson
{
    /// <summary>Serialises a tree canonically (sorted keys, no whitespace, ASCII only).</summary>
    /// <param name="value">The tree.</param>
    /// <returns>The JSON text.</returns>
    public static string Dumps(object? value)
    {
        var sb = new StringBuilder();
        Write(sb, value);
        return sb.ToString();
    }

    /// <summary>SHA-256 of the canonical JSON as <c>sha256:&lt;hex&gt;</c>, as the trail recorder stamps it.</summary>
    /// <param name="value">The tree.</param>
    /// <returns>The fingerprint.</returns>
    public static string EvidenceHash(object? value) =>
        "sha256:" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Dumps(value)))).ToLowerInvariant();

    private static void Write(StringBuilder sb, object? value)
    {
        switch (value)
        {
            case null:
                sb.Append("null");
                break;
            case bool b:
                sb.Append(b ? "true" : "false");
                break;
            case long l:
                sb.Append(l.ToString(CultureInfo.InvariantCulture));
                break;
            case int i:
                sb.Append(i.ToString(CultureInfo.InvariantCulture));
                break;
            case double d:
                sb.Append(double.IsNaN(d) ? "NaN" : double.IsPositiveInfinity(d) ? "Infinity" : double.IsNegativeInfinity(d) ? "-Infinity" : PyFloat.Repr(d));
                break;
            case string s:
                WriteString(sb, s);
                break;
            case PyDict dict:
                sb.Append('{');
                var first = true;
                foreach (var kv in dict.OrderBy(k => k.Key, PyStr.Comparer))
                {
                    if (!first)
                    {
                        sb.Append(',');
                    }

                    first = false;
                    WriteString(sb, kv.Key);
                    sb.Append(':');
                    Write(sb, kv.Value);
                }

                sb.Append('}');
                break;
            case IReadOnlyList<object?> list:
                sb.Append('[');
                for (var k = 0; k < list.Count; k++)
                {
                    if (k > 0)
                    {
                        sb.Append(',');
                    }

                    Write(sb, list[k]);
                }

                sb.Append(']');
                break;
            default:
                throw new PyUnsupportedException("Unsupported JSON value type " + value.GetType().Name);
        }
    }

    private static void WriteString(StringBuilder sb, string s)
    {
        sb.Append('"');
        foreach (var c in s)
        {
            switch (c)
            {
                case '\\':
                    sb.Append("\\\\");
                    break;
                case '"':
                    sb.Append("\\\"");
                    break;
                case '\n':
                    sb.Append("\\n");
                    break;
                case '\r':
                    sb.Append("\\r");
                    break;
                case '\t':
                    sb.Append("\\t");
                    break;
                case '\b':
                    sb.Append("\\b");
                    break;
                case '\f':
                    sb.Append("\\f");
                    break;
                default:
                    if (c is >= ' ' and <= '~')
                    {
                        sb.Append(c);
                    }
                    else
                    {
                        sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                    }

                    break;
            }
        }

        sb.Append('"');
    }
}
