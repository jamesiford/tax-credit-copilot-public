using System.Globalization;
using System.Numerics;
using System.Text;

namespace TaxCredit.Domain.Numerics;

/// <summary>Mirrors <c>json.JSONDecodeError</c> (a <c>ValueError</c> subclass): the message carries line, column and char offset.</summary>
public sealed class PyJsonDecodeError(string message) : PyException("JSONDecodeError", message);

public static partial class PyJson
{
    private const int MaxIntDigits = 4300;

    /// <summary>
    /// Python <c>json.loads(text)</c> with default hooks: objects become <see cref="PyDict"/> (duplicate keys keep the last
    /// value at the first position), arrays <c>List&lt;object?&gt;</c>, ints <c>long</c> or <see cref="BigInteger"/>,
    /// floats <c>double</c>, and <c>NaN</c>/<c>Infinity</c>/<c>-Infinity</c> are accepted.
    /// </summary>
    /// <param name="text">The document.</param>
    /// <returns>The parsed tree.</returns>
    /// <exception cref="PyJsonDecodeError">For malformed input, with CPython's message and offsets.</exception>
    /// <exception cref="PyValueError">For an integer lexeme beyond 4300 digits, as CPython 3.12 limits it.</exception>
    public static object? Loads(string text)
    {
        if (text.Length > 0 && text[0] == '\uFEFF')
        {
            throw Error("Unexpected UTF-8 BOM (decode using utf-8-sig)", text, 0);
        }

        var r = new Reader(text);
        var idx = r.SkipWs(0);
        object? value;
        try
        {
            value = r.Scan(idx, out idx);
        }
        catch (StopScan stop)
        {
            throw Error("Expecting value", text, stop.Index);
        }

        idx = r.SkipWs(idx);
        return idx != text.Length ? throw Error("Extra data", text, idx) : value;
    }

    private static PyJsonDecodeError Error(string message, string doc, int index)
    {
        var pos = 0;
        var line = 1;
        var lastNl = -1;
        for (var i = 0; i < index; i++)
        {
            if (char.IsHighSurrogate(doc[i]) && i + 1 < doc.Length && char.IsLowSurrogate(doc[i + 1]))
            {
                i++;
            }

            if (doc[i] == '\n')
            {
                line++;
                lastNl = pos;
            }

            pos++;
        }

        var col = lastNl < 0 ? pos + 1 : pos - lastNl;
        return new PyJsonDecodeError($"{message}: line {line} column {col} (char {pos})");
    }

    private sealed class StopScan(int index) : Exception
    {
        public int Index { get; } = index;
    }

    private sealed class Reader(string s)
    {
        public int SkipWs(int i)
        {
            while (i < s.Length && s[i] is ' ' or '\t' or '\n' or '\r')
            {
                i++;
            }

            return i;
        }

        public object? Scan(int idx, out int next)
        {
            if (idx >= s.Length)
            {
                throw new StopScan(idx);
            }

            switch (s[idx])
            {
                case '"':
                    return ScanString(idx + 1, out next);
                case '{':
                    return ScanObject(idx + 1, out next);
                case '[':
                    return ScanArray(idx + 1, out next);
                case 'n' when Match(idx, "null"):
                    next = idx + 4;
                    return null;
                case 't' when Match(idx, "true"):
                    next = idx + 4;
                    return true;
                case 'f' when Match(idx, "false"):
                    next = idx + 5;
                    return false;
                case 'N' when Match(idx, "NaN"):
                    next = idx + 3;
                    return double.NaN;
                case 'I' when Match(idx, "Infinity"):
                    next = idx + 8;
                    return double.PositiveInfinity;
                case '-' when Match(idx, "-Infinity"):
                    next = idx + 9;
                    return double.NegativeInfinity;
                default:
                    return ScanNumber(idx, out next);
            }
        }

        private bool Match(int idx, string literal) =>
            idx + literal.Length <= s.Length && string.CompareOrdinal(s, idx, literal, 0, literal.Length) == 0;

        private bool IsDigit(int i) => i < s.Length && s[i] is >= '0' and <= '9';

        private object ScanNumber(int start, out int next)
        {
            var idx = start;
            if (s[idx] == '-')
            {
                idx++;
                if (idx >= s.Length)
                {
                    throw new StopScan(start);
                }
            }

            if (s[idx] is >= '1' and <= '9')
            {
                idx++;
                while (IsDigit(idx))
                {
                    idx++;
                }
            }
            else if (s[idx] == '0')
            {
                idx++;
            }
            else
            {
                throw new StopScan(start);
            }

            var isFloat = false;
            if (idx + 1 < s.Length && s[idx] == '.' && IsDigit(idx + 1))
            {
                isFloat = true;
                idx += 2;
                while (IsDigit(idx))
                {
                    idx++;
                }
            }

            if (idx + 1 < s.Length && s[idx] is 'e' or 'E')
            {
                var eStart = idx;
                idx++;
                if (idx + 1 < s.Length && s[idx] is '-' or '+')
                {
                    idx++;
                }

                while (IsDigit(idx))
                {
                    idx++;
                }

                if (IsDigit(idx - 1))
                {
                    isFloat = true;
                }
                else
                {
                    idx = eStart;
                }
            }

