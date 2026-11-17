using System.Text.Json;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Proposes new statute without installing it.</summary>
public sealed record CreateDraftCommand(JsonElement? Body) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}
internal sealed class CreateDraftHandler(DraftLifecycle lifecycle) : IRequestHandler<CreateDraftCommand, object>
{
    public ValueTask<object> Handle(CreateDraftCommand request, CancellationToken cancellationToken) =>
        ValueTask.FromResult<object>(DraftViews.Detail(lifecycle.Create(FeatureValues.Document(request.Body))));
}

/// <summary>Replaces all draft documents at an expected version.</summary>
public sealed record EditDraftCommand(string DraftId, JsonElement? Body) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}
internal sealed class EditDraftHandler(DraftLifecycle lifecycle) : IRequestHandler<EditDraftCommand, object>
{
    public ValueTask<object> Handle(EditDraftCommand request, CancellationToken cancellationToken) =>
        ValueTask.FromResult<object>(DraftViews.Detail(lifecycle.Edit(request.DraftId, FeatureValues.Document(request.Body))));
}

/// <summary>Stores exact validation counts and bounded findings.</summary>
public sealed record ValidateDraftCommand(string DraftId, JsonElement? Body) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}
internal sealed class ValidateDraftHandler(DraftLifecycle lifecycle) : IRequestHandler<ValidateDraftCommand, object>
{
    public ValueTask<object> Handle(ValidateDraftCommand request, CancellationToken cancellationToken) =>
        ValueTask.FromResult<object>(lifecycle.Validate(request.DraftId, FeatureValues.Document(request.Body)));
}

/// <summary>Submits only a current, valid document set.</summary>
public sealed record RequestDraftReviewCommand(string DraftId, JsonElement? Body) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}
internal sealed class RequestDraftReviewHandler(DraftLifecycle lifecycle) : IRequestHandler<RequestDraftReviewCommand, object>
{
    public ValueTask<object> Handle(RequestDraftReviewCommand request, CancellationToken cancellationToken) =>
        ValueTask.FromResult<object>(DraftViews.Detail(lifecycle.RequestReview(request.DraftId, FeatureValues.Document(request.Body))));
}

/// <summary>Approves for export or requests changes with separation of authors and reviewers.</summary>
public sealed record ReviewDraftCommand(string DraftId, JsonElement? Body) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}
internal sealed class ReviewDraftHandler(DraftLifecycle lifecycle) : IRequestHandler<ReviewDraftCommand, object>
{
    public ValueTask<object> Handle(ReviewDraftCommand request, CancellationToken cancellationToken) =>
        ValueTask.FromResult<object>(DraftViews.Detail(lifecycle.Review(request.DraftId, FeatureValues.Document(request.Body))));
}

/// <summary>Closes an unexported proposal while retaining its history.</summary>
public sealed record WithdrawDraftCommand(string DraftId, JsonElement? Body) : ICommand<object>, IRequirePolicy
{
    /// <inheritdoc />
    public Policy Policy => Policy.Writer;
}
internal sealed class WithdrawDraftHandler(DraftLifecycle lifecycle) : IRequestHandler<WithdrawDraftCommand, object>
{
    public ValueTask<object> Handle(WithdrawDraftCommand request, CancellationToken cancellationToken) =>
        ValueTask.FromResult<object>(DraftViews.Detail(lifecycle.Withdraw(request.DraftId, FeatureValues.Document(request.Body))));
}
