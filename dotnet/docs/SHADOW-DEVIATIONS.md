# Shadow deviations and decisions

This is an inventory, **not cutover approval**. Complete reasons, exact source scopes, historical versions and field-level residuals are in [SHADOW-DEVIATIONS.json](SHADOW-DEVIATIONS.json). Raw payloads are absent.

## Register inventory

| Register | Current entries | Historical versions | Empty historical versions |
|---|---:|---:|---:|
| `dotnet/docs/improvements/W1-skeleton.json` | 4 | 1 | 0 |
| `dotnet/docs/improvements/composition.json` | 3 | 1 | 0 |
| `dotnet/docs/improvements/gateway.json` | 8 | 1 | 0 |
| `dotnet/docs/improvements/integrate-W1.json` | 0 | 1 | 1 |
| `dotnet/docs/improvements/integrate-W2.json` | 85 | 2 | 0 |
| `dotnet/docs/improvements/integrate-W3.json` | 0 | 1 | 1 |
| `dotnet/docs/improvements/integration.json` | 0 | 1 | 1 |
| `dotnet/docs/improvements/orchestrator.json` | 3 | 1 | 0 |
| `dotnet/docs/improvements/persistence.json` | 0 | 2 | 1 |
| `dotnet/docs/improvements/routes_ai_agents.json` | 2 | 2 | 0 |
| `dotnet/docs/improvements/routes_claims.json` | 6 | 2 | 0 |
| `dotnet/docs/improvements/routes_drafts_runs.json` | 4 | 3 | 0 |
| `dotnet/docs/improvements/routes_reads.json` | 37 | 2 | 0 |
| `dotnet/docs/improvements/skeleton.json` | 4 | 1 | 0 |
| `dotnet/docs/improvements/sources_auth_ai.json` | 0 | 3 | 1 |

Duplicate skeleton IDs/content are coalesced with both source files retained. Narrowed scopes remain separate historical variants; removed IDs are withdrawn, not current exceptions.

## Current and historical differences

