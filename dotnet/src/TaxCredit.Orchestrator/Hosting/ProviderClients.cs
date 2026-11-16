using System.Text.Json;
using System.Text.Json.Nodes;
using Azure.Core;
using Microsoft.Extensions.AI;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Auth;
using TaxCredit.Infrastructure.Ai.Gateway;
using TaxCredit.Orchestrator.Framework;
using AiGatewaySettings = TaxCredit.Infrastructure.Ai.Gateway.GatewaySettings;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;

namespace TaxCredit.Orchestrator.Hosting;

/// <summary>Configuration selects clients explicitly; SDKs cannot discover an unrelated endpoint or API key.</summary>
public sealed class ProviderClients : IDisposable
{
    private readonly List<IDisposable> _resources = [];
    private readonly Dictionary<string, IChatClient> _clients = new(StringComparer.Ordinal);

    /// <summary>Construction validates configured providers but performs no token acquisition or network calls.</summary>
    public ProviderClients(RuntimeSettings settings, TokenCredential credential)
    {
        try
        {
            foreach (var name in settings.Providers)
            {
                var deployments = Enum.GetValues<ModelRole>().ToDictionary(role => role, role => settings.Deployment(role, name));
                _clients[name] = name == "foundry" ? Foundry(settings, credential, deployments) : Gateway(settings, credential, deployments);
            }
            SupportsTools = settings.Chains[ModelRole.Narrator].Any(name => name == "foundry" || settings.Flag("AI_GATEWAY_SUPPORTS_TOOLS", true));
        }
        catch
        {
            Dispose();
            throw;
        }
    }

    /// <summary>The registered provider dictionary has no person or conversation state.</summary>
    public IReadOnlyDictionary<string, IChatClient> Clients => _clients;
    /// <summary>A reachable Foundry member may call tools even if another chain member cannot.</summary>
    public bool SupportsTools { get; }

    private static RoleClient Foundry(RuntimeSettings settings, TokenCredential credential, Dictionary<ModelRole, string> deployments)
    {
        var endpoint = settings.Https("FOUNDRY_PROJECT_ENDPOINT");
        return new RoleClient(deployments.ToDictionary(pair => pair.Key,
            pair => FoundryModelClientFactory.Create(endpoint, pair.Value, credential)));
    }

    private PortModelClient Gateway(RuntimeSettings settings, TokenCredential credential, Dictionary<ModelRole, string> deployments)
    {
        if (!settings.Flag("AI_GATEWAY_TLS_VERIFY", true))
        {
            throw new InvalidOperationException("The hosted orchestrator requires AI_GATEWAY_TLS_VERIFY=true.");
        }
        var endpoint = settings.Https("AI_GATEWAY_ENDPOINT");
        var style = settings.Text("AI_GATEWAY_API_STYLE", "openai_v1") switch
        {
            "openai_v1" => GatewayDialect.OpenAiV1,
            "azure_deployments" => GatewayDialect.AzureDeployments,
            _ => throw new InvalidOperationException("AI_GATEWAY_API_STYLE is invalid."),
        };
        var http = new HttpClient(new SocketsHttpHandler
        {
            AllowAutoRedirect = false,
            UseCookies = false,
            ConnectTimeout = settings.Seconds("AI_GATEWAY_CONNECT_TIMEOUT_SECONDS", 5),
        })
        {
            Timeout = settings.Seconds("AI_GATEWAY_TIMEOUT_SECONDS", 30),
        };
        _resources.Add(http);
        var auth = Auth(settings, credential, http, endpoint);
        var wire = new AiGatewaySettings(endpoint, style, settings.Text("AI_GATEWAY_API_VERSION", "2024-10-21"),
            settings.Flag("AI_GATEWAY_STREAMING", true), ExtraHeaders(settings));
        return new PortModelClient(new OpenAiCompatibleChatModel(http, wire, auth), deployments);
    }

    private IRequestAuthenticator Auth(RuntimeSettings settings, TokenCredential credential, HttpClient http, Uri endpoint)
    {
        var scheme = settings.Required("AI_GATEWAY_AUTH");
        if (scheme == "none") { return new NoAuth(); }
        if (scheme == "api_key")
        {
            return new ApiKeyAuth(settings.Text("AI_GATEWAY_API_KEY_HEADER", "Authorization"),
                settings.Raw("AI_GATEWAY_API_KEY_PREFIX", "Bearer "), settings.Required("AI_GATEWAY_API_KEY"));
        }
        var source = scheme switch
        {
            "entra_token" => (IModelTokenSource)new EntraTokenSource(credential),
            "oauth_client_credentials" => new OAuthTokenSource(http, settings.Https("AI_GATEWAY_OAUTH_TOKEN_URL"),
                settings.Required("AI_GATEWAY_OAUTH_CLIENT_ID"), settings.Required("AI_GATEWAY_OAUTH_CLIENT_SECRET"),
                settings.Text("AI_GATEWAY_OAUTH_SCOPE")),
            _ => throw new InvalidOperationException("AI_GATEWAY_AUTH must explicitly select a supported scheme."),
        };
        var audience = scheme == "entra_token" ? settings.Required("AI_GATEWAY_ENTRA_AUDIENCE") :
            settings.Text("AI_GATEWAY_OAUTH_SCOPE", endpoint.GetLeftPart(UriPartial.Authority));
        var cached = new CachedTokenAuth(source, audience);
        _resources.Add(cached);
        return cached;
    }

    private static Dictionary<string, string> ExtraHeaders(RuntimeSettings settings)
    {
        var text = settings.Text("AI_GATEWAY_EXTRA_HEADERS");
        if (text.Length == 0) { return new Dictionary<string, string>(); }
        try
        {
            if (JsonNode.Parse(text) is not JsonObject obj ||
                obj.Any(pair => pair.Value is not JsonValue value || !value.TryGetValue<string>(out _)))
            {
                throw new InvalidOperationException("AI_GATEWAY_EXTRA_HEADERS must contain only string-valued headers.");
            }
            return obj.ToDictionary(pair => pair.Key, pair => pair.Value!.GetValue<string>(), StringComparer.OrdinalIgnoreCase);
        }
        catch (JsonException) { throw new InvalidOperationException("AI_GATEWAY_EXTRA_HEADERS must be a JSON object."); }
    }

    /// <inheritdoc/>
    public void Dispose()
    {
        foreach (var client in _clients.Values) { client.Dispose(); }
        foreach (var resource in Enumerable.Reverse(_resources)) { resource.Dispose(); }
    }

    private sealed class RoleClient(Dictionary<ModelRole, IChatClient> clients) : IChatClient
    {
        public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            var role = options?.AdditionalProperties?["tcc.role"] is ModelRole chosen ? chosen : ModelRole.Narrator;
            return clients[role].GetResponseAsync(messages, options, cancellationToken);
        }
        public IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages,
            ChatOptions? options = null, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public object? GetService(Type serviceType, object? serviceKey = null) => null;
        public void Dispose() { foreach (var client in clients.Values) { client.Dispose(); } }
    }
}
