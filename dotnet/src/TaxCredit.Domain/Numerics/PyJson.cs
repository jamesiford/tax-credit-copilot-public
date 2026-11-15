using System.Globalization;
using System.Numerics;
using System.Security.Cryptography;
using System.Text;

namespace TaxCredit.Domain.Numerics;

/// <summary>
/// Python's <c>json</c> module: <c>dumps</c> with <c>ensure_ascii</c> and <c>loads</c> with CPython's C scanner semantics.
/// </summary>
/// <remarks>
/// Why a port: a rule pack's <c>35</c> is an <c>int</c> and <c>35.0</c> a <c>float</c>, and the two take different
/// paths through <c>Decimal(str(x))</c>, so the reader decides the type from the lexeme. <c>System.Text.Json</c>
/// reads every number as a double-capable token and writes its own float layout; the calculation trail's evidence
/// hash is SHA-256 over these exact bytes. Sources: CPython <c>Lib/json/encoder.py</c>, <c>Modules/_json.c</c>.
/// Writer limit: ints beyond 4300 digits are not subject to Python's <c>str()</c> conversion limit here.
/// </remarks>
public static partial class PyJson
{
    /// <summary>Serialises a tree canonically: <c>sort_keys=True, separators=(',', ':')</c>, ASCII only.</summary>
    /// <param name="value">The tree.</param>
    /// <returns>The JSON text.</returns>
    public static string Dumps(object? value) => Dumps(value, sortKeys: true, compact: true);

    /// <summary>Serialises a tree like <c>json.dumps</c> with <c>ensure_ascii=True</c>.</summary>
    /// <param name="value">The tree.</param>
    /// <param name="sortKeys">Python <c>sort_keys</c>.</param>
    /// <param name="compact"><c>true</c> for separators <c>(',', ':')</c>; <c>false</c> for the default <c>(', ', ': ')</c>.</param>
    /// <returns>The JSON text.</returns>
    public static string Dumps(object? value, bool sortKeys, bool compact)
    {
        var sb = new StringBuilder();
        Write(sb, value, sortKeys, compact ? "," : ", ", compact ? ":" : ": ");
        return sb.ToString();
    }

    /// <summary>SHA-256 of the canonical JSON as <c>sha256:&lt;hex&gt;</c>, as the trail recorder stamps it.</summary>
    /// <param name="value">The tree.</param>
    /// <returns>The fingerprint.</returns>
    public static string EvidenceHash(object? value) =>
        "sha256:" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Dumps(value)))).ToLowerInvariant();

    private static void Write(StringBuilder sb, object? value, bool sortKeys, string itemSep, string keySep)
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
            case BigInteger big:
                sb.Append(big.ToString(CultureInfo.InvariantCulture));
                break;
            case double d:
                sb.Append(double.IsNaN(d) ? "NaN" : double.IsPositiveInfinity(d) ? "Infinity" : double.IsNegativeInfinity(d) ? "-Infinity" : PyFloat.Repr(d));
                break;
            case string s:
                WriteString(sb, s);
                break;
            case PyDict dict:
                WriteObject(sb, dict, sortKeys, itemSep, keySep);
                break;
            case IReadOnlyList<object?> list:
                sb.Append('[');
                for (var k = 0; k < list.Count; k++)
                {
                    if (k > 0)
                    {
                        sb.Append(itemSep);
                    }

                    Write(sb, list[k], sortKeys, itemSep, keySep);
                }

                sb.Append(']');
                break;
            default:
                throw new PyUnsupportedException("Unsupported JSON value type " + value.GetType().Name);
        }
    }

    private static void WriteObject(StringBuilder sb, PyDict dict, bool sortKeys, string itemSep, string keySep)
    {
        sb.Append('{');
        var first = true;
        IEnumerable<KeyValuePair<string, object?>> items = sortKeys ? dict.OrderBy(k => k.Key, PyStr.Comparer) : dict;
        foreach (var kv in items)
        {
            if (!first)
            {
                sb.Append(itemSep);
            }

            first = false;
            WriteString(sb, kv.Key);
            sb.Append(keySep);
            Write(sb, kv.Value, sortKeys, itemSep, keySep);
        }

        sb.Append('}');
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
