using System.Globalization;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Api.Wire;

/// <summary>Standard JSON for transport; the domain's canonical writer remains exclusively for evidence hashes.</summary>
public static class WireJson
{
    /// <summary>Configures field names, explicit nulls, literal UTF-8 and decimal strings.</summary>
    public static void Configure(JsonSerializerOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        options.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower;
        options.DefaultIgnoreCondition = JsonIgnoreCondition.Never;
        options.Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping;
        options.Converters.Add(new MoneyConverter());
        options.Converters.Add(new EngineMoneyConverter());
    }

    private sealed class MoneyConverter : JsonConverter<decimal>
    {
        public override decimal Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
            reader.TokenType == JsonTokenType.String
                ? decimal.Parse(reader.GetString()!, CultureInfo.InvariantCulture)
                : reader.GetDecimal();

        public override void Write(Utf8JsonWriter writer, decimal value, JsonSerializerOptions options) =>
            writer.WriteStringValue(value.ToString(CultureInfo.InvariantCulture));
    }

    private sealed class EngineMoneyConverter : JsonConverter<PyDecimal>
    {
        public override PyDecimal Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
            PyDecimal.Parse(reader.TokenType == JsonTokenType.String ? reader.GetString()! : reader.GetDecimal().ToString(CultureInfo.InvariantCulture));

        public override void Write(Utf8JsonWriter writer, PyDecimal value, JsonSerializerOptions options) =>
            writer.WriteStringValue(value.ToString());
    }
}
