using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Routing;
using TaxCredit.Api.Contract;

namespace TaxCredit.Api.Tests.Framework;

public sealed class RegistryTests
{
    [Fact]
    public void The_generated_registry_tracks_every_inventory_operation_and_its_contract()
    {
        var source = Corpus.Read(Path.Combine("contract", "inventory", "routes.json"));
        var schema = Corpus.Read(Path.Combine("contract", "inventory", "openapi.json"));
        var table = new RouteTable();
        var expected = new List<string>();
        foreach (var route in source.GetProperty("routes").EnumerateArray())
        {
            var methods = route.GetProperty("method");
            var names = methods.ValueKind == JsonValueKind.Array ? methods.EnumerateArray().Select(m => m.GetString()!).ToArray() : [methods.GetString()!];
            foreach (var method in names)
            {
                var path = route.GetProperty("path").GetString()!;
                expected.Add(method + " " + path);
                var generated = Assert.Single(table.Operations, o => o.Method == method && o.Path == path);
                Assert.Equal(route.GetProperty("name").GetString(), generated.Name);
                Assert.Equal(!route.GetProperty("untyped").GetBoolean(), generated.Typed);
                if (route.TryGetProperty("endpoint", out var endpoint))
                {
                    Assert.Equal(endpoint.GetString(), generated.Endpoint);
                    Assert.True(JsonElement.DeepEquals(route.GetProperty("request_body_schema"), generated.RequestBodySchema));
                    AssertParameters(route.GetProperty("parameters"), generated);
                }
            }
        }

        var channel = Corpus.Read(Path.Combine("contract", "inventory", "channel.json"));
        foreach (var route in channel.GetProperty("gateway_routes").EnumerateArray())
        {
            expected.AddRange(route.GetProperty("methods").EnumerateArray().Select(m => m.GetString() + " " + route.GetProperty("path").GetString()));
        }

        Assert.Equal(expected.Order(StringComparer.Ordinal), table.Operations.Select(o => o.Method + " " + o.Path).Order(StringComparer.Ordinal));
        Assert.True(JsonElement.DeepEquals(schema.GetProperty("components").GetProperty("schemas"), table.Schemas));
        Assert.True(JsonElement.DeepEquals(schema, RouteTable.OpenApi()));
    }

    private static void AssertParameters(JsonElement parameters, RouteOperation generated)
    {
        foreach (var location in parameters.EnumerateObject())
        {
            var source = location.Value.EnumerateArray().ToArray();
            Assert.Equal(source.Length, generated.Parameters[location.Name].Count);
            foreach (var parameter in source)
            {
                var target = Assert.Single(generated.Parameters[location.Name], p => p.Name == parameter.GetProperty("name").GetString());
                Assert.Equal(parameter.GetProperty("annotation").GetString(), target.Annotation);
                Assert.Equal(parameter.GetProperty("required").GetBoolean(), target.Required);
            }
        }
    }

    [Fact]
    public void Groups_partition_the_whole_surface_once()
    {
        var groups = Corpus.Read(Path.Combine("dotnet", "docs", "route-groups.json")).GetProperty("groups");
        var operations = groups.EnumerateObject().SelectMany(g => g.Value.EnumerateArray().Select(r => (Group: g.Name, Route: r.GetString()!))).ToArray();
        var table = new RouteTable();
        Assert.Equal(operations.Length, operations.Select(o => o.Route).Distinct(StringComparer.Ordinal).Count());
        Assert.Equal(table.Operations.Count, operations.Length);
        foreach (var operation in table.Operations)
        {
            Assert.Contains((operation.Group, operation.Method + " " + operation.Path), operations);
            var expected = operation.Endpoint.Split('.')[1] switch
            {
                "chat" or "summary" or "capabilities" => "ai",
                "program_drafts" or "programs" or "run_batches" => "drafts_runs",
                "workspace" => "workspace_sealed",
                _ => operation.Group,
            };
            Assert.Equal(expected, operation.Group);
        }

        Assert.All(table.Operations.Where(o => o.Path.Contains("/runs", StringComparison.Ordinal) || o.Path.EndsWith("/base-year", StringComparison.Ordinal) || o.Path.EndsWith("/rebase", StringComparison.Ordinal)),
            o => Assert.Equal("drafts_runs", o.Group));
    }

    [Fact]
    public async Task A_real_operation_replaces_only_its_stub_without_ambiguity()
    {
        await using var host = await TestHost.Start(routes: app => app.MapGet("/api/scope", () => new { real = true }));
        using var response = await host.Client.GetAsync("/api/scope");
        Assert.Equal("""{"real":true}""", await response.Content.ReadAsStringAsync());
        var endpoints = ((IEndpointRouteBuilder)host.App).DataSources.SelectMany(s => s.Endpoints).OfType<RouteEndpoint>();
        var claims = endpoints.Where(e => e.RoutePattern.RawText == "/api/scope" && e.Metadata.GetMetadata<IHttpMethodMetadata>()!.HttpMethods.Contains("GET")).ToArray();
        Assert.Single(claims);
        using var deferred = await host.Client.GetAsync("/api/rules");
        Assert.Equal(501, (int)deferred.StatusCode);
    }
}
