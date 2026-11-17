using System.Globalization;
using System.Text;

namespace TaxCredit.Domain.Numerics;

/// <summary>Mirrors Python <c>UnicodeEncodeError</c> as <c>str.encode("utf-8")</c> raises it for a lone surrogate.</summary>
/// <param name="message">Python's message.</param>
public sealed class PyUnicodeEncodeError(string message) : PyException("UnicodeEncodeError", message);

/// <summary>Python <c>str.encode("utf-8")</c> (strict): a lone surrogate is an error, not a replacement character.</summary>
public static class PyUtf8
{
    /// <summary>Encodes <paramref name="text"/> as UTF-8, refusing lone surrogates the way CPython does.</summary>
    /// <remarks>
    /// Why a port: <c>Encoding.UTF8.GetBytes</c> silently substitutes U+FFFD, so a document with a stray <c>\ud800</c> would hash instead of
    /// failing. The message counts positions in code points (a surrogate pair is one) and reports the first run of lone surrogates.
    /// </remarks>
    /// <param name="text">The string.</param>
    /// <returns>The UTF-8 bytes.</returns>
    /// <exception cref="PyUnicodeEncodeError">When the string holds a lone surrogate.</exception>
    public static byte[] Encode(string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        var position = 0;
        var runStart = -1;
        var runLength = 0;
        var first = '\0';
        for (var i = 0; i < text.Length; i++)
        {
            var c = text[i];
            if (char.IsHighSurrogate(c) && i + 1 < text.Length && char.IsLowSurrogate(text[i + 1]))
            {
                i++;
            }
            else if (char.IsSurrogate(c))
            {
                if (runStart < 0)
                {
                    (runStart, first) = (position, c);
                }

                runLength++;
                position++;
                continue;
            }

            if (runStart >= 0)
            {
                break;
            }

            position++;
        }

        return runStart < 0 ? new UTF8Encoding(false).GetBytes(text) : throw new PyUnicodeEncodeError(Message(runStart, runLength, first));
    }

    private static string Message(int start, int length, char first) => length == 1
        ? $"'utf-8' codec can't encode character '\\u{(int)first:x4}' in position {start.ToString(CultureInfo.InvariantCulture)}: surrogates not allowed"
        : $"'utf-8' codec can't encode characters in position {start.ToString(CultureInfo.InvariantCulture)}-{(start + length - 1).ToString(CultureInfo.InvariantCulture)}: surrogates not allowed";
}