            next = idx;
            var lexeme = s.Substring(start, idx - start);
            return isFloat ? double.Parse(lexeme, NumberStyles.Float, CultureInfo.InvariantCulture) : ParseInt(lexeme);
        }

        private static object ParseInt(string lexeme)
        {
            var digits = lexeme.Length - (lexeme[0] == '-' ? 1 : 0);
            if (digits > MaxIntDigits)
            {
                throw new PyValueError(
                    $"Exceeds the limit ({MaxIntDigits} digits) for integer string conversion: value has {digits} digits; use sys.set_int_max_str_digits() to increase the limit");
            }

            // One CLR type per magnitude: a value that fits a long is always a long, so equal ints compare equal.
            return long.TryParse(lexeme, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var l)
                ? (object)l
                : BigInteger.Parse(lexeme, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture);
        }

        private string ScanString(int end, out int next)
        {
            var begin = end - 1;
            var sb = new StringBuilder();
            while (true)
            {
                var pos = end;
                while (pos < s.Length && s[pos] != '"' && s[pos] != '\\')
                {
                    if (s[pos] <= '\u001f')
                    {
                        throw Error("Invalid control character at", s, pos);
                    }

                    pos++;
                }

                if (pos >= s.Length)
                {
                    throw Error("Unterminated string starting at", s, begin);
                }

                sb.Append(s, end, pos - end);
                end = pos + 1;
                if (s[pos] == '"')
                {
                    next = end;
                    return sb.ToString();
                }

                if (end >= s.Length)
                {
                    throw Error("Unterminated string starting at", s, begin);
                }

                var esc = s[end];
                if (esc != 'u')
                {
                    end++;
                    switch (esc)
                    {
                        case '"': sb.Append('"'); break;
                        case '\\': sb.Append('\\'); break;
                        case '/': sb.Append('/'); break;
                        case 'b': sb.Append('\b'); break;
                        case 'f': sb.Append('\f'); break;
                        case 'n': sb.Append('\n'); break;
                        case 'r': sb.Append('\r'); break;
                        case 't': sb.Append('\t'); break;
                        default: throw Error("Invalid \\escape", s, end - 2);
                    }

                    continue;
                }

                var c = Hex4(end + 1, end);
                end += 5;
                if (c is >= 0xd800 and <= 0xdbff && end + 6 < s.Length && s[end] == '\\' && s[end + 1] == 'u')
                {
                    var c2 = Hex4(end + 2, end + 1);
                    if (c2 is >= 0xdc00 and <= 0xdfff)
                    {
                        sb.Append((char)c).Append((char)c2);
                        end += 6;
                        continue;
                    }
                }

                sb.Append((char)c);
            }
        }

        private int Hex4(int start, int uPos)
        {
            if (start + 4 >= s.Length)
            {
                throw Error("Invalid \\uXXXX escape", s, uPos);
            }

            var v = 0;
            for (var i = start; i < start + 4; i++)
            {
                var ch = s[i];
                var d = ch is >= '0' and <= '9' ? ch - '0' : ch is >= 'a' and <= 'f' ? ch - 'a' + 10 : ch is >= 'A' and <= 'F' ? ch - 'A' + 10 : -1;
                if (d < 0)
                {
                    throw Error("Invalid \\uXXXX escape", s, uPos);
                }

                v = (v << 4) | d;
            }

            return v;
        }

        private PyDict ScanObject(int idx, out int next)
        {
            var result = new PyDict();
            idx = SkipWs(idx);
            if (idx >= s.Length || s[idx] != '}')
            {
                while (true)
                {
                    if (idx >= s.Length || s[idx] != '"')
                    {
                        throw Error("Expecting property name enclosed in double quotes", s, idx);
                    }

                    var key = ScanString(idx + 1, out idx);
                    idx = SkipWs(idx);
                    if (idx >= s.Length || s[idx] != ':')
                    {
                        throw Error("Expecting ':' delimiter", s, idx);
                    }

                    idx = SkipWs(idx + 1);
                    var value = Scan(idx, out idx);
                    result.Set(key, value);
                    idx = SkipWs(idx);
                    if (idx < s.Length && s[idx] == '}')
                    {
                        break;
                    }

                    if (idx >= s.Length || s[idx] != ',')
                    {
                        throw Error("Expecting ',' delimiter", s, idx);
                    }

                    idx = SkipWs(idx + 1);
                }
            }

            next = idx + 1;
            return result;
        }

        private List<object?> ScanArray(int idx, out int next)
        {
            var result = new List<object?>();
            idx = SkipWs(idx);
            if (idx >= s.Length || s[idx] != ']')
            {
                while (true)
                {
                    result.Add(Scan(idx, out idx));
                    idx = SkipWs(idx);
                    if (idx < s.Length && s[idx] == ']')
                    {
                        break;
                    }

                    if (idx >= s.Length || s[idx] != ',')
                    {
                        throw Error("Expecting ',' delimiter", s, idx);
                    }

                    idx = SkipWs(idx + 1);
                }
            }

            next = idx + 1;
            return result;
        }
    }
}
