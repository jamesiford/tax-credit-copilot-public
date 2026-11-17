using System.Text.Json.Nodes;
using TaxCredit.Orchestrator.Boundary;

namespace TaxCredit.Orchestrator.Tests.Boundary;

public sealed class GatewayReplyTests
{
    [Fact]
    public void Full_envelope_and_unknown_fields_survive_without_model_projection_at_transport_boundary()
    {
        var envelope = JsonNode.Parse("""
            {
              "tool":"data_query",
              "facts":{"count":1,"private_rows":[{"record":"synthetic-private","wages":"123.45"}]},
              "blocks":[{"kind":"table","audience":"user","rows":[["synthetic-private","123.45"]]}],
              "provenance":{"run_id":"run-synthetic","source":"test"},
              "warnings":["synthetic warning"],"user_only_facts":["private_rows"],
              "confirmation_token":"never-a-model-value","custom_metadata":{"retained":true}
            }
            """)!.AsObject();
        var reply = new GatewayReply(200, envelope);
        Assert.True(reply.Ok);
        Assert.Equal("ok", reply.ErrorCode);
        Assert.Equal("never-a-model-value", reply.Body["confirmation_token"]!.GetValue<string>());
        Assert.True(reply.Body["custom_metadata"]!["retained"]!.GetValue<bool>());
        var capability = Assert.IsType<TaxCredit.Application.Features.Ai.Capabilities.CapabilityResult>(reply.ToCapabilityResult("data_query"));
        Assert.True(capability.HasUserLane);
        Assert.Equal("synthetic-private", capability.Facts["private_rows"]![0]!["record"]!.GetValue<string>());
        Assert.False(capability.ModelFacts().ContainsKey("private_rows"));
        Assert.Equal("user", capability.Blocks[0]!["audience"]!.GetValue<string>());
        Assert.Equal("run-synthetic", capability.Provenance["run_id"]!.GetValue<string>());
        Assert.Equal("synthetic warning", Assert.Single(capability.Warnings));
        capability.Facts["count"] = 99;
        capability.Blocks.Clear();
        Assert.Equal(1, reply.Body["facts"]!["count"]!.GetValue<int>());
        Assert.Single(reply.Body["blocks"]!.AsArray());
    }

    [Theory]
    [InlineData("""{"facts":{},"user_only_facts":"private"}""")]
    [InlineData("""{"facts":{},"user_only_facts":[9]}""")]
    [InlineData("""{"facts":{},"user_only_facts":["absent"]}""")]
    [InlineData("""{"facts":{},"warnings":[{}]}""")]
    [InlineData("""{"facts":{},"blocks":{}}""")]
    [InlineData("""{"facts":{},"provenance":[]}""")]
    [InlineData("""{"facts":[]}""")]
    [InlineData("""{"error":{"code":"refused"},"facts":{}}""")]
    public void Malformed_lane_metadata_cannot_silently_grant_model_access(string body) =>
        Assert.Null(new GatewayReply(200, JsonNode.Parse(body)!.AsObject()).ToCapabilityResult("data_query"));

    [Theory]
    [InlineData(403, """{"detail":"forbidden"}""", "http_403")]
    [InlineData(409, """{"error":{"code":"confirmation_expired","message":"expired"}}""", "confirmation_expired")]
    [InlineData(503, """{"error":{"code":"unavailable"}}""", "unavailable")]
    [InlineData(200, """{"error":null}""", "http_200")]
    public void Refused_expired_and_unavailable_outcomes_remain_distinct(int status, string body, string expected)
    {
        var reply = new GatewayReply(status, JsonNode.Parse(body)!.AsObject());
        Assert.False(reply.Ok);
        Assert.Equal(expected, reply.ErrorCode);
        Assert.Null(reply.ToCapabilityResult("book_rank"));
    }

    [Fact]
    public void Unknown_block_audience_remains_person_only_after_conversion()
    {
        var reply = new GatewayReply(200, JsonNode.Parse("""
            {"facts":{"count":1},"blocks":[{"kind":"paragraph","text":"reader only","audience":"future-audience"}]}
            """)!.AsObject());
        Assert.True(reply.ToCapabilityResult("read")!.HasUserLane);
    }

    [Theory]
    [InlineData("http://gateway.example")]
    [InlineData("https://user:password@gateway.example")]
    [InlineData("https://gateway.example?token=secret")]
    [InlineData("https://gateway.example#fragment")]
    public void Gateway_destination_cannot_embed_credentials_or_non_https_destinations(string url) =>
        Assert.Throws<ArgumentException>(() => new GatewaySettings(new Uri(url), "api://gateway"));

    [Fact]
    public void Gateway_environment_uses_existing_scope_and_timeout_semantics()
    {
        var settings = GatewaySettings.FromEnvironment(new Dictionary<string, string?>
        {
            ["CHANNEL_GATEWAY_URL"] = " https://gateway.example/ ",
            ["CHANNEL_GATEWAY_AUDIENCE"] = "api://gateway/",
            ["CHANNEL_REQUEST_TIMEOUT_SECONDS"] = "55",
        });
        Assert.Equal("api://gateway/.default", settings.Scope);
        Assert.Equal(TimeSpan.FromSeconds(55), settings.RequestTimeout);
        Assert.Throws<ArgumentOutOfRangeException>(() => new GatewaySettings(new Uri("https://gateway.example"), "gateway", TimeSpan.Zero));
        Assert.Throws<ArgumentOutOfRangeException>(() => new GatewaySettings(new Uri("https://gateway.example"), "gateway", maxResponseBytes: 0));
    }
}
