using System.Globalization;
using System.Numerics;

namespace TaxCredit.Application.Ports.Persistence;

/// <summary>Refuses unbounded client identifiers before SQL binding; the HTTP adapter maps this refusal to 422.</summary>
public static class ClientIdentity
{
    /// <summary>Accepts only a positive, signed-64-bit tenant identifier.</summary>
    public static long Parse(string text)
    {
        if (!BigInteger.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out var value) || value <= 0 || value > long.MaxValue)
        {
            throw new ArgumentOutOfRangeException(nameof(text), "Client identifier must be a positive signed-64-bit integer.");
        }

        return (long)value;
    }
}
