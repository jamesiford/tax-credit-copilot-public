using System.Globalization;
using System.Security.Cryptography;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Ai.Artifacts;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Packages;

/// <summary>Download ownership is checked after existence and before accessing private storage.</summary>
public sealed record DownloadArtifact(long ClientId, string ArtifactId, ApiPrincipal Principal) : IQuery<ArtifactDownload>;

/// <summary>An authorized, integrity-checked byte response with no storage credentials.</summary>
public sealed record ArtifactDownload(byte[] Data, string FileName, string ContentType, string Sha256);

internal sealed class DownloadArtifactHandler(IArtifactRepository artifacts, IArtifactByteStore bytes,
    IClientAuthorizer authorizer, IClock clock, IIdSource ids) : IRequestHandler<DownloadArtifact, ArtifactDownload>
{
    public async ValueTask<ArtifactDownload> Handle(DownloadArtifact request, CancellationToken cancellationToken)
    {
        var artifact = artifacts.Find(request.ArtifactId) ?? throw new FeatureRefusalException(404, "no such artifact");
        if (artifact.ClientId != request.ClientId
            || !await authorizer.IsAuthorizedAsync(request.Principal, request.ClientId, cancellationToken).ConfigureAwait(false))
        {
            Audit(request.Principal, artifact, "denied");
            throw new FeatureRefusalException(403, "not authorized for this artifact");
        }
        if (!ValidMetadata(artifact))
        {
            Audit(request.Principal, artifact, "denied");
            throw new FeatureRefusalException(422, "invalid artifact metadata");
        }
        var data = await bytes.GetAsync(artifact.ContainerName, artifact.BlobPath, cancellationToken).ConfigureAwait(false);
        if (data is null)
        {
            Audit(request.Principal, artifact, "missing");
            throw new FeatureRefusalException(404, "the artifact is registered but its file is missing");
        }
        var hash = Convert.ToHexStringLower(SHA256.HashData(data));
        if (data.LongLength != artifact.SizeBytes || hash != artifact.Sha256)
        {
            Audit(request.Principal, artifact, "missing");
            throw new FeatureRefusalException(503, "the stored artifact failed its integrity check");
        }
        Audit(request.Principal, artifact, "served");
        return new ArtifactDownload(data, artifact.FileName, artifact.ContentType, hash);
    }

    private static bool ValidMetadata(ArtifactMetadata artifact) =>
        artifact.Kind == "claim_package" && artifact.ContainerName == "outputs" && artifact.ClientId is > 0
        && !string.IsNullOrEmpty(artifact.RunId)
        && artifact.BlobPath.StartsWith(artifact.ClientId.Value.ToString(CultureInfo.InvariantCulture) + "/", StringComparison.Ordinal)
        && artifact.BlobPath.Split('/').All(p => p.Length > 0 && p is not ("." or "..") && !p.Contains('\\') && !p.Contains(':'))
        && artifact.ContentType == ClaimPackageBuilder.ContentType
        && artifact.FileName.Length > 0 && !artifact.FileName.Any(c => c is '/' or '\\' or '"' or '\r' or '\n')
        && artifact.SizeBytes >= 0 && artifact.Sha256.Length == 64 && artifact.Sha256.All(char.IsAsciiHexDigitLower);

    private void Audit(ApiPrincipal principal, ArtifactMetadata artifact, string outcome) =>
        artifacts.RecordAccess(new ArtifactAccess(ids.NewId().ToString("N"), artifact.ArtifactId, artifact.ClientId,
            principal.Actor, principal.Oid, FeatureValues.Now(clock), outcome));
}
