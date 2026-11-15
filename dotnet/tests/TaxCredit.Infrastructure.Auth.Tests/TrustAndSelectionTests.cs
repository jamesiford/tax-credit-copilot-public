using System.Text.Json;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth.Tests;

public sealed class TrustAndSelectionTests
{
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("Bearer")]
    [InlineData("Basic abc")]
    [InlineData("abc")]
    [InlineData("Bearer ")]
    public void BearerExtractionRejectsMissingOrOtherSchemes(string? header) => Assert.Null(ApiTrustService.Bearer(header));

    [Fact]
    public void LowerCaseBearerSchemeAndTrimAreAccepted() => Assert.Equal("abc", ApiTrustService.Bearer("bearer  abc "));

    [Theory]
    [InlineData("/api/health")]
    [InlineData("/api/ready")]
    [InlineData("/docs")]
    [InlineData("/docs/oauth2-redirect")]
    [InlineData("/redoc")]
    [InlineData("/openapi.json")]
    public async Task PublicPathsIgnoreExpiredTokenAndMissingAgentHeader(string path)
    {
        using var world = new TokenWorld();
        var claims = world.Claims(true); claims["exp"] = 0;
        var principal = await Service(world).AuthenticateAsync(path, $"Bearer {world.Mint(claims)}", null);
        Assert.False(principal.Authenticated);
        var authorizer = new CountingAuthorizer();
        await new ApiTrustService(world.Configuration, world.Validator, authorizer, new AuthEvents())
            .AuthorizeRequestAsync(principal, "GET", path, [1001]);
        Assert.Equal(0, authorizer.Calls);
    }

    [Fact]
    public async Task HeaderBindingBeforeForbiddenRouteMatchesF16()
    {
        using var world = new TokenWorld();
        var service = Service(world);
        var token = world.Mint(world.Claims(true));
        var missing = await Assert.ThrowsAsync<ApiAuthException>(async () => await service.AuthenticateAsync("/api/claims/assess", $"Bearer {token}", null));
        Assert.Equal(400, missing.StatusCode);
        var principal = await service.AuthenticateAsync("/api/claims/assess", $"Bearer {token}", TokenWorld.Header());
        var forbidden = await Assert.ThrowsAsync<ApiAuthException>(async () => await service.AuthorizeRequestAsync(principal, "POST", "/api/claims/assess", [1001]));
        Assert.Equal(403, forbidden.StatusCode);
        Assert.Equal("agent_forbidden", forbidden.Code);
    }

    [Fact]
    public async Task UsersCannotPromoteHeaderIdentityAndMeShapeKeepsNulls()
    {
        using var world = new TokenWorld();
        var ignored = 0;
        var events = new AuthEvents(ignoredSink: () => ignored++);
        var service = Service(world, events);
        var principal = await service.AuthenticateAsync("/api/me", $"Bearer {world.Mint()}", TokenWorld.Header());
        Assert.Null(principal.ActingFor);
        Assert.Equal(TokenWorld.Reader, principal.Oid);
        Assert.Equal(1, ignored);
        var body = JsonSerializer.SerializeToElement(principal.ToIdentityBody());
        Assert.Equal(JsonValueKind.Null, body.GetProperty("acting_for").ValueKind);
        Assert.Equal("user", body.GetProperty("principal_type").GetString());
    }

    [Fact]
    public void HeaderCarriesBoundContextAndOidFallbackWithoutGatewayAlternatives()
    {
        var header = TokenWorld.Header(new()
        {
            ["oid"] = TokenWorld.Writer.ToUpperInvariant(),
            ["tid"] = TokenWorld.Tenant.ToUpperInvariant(),
            ["name"] = "  Writer  ",
            ["assurance"] = "delegated",
            ["channel"] = "api-test",
            ["conversation_id"] = "conversation",
            ["correlation_id"] = "correlation"
        });
        var user = ActingUserParser.Parse(header, TokenWorld.Tenant);
        Assert.Equal(TokenWorld.Writer, user.Actor);
        Assert.Equal("Writer", user.Name);
        Assert.Equal("conversation", user.ConversationId);
        Assert.Equal("correlation", user.CorrelationId);
        Assert.False(user.IsFirstParty);
        Assert.True(ActingUserParser.Parse(TokenWorld.Header(), TokenWorld.Tenant).IsFirstParty);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData("!!!")]
    [InlineData("W10")]
    [InlineData("ew")]
    public void MalformedActingHeadersAre400(string? header) =>
        Assert.Equal(400, Assert.Throws<ApiAuthException>(() => ActingUserParser.Parse(header, TokenWorld.Tenant)).StatusCode);

    [Theory]
    [InlineData("oid", "not-a-guid")]
    [InlineData("tid", "00000000-0000-0000-0000-0000000000bb")]
    [InlineData("tid", "not-a-guid")]
    [InlineData("assurance", "trust-me")]
    [InlineData("channel", "other")]
    public void InvalidActingFieldsAre400(string field, string value)
    {
        var body = new Dictionary<string, object?> { ["oid"] = TokenWorld.Writer, ["tid"] = TokenWorld.Tenant, [field] = value };
        Assert.Equal(400, Assert.Throws<ApiAuthException>(() => ActingUserParser.Parse(TokenWorld.Header(body), TokenWorld.Tenant)).StatusCode);
    }

    [Fact]
    public void HeaderAndFieldBoundsAreEnforced()
    {
        Assert.Throws<ApiAuthException>(() => ActingUserParser.Parse(new string('A', 2049), TokenWorld.Tenant));
        var body = new Dictionary<string, object?> { ["oid"] = TokenWorld.Writer, ["tid"] = TokenWorld.Tenant, ["name"] = new string('n', 257) };
        Assert.Throws<ApiAuthException>(() => ActingUserParser.Parse(TokenWorld.Header(body), TokenWorld.Tenant));
        body["name"] = new { name = "not-text" };
        Assert.Throws<ApiAuthException>(() => ActingUserParser.Parse(TokenWorld.Header(body), TokenWorld.Tenant));
        body["name"] = new string('n', 256);
        Assert.Equal(256, ActingUserParser.Parse(TokenWorld.Header(body), TokenWorld.Tenant).Name!.Length);
    }

    [Fact]
    public void ActingFieldLimitCountsUnicodeCharactersNotUtf16CodeUnits()
    {
        var name = string.Concat(Enumerable.Repeat("😀", 256));
        var raw = $"{{\"oid\":\"{TokenWorld.Writer}\",\"tid\":\"{TokenWorld.Tenant}\",\"name\":\"{name}\"}}";
        var header = TokenWorld.Url(System.Text.Encoding.UTF8.GetBytes(raw));
        Assert.Equal(name, ActingUserParser.Parse(header, TokenWorld.Tenant).Name);
    }

    [Fact]
    public void SelectionsNormalizeAllLocationsWithoutTreatingBooleansOrFloatsAsIds()
    {
        using var doc = JsonDocument.Parse("""
            {"client_id":" 1002 ","account_id":false,"client_ids":[1001,"1003",1001,true,1.0,"-5","junk"],
             "scope":{"account_ids":[1004,"001005",null]},"other":{"client_id":999}}
            """);
        var path = new KeyValuePair<string, object?>[] { new("client_id", 1001), new("account_id", "1006"), new("other", 999) };
        var query = new KeyValuePair<string, string?>[] { new("client_id", "1007"), new("client_id", "1008"), new("account_id", "abc") };
        Assert.Equal(new long[] { 1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008 }, ClientSelection.Extract(path, query, doc.RootElement));
    }

    [Fact]
    public void UnicodeDecimalDigitSelectionsMatchPythonWithoutSuperscriptIntCrash()
    {
        var query = new KeyValuePair<string, string?>[]
        {
            new("client_id", "١٠٠١"), new("account_id", "²"), new("client_id", " +1002 ")
        };
        Assert.Equal(new long[] { 1001 }, ClientSelection.Extract(query: query));
    }

    [Fact]
    public async Task ClientPermissionsFollowAgentCallerWhileWriterRightsFollowActingPerson()
    {
        var allowed = new AllowListClientAuthorizer(new Dictionary<string, IEnumerable<long>> { [TokenWorld.Agent] = [1001], [TokenWorld.Writer] = [1002] });
        var principal = new ApiPrincipal(Oid: TokenWorld.Agent, Authenticated: true, PrincipalType: "agent",
            ActingFor: ActingUserParser.Parse(TokenWorld.Header(), TokenWorld.Tenant));
        Assert.True(await allowed.IsAuthorizedAsync(principal, 1001));
        Assert.False(await allowed.IsAuthorizedAsync(principal, 1002));
        Assert.Equal(TokenWorld.Writer, principal.EffectiveOid);
        Assert.Equal("writer@example.test", principal.Attributed("forged"));
    }

    [Fact]
    public async Task UnknownBatchExistencePrecedesVisibilityAndVisibleIdsPrecedePaging()
    {
        var authorizer = new CountingAuthorizer();
        var error = await Assert.ThrowsAsync<ApiAuthException>(async () => await ClientVisibility.VisibleBatchClientsAsync(null, ApiPrincipal.Anonymous, authorizer));
        Assert.Equal(404, error.StatusCode); Assert.Equal(0, authorizer.Calls);
        Assert.Equal(new long[] { 1, 3 }, await ClientVisibility.VisibleBatchClientsAsync([1, 2, 3], ApiPrincipal.Anonymous, authorizer));
        Assert.Equal(404, (await Assert.ThrowsAsync<ApiAuthException>(async () => await ClientVisibility.VisibleBatchClientsAsync([2], ApiPrincipal.Anonymous, authorizer))).StatusCode);
    }

    [Fact]
    public async Task ArtifactVisibilityIsDeferredForHandlerAudit()
    {
        using var world = new TokenWorld();
        var authorizer = new CountingAuthorizer();
        var service = new ApiTrustService(world.Configuration, world.Validator, authorizer, new AuthEvents());
        await service.AuthorizeRequestAsync(ApiPrincipal.Anonymous, "GET", "/api/clients/2/artifacts/absent", [2]);
        Assert.Equal(0, authorizer.Calls);
        var error = await Assert.ThrowsAsync<ApiAuthException>(async () => await service.AuthorizeRequestAsync(ApiPrincipal.Anonymous, "GET", "/api/claims/coverage/2", [2]));
        Assert.Equal(403, error.StatusCode);
    }

    [Theory]
    [InlineData("POST", "/api/ingestion/2023/exceptions/x/resolve")]
    [InlineData("POST", "/api/onezero/employee/x/review")]
    [InlineData("POST", "/api/rules/GA_JTC/verify")]
    [InlineData("POST", "/api/rules/ingested/GA/apply")]
    [InlineData("POST", "/api/workspace/refresh")]
    [InlineData("POST", "/api/workspace/comparison/stage")]
    [InlineData("POST", "/api/v2/clients/1001/runs")]
    [InlineData("POST", "/api/claims/assess")]
    [InlineData("POST", "/api/v2/run-batches")]
    [InlineData("POST", "/api/v2/run-batches/x/cancel")]
    [InlineData("POST", "/api/v2/run-batches/x/retry-failed")]
    [InlineData("POST", "/api/v2/program-drafts")]
    [InlineData("PUT", "/api/v2/program-drafts/x/documents")]
    [InlineData("POST", "/api/v2/program-drafts/x/preview")]
    public void AgentForbiddenMetadataCoversPythonPatterns(string method, string path)
    {
        Assert.True(RoutePolicy.IsAgentForbidden(method, path));
        Assert.False(RoutePolicy.IsAgentForbidden("GET", path));
        Assert.False(RoutePolicy.IsAgentForbidden(method, path + "/extra"));
    }

    [Theory]
    [InlineData("POST", "/api/v2/run-batches", "batch_start")]
    [InlineData("PUT", "/api/v2/program-drafts/x/documents", "draft_save")]
    [InlineData("POST", "/api/v2/program-drafts/x/preview", "draft_preview")]
    [InlineData("POST", "/api/v2/program-drafts/x/export", "draft_export")]
    [InlineData("GET", "/api/v2/program-drafts", null)]
    public void LimiterMetadataUsesOnlyApiKinds(string method, string path, string? kind)
    {
        Assert.Equal(kind, RoutePolicy.RateLimitKind(method, path));
        if (kind is not null)
        {
            Assert.True(RoutePolicy.IsAgentForbidden(method, path));
        }
    }

    [Fact]
    public void AgentReadObligationsDoNotImpersonateAQueryAuthor()
    {
        Assert.True(RoutePolicy.IsPersonOnlyRead("GET", "/api/audit/channel"));
        Assert.True(RoutePolicy.RequiresAgentReadReview("GET", "/api/v2/program-drafts"));
        Assert.False(RoutePolicy.IsPersonOnlyRead("GET", "/api/v2/program-drafts"));
        Assert.False(RoutePolicy.IsAgentForbidden("GET", "/api/v2/program-drafts"));
        Assert.False(RoutePolicy.RequiresWriterDecision("GET"));
    }

    [Fact]
    public void DiagnosticRenderingDoesNotExposeIdentityOrConfiguration()
    {
        var acting = ActingUserParser.Parse(TokenWorld.Header(), TokenWorld.Tenant);
        var principal = new ApiPrincipal(Oid: TokenWorld.Agent, Upn: "analyst@example.test", ActingFor: acting);
        Assert.Equal("ActingUser", acting.ToString());
        Assert.Equal("ApiPrincipal", principal.ToString());
        Assert.Equal("AuthConfiguration", new AuthConfiguration { TenantId = TokenWorld.Tenant }.ToString());
    }

    private static ApiTrustService Service(TokenWorld world, IAuthEvents? events = null) =>
        new(world.Configuration, world.Validator, new AllClientsAuthorizer(), events ?? new AuthEvents());
    private sealed class CountingAuthorizer : IClientAuthorizer
    {
        internal int Calls { get; private set; }
        public ValueTask<bool> IsAuthorizedAsync(ApiPrincipal principal, long clientId, CancellationToken cancellationToken = default)
        {
            Calls++; return ValueTask.FromResult(clientId is 1 or 3);
        }
    }
}
