# Live smoke of the channel gateway, 2026-11-03

Customer-neutral and redacted: no token, no object id, no tenant. Run by `scripts/channel-live-smoke.py` as the signed-in
sandbox operator (a delegated token for the gateway's `Channel.Access` scope), against the deployed PoC. Reads were
also compared, tool by tool, with the same capability run **in process** against the same Warehouse (`--compare-local`):
the gateway's facts were identical in every case. The portal's own HTTP endpoints sit behind the web app's Easy Auth
session and the API's subnet restriction, so they cannot be called with a bearer token from a workstation; the in-process
comparison is the engine's own answer (see KNOWN-LIMITATIONS).

Certified figures on the deployed Warehouse (`backend/tools/check_certified_live.py`, read-only): **10,236 employees,
539 Min-Max, 656 Pay Period: CERTIFIED FIGURES REPRODUCE.**

Not shown as PASS, and why (full list in STATUS):

- A person who is in the writers **group** but not on the allow-list was refused (403) at the API: the API's own
  group check was denied by Microsoft Graph, because its identity asked Graph for a token *before* its
  `GroupMember.Read.All` role was granted and the platform caches that token. The gateway's group check, which asked
  after its grant, passed. Expect it to clear when the cached token expires (about a day); until then the operator is on the allow-list too.
- `finding_resolve`: no open finding exists for any synthetic client, so only prepare/commit of the other write tools was run.
- Rate limit: the single gateway worker answers about 1.5 calls a second, barely above the limit's refill, so a client
  cannot outrun it; the 429 is proven offline.

## Run 1: catalog, reads (compared), writes, verify, audit

# live smoke ff139873  steps=['audit', 'catalog', 'reads', 'verify', 'writes']
## catalog
PASS  REST tools/list equals the catalog (plus the debug ping)  (29 tools; missing=[] extra=[])
PASS  MCP tools/list equals REST tools/list  (29 tools)
PASS  no token is a 401
PASS  a wrong-audience token is a 401  (got 401)
## reads
PASS  book_rank answers
PASS  client 2001: a calculated year exists  (TY2026)
PASS  client 2001: client_resolve answers  (ok)
PASS  client 2001: client_resolve facts identical to the engine's own
PASS  client 2001: client_situation answers  (ok)
PASS  client 2001: client_situation facts identical to the engine's own
PASS  client 2001: client_eligibility answers  (ok)
PASS  client 2001: client_eligibility facts identical to the engine's own
PASS  client 2001: client_trend answers  (ok)
PASS  client 2001: client_trend facts identical to the engine's own
PASS  client 2001: client_at_risk answers  (ok)
PASS  client 2001: client_at_risk facts identical to the engine's own
PASS  client 2001: client_discovery answers  (ok)
PASS  client 2001: client_discovery facts identical to the engine's own
PASS  client 2001: calc_walkthrough answers  (ok)
PASS  client 2001: calc_walkthrough facts identical to the engine's own
PASS  client 2002: a calculated year exists  (TY2026)
PASS  client 2002: client_resolve answers  (ok)
PASS  client 2002: client_resolve facts identical to the engine's own
PASS  client 2002: client_situation answers  (ok)
PASS  client 2002: client_situation facts identical to the engine's own
PASS  client 2002: client_eligibility answers  (ok)
PASS  client 2002: client_eligibility facts identical to the engine's own
PASS  client 2002: client_trend answers  (ok)
PASS  client 2002: client_trend facts identical to the engine's own
PASS  client 2002: client_at_risk answers  (ok)
PASS  client 2002: client_at_risk facts identical to the engine's own
PASS  client 2002: client_discovery answers  (ok)
PASS  client 2002: client_discovery facts identical to the engine's own
PASS  client 2002: calc_walkthrough answers  (ok)
PASS  client 2002: calc_walkthrough facts identical to the engine's own
## writes
PASS  engagement_set prepare then commit  (200/200)
PASS  an idempotent retry returns the first result
SKIP  finding_resolve: client 2002 TY2025 has no open finding to resolve
PASS  claim_transition forward to 'proposed' (TY2025) prepare then commit  (200)
PASS  claim_transition restore to 'assessed' (TY2025) prepare then commit  (200)
## verify
PASS  verify_figures accepts a figure from the returned facts  (pass)
PASS  verify_figures rejects a one-digit mutation  (rejected)
## audit
INFO  audit rows are read with scripts/channel-audit.py --detail; this run's correlation ids start 'smoke-ff139873-'

RESULT  41 passed, 0 failed, 41 checks  (smoke id ff139873, 2026-11-03)

## Run 2: a non-writer (off the allow-list and out of the group)

# live smoke 6699ca3a  steps=['nonwriter']
## nonwriter
PASS  a non-writer's change is refused  (got 403)
PASS  a non-writer can still read

RESULT  2 passed, 0 failed, 2 checks  (smoke id 6699ca3a, 2026-11-03)

## Run 3: size cap and rate limit

# live smoke c5f31680  steps=['limits']
## limits
PASS  a body over the cap is a 413  (got 413)
SKIP  rate limit not reached live: 148 ok, 2 502 of 150 (the offline tests prove the 429)

RESULT  1 passed, 0 failed, 1 checks  (smoke id c5f31680, 2026-11-03)

## Audit (scripts/channel-audit.py and a direct read of the store)

Since the first smoke call, for the operator: 659 events with a `smoke-` correlation id, every one
`channel=cowork`, `identity_assurance=delegated`; 330 distinct correlation ids; 8 `end/refused` rows, all
"this user is not entitled to make changes" (the non-writer run and the group-only attempts); 1 `end/error` (a
claim transition on a year that has no claim cell, which returns a 500 `internal_error` instead of a 409: a defect found, recorded
in KNOWN-LIMITATIONS, not fixed here). Longest `request_summary` is 98 characters and none contains a wage, an hour
count, an employee identifier or an email address. The engagement and claim rows the writes made are in the
Warehouse, labelled "live smoke <id>" (engagement history is append-only; the claim cell was restored to its original
status, its history rows remain).