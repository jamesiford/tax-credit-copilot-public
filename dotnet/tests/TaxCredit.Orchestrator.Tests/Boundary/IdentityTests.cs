using TaxCredit.Orchestrator.Boundary;

namespace TaxCredit.Orchestrator.Tests.Boundary;

public sealed class IdentityTests
{
    internal const string Tenant = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee";
    internal const string Person = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
    internal const string Other = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";

    internal static ActingIdentity Who(string person = Person, string conversation = "conversation-1") =>
        IdentityResolver.Resolve(new IdentityContext(
            OriginalSubject: new PlatformOriginalSubject(person, Tenant),
            ConversationId: conversation, ResponseId: "response-1"), new IdentityOptions(Tenant)).Identity!;

    [Fact]
    public void Platform_subject_overrides_conflicting_headers_and_oid_case_is_normalized()
    {
        var context = new IdentityContext(new Dictionary<string, string>
        {
            ["X-MS-Original-Subject-Oid"] = Other,
            ["X-MS-User-Identity"] = Other,
            ["X-Client-Acting-User-Name"] = " Pat Writer ",
        }, new PlatformOriginalSubject(Person.ToUpperInvariant(), Tenant.ToUpperInvariant(), "user"),
            ConversationId: "c");
        var result = IdentityResolver.Resolve(context, new IdentityOptions(Tenant));
        Assert.True(result.IsResolved);
        Assert.Null(result.Refusal);
        Assert.Equal(Person, result.Identity!.Oid);
        Assert.Equal(Tenant, result.Identity.TenantId);
        Assert.Equal("Pat Writer", result.Identity.Name);
        Assert.Equal("original-subject", result.Identity.Source);
    }

    [Theory]
    [InlineData("original-subject", "x-ms-original-subject-oid")]
    [InlineData("platform", "X-MS-USER-IDENTITY")]
    [InlineData("client-headers", "X-Client-Acting-User-Oid")]
    [InlineData("agent-user-id", "x-agent-user-id")]
    public void Configured_sources_resolve_with_case_insensitive_header_names(string source, string header)
    {
        var result = IdentityResolver.Resolve(new IdentityContext(new Dictionary<string, string> { [header] = Person },
            ConversationId: "c"), new IdentityOptions(Tenant, sources: [source]));
        Assert.Equal(Person, result.Identity!.Oid);
        Assert.Equal(source, result.Identity.Source);
        Assert.Equal("(name not provided)", result.Identity.Name);
    }

    [Fact]
    public void Caller_supplied_oid_is_not_trusted_by_default()
    {
        var result = IdentityResolver.Resolve(new IdentityContext(
            new Dictionary<string, string> { ["x-client-acting-user-oid"] = Person }, ConversationId: "c"),
            new IdentityOptions(Tenant));
        Assert.False(result.IsResolved);
        Assert.Contains("no configured source", result.Refusal!.Reason, StringComparison.Ordinal);
        Assert.Equal(IdentityRefusal.RefusalMessage, result.Refusal.Message);
    }

    [Fact]
    public void Source_order_is_configurable_and_opaque_agent_id_does_not_block_the_next_source()
    {
        var context = new IdentityContext(
            new Dictionary<string, string> { ["x-ms-user-identity"] = Person },
            AgentUserId: "opaque-private-partition", ConversationId: "c");
        Assert.Equal("platform", IdentityResolver.Resolve(context,
            new IdentityOptions(Tenant, sources: ["agent-user-id", "platform"])).Identity!.Source);
        Assert.False(IdentityResolver.Resolve(context,
            new IdentityOptions(Tenant, sources: ["agent-user-id"])).IsResolved);
    }

    [Theory]
    [InlineData("not-a-guid")]
    [InlineData("{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa}")]
    [InlineData("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")]
    public void Invalid_higher_precedence_oid_refuses_instead_of_downgrading(string oid)
    {
        var result = IdentityResolver.Resolve(new IdentityContext(
            new Dictionary<string, string> { ["x-ms-user-identity"] = Person },
            new PlatformOriginalSubject(oid, Tenant), ConversationId: "c"), new IdentityOptions(Tenant));
        Assert.Null(result.Identity);
        Assert.Contains("GUID", result.Refusal!.Reason, StringComparison.Ordinal);
    }

