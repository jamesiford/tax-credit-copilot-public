using Azure.Core;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using TaxCredit.Orchestrator.Boundary;
using TaxCredit.Orchestrator.Hosting;
using TaxCredit.Orchestrator.Tests.Support;

namespace TaxCredit.Orchestrator.Tests.Framework;

public sealed class KnowledgeWiringTests
{
    [Theory]
    [InlineData(false, "The cited source supports this reading.", false)]
    [InlineData(true, "The cited source supports this reading.", true)]
    [InlineData(true, "A credit of $1,234 applies.", false)]
    [InlineData(true, "The credit is {{facts.reference.credit}}.", false)]
    public async Task Production_wiring_keeps_opt_in_reference_text_separate_from_facts_and_degraded_replies(
        bool enabled, string narration, bool referencesSurvive)
    {
        var values = RuntimeWireTests.Values();
        values["KNOWLEDGE_ENABLED"] = enabled ? "true" : "false";
        values["KNOWLEDGE_PROVIDER"] = "fake";
        values["KNOWLEDGE_TOP"] = "1";
        var settings = new RuntimeSettings(new ConfigurationBuilder().AddInMemoryCollection(values).Build());
        using var model = new ScriptedModel(ScriptedModel.Tools(("client_trend", new())), ScriptedModel.Text(narration));
        using var wire = new LocalGatewayTransport(new FakeGateway());
        using var http = new HttpClient(wire);
        using var runtime = new OrchestratorRuntime(settings, new Credential(), NullLoggerFactory.Instance, http,
            new Dictionary<string, IChatClient> { ["foundry"] = model });
        var context = new IdentityContext(OriginalSubject: new PlatformOriginalSubject(Rig.Oid, Rig.Tenant, "user"), ConversationId: "knowledge-turn");
        var text = await runtime.Host.AnswerAsync("How has Cascade credit trended?", context);
        Assert.Equal(enabled, model.VisibleRequests().Any(request => request.Contains("REFERENCE TEXT", StringComparison.Ordinal)));
        Assert.Equal(referencesSurvive, text.Contains("**Reference text**", StringComparison.Ordinal));
        Assert.Equal(referencesSurvive, text.Contains("synthetic:example-credit", StringComparison.Ordinal));
        Assert.Contains("494.25", text, StringComparison.Ordinal);
        Assert.All(model.VisibleRequests(), request => Assert.DoesNotContain("synthetic:example-credit", request, StringComparison.Ordinal));
        Assert.DoesNotContain("synthetic:example-eligibility", text, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("none", "true", "3")]
    [InlineData("foundry-iq", "true", "3")]
    [InlineData("unknown", "false", "3")]
    [InlineData("fake", "true", "0")]
    [InlineData("fake", "true", "11")]
    public void Invalid_reference_configuration_fails_at_startup_without_building_a_source(string provider, string enabled, string top)
    {
        var values = RuntimeWireTests.Values();
        values["KNOWLEDGE_PROVIDER"] = provider;
        values["KNOWLEDGE_ENABLED"] = enabled;
        values["KNOWLEDGE_TOP"] = top;
        Assert.Throws<InvalidOperationException>(() => new RuntimeSettings(new ConfigurationBuilder().AddInMemoryCollection(values).Build()));
    }

    private sealed class Credential : TokenCredential
    {
        public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken) =>
            new("synthetic-service-auth", DateTimeOffset.UtcNow.AddMinutes(10));
        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken) =>
            ValueTask.FromResult(GetToken(requestContext, cancellationToken));
    }
}
