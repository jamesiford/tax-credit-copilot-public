using TaxCredit.Domain.Findings;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;

namespace TaxCredit.Application.Ports.Persistence;

/// <summary>Durable queue operations. Item mutations bind both client identity and unexpired lease ownership.</summary>
public interface IRunBatchRepository
{
    /// <summary>Creates a request and its items atomically; an existing requester/key returns its original request.</summary>
    RunBatch Create(RunBatch batch, IReadOnlyList<RunBatchItem> items);
    /// <summary>Reads the request.</summary>
    RunBatch? Get(string batchId);
    /// <summary>Finds a requester's idempotency key.</summary>
    RunBatch? FindByKey(string key, string requestedBy);
    /// <summary>Finds an identical still-open request.</summary>
    RunBatch? FindOpenIdentical(string kind, string specJson, string requestedBy);
    /// <summary>Lists request summaries and the unpaged total.</summary>
    (IReadOnlyList<RunBatch> Items, long Total) ListBatches(int limit, int offset, string? status = null);
    /// <summary>Lists one batch's items and the unpaged total.</summary>
    (IReadOnlyList<RunBatchItem> Items, long Total) ListItems(string batchId, string? status, int limit, int offset);
    /// <summary>Reads a tenant's queue item.</summary>
    RunBatchItem? GetItem(long clientId, string itemId);
    /// <summary>Counts all item statuses for a batch.</summary>
    IReadOnlyDictionary<string, long> StatusCounts(string batchId);
    /// <summary>Publishes counters and status in one transaction.</summary>
    RunBatch Refresh(string batchId, PyDateTime now);
    /// <summary>Cancels queued items, never work already leased.</summary>
    long Cancel(string batchId, PyDateTime now);
    /// <summary>Requeues failed items only, resetting their attempt budget.</summary>
    long RetryFailed(string batchId, PyDateTime now);
    /// <summary>Claims ordered work, at most one live lease per client.</summary>
    IReadOnlyList<RunBatchItem> Claim(string owner, int limit, int leaseSeconds, PyDateTime now);
    /// <summary>Renews an unexpired lease held by this worker.</summary>
    bool Heartbeat(long clientId, string itemId, string owner, int leaseSeconds, PyDateTime now);
    /// <summary>Starts a leased item with its resolved scope.</summary>
    bool MarkRunning(long clientId, string itemId, string owner, long? taxYear, string? programCode, PyDateTime now);
    /// <summary>Finishes an owned item and refreshes its batch counters atomically.</summary>
    bool Finish(long clientId, string itemId, string owner, PyDateTime now, ItemResult result, string batchId);
    /// <summary>Returns owned work for a later attempt after the specified backoff.</summary>
    bool Requeue(long clientId, string itemId, string owner, PyDateTime now, PyDateTime notBefore, string? dependency, string? message);
    /// <summary>Returns untouched work and refunds one attempt.</summary>
    bool Release(long clientId, string itemId, string owner, PyDateTime now);
    /// <summary>Requeues expired leases or fails those with spent attempts, refreshing affected batches.</summary>
    IReadOnlyList<string> ReapExpired(PyDateTime now, int maxAttempts);
    /// <summary>Returns aggregate queue liveness, without reading every item.</summary>
    QueueHealth QueueHealth(PyDateTime now);
}

/// <summary>The queue's waiting-work and worker-liveness facts.</summary>
/// <param name="Queued">Waiting items in uncancelled batches.</param>
/// <param name="OldestQueuedAt">Oldest waiting request.</param>
/// <param name="LiveLeases">Unexpired leases.</param>
/// <param name="LastHeartbeatAt">Latest live heartbeat.</param>
public sealed record QueueHealth(long Queued, PyDateTime? OldestQueuedAt, long LiveLeases, PyDateTime? LastHeartbeatAt);

