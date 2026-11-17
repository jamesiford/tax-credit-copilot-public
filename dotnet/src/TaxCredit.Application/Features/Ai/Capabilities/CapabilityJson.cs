using System.Globalization;
using System.Text.Json.Nodes;

namespace TaxCredit.Application.Features.Ai.Capabilities;

internal static class CapabilityJson
{
    // JSON-Schema accepts 42.0 as an integer; readers must not require its lexical form to be 42.
    internal static long Integer(JsonNode node) =>
        checked((long)decimal.Parse(node.ToJsonString(), NumberStyles.Float, CultureInfo.InvariantCulture));

    internal static int SmallInteger(JsonNode node) => checked((int)Integer(node));

    internal static object Number(JsonNode node)
    {
        var text = node.ToJsonString();
        if (long.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out var integer))
        {
            return integer;
        }
        if (decimal.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var exact))
        {
            return exact;
        }
        throw CapabilityException.Invalid("Filter number is outside the warehouse decimal range.");
    }
}
