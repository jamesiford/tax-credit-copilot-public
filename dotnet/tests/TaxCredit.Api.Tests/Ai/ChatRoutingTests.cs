using System.Text.Json.Nodes;
using TaxCredit.Application.Features.Ai.Chat;
using TaxCredit.Application.Features.Ai.Streams;

namespace TaxCredit.Api.Tests.Ai;

public sealed class ChatRoutingTests
{
    [Theory]
    [InlineData("Who should we be targeting and why?", "book")]
    [InlineData("Who is our next best customer?", "book")]
    [InlineData("Which counted jobs might fall off next year?", "at_risk")]
    [InlineData("What is their trend since their base year?", "trend")]
    [InlineData("Show our complete credit picture", "multi_state")]
    [InlineData("what if we hired a person", "simulate")]
    [InlineData("how much is the credit", "eligibility")]
    public void Fallback_reaches_each_named_question(string message, string intent) =>
        Assert.Equal(intent, ChatRouting.KeywordIntents(message)[0]);

    [Fact]
    public void Compound_questions_keep_both_halves_and_drop_invented_router_names()
    {
        Assert.Equal(["situation", "discovery"], ChatRouting.KeywordIntents("brief me on them and what else might they qualify for"));
        Assert.Equal(["trend", "situation"], ChatRouting.ValidatePlan(JsonNode.Parse("""{"intents":["trend","nonsense","situation","trend"]}"""), "x"));
        Assert.Equal(["simulate"], ChatRouting.ValidatePlan(JsonNode.Parse("""{"intents":[]}"""), "what if we hired"));
        Assert.Equal(["trend"], ChatRouting.ValidatePlan(JsonValue.Create("trend"), "x"));
    }

    [Theory]
    [InlineData("brief me on Alpine", 10L, false, "")]
    [InlineData("brief me on Birch", 10L, true, "names a different client from the one this chat is about")]
    [InlineData("brief me on Alpine and Birch", 10L, true, "names more than one client")]
    [InlineData("brief me on Alpine", null, true, "no client is selected")]
    [InlineData("their trend", null, true, "does not say which client it means")]
    public void Referent_checks_precede_model_routing(string message, long? client, bool clarify, string reason)
    {
        var result = ChatReferents.Resolve(new(message, ClientId: client),
            [new(10, "Alpine Foods", 2024), new(20, "Birch Shops", 2023)]);
        Assert.Equal(clarify, result.Clarify);
        Assert.Equal(reason, result.Reason);
    }

    [Fact]
    public void Follow_up_history_cannot_silently_switch_to_the_page_client()
    {
        ChatClient[] clients = [new(10, "Alpine Foods", 2024), new(20, "Birch Shops", 2023)];
        var query = new ChatQuery("what is their trend?", ClientId: 10,
            History: [new("user", "brief me on Birch"), new("assistant", "Birch Shops")]);
        var result = ChatReferents.Resolve(query, clients);
        Assert.True(result.Clarify);
        Assert.Equal([20, 10], result.Candidates);
        Assert.False(ChatReferents.Resolve(query with { ClientConfirmed = true }, clients).Clarify);
    }
}