/// <summary>Finding decisions and the audit of reopening them.</summary>
public interface IFindingRepository
{
    /// <summary>Reads live decisions, optionally for one year.</summary>
    IReadOnlyList<FindingResolution> Live(long clientId, long? taxYear = null);
    /// <summary>Reads the full decision history.</summary>
    IReadOnlyList<FindingResolution> History(long clientId, string findingId);
    /// <summary>Appends a decision and closes its predecessor.</summary>
    FindingResolution Record(FindingResolution resolution);
    /// <summary>Closes a decision and records who reopened it.</summary>
    bool Reopen(long clientId, string findingId, string decidedBy, PyDateTime at);
    /// <summary>Reads the immutable actions on a finding.</summary>
    IReadOnlyList<FindingAudit> Audit(long clientId, string findingId);
}

/// <summary>An action on a finding, including its actor when no replacement decision exists.</summary>
public sealed record FindingAudit(
    string FindingId,
    long ClientId,
    string Action,
    string Actor,
    PyDateTime At);

/// <summary>An app-owned lookup row. Zero identifies a global row; dates are facts, not a storage-side resolution policy.</summary>
public sealed record LookupEntry(
    string Lookup,
    long ClientId,
    string KeyKind,
    string Key,
    string ValueJson,
    string AuthoredBy,
    string Basis = "",
    bool Inferred = false,
    DateOnly? EffectiveFrom = null,
    DateOnly? EffectiveTo = null);

/// <summary>Neutral storage contract consumed by Sources; no fiscal or pay-code resolution occurs here.</summary>
public interface ILookupReader
{
    /// <summary>Reads current tenant and global rows, preserving authored effective dates.</summary>
    IReadOnlyList<LookupEntry> Entries(string lookup, long clientId);
}

/// <summary>Append-style lookup administration and its action trail.</summary>
public interface ILookupStore : ILookupReader
{
    /// <summary>Closes the exact prior key and appends a replacement.</summary>
    void Put(LookupEntry entry, PyDateTime at);
    /// <summary>Closes, rather than deletes, an exact scoped key.</summary>
    bool Remove(string lookup, long clientId, string keyKind, string key, string actor, PyDateTime at);
    /// <summary>Reads actions scoped to a client; global actions can be read by explicitly selecting client zero.</summary>
    IReadOnlyList<IReadOnlyDictionary<string, object?>> Audit(long clientId, string? lookup = null);
}

/// <summary>Artifact metadata only; byte storage is an independent boundary.</summary>
public sealed record ArtifactMetadata
{
    /// <summary>The artifact identity.</summary>
    public required string ArtifactId { get; init; }
    /// <summary>Rule source or claim package.</summary>
    public required string Kind { get; init; }
    /// <summary>The tenant, absent only on rule sources.</summary>
    public long? ClientId { get; init; }
    /// <summary>The program.</summary>
    public string? ProgramCode { get; init; }
    /// <summary>The tax year.</summary>
    public long? TaxYear { get; init; }
    /// <summary>The run.</summary>
    public string? RunId { get; init; }
    /// <summary>The rule pack.</summary>
    public string? RulePackVersion { get; init; }
    /// <summary>The private storage container.</summary>
    public required string ContainerName { get; init; }
    /// <summary>The immutable byte-store key.</summary>
    public required string BlobPath { get; init; }
    /// <summary>The download name.</summary>
    public required string FileName { get; init; }
    /// <summary>The media type.</summary>
    public required string ContentType { get; init; }
    /// <summary>The byte count.</summary>
    public required long SizeBytes { get; init; }
    /// <summary>The content digest.</summary>
    public required string Sha256 { get; init; }
    /// <summary>The author.</summary>
    public required string CreatedBy { get; init; }
    /// <summary>The creation instant.</summary>
    public required PyDateTime CreatedAt { get; init; }
    /// <summary>The retention end.</summary>
    public DateOnly? RetainUntil { get; init; }
    /// <summary>The supersession instant.</summary>
    public PyDateTime? SupersededAt { get; init; }
}

/// <summary>An attempted artifact download, including refusals and missing bytes.</summary>
public sealed record ArtifactAccess(
    string AccessId,
    string ArtifactId,
    long? ClientId,
    string UserUpn,
    string? UserOid,
    PyDateTime AccessedAt,
    string Outcome);

