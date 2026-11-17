using System.Text.RegularExpressions;

namespace TaxCredit.Infrastructure.Auth;

internal static partial class Base64Url
{
    [GeneratedRegex("^[A-Za-z0-9_-]+={0,2}$", RegexOptions.CultureInvariant)]
    private static partial Regex Alphabet();

    internal static byte[] Decode(string value)
    {
        if (!Alphabet().IsMatch(value))
        {
            throw new FormatException("Invalid base64url.");
        }

        var raw = value.TrimEnd('=').Replace('-', '+').Replace('_', '/');
        return Convert.FromBase64String(raw.PadRight((raw.Length + 3) / 4 * 4, '='));
    }
}
