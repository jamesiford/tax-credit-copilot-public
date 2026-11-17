using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Orchestrator.Framework;

namespace TaxCredit.Orchestrator.Tests.Framework;

public sealed class CatalogProjectionTests
{
    [Fact]
    public void Every_model_tool_description_and_schema_match_the_inventory()
    {
        var catalog = new ModelToolCatalog(new CapabilityCatalog());
        var root = new DirectoryInfo(AppContext.BaseDirectory);
        while (root is not null && !File.Exists(Path.Combine(root.FullName, "contract", "inventory", "orchestrator.json")))
        {
            root = root.Parent;
        }
        Assert.NotNull(root);
        var inventory = JsonNode.Parse(File.ReadAllText(Path.Combine(root.FullName, "contract", "inventory", "orchestrator.json")))!;
        var expected = inventory["tools_offered_to_a_model"]!.AsArray();
        Assert.Equal(expected.Count, catalog.Definitions.Count);
        foreach (var spec in expected)
        {
            var actual = Assert.Single(catalog.Definitions.OfType<AIFunction>(), definition => definition.Name == spec!["name"]!.GetValue<string>());
            Assert.Equal(spec!["description"]!.GetValue<string>(), actual.Description);
            Assert.True(JsonNode.DeepEquals(spec["schema_offered_to_model"], JsonNode.Parse(actual.JsonSchema.GetRawText())), actual.Name);
        }
    }

    [Fact]
    public void Returned_specification_cannot_mutate_the_shared_definitions()
    {
        var catalog = new ModelToolCatalog(new CapabilityCatalog());
        var before = JsonSerializer.Serialize(catalog.Definitions.OfType<AIFunction>().Select(tool => tool.JsonSchema));
        catalog.Find("book_rank")!["description"] = "mutated";
        Assert.Equal(before, JsonSerializer.Serialize(catalog.Definitions.OfType<AIFunction>().Select(tool => tool.JsonSchema)));
        Assert.DoesNotContain("mutated", catalog.Find("book_rank")!["description"]!.ToString(), StringComparison.Ordinal);
    }
}
