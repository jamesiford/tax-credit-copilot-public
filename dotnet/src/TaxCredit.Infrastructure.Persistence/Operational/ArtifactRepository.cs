using System.Globalization;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.Operational;

/// <summary>Immutable artifact metadata and download attempts; bytes are deliberately outside this repository.</summary>
public sealed class ArtifactRepository(PersistenceDatabase database) : IArtifactRepository
{
    private static readonly string[] Columns =
    [
        "artifact_id", "kind", "client_id", "program_code", "tax_year", "run_id", "rule_pack_version", "container_name",
        "blob_path", "file_name", "content_type", "size_bytes", "sha256", "created_by", "created_at", "retain_until", "superseded_at",
    ];
    private static readonly string[] AccessColumns = ["access_id", "artifact_id", "client_id", "user_upn", "user_oid", "accessed_at", "outcome"];
    private static string Select => "SELECT " + string.Join(", ", Columns) + " FROM {ops.artifact}";

    /// <inheritdoc />
    public ArtifactMetadata Record(ArtifactMetadata artifact)
    {
        ArgumentNullException.ThrowIfNull(artifact);
        Validate(artifact);
        return database.Transact(session =>
        {
            if (session.QueryExempt(SqlExemption.ChannelIdentity, "SELECT artifact_id FROM {ops.artifact} WHERE artifact_id = ? "
                + "OR (container_name = ? AND blob_path = ?)", artifact.ArtifactId, artifact.ContainerName, artifact.BlobPath).Count > 0)
            {
                throw new InvalidOperationException("An artifact identity or immutable blob path is already recorded.");
            }

            if (artifact.Kind == "claim_package")
            {
                session.Execute(artifact.ClientId!.Value, "UPDATE {ops.artifact} SET superseded_at = ? WHERE {tenant} AND kind = ? "
                    + "AND (tax_year = ? OR (tax_year IS NULL AND ? IS NULL)) AND superseded_at IS NULL",
                    OpsRow.Timestamp(session, artifact.CreatedAt), artifact.Kind, artifact.TaxYear, artifact.TaxYear);
            }

            object?[] values =
            [
                artifact.ArtifactId, artifact.Kind, artifact.ClientId, artifact.ProgramCode, artifact.TaxYear, artifact.RunId, artifact.RulePackVersion,
                artifact.ContainerName, artifact.BlobPath, artifact.FileName, artifact.ContentType, artifact.SizeBytes, artifact.Sha256,
                artifact.CreatedBy, OpsRow.Timestamp(session, artifact.CreatedAt), artifact.RetainUntil, OpsRow.Timestamp(session, artifact.SupersededAt),
            ];
            if (artifact.ClientId is { } client)
            {
                session.Insert(client, "ops.artifact", Columns, [values]);
            }
            else
            {
                session.InsertExempt(SqlExemption.ChannelIdentity, "ops.artifact", Columns, [values]);
            }

            return artifact;
        });
    }

    /// <inheritdoc />
    public ArtifactMetadata? Find(string artifactId)
    {
        using var session = database.Open();
        return session.QueryExempt(SqlExemption.ChannelIdentity, Select + " WHERE artifact_id = ?", artifactId).Select(Hydrate).SingleOrDefault();
    }

    /// <inheritdoc />
    public IReadOnlyList<ArtifactMetadata> Live(long clientId, string? kind = null, long? taxYear = null)
    {
        using var session = database.Open();
        var sql = Select + " WHERE {tenant} AND superseded_at IS NULL";
        var args = new List<object?>();
        if (kind is not null)
        {
            sql += " AND kind = ?";
            args.Add(kind);
        }

        if (taxYear is not null)
        {
            sql += " AND tax_year = ?";
            args.Add(taxYear);
        }

        return session.Query(clientId, sql + " ORDER BY created_at, artifact_id", args.ToArray()).Select(Hydrate).ToArray();
    }

