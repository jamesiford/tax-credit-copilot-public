using System.Text.Json;
using TaxCredit.Application.Features.ReadsCalc;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Api.Tests.ReadsCalc;

public sealed class ReadTransportTests
{
    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    public async Task Nonpositive_clients_are_unavailable_reads_not_integer_binding_errors(int client)
    {
        await using var host = await TestHost.Start();
        foreach (var route in new[] { "/api/progress/2025", "/api/forecast/2025", "/api/ingestion/2025" })
        {
            using var response = await host.Client.GetAsync($"{route}?account_id={client}&state=GA");
            Assert.Equal(404, (int)response.StatusCode);
            using var body = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
            Assert.Equal(JsonValueKind.String, body.RootElement.GetProperty("detail").ValueKind);
        }
    }

    [Fact]
    public void Engine_maps_and_typed_count_maps_serialize_as_objects_without_losing_null_or_money_scale()
    {
        var source = new PyDict().Add("counts", new Dictionary<string, int>(StringComparer.Ordinal) { ["2025"] = 12 })
            .Add("absent", null).Add("money", PyDecimal.Parse("12.3400")).Add("figure", PyNumber.OfFloat(1.5));
        using var rendered = JsonDocument.Parse(JsonSerializer.Serialize(ReadValues.Transport(source)));
        Assert.Equal(12, rendered.RootElement.GetProperty("counts").GetProperty("2025").GetInt32());
        Assert.Equal(JsonValueKind.Null, rendered.RootElement.GetProperty("absent").ValueKind);
        Assert.Equal(1.5, rendered.RootElement.GetProperty("figure").GetDouble());
        Assert.Equal("12.3400", ReadValues.PythonString(source["money"]));
    }

    [Theory]
    [InlineData("NaN")]
    [InlineData("Infinity")]
    [InlineData("-Infinity")]
    public void Nonfinite_inputs_are_deliberate_client_refusals(string value)
    {
        var args = new ReadArguments(new Dictionary<string, string?>(StringComparer.Ordinal) { ["magnitude"] = value });
        var error = Assert.Throws<ReadRefusalException>(() => args.Number("magnitude"));
        Assert.Equal(422, error.StatusCode);
    }
}