/// <summary>Metadata and access audit, never bytes or SAS tokens.</summary>
public interface IArtifactRepository
{
    /// <summary>Appends metadata; supersession is client/kind/year scoped.</summary>
    ArtifactMetadata Record(ArtifactMetadata artifact);
    /// <summary>Finds metadata by identity; authorization remains the caller's responsibility.</summary>
    ArtifactMetadata? Find(string artifactId);
    /// <summary>Lists live client artifacts with optional selectors.</summary>
    IReadOnlyList<ArtifactMetadata> Live(long clientId, string? kind = null, long? taxYear = null);
    /// <summary>Records a download outcome, even when the bytes or metadata are absent.</summary>
    ArtifactAccess RecordAccess(ArtifactAccess access);
    /// <summary>Reads a client's download attempts.</summary>
    IReadOnlyList<ArtifactAccess> Accesses(long clientId);
}

/// <summary>A channel user's immutable grant and optional revocation.</summary>
public sealed record WriterGrant(string UserOid, string? DisplayName, string Role, string AddedBy, PyDateTime AddedAt, PyDateTime? RemovedAt = null);

/// <summary>A hashed, expiring, single-use write confirmation; neither cleartext tokens nor download URLs are stored.</summary>
public sealed record Confirmation(
    string ConfirmationId, string TokenSha256, string UserOid, string ToolName, string ArgsSha256,
    PyDateTime CreatedAt, PyDateTime ExpiresAt, string? IdempotencyKey = null, PyDateTime? ConsumedAt = null,
    string? Outcome = null, string? ResultJson = null);

/// <summary>Channel allow-list and single-use confirmation state.</summary>
public interface IChannelStateRepository
{
    /// <summary>Appends a grant, closing the previous one.</summary>
    WriterGrant Grant(WriterGrant grant);
    /// <summary>Closes a live grant.</summary>
    bool Revoke(string userOid, PyDateTime at);
    /// <summary>Checks the current writer grant.</summary>
    bool IsWriter(string userOid);
    /// <summary>Reads live grants.</summary>
    IReadOnlyList<WriterGrant> Live();
    /// <summary>Creates a hashed confirmation.</summary>
    Confirmation Create(Confirmation confirmation);
    /// <summary>Reads a confirmation by its token digest.</summary>
    Confirmation? FindByTokenHash(string tokenSha256);
    /// <summary>Reads a completed idempotent result for one person.</summary>
    Confirmation? FindByIdempotencyKey(string userOid, string key);
    /// <summary>Atomically consumes an unexpired confirmation bound to the person and argument digest.</summary>
    bool Consume(string confirmationId, string userOid, string argsSha256, PyDateTime at, string? idempotencyKey = null);
    /// <summary>Stores one consumed confirmation's result; conflicting replays are refused.</summary>
    void RecordResult(string confirmationId, string outcome, string? resultJson);
}

/// <summary>Channel event attributes in the checked-in schema's vocabulary. Unknown columns are refused by the adapter.</summary>
public sealed record ChannelAuditEvent(IReadOnlyDictionary<string, object?> Fields);

/// <summary>Agent-action audit attributes in the checked-in schema's vocabulary, never payroll content.</summary>
public sealed record AgentActionAudit(IReadOnlyDictionary<string, object?> Fields);

/// <summary>Insert-only channel and agent action trails, including begin events for writes that never finish.</summary>
public interface IChannelAuditRepository
{
    /// <summary>Appends one event, rejecting duplicate audit identity and sequence.</summary>
    void Append(ChannelAuditEvent auditEvent);
    /// <summary>Reads one person's events with optional time and tool filters.</summary>
    IReadOnlyList<ChannelAuditEvent> ForUser(string userOid, PyDateTime? since = null, PyDateTime? until = null, string? tool = null, int limit = 200);
    /// <summary>Reads a correlation's events in execution order.</summary>
    IReadOnlyList<ChannelAuditEvent> ByCorrelation(string correlationId);
    /// <summary>Appends an agent action without overwriting earlier observations.</summary>
    void Append(AgentActionAudit action);
    /// <summary>Reads recent agent actions.</summary>
    IReadOnlyList<AgentActionAudit> Recent(string? agentName = null, int limit = 100);
}
