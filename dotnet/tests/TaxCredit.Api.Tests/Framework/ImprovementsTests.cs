namespace TaxCredit.Api.Tests.Framework;

public sealed class ImprovementsTests
{
    [Fact]
    public void The_improvements_register_has_precise_routes_and_reviewable_reasons()
    {
        var register = Corpus.Read(Path.Combine("dotnet", "docs", "improvements", "W1-skeleton.json"));
        var compatibility = Corpus.Read(Path.Combine("dotnet", "docs", "improvements", "skeleton.json"));
        Assert.True(System.Text.Json.JsonElement.DeepEquals(register, compatibility));
        var entries = register.GetProperty("improvements").EnumerateArray().ToArray();
        Assert.NotEmpty(entries);
        Assert.Equal(entries.Length, entries.Select(e => e.GetProperty("id").GetString()).Distinct(StringComparer.Ordinal).Count());
        var routes = new TaxCredit.Api.Contract.RouteTable().Operations.Select(o => o.Method + " " + o.Path).ToArray();
        foreach (var entry in entries)
        {
            Assert.StartsWith("IMP-skeleton-", entry.GetProperty("id").GetString(), StringComparison.Ordinal);
            Assert.Contains(entry.GetProperty("kind").GetString(), new[] { "defect_fix", "error_text", "wire_incidental", "framework_default" });
            Assert.Contains(entry.GetProperty("route").GetString(), routes);
            Assert.True(entry.GetProperty("reason").GetString()!.Length >= 20);
        }
    }
}
