using Microsoft.Extensions.DependencyInjection.Extensions;
using TaxCredit.Api.Hosting;
using TaxCredit.Application.Features.Ai.Briefs;
using TaxCredit.Application.Features.Ai.Capabilities;
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
        // The shared mediator is singleton; these lazy streams must resolve handlers from the HTTP request scope.
        services.AddKeyedScoped<IMediator, Mediator>(MediatorKey);
        services.AddCapabilityServices();
        services.AddScoped<ICapabilityReadBridge, CanonicalCapabilityReads>();
        foreach (var page in new[] { "portfolio", "unit", "employee" })
        {
            services.AddScoped<IAiPageCollaborator>(provider =>
                new CanonicalPageReads(page, provider.GetRequiredService<IMediator>()));
        }
        services.AddAiCapabilityHandlers();
        services.AddAiStreamHandlers();
    }
}