| Source ID | State | Method/template | Case / path | Fresh matches / accepted | Scope review |
|---|---|---|---|---:|---|
| `IMP-skeleton-1` | current-deliberate-difference | `GET /api/workspace/assumptions` | `* / *` | 12 / 9 | broad-scope-owner-review |
| `IMP-skeleton-2` | current-deliberate-difference | `GET /api/progress/{tax_year}` | `get-api-progress-tax-year.query-within-negative / *` | 4 / 1 | broad-scope-owner-review |
| `IMP-skeleton-3` | current-deliberate-difference | `GET /api/v2/clients/{client_id}/units` | `unknown.client-huge / *` | 4 / 1 | broad-scope-owner-review |
| `IMP-skeleton-4` | current-deliberate-difference | `GET /api/simulate/portfolio/{tax_year}` | `* / *` | 5 / 0 | broad-scope-owner-review |
| `IMP-composition-1` | current-deliberate-difference | `GET /api/ready` | `* / source_schema` | 18 / 18 | exact source scope; owner pending |
| `IMP-composition-2` | current-deliberate-difference | `GET /api/me` | `* / *` | 18 / 3 | broad-scope-owner-review |
| `IMP-composition-3` | current-deliberate-difference | `POST /__contract__/env` | `* / *` | 0 / 0 | broad-scope-owner-review, not-hit-in-fresh-sample |
| `IMP-gateway-1` | current-deliberate-difference | `POST /mcp` | `* / result.capabilities.logging` | 4 / 4 | exact source scope; owner pending |
| `IMP-gateway-2` | current-deliberate-difference | `POST /mcp` | `* / error.retryable` | 2 / 2 | exact source scope; owner pending |
| `IMP-gateway-3` | current-deliberate-difference | `POST /channel/v1/tools/client_at_risk` | `tool.client_at_risk.typical / user_only_facts` | 1 / 1 | exact source scope; owner pending |
| `IMP-gateway-4` | current-deliberate-difference | `POST /channel/v1/tools/findings_list` | `* / user_only_facts` | 2 / 2 | exact source scope; owner pending |
| `IMP-gateway-5` | current-deliberate-difference | `POST /channel/v1/tools/{tool}` | `tool.body-too-large / correlation_id` | 1 / 1 | exact source scope; owner pending |
| `IMP-gateway-6` | current-deliberate-difference | `POST /channel/v1/tools/finding_reopen_prepare` | `tool.finding_reopen_prepare.typical / blocks[1].rows[3][2]` | 1 / 1 | exact source scope; owner pending |
| `IMP-gateway-7` | current-deliberate-difference | `POST /mcp` | `call.client_at_risk.typical / result.isError` | 1 / 1 | exact source scope; owner pending |
| `IMP-gateway-8` | current-deliberate-difference | `POST /mcp` | `call.findings_list.typical / result.isError` | 1 / 1 | exact source scope; owner pending |
| `IMP-integrate-W2-1` | current-deliberate-difference | `POST /api/chat` | `chat.ask-client / events` | 34 / 34 | exact source scope; owner pending |
| `IMP-integrate-W2-2` | current-deliberate-difference | `GET /api/v2/portfolio` | `* / items[0].states` | 38 / 38 | exact source scope; owner pending |
| `IMP-integrate-W2-3` | current-deliberate-difference | `GET /api/v2/portfolio` | `* / items[0].priceable_states` | 38 / 38 | exact source scope; owner pending |
| `IMP-integrate-W2-4` | current-deliberate-difference | `GET /api/v2/portfolio` | `* / items[1].states` | 9 / 9 | exact source scope; owner pending |
| `IMP-integrate-W2-5` | current-deliberate-difference | `GET /api/v2/portfolio` | `* / items[1].priceable_states` | 9 / 9 | exact source scope; owner pending |
| `IMP-integrate-W2-6` | current-deliberate-difference | `GET /api/v2/portfolio` | `* / items[2].states` | 7 / 7 | exact source scope; owner pending |
| `IMP-integrate-W2-7` | current-deliberate-difference | `GET /api/v2/portfolio` | `* / items[2].priceable_states` | 7 / 7 | exact source scope; owner pending |
| `IMP-integrate-W2-8` | current-deliberate-difference | `GET /api/v2/portfolio` | `* / items[3].states` | 7 / 7 | exact source scope; owner pending |
| `IMP-integrate-W2-9` | current-deliberate-difference | `GET /api/v2/portfolio` | `* / items[3].priceable_states` | 7 / 7 | exact source scope; owner pending |
| `IMP-integrate-W2-10` | current-deliberate-difference | `GET /api/v2/portfolio` | `portfolio.scope-state / *` | 4 / 3 | broad-scope-owner-review |
| `IMP-integrate-W2-11` | current-deliberate-difference | `GET /docs` | `* / body.text` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-12` | current-deliberate-difference | `GET /redoc` | `* / body.text` | 1 / 1 | exact source scope; owner pending |
| `IMP-integrate-W2-13` | current-deliberate-difference | `GET /docs/oauth2-redirect` | `* / body.text` | 1 / 1 | exact source scope; owner pending |
| `IMP-integrate-W2-14` | current-deliberate-difference | `GET /api/health` | `cors.simple / headers.access-control-allow-origin` | 1 / 1 | exact source scope; owner pending |
| `IMP-integrate-W2-15` | current-deliberate-difference | `GET /api/v2/portfolio` | `* / detail[0].type` | 1 / 1 | exact source scope; owner pending |
| `IMP-integrate-W2-16` | current-deliberate-difference | `POST /api/claims` | `* / detail[0].` | 15 / 4 | exact source scope; owner pending |
| `IMP-integrate-W2-17` | current-deliberate-difference | `POST /api/claims/cell/{client_id}/{program_code}/{tax_year}/transition` | `* / detail[0].` | 22 / 7 | exact source scope; owner pending |
| `IMP-integrate-W2-18` | current-deliberate-difference | `PUT /api/claims/engagement` | `* / detail[0].` | 15 / 4 | exact source scope; owner pending |
| `IMP-integrate-W2-19` | current-deliberate-difference | `POST /api/claims/assess` | `* / detail[0].` | 14 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-20` | current-deliberate-difference | `POST /api/rules/{code}/verify` | `* / detail[0].` | 13 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-21` | current-deliberate-difference | `POST /api/rules/ingested/{state}/apply` | `* / detail[0].` | 13 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-22` | current-deliberate-difference | `POST /api/findings/{finding_id}/resolve` | `* / detail[0].` | 15 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-23` | current-deliberate-difference | `POST /api/findings/{finding_id}/reopen` | `* / detail[0].` | 15 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-24` | current-deliberate-difference | `POST /api/v2/program-drafts` | `* / detail[0].` | 17 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-25` | current-deliberate-difference | `PUT /api/v2/program-drafts/{draft_id}/documents` | `* / detail[0].` | 15 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-26` | current-deliberate-difference | `POST /api/v2/program-drafts/{draft_id}/validate` | `* / detail[0].` | 8 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-27` | current-deliberate-difference | `POST /api/v2/program-drafts/{draft_id}/request-review` | `* / detail[0].` | 8 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-28` | current-deliberate-difference | `POST /api/v2/program-drafts/{draft_id}/review` | `* / detail[0].` | 18 / 4 | exact source scope; owner pending |
| `IMP-integrate-W2-29` | current-deliberate-difference | `POST /api/v2/program-drafts/{draft_id}/preview` | `* / detail[0].` | 11 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-30` | current-deliberate-difference | `POST /api/v2/program-drafts/{draft_id}/withdraw` | `* / detail[0].` | 8 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-31` | current-deliberate-difference | `POST /api/v2/program-drafts/{draft_id}/export` | `* / detail[0].` | 9 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-32` | current-deliberate-difference | `POST /api/v2/clients/{client_id}/units/{unit_id}/base-year` | `* / detail[0].` | 12 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-33` | current-deliberate-difference | `POST /api/v2/clients/{client_id}/runs` | `* / detail[0].` | 14 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-34` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / detail[0].` | 20 / 4 | exact source scope; owner pending |
| `IMP-integrate-W2-35` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.never_run` | 8 / 8 | exact source scope; owner pending |
| `IMP-integrate-W2-36` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.skip_coverage` | 8 / 8 | exact source scope; owner pending |
| `IMP-integrate-W2-38` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[0].last_run.` | 32 / 32 | exact source scope; owner pending |
| `IMP-integrate-W2-39` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[0].last_run.state` | 8 / 8 | exact source scope; owner pending |
| `IMP-integrate-W2-40` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[0].last_run.can_skip` | 8 / 8 | exact source scope; owner pending |
| `IMP-integrate-W2-41` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[0].last_run.reason` | 8 / 8 | exact source scope; owner pending |
| `IMP-integrate-W2-42` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[1].last_run.` | 8 / 8 | exact source scope; owner pending |
| `IMP-integrate-W2-43` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[1].last_run.state` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-44` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[1].last_run.can_skip` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-45` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[1].last_run.reason` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-46` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[2].last_run.` | 8 / 8 | exact source scope; owner pending |
| `IMP-integrate-W2-47` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[2].last_run.state` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-48` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[2].last_run.can_skip` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-49` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[2].last_run.reason` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-50` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[3].last_run.` | 4 / 4 | exact source scope; owner pending |
| `IMP-integrate-W2-51` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[3].last_run.state` | 1 / 1 | exact source scope; owner pending |
| `IMP-integrate-W2-52` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[3].last_run.can_skip` | 1 / 1 | exact source scope; owner pending |
| `IMP-integrate-W2-53` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.first_items[3].last_run.reason` | 1 / 1 | exact source scope; owner pending |
| `IMP-integrate-W2-54` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.programs.none` | 8 / 8 | exact source scope; owner pending |
| `IMP-integrate-W2-55` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / preview.programs.GA_JTC` | 8 / 8 | exact source scope; owner pending |
| `IMP-integrate-W2-56` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / dry_run_summary.never_run` | 5 / 5 | exact source scope; owner pending |
| `IMP-integrate-W2-57` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / dry_run_summary.skip_coverage` | 5 / 5 | exact source scope; owner pending |
| `IMP-integrate-W2-58` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / dry_run_summary.skip_candidates_upper_bound` | 1 / 1 | exact source scope; owner pending |
| `IMP-integrate-W2-59` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / dry_run_summary.programs.none` | 5 / 5 | exact source scope; owner pending |
| `IMP-integrate-W2-60` | current-deliberate-difference | `POST /api/v2/run-batches` | `* / dry_run_summary.programs.GA_JTC` | 5 / 5 | exact source scope; owner pending |
| `IMP-integrate-W2-61` | current-deliberate-difference | `GET /api/v2/run-batches/{batch_id}` | `* / dry_run_summary.never_run` | 5 / 5 | exact source scope; owner pending |
| `IMP-integrate-W2-62` | current-deliberate-difference | `GET /api/v2/run-batches/{batch_id}` | `* / dry_run_summary.skip_coverage` | 5 / 5 | exact source scope; owner pending |
| `IMP-integrate-W2-63` | current-deliberate-difference | `GET /api/v2/run-batches/{batch_id}` | `* / dry_run_summary.skip_candidates_upper_bound` | 1 / 1 | exact source scope; owner pending |
| `IMP-integrate-W2-64` | current-deliberate-difference | `GET /api/v2/run-batches/{batch_id}` | `* / dry_run_summary.programs.none` | 5 / 5 | exact source scope; owner pending |
| `IMP-integrate-W2-65` | current-deliberate-difference | `GET /api/v2/run-batches/{batch_id}` | `* / dry_run_summary.programs.GA_JTC` | 5 / 5 | exact source scope; owner pending |
| `IMP-integrate-W2-66` | current-deliberate-difference | `POST /api/v2/run-batches/{batch_id}/cancel` | `* / dry_run_summary.never_run` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-67` | current-deliberate-difference | `POST /api/v2/run-batches/{batch_id}/cancel` | `* / dry_run_summary.skip_coverage` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-69` | current-deliberate-difference | `POST /api/v2/run-batches/{batch_id}/cancel` | `* / dry_run_summary.programs.none` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-70` | current-deliberate-difference | `POST /api/v2/run-batches/{batch_id}/cancel` | `* / dry_run_summary.programs.GA_JTC` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-71` | current-deliberate-difference | `POST /api/v2/run-batches/{batch_id}/retry-failed` | `* / dry_run_summary.never_run` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-72` | current-deliberate-difference | `POST /api/v2/run-batches/{batch_id}/retry-failed` | `* / dry_run_summary.skip_coverage` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-74` | current-deliberate-difference | `POST /api/v2/run-batches/{batch_id}/retry-failed` | `* / dry_run_summary.programs.none` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-75` | current-deliberate-difference | `POST /api/v2/run-batches/{batch_id}/retry-failed` | `* / dry_run_summary.programs.GA_JTC` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-76` | current-deliberate-difference | `GET /api/v2/run-batches` | `* / items[0].dry_run_summary.never_run` | 4 / 4 | exact source scope; owner pending |
| `IMP-integrate-W2-77` | current-deliberate-difference | `GET /api/v2/run-batches` | `* / items[0].dry_run_summary.skip_coverage` | 4 / 4 | exact source scope; owner pending |
| `IMP-integrate-W2-79` | current-deliberate-difference | `GET /api/v2/run-batches` | `* / items[0].dry_run_summary.programs.none` | 4 / 4 | exact source scope; owner pending |
| `IMP-integrate-W2-80` | current-deliberate-difference | `GET /api/v2/run-batches` | `* / items[0].dry_run_summary.programs.GA_JTC` | 4 / 4 | exact source scope; owner pending |
| `IMP-integrate-W2-81` | current-deliberate-difference | `GET /api/v2/run-batches` | `* / items[1].dry_run_summary.never_run` | 3 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-82` | current-deliberate-difference | `GET /api/v2/run-batches` | `* / items[1].dry_run_summary.skip_coverage` | 3 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-83` | current-deliberate-difference | `GET /api/v2/run-batches` | `* / items[1].dry_run_summary.skip_candidates_upper_bound` | 3 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-84` | current-deliberate-difference | `GET /api/v2/run-batches` | `* / items[1].dry_run_summary.programs.none` | 3 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-85` | current-deliberate-difference | `GET /api/v2/run-batches` | `* / items[1].dry_run_summary.programs.GA_JTC` | 3 / 3 | exact source scope; owner pending |
| `IMP-integrate-W2-86` | current-deliberate-difference | `GET /api/v2/run-batches` | `* / items[2].dry_run_summary.never_run` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-87` | current-deliberate-difference | `GET /api/v2/run-batches` | `* / items[2].dry_run_summary.skip_coverage` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-89` | current-deliberate-difference | `GET /api/v2/run-batches` | `* / items[2].dry_run_summary.programs.none` | 2 / 2 | exact source scope; owner pending |
| `IMP-integrate-W2-90` | current-deliberate-difference | `GET /api/v2/run-batches` | `* / items[2].dry_run_summary.programs.GA_JTC` | 2 / 2 | exact source scope; owner pending |
| `IMP-orchestrator-1` | current-deliberate-difference | `POST /responses` | `* / *` | 0 / 0 | broad-scope-owner-review, not-hit-in-fresh-sample |
| `IMP-orchestrator-2` | current-deliberate-difference | `POST /responses` | `* / *` | 0 / 0 | broad-scope-owner-review, not-hit-in-fresh-sample |
| `IMP-orchestrator-3` | current-deliberate-difference | `POST /responses` | `* / *` | 0 / 0 | broad-scope-owner-review, not-hit-in-fresh-sample |
| `IMP-routes_ai_agents-1` | current-deliberate-difference | `POST /api/chat` | `chat.ask / events` | 32 / 32 | exact source scope; owner pending |
| `IMP-routes_ai_agents-2` | current-deliberate-difference | `POST /api/summary` | `summary.client / events` | 9 / 9 | exact source scope; owner pending |
| `IMP-routes_claims-1` | current-deliberate-difference | `POST /api/clients/{client_id}/packages` | `package.create-again / *` | 5 / 4 | broad-scope-owner-review |
| `IMP-routes_claims-2` | current-deliberate-difference | `POST /api/claims` | `claims.create-duplicate / *` | 38 / 38 | broad-scope-owner-review |
| `IMP-routes_claims-3` | current-deliberate-difference | `GET /api/v2/portfolio` | `portfolio.scope / *` | 4 / 3 | broad-scope-owner-review |
| `IMP-routes_claims-4` | current-deliberate-difference | `GET /api/clients/{client_id}/artifacts/{artifact_id}` | `* / body.zip_entries[xl/worksheets/sheet4.xml]` | 0 / 0 | not-hit-in-fresh-sample |
| `IMP-routes_claims-5` | current-deliberate-difference | `POST /api/clients/{client_id}/packages` | `* / headers.location` | 3 / 2 | exact source scope; owner pending |
| `IMP-routes_claims-6` | current-deliberate-difference | `GET /api/clients/{client_id}/artifacts/{artifact_id}` | `* / status` | 0 / 0 | not-hit-in-fresh-sample |
| `IMP-routes_drafts_runs-1` | current-deliberate-difference | `GET /api/v2/clients/{client_id}/runs/latest` | `* / *` | 113 / 112 | broad-scope-owner-review |
| `IMP-routes_drafts_runs-2` | current-deliberate-difference | `POST /api/v2/program-drafts/{draft_id}/preview` | `preview-client-refused / *` | 13 / 13 | broad-scope-owner-review |
| `IMP-routes_drafts_runs-3` | current-deliberate-difference | `POST /api/v2/program-drafts` | `create-bad-code / detail.reason` | 1 / 0 | exact source scope; owner pending |
| `IMP-routes_drafts_runs-5` | current-deliberate-difference | `POST /api/v2/program-drafts/{draft_id}/export` | `second-export / *` | 1 / 1 | broad-scope-owner-review |
| `IMP-routes_reads-1` | current-deliberate-difference | `GET /api/v2/clients/{client_id}/units` | `unknown.client-huge / *` | 2 / 2 | broad-scope-owner-review |
| `IMP-routes_reads-2` | current-deliberate-difference | `GET /api/progress/{tax_year}` | `get-api-progress-tax-year.query-within-negative / *` | 2 / 2 | broad-scope-owner-review |
| `IMP-routes_reads-3` | current-deliberate-difference | `GET /api/simulate/portfolio/{tax_year}` | `unrecorded.simulate-portfolio-magnitude-over-bound / *` | 0 / 0 | broad-scope-owner-review, not-a-recorded-case, not-hit-in-fresh-sample |
| `IMP-routes_reads-4` | current-deliberate-difference | `POST /api/onezero/employee/{employee_id}/review` | `unrecorded.review-store-reopen / *` | 0 / 0 | broad-scope-owner-review, not-a-recorded-case, not-hit-in-fresh-sample |
| `IMP-routes_reads-5` | current-deliberate-difference | `POST /api/ingestion/{tax_year}/exceptions/{exception_id}/resolve` | `unrecorded.resolve-store-reopen / *` | 0 / 0 | broad-scope-owner-review, not-a-recorded-case, not-hit-in-fresh-sample |
| `IMP-routes_reads-6` | current-deliberate-difference | `GET /api/v2/clients/{client_id}/units/{unit_id}` | `* / detail` | 18 / 1 | exact source scope; owner pending |
| `IMP-routes_reads-7` | current-deliberate-difference | `POST /api/employee/drill` | `* / detail` | 21 / 3 | exact source scope; owner pending |
| `IMP-routes_reads-8` | current-deliberate-difference | `GET /api/me` | `cors.simple-with-token / headers.access-control-allow-origin` | 1 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-9` | current-deliberate-difference | `GET /api/eligibility/{tax_year}` | `* / detail` | 23 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-10` | current-deliberate-difference | `GET /api/progress/{tax_year}` | `* / detail` | 7 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-11` | current-deliberate-difference | `GET /api/forecast/{tax_year}` | `* / detail` | 5 / 1 | exact source scope; owner pending |
| `IMP-routes_reads-12` | current-deliberate-difference | `GET /api/alerts/monthly/{tax_year}` | `* / detail` | 4 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-13` | current-deliberate-difference | `GET /api/triggers` | `* / detail` | 3 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-14` | current-deliberate-difference | `GET /api/performance/{tax_year}` | `* / detail` | 4 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-15` | current-deliberate-difference | `GET /api/onezero/matrix/{tax_year}` | `* / detail` | 1 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-16` | current-deliberate-difference | `GET /api/onezero/{tax_year}` | `* / detail` | 4 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-17` | current-deliberate-difference | `GET /api/onezero/{tax_year}/employee/{employee_id}` | `* / detail` | 4 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-18` | current-deliberate-difference | `POST /api/onezero/employee/{employee_id}/review` | `* / detail` | 20 / 3 | exact source scope; owner pending |
| `IMP-routes_reads-19` | current-deliberate-difference | `GET /api/designations/{state}` | `* / detail` | 1 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-20` | current-deliberate-difference | `GET /api/reconcile/{tax_year}` | `* / detail` | 4 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-21` | current-deliberate-difference | `GET /api/qc/{tax_year}` | `* / detail` | 6 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-22` | current-deliberate-difference | `GET /api/onezero/retroactive/scan` | `* / detail` | 3 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-23` | current-deliberate-difference | `GET /api/simulate/portfolio/{tax_year}` | `* / detail` | 5 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-24` | current-deliberate-difference | `POST /api/simulate/unit` | `* / detail` | 27 / 3 | exact source scope; owner pending |
| `IMP-routes_reads-25` | current-deliberate-difference | `POST /api/simulate/employee` | `* / detail` | 20 / 3 | exact source scope; owner pending |
| `IMP-routes_reads-26` | current-deliberate-difference | `POST /api/simulate/onezero` | `* / detail` | 16 / 3 | exact source scope; owner pending |
| `IMP-routes_reads-27` | current-deliberate-difference | `GET /api/ingestion/{tax_year}` | `* / detail` | 6 / 1 | exact source scope; owner pending |
| `IMP-routes_reads-28` | current-deliberate-difference | `POST /api/ingestion/{tax_year}/exceptions/{exception_id}/resolve` | `* / detail` | 22 / 3 | exact source scope; owner pending |
| `IMP-routes_reads-29` | current-deliberate-difference | `GET /api/ingestion/{tax_year}/rows` | `* / detail` | 7 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-30` | current-deliberate-difference | `GET /api/proximity/{tax_year}` | `* / detail` | 18 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-31` | current-deliberate-difference | `GET /api/scope/client/{account_id}` | `* / detail` | 3 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-32` | current-deliberate-difference | `GET /api/v2/clients/{client_id}/units` | `* / detail` | 16 / 3 | exact source scope; owner pending |
| `IMP-routes_reads-33` | current-deliberate-difference | `GET /api/v2/employees/{record_token}` | `* / detail` | 8 / 2 | exact source scope; owner pending |
| `IMP-routes_reads-34` | current-deliberate-difference | `GET /api/me` | `* / detail` | 15 / 0 | exact source scope; owner pending |
| `IMP-routes_reads-35` | current-deliberate-difference | `GET /api/scope` | `unavailable.scope / *` | 4 / 4 | broad-scope-owner-review |
| `IMP-routes_reads-36` | current-deliberate-difference | `GET /api/forecast/{tax_year}` | `unavailable.forecast / *` | 2 / 1 | broad-scope-owner-review |
| `IMP-routes_reads-37` | current-deliberate-difference | `GET /api/ingestion/{tax_year}` | `unavailable.ingestion / *` | 2 / 1 | broad-scope-owner-review |
| `IMP-persistence-1` | historical-withdrawn | `POST /api/v2/clients/{client_id}/runs` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-persistence-2` | historical-withdrawn | `GET /api/v2/clients/{client_id}/runs/latest` | `client2002.run-latest-after / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-persistence-3` | historical-withdrawn | `GET /api/v2/clients/{client_id}/units` | `unknown.client-huge / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-persistence-4` | historical-withdrawn | `POST /api/claims` | `claims.create-duplicate / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-routes_drafts_runs-4` | historical-withdrawn | `POST /api/v2/program-drafts` | `create / draft_id` | 0 / 0 | exact source scope; owner pending |
| `IMP-sources_auth_ai-1` | historical-withdrawn | `POST /api/clients/{id}/packages` | `p1_artifacts_ai:package.create-again / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-sources_auth_ai-2` | historical-withdrawn | `POST /api/clients/{id}/packages` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-sources_auth_ai-3` | historical-withdrawn | `POST /api/v2/run-batches` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-sources_auth_ai-4` | historical-withdrawn | `POST /api/v2/run-batches` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-sources_auth_ai-5` | historical-withdrawn | `POST /api/chat` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-sources_auth_ai-6` | historical-withdrawn | `POST /api/chat` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-sources_auth_ai-7` | historical-withdrawn | `POST /api/chat` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-sources_auth_ai-8` | historical-withdrawn | `POST /api/chat` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-sources_auth_ai-9` | historical-withdrawn | `POST /api/chat` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-sources_auth_ai-10` | historical-withdrawn | `POST /api/chat` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-routes_drafts_runs-6` | historical-withdrawn | `POST /api/v2/clients/{client_id}/runs` | `* / validation.queries_run` | 0 / 0 | exact source scope; owner pending |
| `IMP-routes_ai_agents-1` | historical-superseded-scope | `POST /api/chat` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-routes_ai_agents-2` | historical-superseded-scope | `POST /api/summary` | `summary.client / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-routes_ai_agents-3` | historical-withdrawn | `POST /api/summary` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-routes_ai_agents-4` | historical-withdrawn | `POST /api/chat` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-routes_ai_agents-5` | historical-withdrawn | `POST /api/summary` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-routes_ai_agents-6` | historical-withdrawn | `POST /api/chat` | `* / headers.content-type` | 0 / 0 | exact source scope; owner pending |
| `IMP-routes_ai_agents-7` | historical-withdrawn | `POST /api/summary` | `* / headers.content-type` | 0 / 0 | exact source scope; owner pending |
| `IMP-routes_ai_agents-8` | historical-withdrawn | `POST /api/capabilities/{tool}` | `* / detail` | 0 / 0 | exact source scope; owner pending |
| `IMP-routes_ai_agents-9` | historical-withdrawn | `POST /api/capabilities/{tool}` | `* / error.message` | 0 / 0 | exact source scope; owner pending |
| `IMP-routes_ai_agents-10` | historical-withdrawn | `POST /api/chat` | `* / detail` | 0 / 0 | exact source scope; owner pending |
| `IMP-routes_ai_agents-11` | historical-withdrawn | `POST /api/summary` | `* / detail` | 0 / 0 | exact source scope; owner pending |
| `IMP-routes_claims-4` | historical-superseded-scope | `POST /api/clients/{client_id}/packages` | `* / *` | 0 / 0 | broad-scope-owner-review |
| `IMP-routes_claims-6` | historical-superseded-scope | `GET /api/clients/{client_id}/artifacts/{artifact_id}` | `* / *` | 0 / 0 | broad-scope-owner-review |

## Fresh unresolved cases

Each row groups all retained failing fields for one synthetic recorded case. The machine register retains category, safe path template and original failure ordinal for reproduction. No register match is treated as approval.

| Group | Scenario / case | Failing fields |
|---|---|---:|
| _unassigned | `p1_auth:cors.preflight-delete-disallowed` | 6 |
| _unassigned | `p1_auth:cors.preflight-no-token` | 7 |
| _unassigned | `p1_auth:cors.preflight-patch-disallowed` | 6 |
| _unassigned | `p1_auth:cors.preflight-put` | 6 |
| _unassigned | `p1_auth:none.trailing-slash` | 5 |
| _unassigned | `p1_program_drafts:get-api-v2-program-drafts-draft-id-export-manifest.trailing-slash` | 4 |
| _unassigned | `p1_program_drafts:get-api-v2-program-drafts-draft-id.trailing-slash` | 4 |
| _unassigned | `p1_program_drafts:get-api-v2-program-drafts.head` | 1 |
| _unassigned | `p1_program_drafts:get-api-v2-program-drafts.options` | 1 |
| _unassigned | `p1_program_drafts:get-api-v2-program-drafts.trailing-slash` | 4 |
| _unassigned | `p1_program_drafts:post-api-v2-program-drafts.wrong-method-delete` | 1 |
| _unassigned | `p1_reads:case.path-uppercase` | 9 |
| _unassigned | `p1_reads:cors.preflight` | 7 |
| _unassigned | `p1_reads:cors.preflight-disallowed-method` | 6 |
| _unassigned | `p1_reads:get-api-alerts-monthly-tax-year.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-audit-channel.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-capabilities.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-claims-cell-client-id-program-code-tax-year.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-claims-coverage-client-id.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-claims-coverage.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-claims-lifecycle.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-clients-client-id-artifacts-artifact-id.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-designations-state.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-eligibility-tax-year.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-findings-client-id-finding-id-history.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-findings-client-id-tax-year.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-forecast-tax-year.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-health.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-ingestion-tax-year-rows.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-ingestion-tax-year.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-me.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-onezero-matrix-tax-year.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-onezero-retroactive-scan.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-onezero-tax-year-employee-employee-id.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-onezero-tax-year.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-performance-tax-year.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-progress-tax-year.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-proximity-tax-year.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-qc-tax-year.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-ready.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-reconcile-tax-year.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-rules-ingested-state-changelog.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-rules-ingested-state-proposals.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-rules-ingested-state-refresh.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-rules-ingested-state.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-rules.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-scope-client-account-id.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-scope.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-simulate-portfolio-tax-year.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-triggers.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-clients-client-id-runs-latest.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-clients-client-id-situation.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-clients-client-id-units-unit-id-rebase.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-clients-client-id-units-unit-id.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-clients-client-id-units.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-employees-record-token.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-portfolio.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-program-drafts-draft-id-export-manifest.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-program-drafts-draft-id.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-program-drafts.head` | 1 |
| _unassigned | `p1_reads:get-api-v2-program-drafts.options` | 1 |
| _unassigned | `p1_reads:get-api-v2-program-drafts.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-programs-code.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-programs.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-run-batches-batch-id-items.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-run-batches-batch-id.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-v2-run-batches.head` | 1 |
| _unassigned | `p1_reads:get-api-v2-run-batches.options` | 1 |
| _unassigned | `p1_reads:get-api-v2-run-batches.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-workspace-assumptions.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-workspace-calculation-walk.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-workspace-comparison.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-workspace-onezero-method.trailing-slash` | 4 |
| _unassigned | `p1_reads:get-api-workspace.trailing-slash` | 4 |
| _unassigned | `p1_reads:trailing.health` | 4 |
| _unassigned | `p1_writes:post-api-findings-finding-id-reopen.wrong-method-delete` | 1 |
| _unassigned | `p1_writes:post-api-findings-finding-id-resolve.wrong-method-delete` | 1 |
| _unassigned | `p1_writes:post-api-workspace-onezero-contributors.wrong-method-delete` | 1 |
| _unassigned | `p2_run_batches:post-api-v2-run-batches.wrong-method-delete` | 1 |
| claims_artifacts_rules | `p1_auth:agent.read-allowed` | 1 |
| claims_artifacts_rules | `p1_auth:agent.write-claims-as-writer` | 1 |
| claims_artifacts_rules | `p1_auth:client-authz.portfolio-names-no-client` | 1 |
| claims_artifacts_rules | `p1_auth:ratelimit.writer-reads-unaffected` | 1 |
| claims_artifacts_rules | `p1_auth:reader.read-portfolio` | 1 |
| claims_artifacts_rules | `p1_auth:writer.assess` | 1 |
| claims_artifacts_rules | `p1_auth:writer.claims-create` | 1 |
| claims_artifacts_rules | `p1_auth:writer.transition` | 1 |
| claims_artifacts_rules | `p1_reads:get-api-claims-coverage.query-tax_year-zero` | 4 |
| claims_artifacts_rules | `p1_workspace_unavailable:unavailable.portfolio` | 20 |
| claims_artifacts_rules | `p1_writes:claims.coverage-final` | 7 |
| claims_artifacts_rules | `p1_writes:claims.create-money-as-number` | 1 |
| claims_artifacts_rules | `p1_writes:claims.create-money-as-string` | 1 |
| claims_artifacts_rules | `p1_writes:claims.create-money-raw-exponent` | 1 |
| claims_artifacts_rules | `p1_writes:claims.create-unknown-client` | 1 |
| claims_artifacts_rules | `p1_writes:claims.portfolio-final` | 2 |
| claims_artifacts_rules | `p1_writes:claims.read-after` | 2 |
| claims_artifacts_rules | `p1_writes:post-api-claims.body-long-string-program_code` | 38 |
| claims_artifacts_rules | `p1_writes:post-api-claims.body-unicode-program_code` | 1 |
| claims_artifacts_rules | `p1_writes:post-api-rules-code-verify.body-long-string-verified_by` | 4 |
| claims_artifacts_rules | `p1_writes:put-api-claims-engagement.body-long-string-program_code` | 10 |
| drafts_runs | `p1_auth:writer.base-year` | 2 |
| drafts_runs | `p1_auth:writer.draft-create` | 1 |
| drafts_runs | `p1_auth:writer.run` | 1 |
| drafts_runs | `p1_writes:baseyear.rebase-after` | 1 |
| drafts_runs | `p1_writes:baseyear.year-null` | 2 |
| drafts_runs | `p1_writes:ok.post-api-v2-clients-client-id-runs` | 1 |
| drafts_runs | `p1_writes:ok.post-api-v2-clients-client-id-units-unit-id-base-year` | 2 |
| drafts_runs | `p2_run_batches:dry-run-filter` | 4 |
| drafts_runs | `p2_run_batches:items-cancelled` | 4 |
| drafts_runs | `p2_run_batches:items-queued` | 1 |
| drafts_runs | `p2_run_batches:unknown-client` | 1 |
| gateway | `g1_mcp:call.client_at_risk.typical` | 8 |
| gateway | `g1_mcp:call.data_catalog.typical` | 10 |
| gateway | `g1_mcp:call.findings_list.typical` | 8 |
| gateway | `g1_rest:download.other-user` | 1 |
| gateway | `g1_rest:download.owner` | 1 |
| gateway | `g1_rest:download.owner-again-single-use` | 1 |
| gateway | `g1_rest:download.unknown-ticket` | 1 |
| gateway | `g1_rest:download.unknown-ticket-with-token` | 1 |
| gateway | `g1_rest:narration.delegated` | 1 |
| gateway | `g1_rest:tool.base_year_set_prepare.typical` | 1 |
| gateway | `g1_rest:tool.claim_package_create_prepare.typical` | 1 |
| gateway | `g1_rest:tool.claim_record_prepare.typical` | 1 |
| gateway | `g1_rest:tool.claim_transition_prepare.typical` | 1 |
| gateway | `g1_rest:tool.data_catalog.typical` | 7 |
| gateway | `g1_rest:tool.delegated-book-rank` | 1 |
| gateway | `g1_rest:tool.engagement_set_prepare.typical` | 1 |
| gateway | `g1_rest:write.claim-package-commit` | 2 |
| gateway | `g1_rest:write.claim-package-prepare` | 1 |
| gateway | `g1_rest:write.prepare` | 1 |
| reads_calc | `p1_auth:reader.read-units` | 45 |
| reads_calc | `p1_query_edges:unknown.client-negative` | 19 |
| reads_calc | `p1_query_edges:unknown.client-zero` | 19 |
| reads_calc | `p1_reads:get-api-v2-clients-client-id-units-unit-id.query-limit-huge` | 21 |
| reads_calc | `p1_reads:get-api-v2-clients-client-id-units.query-limit-huge` | 19 |
| reads_calc | `p1_reads:get-api-v2-employees-record-token.query-client_id-negative` | 12 |
| reads_calc | `p1_reads:get-api-v2-employees-record-token.query-client_id-zero` | 12 |
| reads_calc | `p1_writes:ok.post-api-employee-drill` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-comparison-stage.body-json-null` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-comparison-stage.body-not-json` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-comparison-stage.body-wrong-content-type` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-comparison-stage.body-wrong-type-stage` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-eligibility-search.body-json-null` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-eligibility-search.body-not-json` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-eligibility-search.body-wrong-content-type` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-employee.body-json-null` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-employee.body-not-json` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-employee.body-wrong-content-type` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-onezero-contributors.body-json-null` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-onezero-contributors.body-not-json` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-onezero-contributors.body-wrong-content-type` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-onezero-contributors.body-wrong-type-method` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-source-search.body-json-null` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-source-search.body-not-json` | 1 |
| workspace_sealed | `p1_writes:post-api-workspace-source-search.body-wrong-content-type` | 1 |

## Operational and policy decisions

### DEC-M01 - year-pack ingestion precedence

Captured ingestion overrides a materialised year's wage_basis, measuring_date and pay codes. ADR-005 says fill missing values, never override year-resolved ones. Preserve the ported figure until reconciled.

**Owner:** statutory/domain owner. **Disposition:** Keep current behavior; independently reconcile any correction. **Review:** required.

Evidence: `dotnet/docs/DOMAIN-SLICE-REPORT.md`; `dotnet/docs/findings.md`; `docs/architecture/ADR-005-year-versioned-rules.md`.

### DEC-MULTI-PROGRAM - credit_math first-program pricing

A multi-program state prices its first program in credit_math. Typed run-resolution refusals do not make that helper unambiguous. Adding a refusal there changes valid figures.

**Owner:** statutory/domain owner. **Disposition:** Preserve helper; decide the contextual inward API before correction. **Review:** required.

Evidence: `dotnet/docs/DOMAIN-SLICE-REPORT.md`; `dotnet/docs/findings.md`.

### DEC-ZERO-WORKSITE - source SQL versus row projection

SQL COALESCE keeps worksite zero while the projector's falsy fallback selects location. Aggregated state and source rows can therefore disagree.

**Owner:** source and calculation owners. **Disposition:** Reconcile source semantics and calculated impact; no observer rewrite. **Review:** required.

Evidence: `dotnet/docs/SOURCES-AUTH-AI-REPORT.md`; `dotnet/src/TaxCredit.Infrastructure.Sources/Sql/SourceQueries.cs`.

### DEC-LEAP - strict fiscal-window leap shifts

The contextual strict adapter refuses a Feb-29 to Feb-28 shift into a non-leap target. The certified inward port lacks the year/convention context and can substitute a calendar window.

**Owner:** application/domain and statutory owners. **Disposition:** Design a contextual inward port and reconcile fixtures before changing behavior. **Review:** required.

Evidence: `dotnet/docs/COMPOSITION-REPORT.md`; `dotnet/docs/DOMAIN-SLICE-REPORT.md`.

### DEC-NATIVE-MONEY - native AVG and DECIMAL(19,4) wire scale

Exact SQLite sums and typed decimal binding do not prove native monetary AVG, datetime metadata or string scale. A money string ending .0 is not the same contract as .0000.

**Owner:** persistence and client-contract owners. **Disposition:** Agree exact wire scale and measure native metadata; never float-normalise or waive changed figures. **Review:** required.

Evidence: `dotnet/docs/PERSISTENCE-REPORT.md`; `dotnet/docs/SOURCES-AUTH-AI-REPORT.md`; `dotnet/docs/GATEWAY-CONVERGENCE-REPORT.md`.

### DEC-QC-DROP - CAP-10 QC annotations versus calculation

The QC drop helper is not applied to run computation. A persisted drop annotation is not proof that Gold excluded the source row.

**Owner:** calculation and QC owners. **Disposition:** Preserve inherited result; decide and reconcile any change. **Review:** required.

Evidence: `dotnet/docs/DOMAIN-SLICE-REPORT.md`; `dotnet/docs/findings.md`.

### DEC-LEGACY-FISCAL - legacy forecast, OneZero and tax-year selection

Legacy calendar/scalar-benefit and first-row canonical paths do not consistently use the resolved client fiscal window. Tax-year-zero status/value residuals are not F-18 counters.

**Owner:** ReadsCalc and statutory owners. **Disposition:** Keep URLs and behavior; prioritise separate reconciled fixes. **Review:** required.

Evidence: `dotnet/docs/ROUTES-READS-REPORT.md`; `dotnet/docs/DOMAIN-SLICE-REPORT.md`; `dotnet/docs/port-map.md`.

### DEC-OVERRIDE-ORDER - historical equal-time override order

New write_order makes future equal-time intent deterministic. Backfilling a sequence cannot reconstruct historical intent that was never stored.

**Owner:** persistence and operations owners. **Disposition:** Retain migration provenance and obtain explicit reconciliation for ambiguous history. **Review:** required.

Evidence: `dotnet/docs/COMPOSITION-SCHEMA-PROVISIONING.md`; `dotnet/docs/PERSISTENCE-REPORT.md`.

### DEC-F14 - reader.assess; reader.run; reader.rules-verify; reader.batch-dry-run

These four named valid requests retain the Python authorization outcome under the owner's exception. A general writer-everywhere rule does not authorize silently changing them.

**Owner:** authorization and business owners. **Disposition:** Decide valid-request entitlement explicitly; no shadow policy change. **Review:** required.

Evidence: `contract/FINDINGS.md`; `dotnet/docs/ROUTES-CONVERGENCE-REPORT.md`; `dotnet/docs/ROUTES-READS-REPORT.md`.

### DEC-GATEWAY-LANE - POST /mcp: call.client_at_risk.typical; call.findings_list.typical

Two reader calls are refused as employee_level_not_allowed after person-derived facts are correctly marked. The privacy rationale does not waive missing facts or settle valid-request authorization.

**Owner:** gateway privacy and authorization owners. **Disposition:** Keep fail-closed behavior until a reviewed lane contract is agreed. **Review:** required.

Evidence: `dotnet/docs/GATEWAY-CONVERGENCE-REPORT.md`; `dotnet/docs/improvements/gateway.json`.

### DEC-GATEWAY-DATASETS - REST/MCP data_catalog

Only eight warehouse datasets are bound, versus eleven advertised by the recorded contract. Payroll, location and pay_code source bindings are missing; schema/description/count differences remain real failures.

**Owner:** source, governed-query and gateway owners. **Disposition:** Implement canonical source bindings and rerun complete catalogue and query cases; no missing-fact waiver. **Review:** required.

Evidence: `dotnet/docs/GATEWAY-CONVERGENCE-REPORT.md`; `contract/inventory/channel.json`.

### DEC-ALLOCATION - confirmations, correlations, artifacts and run/override identities

Python previews consume temporary claim identities while .NET previews remain pure. Later real allocations diverge; the standalone gateway's fifteen drift cases are not random UUID noise.

**Owner:** application, persistence and gateway owners. **Disposition:** Agree identity history with real effects; do not burn dummy draws or rewrite response IDs. **Review:** required.

Evidence: `dotnet/docs/GATEWAY-CONVERGENCE-REPORT.md`; `dotnet/docs/findings.md`.

### DEC-STORAGE-BOUNDS - claim/engagement program_code and rule verifier text

Some recorded valid strings exceed native storage limits. Returning 500, truncating data or broad-waiving the difference is not equivalent designed functionality.

**Owner:** claims/rules and persistence owners. **Disposition:** Choose a compatible validation/storage contract, then producer repair and forward migration if needed. **Review:** required.

Evidence: `dotnet/docs/ROUTES-CLAIMS-REPORT.md`; `dotnet/docs/GATEWAY-CONVERGENCE-REPORT.md`.

### DEC-READ-RESIDUALS - unavailable portfolio; stored program/base-year and run-ID residuals

503 versus degraded 200, stored program/base-year decisions, identifiers and money-scale differences remain outside global error-wording tolerances and the F-18 operational-counter exception.

**Owner:** ReadsCalc, claims, drafts/runs and persistence producers. **Disposition:** Use exact fresh case/field inventory for producer fixes; no convergence fixes in observer. **Review:** required.

Evidence: `dotnet/docs/GATEWAY-CONVERGENCE-REPORT.md`; `dotnet/docs/ROUTES-CONVERGENCE-REPORT.md`; `dotnet/docs/integration-replay.json`.

### DEC-NATIVE-SCHEMA - native schemas, supplemental tables and grants

Native access is unproved. finding_audit, operational write sequence, work identity and source-observation additions require the Python operator migration/grant procedure; local SQLite bootstrap is not native provisioning proof.

**Owner:** deployment, database and persistence owners. **Disposition:** Apply reviewed forward-only Python migrations/grants in a change window; verify native read/write/type cases separately. No EF migrations. **Review:** required.

Evidence: `dotnet/docs/COMPOSITION-SCHEMA-PROVISIONING.md`; `dotnet/docs/PERSISTENCE-REPORT.md`; `dotnet/docs/PLATFORM-RISKS.md`.

### DEC-OVERRIDE-QUEUE - POST /api/v2/clients/{client_id}/units/{unit_id}/base-year

Saving override intent and accepting recalculation work are separate transactions. A queue failure may leave saved intent; resaving an unchanged override does not repair it.

**Owner:** drafts/runs and persistence owners. **Disposition:** Decide atomicity/reconciliation protocol; preserve uncertain accepted intent, never retry blindly. **Review:** required.

Evidence: `dotnet/docs/COMPOSITION-REPORT.md`; `dotnet/docs/ROUTES-DRAFTS-RUNS-REPORT.md`.

### DEC-LEASE - synchronous calculation and Worker leases

The 600-second compute lease has no periodic renewal while synchronous compute runs. Publication checks/renewal protect stale commits, not uninterrupted long native work.

**Owner:** calculation, queue and operations owners. **Disposition:** Prove long native work and recovery under agreed lease policy before enabling writes. **Review:** required.

Evidence: `dotnet/docs/COMPOSITION-REPORT.md`; `dotnet/docs/PERSISTENCE-REPORT.md`.

### DEC-FINGERPRINT - account row-count/max-modified marker

Stable count/max misses count/max-preserving edits, SQL synchronization lag and historical snapshot identity. Missing/all-null maxima cannot prove stability.

**Owner:** source and audit owners. **Disposition:** Accept the explicit observation limit or provide a stronger version source; treat changed/unprovable pairs as inconclusive. **Review:** required.

Evidence: `dotnet/docs/PLATFORM-RISKS.md`; `dotnet/src/TaxCredit.Infrastructure.Sources/Sql/SourceQueries.cs`.

### DEC-EXPORTER - real exporter delivery

Instrumentation registration and local traces do not prove the real exporter receives events. Parallel deployment assets and their results are not merged inputs.

**Owner:** deployment and observability owners. **Disposition:** Verify safe real exporter receipt and redaction in an approved environment before cutover. **Review:** required.

Evidence: `dotnet/docs/ORCHESTRATOR-REPORT.md`; `dotnet/docs/COMPOSITION-REPORT.md`.

### DEC-INGRESS - BFF, gateway and orchestrator identity

Header mapping is not authentication. Real signed-token validation alone does not establish employer binding or authentic platform headers at a direct origin.

**Owner:** security, identity and deployment owners. **Disposition:** Strip/replace untrusted headers at authenticated ingress, isolate origins, validate audiences and bind the acting person to the employer. Exclude private reads until proved. **Review:** required.

Evidence: `dotnet/docs/ORCHESTRATOR-REPORT.md`; `dotnet/docs/SOURCES-AUTH-AI-REPORT.md`; `contract/docs/AUTH-CONTRACT.md`.

### DEC-GATEWAY-IDEMPOTENCY - different confirmations sharing an idempotency key

Gateway idempotency-key exclusion is host-local. Same-confirmation atomic consume does not prove fleet-wide exclusion across distinct confirmations or replicas.

**Owner:** gateway and persistence owners. **Disposition:** Choose durable cross-replica reservation/retention or a reviewed single-authority limit. **Review:** required.

Evidence: `dotnet/docs/GATEWAY-REPORT.md`; `dotnet/docs/GATEWAY-CONVERGENCE-REPORT.md`.

### DEC-CHECKPOINTS - orchestrator checkpoints and budgets

Conversation checkpoints and budgets survive fresh graph creation only inside one process. Restart, another replica or expiry can lose confirmations and recovery identity.

**Owner:** orchestrator and operations owners. **Disposition:** Agree retention, affinity, restart and replica durability before directing conversations or confirmations. **Review:** required.

Evidence: `dotnet/docs/ORCHESTRATOR-REPORT.md`; `dotnet/docs/orchestrator-workflow-traceability.md`.

### DEC-RESULT-RECOVERY - production gateway bridge after unknown acknowledgement

The orchestrator retains a recovery-only slot locally, but the production bridge has no resultLookup and no result-recovery endpoint. An uncertain mutation cannot be repaired by replaying it in shadow.

**Owner:** gateway, orchestrator and operations owners. **Disposition:** Stop automatic retries, retain original identity, reconcile durable evidence manually; design recovery before production writes. **Review:** required.

Evidence: `dotnet/docs/ORCHESTRATOR-REPORT.md`; `dotnet/docs/orchestrator-composition-traceability.md`.

### DEC-ONE-WRITER - API, Worker, Gold and manifest ownership

Split accepted Gold/manifest destinations or competing Python/.NET Workers can make a successful write invisible or execute work twice. A route-only traffic change is insufficient.

**Owner:** API, queue, persistence and change owners. **Disposition:** Move the complete write lifecycle under one authority and one accepted destination, with controlled drain and lease reconciliation. **Review:** required.

Evidence: `dotnet/docs/COMPOSITION-REPORT.md`; `dotnet/docs/PERSISTENCE-REPORT.md`.

### DEC-ARTIFACTS - package creation, metadata, download, tickets and export

Package generations and audit must stay coherent. Links mint tickets, downloads consume them and record artifact access, even when the HTTP method is GET. Never mirror them live.

**Owner:** artifact, gateway and operations owners. **Disposition:** Keep each generation/lifecycle on its authority through expiry; preserve immutable bytes, hashes and audit on rollback. **Review:** required.

Evidence: `dotnet/docs/GATEWAY-REPORT.md`; `dotnet/docs/ROUTES-CLAIMS-REPORT.md`; `contract/docs/normalisation.md`.

### DEC-SEALED - all eleven workspace operations

The private reference extract is absent. Neither local synthetic parity nor scoped read matches certify the 10,236 / 539 / 656 reference figures. The source prompt's old count of ten operations is stale.

**Owner:** reference-data and statutory owners. **Disposition:** Keep all eleven operations on the documented unavailable path; obtain separate private-fixture reconciliation before certification. **Review:** required.

Evidence: `dotnet/docs/route-groups.json`; `dotnet/docs/DOMAIN-SLICE-REPORT.md`; `contract/CONTRACT-REPORT.md`.

### DEC-LIVE - current approved live shadow

Shadow approval is present, but the current conductor check cannot establish capacity/access because this worktree lacks Warehouse configuration. No safe endpoint, read-only SQL credential or proven employer-bound ingress is available.

**Owner:** environment, identity and database operators. **Disposition:** Provide runtime-only approved inputs and fresh admission; do not activate capacity, deploy, grant access or use another checkout's oracle. **Review:** required.

Evidence: `dotnet/docs/integration-live.json`; `dotnet/spikes/shadow/admission.py`.

### DEC-PERFORMANCE - read latency/SLO and shared capacity

There is no production SLO or agreed regression threshold. Historical engine minimum-of-five timings and a .NET open-plus-SELECT-1 observation are not live Python HTTP or write-throughput baselines.

**Owner:** service, capacity and business owners. **Disposition:** Agree workload, freshness window and acceptable median/tails/failures before approving a slice; no saturation or production writes in shadow. **Review:** required.

Evidence: `dotnet/docs/SPIKE-REPORT.md`; `dotnet/docs/PLATFORM-RISKS.md`; `dotnet/docs/integration-performance.json`.

### DEC-LIST-POLICY - list totals/counts/populations

Earlier page-independent-count demands are superseded by the injected policy: keep the recorded Python metadata semantics. A genuine post-cutover redesign is separate work.

**Owner:** contract owner. **Disposition:** Resolved for this task: retain recorded semantics, do not reopen the obsolete contradiction. **Review:** resolved or evidence boundary.

Evidence: `dotnet/docs/ROUTES-CONVERGENCE-REPORT.md`; `dotnet/spikes/shadow/policy.py`.

### DEC-FRAMEWORK-CAP - framework waiver cap below forty exchanges

Current cap_min_exchanges=40 exempts the small framework group. Its raw differences and waiver percentage remain visible. The inherited W3 halt is historical, not a current authorization to emulate framework HTML or unsafe CORS.

**Owner:** conductor policy owner. **Disposition:** Resolved for current scoring only; not an approval of other failures or cutover. **Review:** resolved or evidence boundary.

Evidence: `dotnet/docs/waves/W3-policy-stop.md`; `dotnet/docs/GATEWAY-CONVERGENCE-REPORT.md`; `dotnet/spikes/shadow/policy.py`.

### DEC-CONTAINER - ZIP/XLSX Tier-D exceptions

Only declared container bytes/metadata are exempt under existing normalisations. Ordered member names, uncompressed sizes/content hashes, header/body integrity, trails, canonical and per-file manifest hashes remain compared.

**Owner:** contract and artifact owners. **Disposition:** Preserve existing normalisations exactly; use isolated synthetic audit/ticket operations only. **Review:** resolved or evidence boundary.

Evidence: `contract/compare.py`; `contract/normalise.py`; `dotnet/spikes/shadow/test_shadow.py`.

### DEC-TRACEABILITY - 39 orchestrator records and 313 indexed guarantees

The 313 E/P/U/X entries are 156 E, 103 P, 15 U and 39 X guarantees in 32 groups, not 313 equivalent tests. Local scripted composition is not live-model or full API/REST/MCP certification.

**Owner:** orchestrator and release owners. **Disposition:** Keep record, index, transport and live-acceptance denominators separate. **Review:** resolved or evidence boundary.

Evidence: `dotnet/docs/ORCHESTRATOR-REPORT.md`; `dotnet/docs/orchestrator-spec-traceability.md`; `dotnet/docs/orchestrator-composition-traceability.md`; `dotnet/docs/orchestrator-workflow-traceability.md`.
