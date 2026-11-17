using System.Text.Json;
using TaxCredit.Orchestrator.Workflow;

namespace TaxCredit.Orchestrator.Tests.Workflow;

internal sealed class WriteClock : TimeProvider
{
    internal DateTimeOffset Now { get; set; } = new(2030, 1, 1, 0, 0, 0, TimeSpan.Zero);
    public override DateTimeOffset GetUtcNow() => Now;
}

internal sealed class WriteGatewayFake(WriteClock clock)
{
    private readonly Dictionary<string, Ticket> _tickets = new(StringComparer.Ordinal);
    private readonly Dictionary<string, WriteGatewayReply> _results = new(StringComparer.Ordinal);
    private int _issued;
    internal List<(WriteOwner Owner, WriteGatewayRequest Request)> Calls { get; } = [];
    internal List<(string Tool, string Code, WriteOwner Owner)> Audit { get; } = [];
    internal HashSet<string> Writers { get; } = ["writer", "other-writer"];
    internal int Mutations { get; private set; }
    internal bool LoseCommitResponse { get; set; }
    internal bool OmitToken { get; set; }
    internal string? RefuseCommit { get; set; }
    internal TimeSpan GatewayLifetime { get; set; } = TimeSpan.FromMinutes(5);
    internal TaskCompletionSource? CommitEntered { get; set; }
    internal TaskCompletionSource? ReleaseCommit { get; set; }
    internal WriteRecoveryRequest? LastLookup { get; private set; }
    internal string Token => $"synthetic-confirmation-{_issued}";

    internal async Task<WriteGatewayReply> CallAsync(
        WriteOwner owner, WriteGatewayRequest request, CancellationToken cancellationToken)
    {
        Calls.Add((owner, request));
        if (!Writers.Contains(owner.PersonId))
        {
            return Record(owner, request.Tool, Error("not_authorized", 403));
        }

        if (request.Tool is "engagement_set_prepare" or "claim_package_create_prepare")
        {
            _issued++;
            _tickets[Token] = new(owner, request.Tool, request.Arguments.Clone(), clock.Now + GatewayLifetime);
            WriteGatewayReply preview = OmitToken
                ? Reply(200, new { facts = new { before = "out", after = "in" } })
                : Reply(200, new
                {
                    facts = new { confirmation = new { token = Token }, before = "out", after = "in" },
                    blocks = new[] { new { text = $"Trusted preview {Token}" } },
                });
            return Record(owner, request.Tool, preview);
        }

        if (request.Tool == "claim_package_link")
        {
            return Record(owner, request.Tool, Reply(200, new
            {
                tool = "claim_package_link",
                facts = new { link = "gateway-download", confirmation_token = Token },
            }));
        }

        CommitEntered?.TrySetResult();
        if (ReleaseCommit is not null)
        {
            await ReleaseCommit.Task.WaitAsync(cancellationToken);
        }

        if (RefuseCommit is not null)
        {
            return Record(owner, request.Tool, Error(RefuseCommit));
        }

        string? failure = Validate(owner, request);
        if (failure is not null)
        {
            return Record(owner, request.Tool, Error(failure));
        }

        if (_results.TryGetValue(request.IdempotencyKey!, out WriteGatewayReply? previous))
        {
            return Record(owner, request.Tool, previous);
        }

        _tickets[request.ConfirmationToken!].Used = true;
        Mutations++;
        WriteGatewayReply done = Reply(200, new { facts = new { recorded = true }, blocks = new[] { new { text = "Recorded." } } });
        _results.Add(request.IdempotencyKey!, done);
        Record(owner, request.Tool, done);
        if (LoseCommitResponse)
        {
            throw new TimeoutException("Synthetic response loss after dispatch.");
        }

        return done;
    }

    internal Task<WriteGatewayReply?> LookupAsync(
        WriteOwner owner, WriteRecoveryRequest request, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        LastLookup = request;
        if (owner.PersonId != "writer")
        {
            return Task.FromResult<WriteGatewayReply?>(Error("not_authorized", 403));
        }

        _results.TryGetValue(request.IdempotencyKey, out WriteGatewayReply? result);
        return Task.FromResult(result);
    }

    internal void ChangePreviewArguments(JsonElement replacement) => _tickets[Token].Arguments = replacement.Clone();

    internal void ConsumePreview() => _tickets[Token].Used = true;

    private string? Validate(WriteOwner owner, WriteGatewayRequest request)
    {
        if (request.ConfirmationToken is null || !_tickets.TryGetValue(request.ConfirmationToken, out Ticket? ticket))
        {
            return "confirmation_unknown";
        }

        if (ticket.Owner != owner)
        {
            return "confirmation_wrong_user";
        }

        if (clock.Now >= ticket.ExpiresAt)
        {
            return "confirmation_expired";
        }

        if (request.Tool != ticket.Tool[..^8] + "_commit"
            || request.Arguments.GetRawText() != ticket.Arguments.GetRawText())
        {
            return "confirmation_conflict";
        }

        return ticket.Used && !_results.ContainsKey(request.IdempotencyKey ?? "")
            ? "confirmation_replayed" : null;
    }

    private WriteGatewayReply Record(WriteOwner owner, string tool, WriteGatewayReply reply)
    {
        string code = reply.IsSuccess ? "ok" : reply.Body.GetProperty("error").GetProperty("code").GetString()!;
        Audit.Add((tool, code, owner));
        return reply;
    }

    private static WriteGatewayReply Reply(int status, object body) => new(status, JsonSerializer.SerializeToElement(body));
    private static WriteGatewayReply Error(string code, int status = 409) =>
        Reply(status, new { error = new { code, message = code, retryable = false } });

    private sealed class Ticket(WriteOwner owner, string tool, JsonElement arguments, DateTimeOffset expiresAt)
    {
        internal WriteOwner Owner { get; } = owner;
        internal string Tool { get; } = tool;
        internal JsonElement Arguments { get; set; } = arguments;
        internal DateTimeOffset ExpiresAt { get; } = expiresAt;
        internal bool Used { get; set; }
    }
}
