# O6 workflow traceability

## Evidence and scope

The implementation is in `dotnet\src\TaxCredit.Orchestrator\Workflow\`.
The focused tests are in
`dotnet\tests\TaxCredit.Orchestrator.Tests\Workflow\WriteWorkflowTests.cs` and
`WritePostCommitTests.cs` in the same directory.
Integration tests are in
`dotnet\tests\TaxCredit.Orchestrator.Tests\Turns\CheckpointTurnsTests.cs`.
This document maps behavior, rather than copying Python framework implementation details.

The last focused execution by the workflow implementer passed **58 cases**, with
normal build analyzers enabled:

```powershell
Set-Location dotnet
dotnet test tests\TaxCredit.Orchestrator.Tests\TaxCredit.Orchestrator.Tests.csproj --filter 'FullyQualifiedName~TaxCredit.Orchestrator.Tests.Workflow.' --no-restore --nologo -v:q
```

The parent reports **319 combined passing tests and all 39 deterministic records**.
That combined result was not rerun for this documentation-only handoff.
The relevant integrated test methods below were inspected directly.
Neither test set is evidence of deployment or a live gateway write.

## Actual framework boundary

`WriteCheckpointRunner.Build` constructs a real Microsoft Agent Framework
`WorkflowBuilder` graph:

```text
PrepareExecutor ("prepare")
  -> RequestPort<ConfirmationPrompt, ConfirmationResponse> ("await_confirmation")
  -> CommitExecutor ("commit")
