using Azure.Core;
using Azure.Identity;
using Azure.Storage.Blobs;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Ai.Artifacts;

namespace TaxCredit.Infrastructure.Ai.Artifacts;

/// <summary>Composition hooks; metadata, access checks and exporters remain host/Persistence-owned.</summary>
public static class ArtifactByteRegistration
{
    /// <summary>Registers a single development byte store; construction refuses non-local environments.</summary>
    public static IServiceCollection AddLocalArtifactBytes(this IServiceCollection services, string root, string environment)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.AddSingleton<IArtifactByteStore>(new LocalArtifactByteStore(root, environment));
        return services;
    }

    /// <summary>Registers a private Blob SDK client using an injected or default Entra credential.</summary>
    public static IServiceCollection AddBlobArtifactBytes(this IServiceCollection services, Uri accountUrl,
        TokenCredential? credential = null, BlobClientOptions? options = null)
    {
        ArgumentNullException.ThrowIfNull(services);
        ArgumentNullException.ThrowIfNull(accountUrl);
        if (!accountUrl.IsAbsoluteUri || accountUrl.Scheme != Uri.UriSchemeHttps || !string.IsNullOrEmpty(accountUrl.UserInfo) ||
            !string.IsNullOrEmpty(accountUrl.Query) || !string.IsNullOrEmpty(accountUrl.Fragment) ||
            accountUrl.AbsolutePath != "/")
        {
            throw new ArgumentException("Blob storage requires an HTTPS account URL without credentials.", nameof(accountUrl));
        }
        services.AddSingleton<IArtifactByteStore>(new BlobArtifactByteStore(
            new BlobServiceClient(accountUrl, credential ?? new DefaultAzureCredential(), options)));
        return services;
    }
}
