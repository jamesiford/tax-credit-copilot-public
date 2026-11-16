using Azure.Core;
using Microsoft.Extensions.AI;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Budget;
using TaxCredit.Orchestrator.Boundary;
using TaxCredit.Orchestrator.Composition;
using TaxCredit.Orchestrator.Framework;
using TaxCredit.Orchestrator.Planning;
using TaxCredit.Orchestrator.Turns;
using ChatMessage = Microsoft.Extensions.AI.ChatMessage;

namespace TaxCredit.Orchestrator.Hosting;

/// <summary>The executable root binds only REST and model adapters; it has no payroll/database repository dependency.</summary>
public sealed class OrchestratorRuntime : IDisposable
{
    private static readonly Action<ILogger, Exception?> SyntheticKnowledge = LoggerMessage.Define(LogLevel.Warning,
        new EventId(2, "synthetic_knowledge"), "Synthetic reference source is enabled; its content is not statute.");
    private readonly HttpClient _gatewayHttp;
    private readonly ProviderClients? _providers;
    private readonly FrameworkModelRouter? _models;
    private readonly SystemDiagnosticNetworkProbe? _networkDiagnostics;

    /// <summary>Injected collaborators make production composition hermetic without replacing the SDK transport.</summary>
    public OrchestratorRuntime(RuntimeSettings settings, TokenCredential credential, ILoggerFactory loggerFactory,
        HttpClient? gatewayHttp = null, IReadOnlyDictionary<string, IChatClient>? modelClients = null,
        bool? supportsTools = null, IReferenceSource? knowledge = null, IDebugDiagnostics? diagnostics = null)
    {
        _gatewayHttp = gatewayHttp ?? GatewayClient.CreateHttpClient();
        var gateway = new GatewayClient(_gatewayHttp, new AzureCredentialTokenProvider(credential, settings.Gateway.Scope), settings.Gateway);
        var catalog = new ModelToolCatalog(new CapabilityCatalog());
        var workflow = new WorkflowBridge(gateway, catalog, confirmationLifetime: settings.ConfirmationLifetime);
        var store = new ConversationStore(settings.StateLifetime);
        if (modelClients is null) { _providers = new ProviderClients(settings, credential); }
        var clients = modelClients ?? _providers!.Clients;
        if (clients.Count != 0)
        {
            _models = new FrameworkModelRouter(clients, settings.Chains,
                new InMemoryTokenBudget(settings.Ai.GlobalDailyTokens, settings.Ai.PrincipalDailyTokens),
                settings.Ai, () => workflow.CurrentIdentity?.TenantId + ":" + workflow.CurrentIdentity?.Oid,
                supportsTools: clients.Keys.ToDictionary(name => name,
                    name => name != "gateway" || settings.Flag("AI_GATEWAY_SUPPORTS_TOOLS", true)));
        }
        var toolsAvailable = supportsTools ?? _providers?.SupportsTools ?? true;
        if (settings.KnowledgeEnabled && knowledge is null)
        {
            knowledge = new SyntheticReferenceSource();
            SyntheticKnowledge(loggerFactory.CreateLogger<OrchestratorRuntime>(), null);
        }
        var planner = new TurnPlanner(catalog, new FrameworkToolLoop(catalog), _models, toolsAvailable,
            knowledge, settings.KnowledgeEnabled, settings.KnowledgeTop);
        var pipeline = new TurnPipeline(gateway, catalog, planner, store, workflow, settings.Turns,
            loggerFactory.CreateLogger<TurnPipeline>());
        if (diagnostics is null && settings.Identity.DebugWhoami)
        {
            _networkDiagnostics = new SystemDiagnosticNetworkProbe();
            ModelDiagnosticCall? probe = clients.TryGetValue("foundry", out var foundry) ? async (endpoint, _, token) =>
            {
                var response = await foundry.GetResponseAsync([new ChatMessage(ChatRole.User, "Reply with OK.")],
                    new ChatOptions { AdditionalProperties = new() { ["tcc.role"] = ModelRole.Narrator } }, token).ConfigureAwait(false);
                return new ModelProbeObservation(FoundryModelClientFactory.OpenAiBase(endpoint), response.Text.Length);
            }
            : null;
            diagnostics = new SafeDebugDiagnostics(new DiagnosticOptions(
                projectEndpoint: settings.Text("FOUNDRY_PROJECT_ENDPOINT"),
                gatewayUrl: settings.Text("CHANNEL_GATEWAY_URL"), providers: settings.Providers,
                environment: new Dictionary<string, string?>
                {
                    ["FOUNDRY_MODEL"] = settings.Deployment(ModelRole.Narrator, "foundry"),
                    ["AI_PROVIDER_CHAIN"] = string.Join(",", settings.Providers),
                }), _networkDiagnostics, probe);
        }
        Host = new ChannelHost(settings.Identity, pipeline, store,
            new DebugCommandHandler(settings.Identity, diagnostics, loggerFactory.CreateLogger<DebugCommandHandler>()),
            settings.Providers, _models is not null, _models is not null && toolsAvailable);
    }

    /// <summary>The installed Responses host receives the fully composed text handler only.</summary>
    public ChannelHost Host { get; }
    /// <inheritdoc/>
    public void Dispose()
    {
        if (_providers is null) { _models?.Dispose(); }
        _providers?.Dispose();
        _networkDiagnostics?.Dispose();
        _gatewayHttp.Dispose();
    }
}
