using System.Text.Json;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Transport-neutral download; its bytes and digest come from the approved saved documents.</summary>
public sealed record DraftDownload(byte[] Bytes, string Sha256, string FileName);

/// <summary>Export records who took a proposal, never installs it in the runtime registry.</summary>
public sealed record ExportDraftCommand(string DraftId, JsonElement? Body) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}
internal sealed class ExportDraftHandler(DraftLifecycle lifecycle, IProgramDraftRepository repository, DraftCustomerData customerData, IClock clock)
    : IRequestHandler<ExportDraftCommand, object>
{
    public ValueTask<object> Handle(ExportDraftCommand request, CancellationToken cancellationToken)
    {
        var body = FeatureValues.Document(request.Body);
        var draft = lifecycle.Load(request.DraftId);
        Check(draft);
        if (customerData.Scan(draft).Count > 0) { throw new CustomerDataInDraft("The documents may hold customer data. Remove it and request review again."); }
        if (FeatureValues.Flag(body, "write_local")) { throw new DraftsRunsRefusalException(422, new { code = "local_write_refused", reason = "Writing into the authored rules folder is disabled; export and commit the reviewed files instead." }); }
        var bundle = DraftBundle.Build(draft, repository.Events(draft.DraftId));
        lifecycle.Save(draft, draft with { Status = DraftStatus.Exported, ExportedAt = draft.ExportedAt ?? FeatureValues.Now(clock), ExportSha256 = bundle.Sha256 },
            body, "exported", new PyDict().Add("bundle_sha256", bundle.Sha256).Add("first_export", draft.Status == DraftStatus.ApprovedForExport).Add("wrote_local_files", new List<object?>()));
        return ValueTask.FromResult<object>(new DraftDownload(bundle.Bytes, bundle.Sha256, draft.ProposedCode.ToLowerInvariant() + "-bundle.zip"));
    }

    internal static void Check(ProgramDraft draft)
    {
        if (draft.Status is not (DraftStatus.ApprovedForExport or DraftStatus.Exported)) { throw new InvalidTransition("Only an approved draft has an export bundle."); }
        if (!DraftViews.Current(draft) || draft.ApprovedSha256 != draft.ContentSha256) { throw new ReviewRefused("The documents differ from those approved."); }
    }
}

/// <summary>Inspects the real deterministic bundle without changing the draft or audit history.</summary>
public sealed record DraftManifestQuery(string DraftId) : IQuery<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}
internal sealed class DraftManifestHandler(DraftLifecycle lifecycle, IProgramDraftRepository repository) : IRequestHandler<DraftManifestQuery, object>
{
    public ValueTask<object> Handle(DraftManifestQuery request, CancellationToken cancellationToken)
    {
        var draft = lifecycle.Load(request.DraftId);
        ExportDraftHandler.Check(draft);
        var bundle = DraftBundle.Build(draft, repository.Events(draft.DraftId));
        return ValueTask.FromResult<object>(bundle.Manifest.Add("bundle_sha256", bundle.Sha256).Add("bundle_bytes", (long)bundle.Bytes.Length));
    }
}
