extern alias AzureIdentity;
using System.ClientModel.Primitives;
using Azure.Core;
using Microsoft.Extensions.AI;
using OpenAI;
using DefaultAzureCredential = AzureIdentity::Azure.Identity.DefaultAzureCredential;

namespace TaxCredit.Orchestrator.Framework;

/// <summary>Foundry-only access uses the official OpenAI adapter inside the actual framework loop.</summary>
public static class FoundryModelClientFactory
{
    private static readonly Lazy<TokenCredential> DefaultCredential = new(() => new DefaultAzureCredential());

    /// <summary>The project URL is not the chat-completions endpoint used by the hosted runtime.</summary>
    public static Uri OpenAiBase(Uri projectEndpoint)
    {
        ArgumentNullException.ThrowIfNull(projectEndpoint);
        if (projectEndpoint.Scheme != Uri.UriSchemeHttps || !string.IsNullOrEmpty(projectEndpoint.UserInfo) ||
            !string.IsNullOrEmpty(projectEndpoint.Query) || !string.IsNullOrEmpty(projectEndpoint.Fragment))
        {
            throw new ArgumentException("The Foundry project endpoint must be an HTTPS URL without credentials.", nameof(projectEndpoint));
        }
        var host = projectEndpoint.Host;
        const string suffix = ".services.ai.azure.com";
        if (host.EndsWith(suffix, StringComparison.OrdinalIgnoreCase))
        {
            host = host[..^suffix.Length] + ".openai.azure.com";
        }
        return new UriBuilder(projectEndpoint) { Host = host, Path = "/openai/v1/", Query = "", Fragment = "" }.Uri;
    }

    /// <summary>Authentication is acquired for each admitted request; no API key or inbound credential is used.</summary>
    public static IChatClient Create(Uri projectEndpoint, string deployment,
        TokenCredential? credential = null, HttpClient? transport = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(deployment);
        var options = new OpenAIClientOptions
        {
            Endpoint = OpenAiBase(projectEndpoint),
            RetryPolicy = new ClientRetryPolicy(0),
        };
        if (transport is not null) { options.Transport = new HttpClientPipelineTransport(transport); }
        var auth = new BearerTokenPolicy(credential ?? DefaultCredential.Value, "https://cognitiveservices.azure.com/.default");
#pragma warning disable OPENAI001 // Token-policy authentication is explicitly approved for this hosted preview integration.
        return new SamplingClient(new OpenAIClient(auth, options).GetChatClient(deployment).AsIChatClient(), deployment);
#pragma warning restore OPENAI001
    }

    private sealed class SamplingClient(IChatClient inner, string deployment) : DelegatingChatClient(inner)
    {
        public override Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
            CancellationToken cancellationToken = default)
        {
            var safe = options?.Clone() ?? new ChatOptions();
            if (deployment.StartsWith("gpt-5", StringComparison.OrdinalIgnoreCase))
            {
                safe.Temperature = null;
                safe.TopP = null;
            }
            else { safe.Temperature ??= 0.2f; }
            return base.GetResponseAsync(messages, safe, cancellationToken);
        }
    }
}
