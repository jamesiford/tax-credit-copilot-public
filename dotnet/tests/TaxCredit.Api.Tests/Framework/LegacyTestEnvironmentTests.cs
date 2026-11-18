using TaxCredit.TestSupport;

namespace TaxCredit.Api.Tests.Framework;

/// <summary>The test-switch fallback linked into every test project.</summary>
public sealed class LegacyTestEnvironmentTests
{
    [Fact]
    public void A_deprecated_switch_is_copied_to_its_new_name_unless_the_new_name_is_set_and_no_value_is_reported()
    {
        var environment = new Dictionary<string, string?>
        {
            ["TCC_RUN_BENCH"] = "secret-1",
            ["TCC_FUZZ_N"] = "secret-2",
            ["FUZZ_N"] = "5",
        };
        var lines = new List<string>();
        LegacyTestEnvironment.Apply(name => environment.GetValueOrDefault(name), (name, value) => environment[name] = value, lines.Add);
        Assert.Equal("secret-1", environment["BENCH_RUN"]);
        Assert.Equal("5", environment["FUZZ_N"]);
        var line = Assert.Single(lines);
        Assert.Contains("TCC_RUN_BENCH", line, StringComparison.Ordinal);
        Assert.DoesNotContain("secret", line, StringComparison.Ordinal);
    }

    [Fact]
    public void Every_switch_in_the_table_is_a_deprecated_name_with_a_new_one()
    {
        Assert.All(LegacyTestEnvironment.Table, pair =>
        {
            Assert.StartsWith("TCC_", pair.Value, StringComparison.Ordinal);
            Assert.DoesNotContain("TCC_", pair.Key, StringComparison.Ordinal);
        });
    }
}