    [Fact]
    public void Foreign_tenant_refuses_without_exposing_its_asserted_value()
    {
        var result = IdentityResolver.Resolve(new IdentityContext(
            OriginalSubject: new PlatformOriginalSubject(Person, Other), ConversationId: "c"), new IdentityOptions(Tenant));
        Assert.Contains("different tenant", result.Refusal!.Reason, StringComparison.Ordinal);
        Assert.DoesNotContain(Other, result.Refusal.Reason, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("explicit", "chain", "explicit")]
    [InlineData(null, "chain", "chain")]
    [InlineData("", "chain", "chain")]
    public void Conversation_prefers_explicit_then_chain(string? explicitId, string? chain, string expected)
    {
        var context = new IdentityContext(OriginalSubject: new PlatformOriginalSubject(Person),
            ConversationId: explicitId, ConversationChainId: chain);
        Assert.Equal(expected, IdentityResolver.ConversationOf(context));
        Assert.Equal(expected, IdentityResolver.Resolve(context, new IdentityOptions(Tenant)).Identity!.ConversationId);
    }

    [Fact]
    public void Response_id_and_caller_conversation_header_do_not_invent_a_conversation()
    {
        var context = new IdentityContext(
            new Dictionary<string, string> { ["x-client-conversation-id"] = "untrusted-conversation" },
            new PlatformOriginalSubject(Person), ResponseId: "response-not-conversation");
        Assert.Equal("no conversation id", IdentityResolver.Resolve(context, new IdentityOptions(Tenant)).Refusal!.Reason);
    }

    [Fact]
    public void Keys_separate_people_even_when_the_response_chain_is_reused()
    {
        var keys = new[] { Who().Key, Who(Other).Key, Who(conversation: "other").Key };
        Assert.Equal(3, keys.Distinct().Count());
        Assert.Equal(new PersonConversationKey(Person, "conversation-1"), keys[0]);
    }

    [Theory]
    [InlineData("resp/ bad:id", "respbadid")]
    [InlineData("resp._-123", "resp._-123")]
    [InlineData("r\r\nheader: value", "rheadervalue")]
    [InlineData("é漢１9", "9")]
    public void Correlation_is_ascii_header_safe(string raw, string expected) =>
        Assert.Equal(expected, IdentityResolver.CorrelationOf(raw));

    [Fact]
    public void Correlation_is_bounded_or_new_when_nothing_safe_arrives()
    {
        Assert.Equal(64, IdentityResolver.CorrelationOf(new string('a', 100)).Length);
        Assert.True(Guid.TryParseExact(IdentityResolver.CorrelationOf(null), "N", out _));
        Assert.NotEqual(IdentityResolver.CorrelationOf("///"), IdentityResolver.CorrelationOf("///"));
    }

    [Fact]
    public void Gateway_assertions_are_not_backend_api_headers_or_credentials()
    {
        var headers = Who().GatewayHeaders();
        Assert.Equal(6, headers.Count);
        Assert.Equal(Person, headers["X-Acting-User-Oid"]);
        Assert.Equal(Tenant, headers["X-Acting-Tenant"]);
        Assert.Equal("teams", headers["X-Channel"]);
        Assert.Equal("conversation-1", headers["X-Conversation-Id"]);
        Assert.Equal("response-1", headers["X-Correlation-Id"]);
        Assert.False(headers.ContainsKey("X-TCC-Acting-User"));
        Assert.False(headers.ContainsKey("Authorization"));
    }

    [Theory]
    [InlineData("c\r\nforged: yes")]
    [InlineData(" ")]
    public void Unsafe_conversations_refuse_before_a_header_can_be_constructed(string conversation)
    {
        var result = IdentityResolver.Resolve(new IdentityContext(
            OriginalSubject: new PlatformOriginalSubject(Person), ConversationId: conversation), new IdentityOptions(Tenant));
        Assert.False(result.IsResolved);
    }

    [Fact]
    public void Settings_are_validated_and_sources_snapshot_the_callers_list()
    {
        var sources = new List<string> { " PLATFORM ", "client-headers" };
        var options = new IdentityOptions(Tenant.ToUpperInvariant(), sources: sources);
        sources.Clear();
        Assert.Equal(new[] { "platform", "client-headers" }, options.Sources);
        Assert.Equal(Tenant, options.TenantId);
        Assert.Throws<ArgumentException>(() => new IdentityOptions("invalid"));
        Assert.Throws<ArgumentException>(() => new IdentityOptions(Tenant, channel: "other"));
        Assert.Throws<ArgumentException>(() => new IdentityOptions(Tenant, sources: []));
        Assert.Throws<ArgumentException>(() => new IdentityOptions(Tenant, sources: ["x-agent-user-id"]));
    }

    [Fact]
    public void Environment_defaults_match_the_current_platform_source_policy()
    {
        var options = IdentityOptions.FromEnvironment(new Dictionary<string, string?> { ["TENANT_ID"] = Tenant });
        Assert.False(options.DebugWhoami);
        Assert.Equal(new[] { "original-subject", "platform", "agent-user-id" }, options.Sources);
        var configured = IdentityOptions.FromEnvironment(new Dictionary<string, string?>
        {
            ["TENANT_ID"] = Tenant,
            ["CHANNEL_DEBUG_WHOAMI"] = "YES",
            ["CHANNEL_IDENTITY_SOURCES"] = "CLIENT-HEADERS",
            ["CHANNEL_NAME"] = "m365-copilot",
        });
        Assert.True(configured.DebugWhoami);
        Assert.Equal("m365-copilot", configured.Channel);
        Assert.Equal("client-headers", Assert.Single(configured.Sources));
    }
}
