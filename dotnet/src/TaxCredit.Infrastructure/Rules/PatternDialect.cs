using System.Text;
using System.Text.Json.Nodes;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Infrastructure.Rules;

/// <summary>
/// Python <c>re</c> to .NET: the one place the two regular-expression dialects disagree for the patterns the rule-pack schema uses. The schema is
/// written for Python (it is the shared source of truth), so it is translated on load and never edited.
/// </summary>
/// <remarks>
/// <c>\s</c> in a Python <c>str</c> pattern matches whatever <c>str.isspace()</c> accepts; .NET's ECMAScript mode (which the schema library uses) matches only
/// ASCII white space, so <c>"\u00a0"</c> would satisfy <c>\S</c> in .NET and not in Python. <c>$</c> and the character classes the schema uses agree
/// (both let <c>$</c> match before a final newline), so they are left alone. A <c>\S</c> inside a character class is not translated (the schema has none).
/// </remarks>
internal static class PatternDialect
{
    private static readonly Lazy<string> Spaces = new(BuildSpaces);

    /// <summary>Rewrites every string <c>pattern</c> in the schema document in place.</summary>
    internal static void Translate(JsonNode? node)
    {
        switch (node)
        {
            case JsonObject obj:
                foreach (var key in obj.Select(kv => kv.Key).ToList())
                {
                    if (key == "pattern" && obj[key] is JsonValue value && value.TryGetValue<string>(out var pattern))
                    {
                        obj[key] = Rewrite(pattern);
                    }
                    else
                    {
                        Translate(obj[key]);
                    }
                }

                break;
            case JsonArray array:
                foreach (var item in array)
                {
                    Translate(item);
                }

                break;
        }
    }

    internal static string Rewrite(string pattern)
    {
        var sb = new StringBuilder();
        var inClass = false;
        for (var i = 0; i < pattern.Length; i++)
        {
            var c = pattern[i];
            if (c == '\\' && i + 1 < pattern.Length)
            {
                var next = pattern[++i];
                switch (next)
                {
                    case 's':
                        sb.Append(inClass ? Spaces.Value : "[" + Spaces.Value + "]");
                        break;
                    case 'S' when !inClass:
                        sb.Append("[^").Append(Spaces.Value).Append(']');
                        break;
                    default:
                        sb.Append(c).Append(next);
                        break;
                }

                continue;
            }

            inClass = c == '[' ? true : c == ']' ? false : inClass;
            sb.Append(c);
        }

        return sb.ToString();
    }

    // The BMP is enough: every Unicode white-space code point (Python's table) is below U+3100.
    private static string BuildSpaces()
    {
        var sb = new StringBuilder();
        var start = -1;
        for (var cp = 0; cp <= 0x3100; cp++)
        {
            var space = PyStr.IsSpaceCodePoint(cp);
            if (space && start < 0)
            {
                start = cp;
            }

            if (!space && start >= 0)
            {
                sb.Append(Escape(start));
                if (cp - 1 > start)
                {
                    sb.Append('-').Append(Escape(cp - 1));
                }

                start = -1;
            }
        }

        return sb.ToString();
    }

    private static string Escape(int cp) => $"\\u{cp:x4}";
}
