using System.Runtime.CompilerServices;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai;
using TaxCredit.Infrastructure.Ai.Runtime;
using TaxCredit.Infrastructure.Ai.Telemetry;

namespace TaxCredit.ServiceDefaults.Hosting;

internal static class RuntimeAiRegistration
{
    private static readonly string[] Offline = ["foundry"];
    internal static void AddRuntimeAi(this IServiceCollection services, RuntimeConfiguration settings)
    {
        var providers = new ProviderRegistry();
        providers.Register("foundry", () => new OfflineRuntime(!string.IsNullOrEmpty(settings.Get("FOUNDRY_PROJECT_ENDPOINT"))));
        services.AddTaxCreditAi(providers, Enum.GetValues<ModelRole>().ToDictionary(role => role,
            _ => (IReadOnlyList<string>)Offline), [], new ActivityAiTelemetry(Offline),
            new AiRuntimeOptions(), services.Last(d => d.ServiceType == typeof(RuntimeSources)).ImplementationInstance as TimeProvider);
    }

    private sealed class OfflineRuntime(bool configured) : IAgentRuntime
    {
        public string Name => "foundry";
        public bool ReadyFor(string agentName) => false;
        public string? VersionOf(string agentName) => null;
        public ProviderStatus Status() => configured
            ? new(Name, ProviderState.Unavailable, "No Foundry invocation factory is installed")
            : new(Name, ProviderState.Disabled, "FOUNDRY_PROJECT_ENDPOINT is not set");
        public async IAsyncEnumerable<ModelEvent> StreamAsync(NarrationRequest request,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            await Task.CompletedTask.ConfigureAwait(false);
            throw new ModelException(ModelErrorKind.NarrationUnavailable, "offline");
#pragma warning disable CS0162
            yield break;
#pragma warning restore CS0162
        }
    }
}
