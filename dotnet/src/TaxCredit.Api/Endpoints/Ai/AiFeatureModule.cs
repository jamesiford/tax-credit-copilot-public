using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Api.Hosting;
using TaxCredit.Application.Features.Ai.Briefs;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Application.Features.Ai.Capabilities.Bindings;
using TaxCredit.Application.Features.Ai.Chat;
using TaxCredit.Application.Features.Ai.Streams;
using TaxCredit.Application.Messaging;

namespace TaxCredit.Api.Endpoints.Ai;

/// <summary>Owned composition binds inward features without changing the host's provider graph.</summary>
public sealed class AiFeatureModule : IFeatureModule
{
    internal const string MediatorKey = "ai-request";

    /// <inheritdoc />
    public void ConfigureServices(IServiceCollection services, IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.AddTaxCreditPromptAgents();
        services.TryAddScoped<IPageFactSource, StoredPageFacts>();
        services.TryAddScoped<IPageScope, StoredPageScope>();
        services.TryAddScoped<IChatClientSource, StoredChatClients>();
        services.TryAddScoped<IChatFactSource, CapabilityChatFacts>();
        services.TryAddScoped<PageBriefBuilder>();
        services.TryAddScoped<ChatPlanner>();
        // Lazy streams resolve handlers from the HTTP request scope.
        services.AddKeyedScoped<IMediator, Mediator>(MediatorKey);
        services.AddCapabilityServices();
        services.AddScoped<CanonicalCapabilityReads>();
        services.AddScoped<CapabilityPackageTickets>();
        services.AddScoped<CapabilityDecisionPreviews>();
        services.AddScoped<CapabilityOperationalPreviews>();
        services.AddScoped<CapabilityRiskReads>();
        services.AddScoped<ICapabilityReadBridge, ApplicationCapabilityReads>();
        services.AddScoped<ICapabilityWriteBridge, ApplicationCapabilityWrites>();
        foreach (var page in new[] { "portfolio", "unit", "employee" })
        {
            services.AddScoped<IAiPageCollaborator>(provider =>
                new CanonicalPageReads(page, provider.GetRequiredService<IMediator>()));
        }
        services.AddAiCapabilityHandlers();
        services.AddAiStreamHandlers();
    }
}
