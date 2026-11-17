using System.Text;
using TaxCredit.Infrastructure.Ai.Agents;

namespace TaxCredit.Api.Tests.Ai.Agents;

public sealed class CapturedPublicationTests
{
    public static IEnumerable<object[]> CapturedAgentNames => Corpus.Read(Path.Combine("contract", "recordings", "agents.json"))
        .GetProperty("agents").EnumerateArray().Select(agent => new object[] { agent.GetProperty("spec_name").GetString()! });

    [Theory]
    [MemberData(nameof(CapturedAgentNames))]
    public async Task Every_fake_publication_matches_the_captured_request_and_response(string specName)
    {
        var roster = AgentRoster.Load();
        var client = new RecordingClient();
        var publisher = AgentPublicationTests.Publisher(client, "contract-model");
        var spec = roster.Specs.Single(spec => spec.Name == specName);
        var result = await publisher.PublishAsync(spec);
        var actual = Assert.Single(client.Created);
        var oracle = Corpus.Read(Path.Combine("contract", "recordings", "agents.json"));
        var expected = oracle.GetProperty("foundry_requests").EnumerateArray()
            .Single(request => request.GetProperty("name").GetString() == actual.Name);
        Assert.Equal(expected.GetProperty("call").GetString(), actual.Call);
        Assert.Equal(expected.GetProperty("name").GetString(), actual.Name);
        Assert.Equal(expected.GetProperty("definition_type").GetString(), actual.Definition.GetType().Name);
        Assert.Equal(expected.GetProperty("model").GetString(), actual.Definition.Model);
        Assert.Equal(expected.GetProperty("temperature").GetDouble(), actual.Definition.Temperature);
        Assert.Equal(expected.GetProperty("instructions_chars").GetInt32(), actual.Definition.Instructions.EnumerateRunes().Count());
        Assert.Equal(expected.GetProperty("instructions_sha256").GetString(), VersionedPrompt.Hash(actual.Definition.Instructions));
        Assert.Equal(expected.GetProperty("extra_kwargs").EnumerateArray().Select(item => item.GetString()), actual.ExtraKeywordArguments);
        Assert.Empty(actual.Definition.Tools);
        var agent = oracle.GetProperty("agents").EnumerateArray().Single(agent => agent.GetProperty("spec_name").GetString() == specName);
        var projection = agent.GetProperty("published");
        Assert.Equal(agent.GetProperty("temperature_spec").GetDouble(), spec.Temperature);
        Assert.Equal(specName, result.Name);
        Assert.Equal(projection.GetProperty("name").GetString(), result.PublishedName);
        Assert.Equal(projection.GetProperty("version").GetString(), result.Version);
        Assert.Equal(projection.GetProperty("agent_id").GetString(), result.AgentId);
        Assert.Equal(projection.GetProperty("model").GetString(), result.Model);
        Assert.Equal(projection.GetProperty("portal_url").GetString(), result.PortalUrl);
    }
}
