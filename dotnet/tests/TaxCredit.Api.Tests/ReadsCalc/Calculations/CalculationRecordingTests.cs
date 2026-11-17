using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Api.Tests.Contract;
using TaxCredit.Application.Features.ReadsCalc.Calculations;

namespace TaxCredit.Api.Tests.ReadsCalc.Calculations;

[Trait("Category", "heavy")]
public sealed class CalculationRecordingTests
{
    [Theory]
    [InlineData("forecast", "ok.api-forecast-tax-year")]
    [InlineData("monthly_alerts", "ok.api-alerts-monthly-tax-year")]
    [InlineData("triggers", "ok.api-triggers")]
    [InlineData("performance", "ok.api-performance-tax-year")]
    [InlineData("onezero", "ok.api-onezero-tax-year")]
    [InlineData("onezero_employee", "ok.api-onezero-tax-year-employee-employee-id")]
    [InlineData("designations", "ok.api-designations-state")]
    [InlineData("reconcile", "ok.api-reconcile-tax-year")]
    [InlineData("qc", "ok.api-qc-tax-year")]
    [InlineData("retroactive", "ok.api-onezero-retroactive-scan")]
    [InlineData("simulate_portfolio", "ok.api-simulate-portfolio-tax-year")]
    public async Task Source_views_match_recorded_public_payroll(string operation, string id)
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        using var scope = host.App.Services.CreateScope();
        var service = scope.ServiceProvider.GetRequiredService<ReadsCalculationViews>();
        var record = Recording("p1_reads", id);
        var parameters = Parameters(record);
        parameters["tax_year"] = "2025";
        parameters["state"] = operation is "triggers" or "reconcile" or "retroactive" or "simulate_portfolio" ? null : "GA";
        if (operation == "simulate_portfolio")
        {
            parameters["state"] = "GA";
        }
        parameters["employee_id"] = "E00048";
        var actual = JsonSerializer.SerializeToElement(service.Execute(operation, parameters));
        Equivalent(record.GetProperty("response").GetProperty("body").GetProperty("value"), actual);
    }

    [Theory]
    [InlineData("simulate_onezero", "ok.post-api-simulate-onezero")]
    [InlineData("simulate_unit", "ok.post-api-simulate-unit")]
    [InlineData("simulate_employee", "ok.post-api-simulate-employee")]
    public async Task Simulations_match_recorded_seeded_run(string operation, string id)
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host);
        using var scope = host.App.Services.CreateScope();
        var service = scope.ServiceProvider.GetRequiredService<ReadsCalculationViews>();
        var record = Recording("p1_writes", id);
        var actual = JsonSerializer.SerializeToElement(service.Execute(operation, new Dictionary<string, string?>(),
            record.GetProperty("request").GetProperty("body").GetProperty("value")));
        Equivalent(record.GetProperty("response").GetProperty("body").GetProperty("value"), actual);
    }

    [Theory]
    [InlineData(2001)]
    [InlineData(2002)]
    [InlineData(2003)]
    [InlineData(2004)]
    public async Task Forecast_preserves_staged_source_values(int client)
    {
        await using var host = await TestHost.Start();
        await RuntimeRequests.Reset(host, "P2");
        using var scope = host.App.Services.CreateScope();
        var service = scope.ServiceProvider.GetRequiredService<ReadsCalculationViews>();
        var record = Recording("p2_reads_writes", $"client{client}.forecast");
        var args = Parameters(record);
        args["tax_year"] = "2025";
        var actual = JsonSerializer.SerializeToElement(service.Execute("forecast", args));
        Equivalent(record.GetProperty("response").GetProperty("body").GetProperty("value"), actual);
    }

    internal static JsonElement Recording(string file, string id) =>
        File.ReadLines(Path.Combine(Corpus.Root, "contract", "recordings", file + ".jsonl"))
            .Select(line => JsonSerializer.Deserialize<JsonElement>(line))
            .First(row => row.GetProperty("id").GetString() == id);

    private static Dictionary<string, string?> Parameters(JsonElement record)
    {
        var query = record.GetProperty("request").GetProperty("query").GetString()!;
        return query.Split('&', StringSplitOptions.RemoveEmptyEntries).Select(part => part.Split('=', 2))
            .ToDictionary(pair => Uri.UnescapeDataString(pair[0]), pair => (string?)Uri.UnescapeDataString(pair.Length == 1 ? "" : pair[1]), StringComparer.Ordinal);
    }

    internal static void Equivalent(JsonElement expected, JsonElement actual, string path = "$")
    {
        Assert.True(expected.ValueKind == actual.ValueKind, $"{path}: expected {expected.ValueKind}, got {actual.ValueKind}.");
        if (expected.ValueKind == JsonValueKind.Object)
        {
            var keys = expected.EnumerateObject().Select(property => property.Name).Order(StringComparer.Ordinal).ToList();
            Assert.True(keys.SequenceEqual(actual.EnumerateObject().Select(property => property.Name).Order(StringComparer.Ordinal)), $"{path}: object fields differ.");
            foreach (var key in keys)
            {
                Equivalent(expected.GetProperty(key), actual.GetProperty(key), path + "." + key);
            }
        }
        else if (expected.ValueKind == JsonValueKind.Array)
        {
            Assert.True(expected.GetArrayLength() == actual.GetArrayLength(), $"{path}: array length {expected.GetArrayLength()} != {actual.GetArrayLength()}.");
            for (var index = 0; index < expected.GetArrayLength(); index++)
            {
                Equivalent(expected[index], actual[index], $"{path}[{index}]");
            }
        }
        else if (expected.ValueKind == JsonValueKind.Number)
        {
            Assert.True(expected.GetDouble() == actual.GetDouble(), $"{path}: expected {expected}, got {actual}.");
        }
        else
        {
            Assert.True(JsonElement.DeepEquals(expected, actual), $"{path}: expected {expected}, got {actual}.");
        }
    }
}
