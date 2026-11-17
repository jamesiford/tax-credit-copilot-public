using System.Text.Json;
using System.Text.Json.Nodes;
using TaxCredit.Orchestrator.Boundary;
using TaxCredit.Orchestrator.Tests.Support;
using TaxCredit.Orchestrator.Turns;

namespace TaxCredit.Orchestrator.Tests.Turns;

public sealed class RecordedTurnsTests
{
    public static IEnumerable<object[]> Cases() => Records().Select(record => new object[] { record["id"]!.ToString() });

    [Theory]
    [MemberData(nameof(Cases))]
    public async Task All_thirty_nine_source_records_are_compared_by_id(string id)
    {
        var records = Records();
        var record = records.Single(row => row["id"]!.ToString() == id);
        if (id == "host.conversation-key")
        {
            Assert.Equal(record["explicit"]!.ToString(), IdentityResolver.ConversationOf(new IdentityContext(ConversationId: "c", ConversationChainId: "chain-1")));
            Assert.Equal(record["chain"]!.ToString(), IdentityResolver.ConversationOf(new IdentityContext(ConversationChainId: "chain-1")));
            Assert.True(JsonNode.DeepEquals(record["signals"], JsonSerializer.SerializeToNode(IdentityResolver.SignalsOf(
                new IdentityContext(new Dictionary<string, string> { ["X-Client-Tenant"] = Rig.Tenant }, AgentUserId: "opaque")))));
            return;
        }
        var rig = new Rig(debug: record["debug"]?.GetValue<bool>() ?? false);
        var question = record["question"]!.ToString();
        if (id.StartsWith("host.", StringComparison.Ordinal))
        {
            var subject = id is "host.no-signal" or "host.whoami-on-no-signal" ? null : new PlatformOriginalSubject(Rig.Oid, Rig.Tenant, "user");
            var context = new IdentityContext(OriginalSubject: subject, AgentUserId: id == "host.no-signal" ? "opaque" : null,
                ConversationId: "conv-1", ConversationChainId: "chain-1", ResponseId: "resp_1");
            var actual = await rig.Host.AnswerAsync(question, context);
            AssertText(record["text"]!.ToString(), actual);
            return;
        }
        TurnReply reply;
        if (id == "identity.nobody")
        {
            reply = await rig.Pipeline.HandleAsync(question, null);
        }
        else if (id.StartsWith("conversation.", StringComparison.Ordinal))
        {
            reply = null!;
            foreach (var previous in records.Where(row => row["id"]!.ToString().StartsWith("conversation.", StringComparison.Ordinal)))
            {
                reply = await rig.SayAsync(previous["question"]!.ToString());
                if (previous["id"]!.ToString() == id) { break; }
            }
        }
        else { reply = await rig.SayAsync(question); }
        Assert.Equal(record["mode"]!.ToString(), reply.Mode);
        Assert.Equal(record["model_called"]!.GetValue<bool>(), reply.ModelCalled);
        AssertText(record["text"]!.ToString(), reply.Text);
        var captured = id.StartsWith("conversation.", StringComparison.Ordinal) ? rig.Gateway.Calls.TakeLast(2) : rig.Gateway.Calls;
        var calls = new JsonArray(captured.Select(call => (JsonNode)new JsonObject
        {
            ["tool"] = call.Tool,
            ["args"] = call.Arguments.DeepClone(),
        }).ToArray());
        Assert.True(JsonNode.DeepEquals(record["gateway_calls"], calls),
            $"Expected: {record["gateway_calls"]}\nActual: {calls}");
    }

    private static void AssertText(string expected, string actual)
    {
        if (expected.StartsWith('{'))
        {
            Assert.True(JsonNode.DeepEquals(JsonNode.Parse(expected), JsonNode.Parse(actual)), actual);
        }
        else { Assert.Equal(expected, actual); }
    }

    internal static JsonObject[] Records()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null && !Directory.Exists(Path.Combine(directory.FullName, "contract"))) { directory = directory.Parent; }
        Assert.NotNull(directory);
        return JsonNode.Parse(File.ReadAllText(Path.Combine(directory.FullName, "contract", "recordings", "orchestrator.json")))!
            ["records"]!.AsArray().OfType<JsonObject>().ToArray();
    }
}