    /// <inheritdoc />
    public ArtifactAccess RecordAccess(ArtifactAccess access)
    {
        ArgumentNullException.ThrowIfNull(access);
        if (access.Outcome is not ("served" or "denied" or "missing"))
        {
            throw new ArgumentException("Unknown artifact access outcome.", nameof(access));
        }

        return database.Transact(session =>
        {
            if (session.QueryExempt(SqlExemption.ChannelIdentity, "SELECT access_id FROM {ops.artifact_access} WHERE access_id = ?", access.AccessId).Count != 0)
            {
                throw new InvalidOperationException("The artifact access identity is already recorded.");
            }

            var metadata = session.QueryExempt(SqlExemption.ChannelIdentity, "SELECT client_id FROM {ops.artifact} WHERE artifact_id = ?", access.ArtifactId);
            if (access.Outcome == "served" && (metadata.Count != 1 || new OpsRow(metadata[0]).OptionalLong("client_id") != access.ClientId))
            {
                throw new InvalidOperationException("A served access must name an artifact belonging to its client.");
            }

            object?[] values = [access.AccessId, access.ArtifactId, access.ClientId, access.UserUpn, access.UserOid, OpsRow.Timestamp(session, access.AccessedAt), access.Outcome];
            if (access.ClientId is { } client)
            {
                session.Insert(client, "ops.artifact_access", AccessColumns, [values]);
            }
            else
            {
                session.InsertExempt(SqlExemption.ChannelIdentity, "ops.artifact_access", AccessColumns, [values]);
            }

            return access;
        });
    }

    /// <inheritdoc />
    public IReadOnlyList<ArtifactAccess> Accesses(long clientId)
    {
        using var session = database.Open();
        return session.Query(clientId, "SELECT " + string.Join(", ", AccessColumns)
            + " FROM {ops.artifact_access} WHERE {tenant} ORDER BY accessed_at, access_id").Select(values =>
            {
                var r = new OpsRow(values);
                return new ArtifactAccess(r.Required("access_id"), r.Required("artifact_id"), r.OptionalLong("client_id"),
                    r.Required("user_upn"), r.Text("user_oid"), r.Instant("accessed_at")!.Value, r.Required("outcome"));
            }).ToArray();
    }

    private static void Validate(ArtifactMetadata artifact)
    {
        if (artifact.Kind is not ("claim_package" or "rule_source") || artifact.SizeBytes < 0)
        {
            throw new ArgumentException("Invalid artifact kind or byte count.", nameof(artifact));
        }

        if (artifact.Kind == "claim_package" && (artifact.ClientId is null || artifact.RunId is null))
        {
            throw new ArgumentException("A claim package must belong to one client and one run.", nameof(artifact));
        }

        if (artifact.ContainerName == "outputs" && (artifact.ClientId is null
            || !artifact.BlobPath.StartsWith(artifact.ClientId.Value.ToString(CultureInfo.InvariantCulture) + "/", StringComparison.Ordinal)))
        {
            throw new ArgumentException("An output path must carry its client's prefix.", nameof(artifact));
        }
    }

    private static ArtifactMetadata Hydrate(IReadOnlyDictionary<string, object?> values)
    {
        var r = new OpsRow(values);
        return new ArtifactMetadata
        {
            ArtifactId = r.Required("artifact_id"),
            Kind = r.Required("kind"),
            ClientId = r.OptionalLong("client_id"),
            ProgramCode = r.Text("program_code"),
            TaxYear = r.OptionalLong("tax_year"),
            RunId = r.Text("run_id"),
            RulePackVersion = r.Text("rule_pack_version"),
            ContainerName = r.Required("container_name"),
            BlobPath = r.Required("blob_path"),
            FileName = r.Required("file_name"),
            ContentType = r.Required("content_type"),
            SizeBytes = r.Long("size_bytes"),
            Sha256 = r.Required("sha256").Trim(),
            CreatedBy = r.Required("created_by"),
            CreatedAt = r.Instant("created_at")!.Value,
            RetainUntil = r.Day("retain_until"),
            SupersededAt = r.Instant("superseded_at"),
        };
    }
}
