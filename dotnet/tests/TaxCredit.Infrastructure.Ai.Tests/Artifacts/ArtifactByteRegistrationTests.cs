using Azure.Core;
using Azure.Storage.Blobs;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Ports.Ai.Artifacts;
using TaxCredit.Infrastructure.Ai.Artifacts;

namespace TaxCredit.Infrastructure.Ai.Tests.Artifacts;

public sealed class ArtifactByteRegistrationTests
{
    [Fact]
    public void Local_registration_refuses_deployment_without_creating_a_directory()
    {
        var services = new ServiceCollection();
        var root = Path.Combine(Path.GetTempPath(), "tcc-local-registration-" + Guid.NewGuid().ToString("N"));
        var error = Assert.Throws<ArtifactByteException>(() => services.AddLocalArtifactBytes(root, "enterprise"));
        Assert.Equal("local_write_refused", error.Code);
        Assert.Empty(services);
        Assert.False(Directory.Exists(root));
        services.AddLocalArtifactBytes(root, "local");
        var registration = Assert.Single(services);
        Assert.False(Assert.IsType<LocalArtifactByteStore>(registration.ImplementationInstance).IsDurable);
    }

    [Theory]
    [InlineData("http://storage.invalid")]
    [InlineData("https://storage.invalid/?sig=forbidden")]
    [InlineData("https://name@storage.invalid")]
    [InlineData("https://storage.invalid/#fragment")]
    [InlineData("https://storage.invalid/container")]
    public void Blob_registration_rejects_nonprivate_credential_forms(string endpoint)
    {
        var services = new ServiceCollection();
        Assert.Throws<ArgumentException>(() => services.AddBlobArtifactBytes(new Uri(endpoint), new NeverCalledCredential()));
        Assert.Empty(services);
    }

    [Fact]
    public void Blob_registration_does_not_acquire_a_token_or_contact_a_service()
    {
        var services = new ServiceCollection();
        services.AddBlobArtifactBytes(new Uri("https://storage.invalid"), new NeverCalledCredential(), new BlobClientOptions());
        var descriptor = Assert.Single(services);
        Assert.True(Assert.IsType<BlobArtifactByteStore>(descriptor.ImplementationInstance).IsDurable);
    }

    [Fact]
    public void Blob_registration_requires_an_absolute_account_url()
    {
        var services = new ServiceCollection();
        Assert.Throws<ArgumentException>(() =>
            services.AddBlobArtifactBytes(new Uri("container", UriKind.Relative), new NeverCalledCredential()));
        Assert.Empty(services);
    }

    private sealed class NeverCalledCredential : TokenCredential
    {
        public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken) =>
            throw new InvalidOperationException("Registration must not acquire credentials.");

        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken) =>
            throw new InvalidOperationException("Registration must not acquire credentials.");
    }
}
