# Authentication and policy contract (as observed)

Recorded in `recordings/p1_auth.jsonl` (API) and `recordings/g1_*.jsonl` (channel gateway). Tokens are minted at run time with a
throwaway RSA key (`POST /__contract__/mint`); the recordings hold `Bearer {{token.<name>}}`, never a token.

## API: the order of checks (every route except `/api/health` and `/api/ready`)

1. **Public paths.** `GET /api/health`, `GET /api/ready` need nothing; an expired token on them is ignored (`token.expired-on-public-health` 200). `/docs`, `/redoc`, `/openapi.json` are framework routes outside the guard: **200 without a token** (`none.docs`, `none.openapi`), so the full route list is public.
2. **Bearer extraction.** Scheme compared case-insensitively (`bearer x` is accepted as a scheme); the token must be non-empty. Anything else is **401** `{"detail":"no bearer token"}` with `WWW-Authenticate: Bearer` (`Basic ...`, `Bearer`, `Bearer `, a bare word).
3. **Token validation (401, `detail: "invalid token: <ExceptionName>"`, `WWW-Authenticate: Bearer`).** RS256 only; signature (`InvalidSignatureError`), issuer exactly `https://login.microsoftonline.com/<tenant>/v2.0` (`InvalidIssuerError`; a v1 `sts.windows.net` issuer and a different tenant both fail here), audience in `{api://<client id>, <client id>}` (`InvalidAudienceError`), claims `exp`, `iat`, `iss`, `aud` required (`MissingRequiredClaimError`), `exp` (`ExpiredSignatureError`) and `nbf` (`ImmatureSignatureError`) with 60 s leeway, malformed (`DecodeError`).
4. **Token shape (403, plain `detail`).** *User* (delegated): needs scope `user_impersonation` and role `TCC.User`; refused if it also carries `TCC.Agent` ("a delegated token must not carry the 'TCC.Agent' role"). *Agent* (app-only: `idtyp=app`, or `oid == sub` with no name): no `scp`, role `TCC.Agent`, must not carry `TCC.User`; a token that shows both shapes is refused ("token mixes app-only and delegated claims").
5. **Acting user.** Only for an agent principal: header `X-TCC-Acting-User` (base64url JSON `{oid, tid, name?, upn?, assurance?, channel?, conversation_id?, correlation_id?}`) is required: missing/blank, oversized (> 2048 bytes), not base64url, not JSON, not an object, `tid` != the configured tenant, `oid`/`tid` not a GUID, a field > 256 chars, `channel` not in `teams|m365-copilot|cowork|api-test`, `assurance` not `channel-asserted|delegated` are all **400** with a specific `detail`. A *user* token that sends the header has it ignored (logged), never honoured.
6. **Agent-forbidden writes (403 "this route is not available to the channel agent").** `POST` of ingestion resolve, onezero review, rules verify / apply, workspace refresh / stage, `/api/v2/clients/{id}/runs`, `/api/claims/assess`, run-batch create/cancel/retry, and every program-draft write. Checked after step 5.
7. **Client authorisation (403 "not authorized for client <id>").** Every client id named in the path (`client_id`, `account_id`), the query string, the top level of a JSON body, and `client_ids`/`account_ids` lists (also inside `scope`) is checked against the allow-list for the principal's `oid` (agent: the gateway's own `oid`). `/api/clients/{id}/artifacts/{artifact}` authorises itself in the handler. A run batch or artifact that does not exist is **404 even for a caller with no access** (`client-authz.unknown-batch-is-404`).
8. **Writer policy (403 "this user is not entitled to make changes").** Only when `CHANNEL_ENFORCE_WRITER_FOR_USERS` is on for users; always for agents (the acting person must be a listed writer *and* the command's `actor` must equal the acting person: "the command's author is not the user the agent acts for"). Not every write route is a policy-gated command (FINDINGS F-14).
9. **Per-caller limit (429).** Routes with a `rate_limited` dependency: batch start, draft save, preview, export. Bucket per (kind, caller oid); `RATE_LIMIT_PER_MINUTE` tokens, refilled continuously; body `{"detail":{"code":"rate_limited","reason":...,"remedy":...}}`, header `Retry-After: <seconds>` (an integer, `floor((1-tokens)/rate)+1`). Only signed-in callers are counted.

CORS is the outermost layer: a preflight needs no token and answers 200 (`allow-origin: *`, methods `GET, POST, PUT, OPTIONS`, `max-age: 600`, requested headers reflected); `DELETE`/`PATCH` preflights answer 400. Error responses carry `access-control-allow-origin: *` when the request had an `Origin`.

## Roles, scopes, audiences

| Name | Value |
|---|---|
| API audience | `api://<client id>` or the bare client id |
| Issuer | `https://login.microsoftonline.com/<tenant>/v2.0` |
| User scope / role | `user_impersonation` / `TCC.User` |
| Agent role | `TCC.Agent` |
| Acting-user header | `X-TCC-Acting-User` |
| Gateway audience | `api://contract-gateway` in the recordings (configuration) |
| Gateway delegated scope | `Channel.Access` (a delegated token carrying `Channel.Invoke` is refused: `mixed_token`) |
| Gateway agent role | `Channel.Invoke`, or an app id on `CHANNEL_ALLOWED_CALLER_APP_IDS` (`caller_not_allowed` otherwise) |
| Gateway agent headers | `X-Acting-User-Oid`, `X-Acting-User-Name`, `X-Acting-Tenant`, `X-Channel` (`teams|m365-copilot|cowork|api-test`), `X-Conversation-Id`, optional `X-Correlation-Id` (`^[A-Za-z0-9._-]{1,64}$`) |

## Gateway error body

`{"error": {"code", "message", "retryable", ...}, "correlation_id"}` (a 401 carries `WWW-Authenticate: Bearer` and no correlation id). Codes seen: `unauthenticated`, `missing_scope`, `mixed_token`, `caller_not_allowed`, `tenant_mismatch`, `invalid_acting_user`, `invalid_correlation_id`, `channel_not_allowed`, `invalid_arguments`, `unknown_tool`, `not_authorized`, `rate_limited` (with `retry_after_seconds` and a `Retry-After` header), `confirmation_unknown|wrong_tool|wrong_args|wrong_user|replayed`, `not_calculated`, `request_too_large` (413).