```

Only the commit executor is registered with `WithOutputFrom`. Preparation returns
its sanitized gateway reply through the invocation-local `WriteExecutionContext`;
it does not pretend the preview is a completed commit.

`PrepareExecutor.HandleAsync` writes the immutable `HeldCommand` through
`IWorkflowContext.QueueStateUpdateAsync` under the shared workflow scope, then
sends a token-free `ConfirmationPrompt` to the request port. The command contains
the bound owner, canonical prepare tool and cloned arguments, confirmation
secret, original commit idempotency identity, and expiry.

`WriteCheckpointRunner.PrepareAsync` calls `InProcessExecution.RunAsync` with
`CheckpointManager.CreateInMemory()`. It retains a pending handle only when
execution produced both a `RequestInfoEvent` and `Run.LastCheckpoint`.
`WriteCheckpointRunner.ResumeAsync` builds a **new graph**, calls
`InProcessExecution.ResumeAsync` with the stored checkpoint and manager, then
supplies the matching `ExternalResponse` to `Run.ResumeAsync`.

The private `PausedWrite` record contains exactly `Storage`, `Checkpoint`, and
`RequestId`. It does not duplicate the prepared command. The surrounding
`WriteSlot` supplies ownership-keyed serialization and distinguishes a
confirmable checkpoint from a recovery-only checkpoint; the actual command
remains in framework checkpoint state.
After a known successful gateway commit, the invocation-local execution context
also retains its completed result. An optional link-read failure or cancellation
cannot turn that acknowledged success back into an unknown mutation outcome.

## Every named source write-flow guarantee

Source: `backend\tests\channel_orchestrator\test_orch_write_flow.py`.
Methods without a class prefix below belong to `WriteWorkflowTests`.

| Named Python guarantee | Actual .NET implementation and evidence |
| --- | --- |
| `test_the_graph_is_prepare_then_the_request_step_then_commit_and_nothing_else` | `WriteCheckpointRunner.Build` declares precisely the two edges above. `GraphUsesSdkRequestPortAndProducesACheckpoint` invokes the installed SDK, observes its request event and checkpoint, and asserts no workflow error. The .NET test is a runtime boundary assertion, not a separate exhaustive edge-inventory assertion. The request port replaces Python's custom wait executor. |
| `test_the_only_thing_that_can_start_the_workflow_is_a_prepare_request_so_commit_is_unreachable_from_outside` | `PrepareExecutor : Executor<WritePrepareRequest>` is the graph entry; `Build`, `ConfirmationResponse`, and `CommitExecutor` are not public model APIs. `WriteWorkflow.PrepareAsync` additionally allowlists canonical prepares. `NonPrepareAndUnknownToolsNeverReachGateway` proves public ingress refusal. There is no separate .NET test injecting an arbitrary message directly into the private graph entry. |
| `test_the_prepare_step_refuses_anything_that_is_not_a_preview` | `WriteWorkflow` constructor requires allowlisted names ending in `_prepare`; `PrepareAsync` checks membership before any gateway call. `NonPrepareAndUnknownToolsNeverReachGateway` covers commit, unknown prepare, and read names. |
| `test_the_workflow_holds_no_model_and_no_tool_and_stores_nothing_on_disk` | The workflow classes use typed executors, the request port, checkpoint/state APIs, delegates and JSON; no agent or tool loop executes inside this graph. `WriteCheckpointRunner.PrepareAsync` selects only the in-memory manager. `GraphUsesSdkRequestPortAndProducesACheckpoint` and `AssertSdkCheckpoint` verify actual SDK references and the handle boundary. This is implementation/reference evidence, not a Python-style import AST test or a claim that the entire host has no model. |
| `test_a_prepare_pauses_the_workflow_in_memory_and_sends_nothing_but_the_preview` | `PrepareExecutor.HandleAsync`, `WriteCheckpointRunner.PrepareAsync`; `PrepareActuallyPausesInSdkCheckpointAndFreshGraphResumesOnce` verifies `Waiting`, preserved before/after facts, no mutation, one prepare call, real SDK checkpoint types, and secret exclusion. |
| `test_the_confirmation_resumes_on_a_freshly_built_graph_and_the_commit_is_sent_once_as_the_person_who_confirmed` | `WriteCheckpointRunner.ResumeAsync` rebuilds the graph; `CommitExecutor.HandleAsync` reads checkpoint state and checks its owner. `PrepareActuallyPausesInSdkCheckpointAndFreshGraphResumesOnce` checks unchanged arguments, original secret, idempotency shape, attribution, and no second dispatch. `CheckpointTurnsTests.Actual_agent_prepare_pauses_then_confirm_resumes_once_with_current_attribution` proves the real agent prepare path and current confirmation-turn correlation through `WorkflowBridge.AsAsync`. |
| `test_somebody_elses_confirm_finds_nothing_and_does_not_touch_the_owners_preview` | `WriteWorkflow.RespondAsync` looks up the exact `WriteOwner` before consuming a handle. `WrongOwnerCannotConsumeOrCommitTheOwnersPreview` covers a different person and a different conversation. `CheckpointTurnsTests.Wrong_person_cannot_consume_the_preview_even_with_the_same_conversation` exercises the shared host path. |
| `test_a_confirmation_at_the_expiry_is_refused_and_one_second_before_it_is_not` | `CommitExecutor.HandleAsync` compares injected `TimeProvider.GetUtcNow() >= HeldCommand.ExpiresAt` before dispatch. `ExpiryUsesExactGreaterThanOrEqualBoundary` covers immediately before, at, and after the boundary. `CheckpointTurnsTests.At_the_expiry_boundary_a_checkpoint_cannot_dispatch` covers the host path. |
| `test_every_refusal_the_gateway_gives_a_commit_is_reported_and_never_retried` | `CommitExecutor.Outcome` preserves sanitized canonical refusal codes. `GatewayRefusalsRemainVisibleAndAreNeverRetried` covers expired, replayed, wrong-user, unknown, conflict, and authorization refusals. `GatewayIndependentlyChecksTokenExpiry`, `GatewayIndependentlyRejectsATokenConsumedElsewhere`, `GatewayIndependentlyRejectsPreviewArgumentConflict`, and `RevokedWriterCannotCommitAnEarlierAuthorizedPreview` exercise the fake gateway's own checks rather than only overriding response codes. |
| `test_cancel_resumes_the_workflow_with_a_refusal_so_it_ends_and_nothing_is_sent` | `RespondAsync` consumes the pending handle and sends `WriteDecision.Cancel` through the real request port. `CommitExecutor.HandleAsync` yields `Cancelled` without calling `CommitAsync`. `CancellationResumesFrameworkWithoutGatewayCommit` verifies no gateway commit and no remaining confirmable preview. |
| `test_any_other_message_cancels_the_frameworks_pending_request_and_says_the_change_was_dropped` | `WriteWorkflow.ParseDecision` maps other text to `Drop`; `ResumeAsync` answers the SDK request with that decision, and the executor yields `Dropped` without dispatch. This is terminal port-response cancellation, not Python's `cancel_pending_requests` API. `OnlyExactReaderWordsCanCommit` proves discard/no later commit; `AReplacementPreviewCancelsThePreviousFrameworkRequest` proves a replacement cannot commit the earlier arguments. `TurnPipeline.AttributedAsync` appends `Replies.Dropped` to the subsequent answer. `CheckpointTurnsTests.Non_confirmation_never_applies_a_preview` covers cancel, bare yes/no, and a different question. |
| `test_a_framework_fault_while_dropping_never_blocks_the_answer_or_leaves_the_change_confirmable` | `WriteCheckpointRunner.SafeFailure(Drop)` yields an explicit dropped/checkpoint-unavailable outcome; the handle has already been consumed. `MissingFrameworkCheckpointIsExplicitAndNeverRetainsConfirmableState` with a different question proves this fault boundary. `TurnPipeline.AttributedAsync` continues planning on `Dropped`; the broken-checkpoint-plus-subsequent-answer combination is not a separate integrated fault-injection test. |
| `test_a_framework_fault_while_confirming_says_the_outcome_is_unknown_and_is_not_retried` | Before any known successful commit response, `ResumeAsync` converts a resume/commit fault into `Unknown`; `RespondAsync` retains only a recovery-only checkpoint, never a confirmable one. `MissingFrameworkCheckpointIsExplicitAndNeverRetainsConfirmableState` with confirm and `LostDispatchResponseIsUnknownNeverReconfirmableAndRecoveryUsesOriginalIdentity` prove no retry. `TurnPipeline.CommitReply` renders an explicit unknown-outcome statement. Unlike Python's cleared state, .NET blocks further writes for safe result recovery while allowing ordinary reads. |
| `test_a_framework_fault_while_preparing_is_an_error_and_not_a_preview_that_can_be_confirmed` | `WriteWorkflow.PrepareAsync` clears pending state and returns `PrepareFailed` if preparing/checkpointing fails. `PrepareFaultDoesNotMasqueradeAsAHeldPreview` injects a gateway/prepare-step exception through the real graph. The runner also requires a request event plus checkpoint before returning `Waiting`; there is no separate test that replaces the SDK manager with a failing custom checkpoint store. |
| `test_a_refused_preview_never_pauses_a_workflow` | `PrepareExecutor.HandleAsync` requires a successful object envelope without an error and a nonblank string at `facts.confirmation.token`. `ReaderAuthorizationIsEnforcedAtPreviewAndCannotPause`, `SuccessWithoutValidConfirmationTokenDoesNotPause`, `InvalidPrepareTokenCannotCreateARequest`, and `RefusedGatewayEnvelopeCannotLeakAConfirmationTokenOrCreateARequest` cover refusal and malformed/missing secret cases. `CheckpointTurnsTests.Reader_authorization_is_enforced_by_the_gateway_before_a_checkpoint_can_commit` covers the host path. |
| `test_the_model_can_name_a_preview_but_never_a_commit_and_a_read_never_starts_a_workflow` | The workflow's allowlist and prepare-only entry enforce its boundary. `NonPrepareAndUnknownToolsNeverReachGateway` proves refusal. `Framework.CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` verifies the model-facing catalogue, and `CheckpointTurnsTests.Actual_agent_prepare_pauses_then_confirm_resumes_once_with_current_attribution` proves an actual framework agent can prepare without receiving commit authority. |
| `test_the_confirmation_state_is_the_frameworks_checkpoint_and_not_a_second_copy_of_the_change` | `PausedWrite` has only manager, checkpoint and request ID; `HeldCommand` is written/read with the SDK state APIs. `PrepareActuallyPausesInSdkCheckpointAndFreshGraphResumesOnce` calls `AssertSdkCheckpoint`, which checks precisely these handle properties/types without serializing the secret payload. Parent `ConversationState` has no checkpoint/command copy. |

## Additional cancellation, concurrency and recovery proof

- `CompetingConfirmationsDispatchAtMostOneCommit` holds the first gateway commit
  open while starting another confirmation. The per-owner `WriteSlot.Gate`
  serializes consumption and only one commit callback runs.
  `CheckpointTurnsTests.Concurrent_confirms_serialize_the_whole_turn_and_make_one_mutation`
  also exercises whole-turn serialization.
- `CancellationAfterCommitDispatchLeavesExplicitUnknownAndCannotRetry` cancels
  the supplied cancellation token after the gateway callback has been entered.
  The result is unknown, not a fabricated no-change result. Cancellation while
  waiting to acquire a slot propagates before a pending handle is consumed.
- `TransportFailureRepliesAfterDispatchRemainUnknownRatherThanDefiniteRefusals`
  covers the boundary client's returned timeout/unreachable/malformed/oversize
  failure envelopes. `CommitExecutor.CommitAsync` also treats status zero and
  HTTP 5xx as uncertain. An exception, including cancellation during resume
  before a known successful response, reaches the same safe unknown outcome
  through `WriteCheckpointRunner`.
- `LostDispatchResponseIsUnknownNeverReconfirmableAndRecoveryUsesOriginalIdentity`
  proves a mutation can occur before response loss, that repeated confirmation
  and reprepare do not dispatch, and that a dedicated lookup receives the
  **original** commit tool, arguments and idempotency identity. The lookup is not
  another commit call. `CheckpointTurnsTests.Lost_commit_response_is_unknown_and_cannot_reconfirm_or_retry`
  proves the integrated timeout-after-mutation behavior.
- `CheckpointTurnsTests.Model_failure_after_prepare_keeps_the_preview_without_preparing_again`
  establishes that failed model narration does not reissue an accepted prepare.
- `UnknownWriteAllowsOrdinaryReadsWithoutDiscardingRecoveryOrEnablingPrepare`
  proves an ordinary subsequent request returns `NothingPending` with the
  recovery identity intact, while confirmation and new prepare remain blocked.
  The eventual read-only result lookup receives the original identity.
- Token-boundary tests also include
  `CommitErrorCodesAndMessagesCannotReflectTheConfirmationToken` and
  `Composition.ModelLaneTests.Confirmation_tokens_are_neither_placeholder_authority_nor_reader_or_model_content`.
  The integrated actual-agent test checks every captured model request and the
  reader's preview/result text for secret exclusion.

## Package creation supplementary read

After an acknowledged successful `claim_package_create_commit`,
`CommitExecutor.CompleteAsync` calls `WritePostCommit.EnrichAsync` **inside the
same resumed workflow executor**. The helper calls `claim_package_link` as the
current verified owner with only `client_id` and `tax_year` copied from the
checkpointed prepare arguments. No confirmation secret or commit idempotency
identity is sent to that read. Parent code must not dispatch another commit or
duplicate the link lookup.

On success, `WriteResult.Reply` remains the primary commit envelope and
`FollowUps` contains a `WriteFollowUp("claim_package_link", sanitizedReply)`.
On link refusal, transport exception, or cancellation, status stays `Committed`,
the primary envelope remains available, and `Note` states:
**The package was built, but its link is unavailable.**
No failed lookup is presented as a successful link. No commit is retried.

`WritePostCommitTests` proves these cases:

- `PackageCommitFetchesSanitizedLinkOnceUsingOnlyOriginalHeldScope`: exact
  prepare -> commit -> link call order, original scope, no unrelated arguments
  or confirmation metadata on the link read, sanitized supplementary envelope,
  one mutation, and no repeated lookup on another confirm.
- `LinkFailurePreservesCommittedMutationAndReportsPublicNoteWithoutRetry`:
  both refused link replies and thrown timeouts retain success and the public
  failure note.
- `CancellationWhileFetchingLinkCannotEraseKnownSuccessfulMutation`:
  cancellation after the acknowledged mutation preserves `Committed` and the
  unavailable-link note through the actual framework runtime.
- `RefusedCommitNeverFetchesPackageLink`: unsuccessful commits perform no link
  read and produce no supplementary success envelope.
- `UnknownCommitDoesNotFetchLinkUntilReadOnlyRecoveryEstablishesSuccess`: a lost
  commit response triggers no premature link read; a subsequent successful
  result lookup can obtain the link without dispatching the commit again.

## Caller and adapter contract

1. Retain one `WriteWorkflow`/`WorkflowBridge` service for the process. Do not
   construct a new workflow service per turn; graphs themselves are rebuilt.
   The workflow owns its pending handles. Parent conversation state must not
   hold another mutable command or confirmation secret.
2. Resolve identity before accessing the workflow. The parent bridge keys
   `WriteOwner.PersonId` by tenant plus person, and `ConversationId` by the
   selected conversation. Its `AsAsync` installs the current verified
   `ActingIdentity` in `AsyncLocal`, restores the previous value in `finally`,
   and checks that the callback's owner matches. Gateway attribution therefore
   uses the confirming invocation, not the preparing invocation's correlation.
3. Call `WorkflowBridge.RespondAsync` before planning. Exact commands terminate
   at the confirmation path. Ordinary questions with no pending workflow
   continue normally; a dropped preview allows the new question plus a discard
   notice. An ordinary question while write recovery is pending returns
   `NothingPending` with code `recovery_pending`, so read planning can continue
   without discarding the recovery checkpoint. A model-proposed new prepare is
   still refused with `Unknown`. The parent serializes the whole turn as well.
4. Pass only already-settled canonical prepare names/arguments to `PrepareAsync`.
   The bridge derives the allowlist from catalogue entries with
   `kind == write_prepare`. Preparing **calls the gateway inside the executor**;
   the caller must not call gateway prepare a second time.
5. Forward the request's tool, arguments, idempotency identity and confirmation
   secret unchanged to `IGatewayClient.CallToolAsync`, with the current verified
   identity and cancellation token. Do not enable automatic mutation retries.
   Forwarding the secret on that private authenticated transport is necessary;
   forwarding the raw gateway reply to a model or reader is not permitted.
6. Prepare receives no idempotency identity. After a successful preview, the
   executor generates the original commit identity and stores it in the
   checkpoint before commit can be dispatched. Confirm and optional result
   recovery use that identity; neither creates a replacement commit identity.
7. `WriteResult.Reply` is `WriteGatewayReply?`; its `Body` is the complete
   sanitized canonical envelope, not merely `facts`. Before/after facts, trusted
   blocks and provenance retain their gateway locations. Secret fields are
   removed recursively and known secret values are scrubbed from returned
   strings, including error codes. Normal model/person lane projection and
   guarded composition are still required; token sanitization is not that
   broader projection.
   Compose the primary reply and successful named `WriteResult.FollowUps`, then
   include the public `Note` if nonempty. The follow-up envelopes need the same
   ordinary lane projection and trusted composition as other gateway results.
8. An optional `WriteResultLookup` must be a **read-only lookup of the original
   dispatch's result**. Return a known original terminal result, or return null/
   throw if the result cannot be established. Do not return an authorization,
   transport, or not-found error from the lookup operation as though it proved
   the original write was refused: a returned non-success reply is treated as
   a known original refusal and releases the recovery block.
9. Gateway/API authorization, confirmation expiry, argument binding, single-use
   redemption and durable idempotency remain authoritative. The workflow adds
   safe orchestration, not a replacement entitlement or transactional store.
   The local fake records both gateway steps and their bound owners; those fake
   records are not proof of durable production API audit persistence.

## Durability, lifetime and unresolved limits

- Checkpoints use `CheckpointManager.CreateInMemory()` only. No disk, shared
  replica store, or durable recovery manifest is configured here. The checkpoint
  contains sensitive transient confirmation material; it must not be logged,
  exported or supplied to a model. `HeldCommand` and `WriteGatewayRequest`
  have restricted diagnostic string representations.
- Process restart, singleton replacement, or routing a follow-up to a replica
  without the original slot loses the preview. That instance returns
  `NothingPending` and cannot resume or commit the missing preview. This is
  **not** cross-replica continuation or exactly-once processing across restarts.
- Restart also loses a recovery-only checkpoint and its original idempotency
  identity. A prior dispatched write may still have completed. A fresh prepare
  after restart must not be represented as safe recovery of that earlier write;
  operators must inspect the authoritative record. Durable result recovery
  across process loss is not implemented.
- `WriteWorkflow` defaults confirmation lifetime to five minutes and checks
  expiry lazily at confirmation, using injected UTC time with `>=`. There is
  no timer, and this is not a monotonic-clock guarantee under UTC clock changes.
  The gateway independently enforces its own confirmation deadline.
- The workflow slot dictionary has no independent global capacity or TTL
  sweep. Completed empty slots remain allocated. A dormant expired checkpoint
  remains resident until that owner is accessed/dropped or the process ends.
  Parent `ConversationStore` has TTL eviction and its next new lease asks the
  bridge to drop an old preview, but that is not a global checkpoint-memory
  sweep and does not clear an unknown recovery-only slot.
- **Recovery integration is not configured in the inspected host bridge.**
  `WriteWorkflow.RecoverAsync` and its injected fake lookup are tested, but
  `WorkflowBridge` currently supplies no `resultLookup` and exposes no recovery
  operation. An unknown slot therefore stays **write-blocked** for the process
  lifetime unless a caller supplies recovery integration. Subsequent ordinary
  read turns may continue, but confirmation and new prepares cannot release or
  overwrite the original recovery identity. No automatic retry or administrative
  unlock is implied.
- The previously reported host punctuation difference has been corrected by
  the parent: the inspected `Replies.Command` now uses the same
  `.TrimEnd('.', '!').Trim()` normalization as `WriteWorkflow.ParseDecision`
  and Python. Bare yes/no remain non-confirmations.
- The package-link read described above is covered with the local faithful
  gateway fake and actual SDK workflow runtime. This is not a claim of a live
  gateway end-to-end equivalence test. Parent composition must consume the
  exposed supplementary envelopes and note; that adapter change is outside
  this workflow follow-up.

The unresolved host/operational limits above are reported for the parent; no
parent implementation or tests were changed in this documentation follow-up.
