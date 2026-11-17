using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.ReadsCalc;
using TaxCredit.Application.Features.ReadsCalc.Portfolio;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Api.Tests.ReadsCalc.Portfolio;

internal sealed class PortfolioTestData : IPortfolioReferenceData
{
    public long CountFederalNewHires(long taxYear) => taxYear switch { 2023 => 34, 2024 => 35, 2025 => 200, 2026 => 25, _ => 0 };

    public PortfolioWorksite? Worksite(string unitId) => unitId switch
    {
        "GA_ATL_HQ" => new("Atlanta HQ", "Fulton", "Atlanta"),
        "GA_CUM_OPS" => new("Cumberland Center", "Cobb", "Cumberland"),
        "GA_MAC_OPS" => new("Macon Operations", "Bibb", "Macon"),
        "GA_SAV_DC" => new("Savannah Distribution Center", "Chatham", "Savannah"),
        _ => null,
    };

    internal static void Register(IServiceCollection services)
    {
        services.AddReadsCalcPortfolio();
        services.AddSingleton<IPortfolioReferenceData, PortfolioTestData>();
    }

    internal static void EqualFixture(string fixture, object value)
    {
        var path = Path.Combine(Corpus.Root, "dotnet", "tests", "TaxCredit.Api.Tests", "ReadsCalc", "Portfolio", "Fixtures", fixture + ".json");
        var expected = JsonNode.Parse(File.ReadAllText(path))!;
        var actual = JsonSerializer.SerializeToNode(ReadValues.Transport(value))!;
        NormalizeDeclines(expected);
        NormalizeDeclines(actual);
        Assert.True(JsonNode.DeepEquals(expected, actual), FirstDifference(expected, actual, "$"));
    }

    private static void NormalizeDeclines(JsonNode node)
    {
        if (node is JsonObject obj && obj["declined_years"] is JsonArray declines)
        {
            foreach (var decline in declines)
            {
                Assert.False(string.IsNullOrEmpty(decline!["reason"]!.GetValue<string>()));
                decline["reason"] = "declined";
            }
        }
    }

    private static string FirstDifference(JsonNode? expected, JsonNode? actual, string path)
    {
        if (expected is JsonObject left && actual is JsonObject right)
        {
            foreach (var (key, value) in left)
            {
                if (!JsonNode.DeepEquals(value, right[key]))
                {
                    return FirstDifference(value, right[key], path + "." + key);
                }
            }
        }
        if (expected is JsonArray first && actual is JsonArray second && first.Count == second.Count)
        {
            for (var index = 0; index < first.Count; index++)
            {
                if (!JsonNode.DeepEquals(first[index], second[index]))
                {
                    return FirstDifference(first[index], second[index], path + "[" + index + "]");
                }
            }
        }
        return $"{path}: expected {expected}, actual {actual}";
    }
}

internal sealed class PortfolioPayroll(Func<long?, IReadOnlyList<PayRow>> load) : IPayrollSource
{
    public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId) => load(accountId);
}
