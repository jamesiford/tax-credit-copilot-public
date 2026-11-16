using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Capabilities;

namespace TaxCredit.Api.Tests.Ai.Capabilities;

public sealed class CapabilityCatalogTests
{
    [Fact]
    public void Complete_catalogue_equals_the_captured_declaration_not_a_success_only_subset()
    {
        var catalog = new CapabilityCatalog();
        var expected = Corpus.Recording("p1_artifacts_ai", "capabilities.list")
            .GetProperty("response").GetProperty("body").GetProperty("value");
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(expected.GetRawText()), catalog.List()));
        Assert.Equal(37, catalog.Declared().Count);
        Assert.Equal(36, catalog.Offered().Count);
        var modelNames = catalog.ModelOffered().Select(spec => spec!["name"]!.GetValue<string>()).ToArray();
        Assert.DoesNotContain("client_resolve", modelNames);
        Assert.DoesNotContain("employee_drill", modelNames);
        Assert.DoesNotContain("verify_figures", modelNames);
        Assert.DoesNotContain("claim_package_redeem", modelNames);
        Assert.DoesNotContain(modelNames, name => name.EndsWith("_commit", StringComparison.Ordinal));
        catalog.List()["tools"]![0]!["name"] = "mutated";
        Assert.Equal("book_rank", catalog.List()["tools"]![0]!["name"]!.GetValue<string>());
    }

    [Fact]
    public void Declared_unbuilt_gateway_local_and_debug_tools_have_different_refusals()
    {
        var declaration = new CapabilityCatalog().Resolve("book_rank");
        declaration["implemented"] = false;
        var unbuilt = new CapabilityCatalog([declaration]);
        Assert.Single(unbuilt.List()["tools"]!.AsArray());
        Assert.Empty(unbuilt.Offered());
        Assert.Equal("not_implemented", Assert.Throws<CapabilityException>(() => unbuilt.Resolve("book_rank")).Code);
        var catalog = new CapabilityCatalog();
        Assert.Equal("gateway_local", Assert.Throws<CapabilityException>(() => catalog.Resolve("verify_figures")).Code);
        Assert.Equal("unknown_tool", Assert.Throws<CapabilityException>(() => catalog.Resolve("channel_ping")).Code);
        Assert.Equal("unknown_tool", Assert.Throws<CapabilityException>(() => catalog.Resolve("absent")).Code);
        Assert.Equal("claim_package_redeem", catalog.Resolve("claim_package_redeem")["name"]!.GetValue<string>());
    }

    [Theory]
    [InlineData("book_rank", """{"limit":0}""")]
    [InlineData("book_rank", """{"limit":true}""")]
    [InlineData("book_rank", """{"limit":1.5}""")]
    [InlineData("book_rank", """{"unexpected":1}""")]
    [InlineData("client_situation", """{}""")]
    [InlineData("employee_drill", """{"client_id":42,"tax_year":2025,"record_token":"short"}""")]
    [InlineData("data_query", """{"dataset":"unit_year_master","client_id":42,"measures":[{"column":"*","agg":"count","as":"not;sql"}]}""")]
    [InlineData("data_query", """{"dataset":"unit_year_master","client_id":42,"tax_years":{"from":2020}}""")]
    [InlineData("run_batch_prepare", """{"scope":{"kind":"list","client_ids":[true]}}""")]
    public void Schemas_refuse_wrong_types_bounds_nested_shapes_and_unknown_arguments(string tool, string args)
    {
        var schema = new CapabilityCatalog().Resolve(tool)["schema"]!.AsObject();
        var error = Assert.Throws<CapabilityException>(() => CapabilitySchema.Validate(schema, JsonNode.Parse(args)));
        Assert.Equal(422, error.StatusCode);
        Assert.Equal("invalid_arguments", error.Code);
    }

    [Theory]
    [InlineData("book_rank", """{"limit":1.0}""")]
    [InlineData("client_resolve", """{"name_or_text":"Synthetic","current_client_id":null}""")]
    [InlineData("data_query", """{"dataset":"unit_year_master","client_id":42,"tax_years":{"from":2020,"to":2022},"filters":[{"column":"worksite_id","op":"in","value":["UNIT-A","UNIT-B"]}]}""")]
    public void Schemas_accept_semantically_integral_numbers_nullable_fields_and_union_shapes(string tool, string args)
    {
        var schema = new CapabilityCatalog().Resolve(tool)["schema"]!.AsObject();
        CapabilitySchema.Validate(schema, JsonNode.Parse(args));
    }

    [Fact]
    public async Task Every_recorded_non_binding_refusal_keeps_its_status_and_code()
    {
        using var harness = new CapabilityHarness();
        var failures = Corpus.Recordings("p1_artifacts_ai").Where(row =>
            row.GetProperty("id").GetString()!.StartsWith("capabilities.", StringComparison.Ordinal) &&
            row.GetProperty("response").GetProperty("body").TryGetProperty("value", out var body) && body.TryGetProperty("error", out _));
        foreach (var recording in failures)
        {
            var request = recording.GetProperty("request");
            var tool = request.GetProperty("path").GetString()!.Split('/')[^1];
            var args = JsonNode.Parse(request.GetProperty("body").GetProperty("value").GetProperty("args").GetRawText())!.AsObject();
            var error = await Assert.ThrowsAsync<CapabilityException>(() => harness.Service.InvokeAsync(tool, args));
            Assert.Equal(recording.GetProperty("response").GetProperty("status").GetInt32(), error.StatusCode);
            Assert.Equal(recording.GetProperty("response").GetProperty("body").GetProperty("value")
                .GetProperty("error").GetProperty("code").GetString(), error.Code);
        }
    }
}
