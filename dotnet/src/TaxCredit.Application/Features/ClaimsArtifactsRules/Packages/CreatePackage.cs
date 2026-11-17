using System.Security.Cryptography;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Ai.Artifacts;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Packages;

/// <summary>Publishes a new immutable package generation from stored results, never from payroll.</summary>
public sealed record CreatePackage(long ClientId, int TaxYear, string Actor) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}

internal sealed class CreatePackageHandler(ClaimPackageBuilder builder, IArtifactByteStore bytes,
    IArtifactRepository artifacts, IClock clock, IIdSource ids) : IRequestHandler<CreatePackage, object>
{
    public async ValueTask<object> Handle(CreatePackage request, CancellationToken cancellationToken)
    {
        var package = builder.Build(request.ClientId, request.TaxYear, request.Actor);
        var generation = ids.NewId().ToString("N");
        var metadata = new ArtifactMetadata
        {
            ArtifactId = ids.NewId().ToString("N"),
            Kind = "claim_package",
            ClientId = request.ClientId,
            ProgramCode = package.ProgramCode,
            TaxYear = request.TaxYear,
            RunId = package.RunId,
            ContainerName = "outputs",
            BlobPath = $"{request.ClientId}/{package.RunId}/{generation}/{package.FileName}",
            FileName = package.FileName,
            ContentType = ClaimPackageBuilder.ContentType,
            SizeBytes = package.Data.LongLength,
            Sha256 = Convert.ToHexStringLower(SHA256.HashData(package.Data)),
            CreatedBy = request.Actor,
            CreatedAt = FeatureValues.Now(clock),
            RetainUntil = DateOnly.FromDateTime(clock.UtcNow.UtcDateTime.AddDays(2555)),
        };
        await bytes.PutAsync(metadata.ContainerName, metadata.BlobPath, package.Data, metadata.ContentType, cancellationToken).ConfigureAwait(false);
        var stored = artifacts.Record(metadata);
        var result = PackageMetadata.Body(stored);
        result.Add("rows", package.Rows);
        return result;
    }
}

internal static class PackageMetadata
{
    internal static Dictionary<string, object?> Body(ArtifactMetadata value) => new(StringComparer.Ordinal)
    {
        ["artifact_id"] = value.ArtifactId,
        ["kind"] = value.Kind,
        ["client_id"] = value.ClientId,
        ["program_code"] = value.ProgramCode,
        ["tax_year"] = value.TaxYear,
        ["run_id"] = value.RunId,
        ["file_name"] = value.FileName,
        ["content_type"] = value.ContentType,
        ["size_bytes"] = value.SizeBytes,
        ["sha256"] = value.Sha256,
        ["created_by"] = value.CreatedBy,
        ["created_at"] = value.CreatedAt.IsoFormat(),
    };
}
