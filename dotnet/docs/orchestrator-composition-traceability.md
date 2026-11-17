# O5 guarded composition: named guarantee traceability

Source of guarantee names: `contract\docs\ORCHESTRATOR-SPEC.md`. This is a
test-to-guarantee map, not a claim that the Python suites were executed or that
every Python test was reproduced. The Python files named by the eight sections
below were read alongside the composer, lane projection and knowledge contracts.

## Evidence boundaries and notation

- **E**: a named .NET test directly exercises the relevant composition behavior
  using synthetic facts and injected collaborators.
- **P**: the cited test proves a narrower behavior; the remaining difference is
  stated in the same row. This is not a full-equivalence claim.
- **U**: no equivalent named .NET assertion is mapped here.
- **X**: cross-surface evidence outside this composition handoff. A nearby
  orchestrator test is identified where useful, but is not a substitute.

All test references below are methods in
`dotnet\tests\TaxCredit.Orchestrator.Tests\`, with namespace prefix
`TaxCredit.Orchestrator.Tests.`. Class/file locations:

| Class prefix used below | File |
|---|---|
| `ModelLaneTests` | `Composition\ModelLaneTests.cs` |
| `PlaceholderTests` | `Composition\PlaceholderTests.cs` |
| `GuardedReplyTests` | `Composition\GuardedReplyTests.cs` |
| `ExactnessTests` | `Composition\ExactnessTests.cs` |
| `ReferenceTests` | `Composition\ReferenceTests.cs` |
| `ScriptedTurnsTests` | `Turns\ScriptedTurnsTests.cs` |
| `RecordedTurnsTests` | `Turns\RecordedTurnsTests.cs` |
| `CheckpointTurnsTests` | `Turns\CheckpointTurnsTests.cs` |
| `CatalogProjectionTests` | `Framework\CatalogProjectionTests.cs` |
| `PackageLoopTests` | `Framework\PackageLoopTests.cs` |
| `KnowledgeWiringTests` | `Framework\KnowledgeWiringTests.cs` |
| `GatewayReplyTests` | `Boundary\GatewayReplyTests.cs` |
| `GatewayTests` | `Boundary\GatewayTests.cs` |

`CompositionFixture` supplies synthetic capability envelopes, not real payroll.
`ExactnessTests` varies synthetic exact decimal facts and checks the retained
body independently against Application's `FactIndex` and `NumericGuard`.
`ScriptedTurnsTests` crosses the actual Agent Framework tool loop and turn
pipeline, but uses an injected model and fake gateway. It is not a live Foundry
or gateway deployment test.

`ComposedReply.Body` is the independently guarded engine/narrator body.
`ReferenceText` is separately labelled quoted reference material, not numeric
authority. `Footer` contains trusted source identifiers and is appended without
model rewriting. Therefore a claim that **all of `Text`**, including quoted
references and identifier footer, passed the numeric fact guard would be wrong.

The focused validation command is:

```powershell
Set-Location dotnet
dotnet test tests\TaxCredit.Orchestrator.Tests\TaxCredit.Orchestrator.Tests.csproj --no-restore --filter FullyQualifiedName~Composition -v quiet
```

The O5 implementation handoff ran this command successfully: 113 test cases,
no failures or skips. This count includes theory cases; it is not the number of
named source guarantees. The current documentation follow-up is read-only with
respect to implementation. The parent separately reports passing all 39
deterministic records and package-backed pipeline/e2e tests; the exact named
assertions used here are identified below.

## `test_orch_data_lanes.py`

| Named source guarantee | Status | Actual .NET test method(s) and evidence limit |
|---|---|---|
| `test_the_person_gets_the_rows_and_no_model_is_sent_one` | E | `ModelLaneTests.Every_model_request_projection_contains_names_and_structure_never_person_values`; `ScriptedTurnsTests.Every_model_request_excludes_person_rows_while_the_reader_keeps_them`. The latter inspects every visible scripted-model request and the narration audit payload. |
| `test_what_a_model_is_told_about_the_rows_is_the_count_and_the_column_names` | P | `ModelLaneTests.Every_model_request_projection_contains_names_and_structure_never_person_values` asserts the public row-count path and withheld rows. Its fixture carries column names, but it does not independently assert the complete expected set of column-name paths. |
| `test_an_aggregate_is_shown_to_the_model_by_name_so_it_can_be_narrated` | E | `ModelLaneTests.Aggregate_rows_are_narratable_but_only_the_first_fifty_are_advertised` checks public aggregate paths, withheld scalar values in the brief, and successful substitution. |
| `test_the_catalog_and_the_distinct_values_are_the_declared_exception_and_nothing_else_is` | P | `ModelLaneTests.A_lookup_receives_only_its_declared_model_safe_structural_projection`; `ModelLaneTests.Even_a_misdeclared_lookup_cannot_receive_an_employee_identifier`. These exercise the explicit lookup projection and private-lane defense. There is no separate distinct-values capability fixture or assertion here that only the canonical catalog and distinct-values tools have the lookup classification. |
| `test_the_catalog_blocks_are_left_out_of_a_reply_that_something_else_answered` | E | `ModelLaneTests.A_lookup_receives_only_its_declared_model_safe_structural_projection` composes the catalog alone and beside an answering credit tool. |
| `test_a_catalog_question_is_answered_with_the_catalog` | E | `ModelLaneTests.A_lookup_receives_only_its_declared_model_safe_structural_projection` asserts the catalog heading remains when it is the answer. |
| `test_a_names_only_diagnostic_line_says_what_the_model_was_handed` | U | No equivalent diagnostic-line/logging assertion mapped. Payload privacy is checked by `ScriptedTurnsTests.Every_model_request_excludes_person_rows_while_the_reader_keeps_them`, but that is not proof of the source's named diagnostic fields or log format. |
| `test_the_diagnostic_for_an_aggregate_reports_no_withheld_lane` | U | No equivalent aggregate diagnostic-line assertion mapped. `ModelLaneTests.Aggregate_rows_are_narratable_but_only_the_first_fifty_are_advertised` tests projection, not logging. |
| `test_the_projection_the_model_reads_drops_the_persons_lane_and_the_reply_keeps_it` | E | `ModelLaneTests.Every_model_request_projection_contains_names_and_structure_never_person_values`; `ModelLaneTests.Unknown_fact_audience_hides_rows_even_when_producer_omits_user_only_keys`; `ModelLaneTests.Unknown_block_audience_never_exposes_block_text_or_warnings_to_the_model`. |
| `test_every_field_of_every_data_tool_envelope_is_either_the_persons_or_free_of_row_values` | P | `ModelLaneTests.Every_model_request_projection_contains_names_and_structure_never_person_values` checks brief, model answer and model-fact projection for synthetic private values; `GatewayReplyTests.Full_envelope_and_unknown_fields_survive_without_model_projection_at_transport_boundary` checks full transport retention. This does not enumerate every field from every canonical data capability's real producer. |
| `test_a_model_cannot_choose_a_data_tool_that_writes_or_a_commit_and_the_data_tools_are_named_for_it` | P | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` verifies exact model-tool membership/descriptions/schemas against the inventory; `PackageLoopTests.Unlisted_name_never_executes_a_body` checks the execution boundary. There is no independent data-tool-kind/write classification assertion in these composition tests. |

## `test_orch_numeric_lanes.py`

| Named source guarantee | Status | Actual .NET test method(s) and evidence limit |
|---|---|---|
| `test_the_wages_exist_only_in_the_persons_lane` | E | `ModelLaneTests.Every_model_request_projection_contains_names_and_structure_never_person_values` checks wage absence from all model projections and presence in the reader answer. |
| `test_the_readers_allowed_numerals_never_include_a_figure_from_the_rows` | P | `GuardedReplyTests.Reader_numbers_and_resolved_scope_are_allowed_but_person_rows_are_not_context` proves a private-row wage is refused despite being held in the full facts. It does not expose and inspect Application's internal allowed-context sets directly. |
| `test_a_narration_that_types_a_wage_only_the_rows_hold_is_rejected_and_the_person_still_gets_the_rows` | E | `ModelLaneTests.A_person_only_path_or_copied_row_is_rejected_without_private_audit_material`, wage inline case; `GuardedReplyTests.Reader_numbers_and_resolved_scope_are_allowed_but_person_rows_are_not_context`. |
| `test_a_placeholder_pointing_into_the_persons_lane_is_rejected` | E | `ModelLaneTests.A_person_only_path_or_copied_row_is_rejected_without_private_audit_material`, wage/token/method placeholder inline cases. |
| `test_the_rejection_is_audited_as_a_code_never_naming_the_path` | E | `ModelLaneTests.A_person_only_path_or_copied_row_is_rejected_without_private_audit_material` serializes the guard and rejects private paths, values and identifiers; `ScriptedTurnsTests.Every_model_request_excludes_person_rows_while_the_reader_keeps_them` checks the gateway narration report excludes the private value. |
| `test_a_placeholder_for_a_fact_the_model_was_shown_is_still_rendered` | E | `ModelLaneTests.Every_brief_token_is_copyable_renderable_and_contains_no_value`; `ModelLaneTests.Aggregate_rows_are_narratable_but_only_the_first_fifty_are_advertised`. |
| `test_the_rule_is_about_the_lane_not_about_rows_an_aggregate_is_narratable` | E | `ModelLaneTests.Aggregate_rows_are_narratable_but_only_the_first_fifty_are_advertised`. |
| `test_rows_past_the_models_cut_are_not_a_placeholder_target_either` | E | `ModelLaneTests.Aggregate_rows_are_narratable_but_only_the_first_fifty_are_advertised` checks the advertised boundary, rejected out-of-view placeholder, and full reader-fact row count. |
| `test_a_path_that_does_not_exist_is_still_the_composers_to_reject` | E | `PlaceholderTests.Unsafe_placeholders_are_refused_with_only_a_rule_code`; `GuardedReplyTests.Any_untrusted_figure_or_placeholder_drops_the_entire_narration`. |
| `test_a_reply_with_no_narration_is_unchanged_and_verifies_its_own_blocks` | E | `GuardedReplyTests.Any_untrusted_figure_or_placeholder_drops_the_entire_narration` compares rejection to the no-narration baseline and requires verified blocks; `ModelLaneTests.Unknown_fact_audience_hides_rows_even_when_producer_omits_user_only_keys` composes the person table without narration; `GuardedReplyTests.Unverified_blocks_are_withheld_even_if_narration_is_clean` proves invalid deterministic evidence is not retained. |
| `test_a_figure_a_data_tool_did_not_return_is_rejected` | P | `ExactnessTests.Many_scripted_narrators_cannot_change_exact_synthetic_figures`; `GuardedReplyTests.Any_untrusted_figure_or_placeholder_drops_the_entire_narration`. These prove the common guard, not a parameterized matrix over catalog, distinct-values and query capabilities. |
| `test_a_figure_a_data_tool_did_return_is_still_not_the_models_to_type` | P | `ModelLaneTests.A_person_only_path_or_copied_row_is_rejected_without_private_audit_material` covers a returned query wage; `ExactnessTests.Many_scripted_narrators_cannot_change_exact_synthetic_figures` covers exact copied public figures. The source's three-data-tool matrix is not separately reproduced. |
| `test_an_invented_path_on_a_data_tool_is_rejected` | P | `PlaceholderTests.Unsafe_placeholders_are_refused_with_only_a_rule_code` and `GuardedReplyTests.Any_untrusted_figure_or_placeholder_drops_the_entire_narration` prove common unknown-path rejection. The invented-path case is not separately parameterized over the three data-tool names. |
| `test_the_one_way_a_data_tool_figure_reaches_the_reader_is_a_placeholder_the_platform_renders` | P | `ModelLaneTests.Aggregate_rows_are_narratable_but_only_the_first_fifty_are_advertised` covers a public query aggregate; `ModelLaneTests.Every_brief_token_is_copyable_renderable_and_contains_no_value` proves general token round trips. No three-tool numeric-placeholder matrix is claimed. |
| `test_a_data_tools_facts_are_the_guards_facts` | P | `ExactnessTests.Many_scripted_narrators_cannot_change_exact_synthetic_figures` independently guards each retained body against that run's `FactsOf`; `GuardedReplyTests.Clean_narration_precedes_independently_validated_blocks_and_trusted_footer` does the same for the synthetic credit envelope. Canonical data-tool producer integration is outside these local assertions. |
| `test_the_composer_is_reached_only_through_compose_reply` | P | `GuardedReplyTests.Composition_is_cached_and_invalidated_only_for_new_narration_or_fallback`; `ScriptedTurnsTests.Actual_agent_keeps_canonical_figures_and_audits_the_guard`. These prove the operational composition path and cache; no AST/reflection assertion counts all composer call sites. |
| `test_every_data_tool_is_an_ordinary_read_the_guard_sees` | P | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` checks model exposure; `ScriptedTurnsTests.Every_model_request_excludes_person_rows_while_the_reader_keeps_them` drives a query through the common turn. An explicit catalog-kind/tag assertion for all data tools is not mapped. |

## `test_orch_exactness.py`

| Named source guarantee | Status | Actual .NET test method(s) and evidence limit |
|---|---|---|
| `test_each_narrator_behaviour_gets_exactly_its_outcome` | E | `ExactnessTests.Many_scripted_narrators_cannot_change_exact_synthetic_figures` exercises valid placeholders, copied figures, invented figures and hedging over varying synthetic exact amounts; `GuardedReplyTests.Any_untrusted_figure_or_placeholder_drops_the_entire_narration` includes changed digits, truncated decimals, abbreviations, Unicode numeric evasions, dates and years. |
| `test_whatever_the_model_did_the_finished_reply_passes_the_guard_on_its_own` | E | `ExactnessTests.Many_scripted_narrators_cannot_change_exact_synthetic_figures` independently calls Application's guard on every returned `Body`; `GuardedReplyTests.Full_finished_output_is_checked_independently_of_each_valid_placeholder` proves adjacent individually valid substitutions cannot manufacture another number. References/footer are explicitly outside this body claim. |
| `test_a_figure_the_model_types_is_rejected_even_when_it_equals_a_fact` | E | `ExactnessTests.Many_scripted_narrators_cannot_change_exact_synthetic_figures`; `GuardedReplyTests.Any_untrusted_figure_or_placeholder_drops_the_entire_narration`, exact-money inline case; `ScriptedTurnsTests.Actual_agent_keeps_canonical_figures_and_audits_the_guard`, exact returned headcount inline case. |

Additional exactness evidence, without adding source guarantee names:
`ExactnessTests.Arbitrary_precision_figures_survive_without_decimal_or_double_conversion`;
`ExactnessTests.Rendering_remains_invariant_without_localized_grouping_or_decimal_marks`;
`GuardedReplyTests.Narrator_percent_format_does_not_grant_authority_to_invalid_blocks`;
`GuardedReplyTests.A_hedge_next_to_an_exact_placeholder_is_not_numerically_honest`;
`GuardedReplyTests.Rounding_claims_are_refused_even_without_a_nearby_figure`;
`GuardedReplyTests.Output_policy_is_not_replaced_by_a_numeric_check`;
`GuardedReplyTests.Explicit_link_allow_list_compares_hosts_not_substrings`.

## `test_orch_placeholders.py`

| Named source guarantee | Status | Actual .NET test method(s) and evidence limit |
|---|---|---|
| `test_a_placeholder_names_the_path_and_the_format_hint` | E | `ModelLaneTests.Every_brief_token_is_copyable_renderable_and_contains_no_value` consumes each generated token and its format hint; `PlaceholderTests.Trusted_renderings_are_exact` verifies explicit and inferred formatting; `PlaceholderTests.Known_digit_components_are_validated_before_the_caller_masks_them` verifies digit-bearing paths. |
| `test_entries_keep_their_own_keys_and_gain_a_placeholder` | P | `ModelLaneTests.Every_brief_token_is_copyable_renderable_and_contains_no_value` checks generated entry format/token usability. .NET builds the fixed `path`, `format`, `placeholder` entry shape; it has no generic dictionary-enrichment API and no assertion that arbitrary extra caller keys survive enrichment. |
| `test_every_placeholder_the_model_is_given_resolves_to_the_engines_figure` | E | `ModelLaneTests.Every_brief_token_is_copyable_renderable_and_contains_no_value`; `PlaceholderTests.Trusted_renderings_are_exact`; `PlaceholderTests.Percent_authority_attaches_only_to_an_explicitly_rendered_path`. |
| `test_the_path_without_the_facts_prefix_is_still_refused_not_loosened` | E | `PlaceholderTests.Unsafe_placeholders_are_refused_with_only_a_rule_code`, missing-prefix inline case. |

Additional defensive cases:
`PlaceholderTests.Conflicting_paths_are_not_maskable`,
`PlaceholderTests.A_closed_fence_does_not_capture_later_placeholders`,
`PlaceholderTests.Unbounded_exponents_never_reach_the_shared_formatter`,
and `ModelLaneTests.Duplicate_labels_do_not_silently_replace_a_result`.
These use Application's formatter/index/guard rather than introducing another
calculation implementation.

## `test_orch_knowledge.py`

| Named source guarantee | Status | Actual .NET test method(s) and evidence limit |
|---|---|---|
| `test_with_the_tier_off_the_model_is_told_no_reference_text_and_the_reply_carries_none` | E | `ReferenceTests.Disabled_knowledge_calls_no_source_and_adds_no_text` checks no source invocation, no model context and no reader reference text. |
| `test_the_planner_and_the_agent_builder_default_to_no_knowledge` | P | `ReferenceTests.Disabled_knowledge_calls_no_source_and_adds_no_text` proves the disabled composition/provider boundary. No constructor-signature or actual planner/agent-builder default assertion is mapped here. |
| `test_the_default_wiring_builds_no_knowledge_source` | P | `ReferenceTests.Disabled_knowledge_calls_no_source_and_adds_no_text` proves no provider call at the disabled composition boundary; `KnowledgeWiringTests.Production_wiring_keeps_opt_in_reference_text_separate_from_facts_and_degraded_replies` proves explicitly disabled production runtime wiring adds no model/reader references. Neither independently counts source constructions or asserts the unset-setting constructor default. |
| `test_switching_it_on_in_the_environment_builds_the_fake_and_a_bad_setting_stops_the_start` | E | `KnowledgeWiringTests.Production_wiring_keeps_opt_in_reference_text_separate_from_facts_and_degraded_replies` constructs the production runtime from `KNOWLEDGE_ENABLED`, `KNOWLEDGE_PROVIDER=fake`, `KNOWLEDGE_TOP=1` configuration, observes reference text in captured model requests and the selected synthetic citation only beside surviving narration. `KnowledgeWiringTests.Invalid_reference_configuration_fails_at_startup_without_building_a_source` rejects invalid provider/enabled/top combinations while constructing settings, before runtime construction; enabled `foundry-iq` is explicitly unsupported. This is a labelled synthetic provider through the real local wiring, not live retrieval. |
| `test_the_model_is_told_the_passages_as_fenced_reference_text_without_their_citations` | E | `ReferenceTests.References_are_bounded_fenced_cited_and_never_part_of_engine_facts`; `ReferenceTests.A_passage_cannot_escape_its_untrusted_fence` inspect fences and escaping. `KnowledgeWiringTests.Production_wiring_keeps_opt_in_reference_text_separate_from_facts_and_degraded_replies` additionally checks enabled production-wiring model requests contain reference text but no citation identifier. The model remains injected/local. |
| `test_the_reader_gets_the_quoted_passages_with_their_citations_beside_a_surviving_narration` | E | `ReferenceTests.References_are_bounded_fenced_cited_and_never_part_of_engine_facts` asserts citation, retrieval date, surviving narration and placement before the provenance footer. |
| `test_only_as_many_passages_as_the_setting_allows_are_retrieved_and_shown` | E | `ReferenceTests.References_are_bounded_fenced_cited_and_never_part_of_engine_facts` passes `top: 2`, checks the source argument and excludes a third returned passage. `KnowledgeWiringTests.Production_wiring_keeps_opt_in_reference_text_separate_from_facts_and_degraded_replies` adds `KNOWLEDGE_TOP=1` production configuration evidence: the credit citation survives the credit question and the eligibility citation is absent. This is synthetic corpus selection, not live search ranking certification. |
| `test_a_narration_that_repeats_a_figure_read_only_in_a_passage_is_dropped_and_no_reference_block_is_shown` | E | `ReferenceTests.A_reference_never_authorizes_a_number_or_placeholder`, typed-reference-rate inline case. |
| `test_the_turns_facts_are_the_tools_facts_and_hold_nothing_from_a_passage` | E | `ReferenceTests.References_are_bounded_fenced_cited_and_never_part_of_engine_facts` checks `FactsOf`, brief paths and an independent guard over the engine body. |
| `test_a_placeholder_into_reference_text_drops_the_narration` | E | `ReferenceTests.A_reference_never_authorizes_a_number_or_placeholder`, reference-path inline case. |
| `test_a_knowledge_source_that_fails_leaves_the_turn_exactly_as_it_was` | P | `ReferenceTests.Retrieval_errors_and_invalid_passages_add_nothing` checks empty context after failure; `ReferenceTests.Disabled_knowledge_calls_no_source_and_adds_no_text` checks the empty-reference composition. There is no failing-source full-turn equality assertion through the SDK pipeline. |
| `test_a_turn_with_no_matching_passage_shows_no_reference_block` | P | `ReferenceTests.Retrieval_errors_and_invalid_passages_add_nothing` checks an empty usable passage set and `ReferenceTests.Disabled_knowledge_calls_no_source_and_adds_no_text` checks no rendered references. No dedicated successful-empty-search full-turn test is mapped. |
| `test_falling_back_to_the_platforms_own_answer_forgets_the_reference` | E | `ReferenceTests.Fallback_discards_references_even_if_a_subsequent_plain_narration_is_supplied`. |
| `test_the_provider_adds_instructions_only_and_keeps_what_it_found` | P | `ReferenceTests.References_are_bounded_fenced_cited_and_never_part_of_engine_facts` proves separate reference context and facts, with passages retained for reader rendering. The provider returns a context string; no Agent Framework `SessionContext` hook or assertion about added tools/messages/middleware is claimed. |
| `test_the_provider_with_nothing_found_or_a_failing_source_adds_nothing` | P | `ReferenceTests.Retrieval_errors_and_invalid_passages_add_nothing` checks failed retrieval and all-invalid returned passages. A dedicated successful-empty source and actual framework context-provider hook are not mapped. |

Additional provider-boundary evidence:
`ReferenceTests.Provider_cancellation_is_propagated_without_turning_into_empty_evidence`.
Production opt-in configuration and captured local model-request injection now
have the `KnowledgeWiringTests` evidence above. There is no live reference
retrieval, Foundry IQ/Search deployment or separate Agent Framework
`SessionContext` provider-hook claim. `foundry-iq` is rejected, not silently
represented by the labelled synthetic provider.

## `test_orch_golden.py`

| Named source guarantee | Status | Actual .NET test method(s) and evidence limit |
|---|---|---|
| `test_there_are_enough_golden_prompts_and_every_read_tool_is_asked_for` | U | No assertion loads the Python `golden` conversation corpus, checks its minimum case count or proves that every read tool is exercised by it. `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` proves definitions, not execution coverage. |
| `test_golden` | P | `RecordedTurnsTests.All_thirty_nine_source_records_are_compared_by_id`; `ScriptedTurnsTests.Actual_agent_keeps_canonical_figures_and_audits_the_guard`; `ScriptedTurnsTests.Model_failure_before_tools_falls_back_but_after_tools_never_replays_them`; `ScriptedTurnsTests.Every_model_request_excludes_person_rows_while_the_reader_keeps_them`; `CheckpointTurnsTests.Actual_agent_prepare_pauses_then_confirm_resumes_once_with_current_attribution`. These are deterministic-record and scripted scenario evidence, not execution of every Python golden conversation. |

The 39-record test reads `contract\recordings\orchestrator.json`. It compares
text, mode, gateway calls/arguments and the model-called flag, preserves fresh
keyword rigs, and replays shared conversations with cumulative call-tail
comparison. Those 39 records are **not** the Python model-scripted golden corpus,
and keyword/conversation records do not alone prove a successful prepare/commit
workflow.

## `test_parity_conformance.py`

These are chiefly cross-surface catalogue assertions. The O5 composer does not
implement or certify the API, gateway REST, MCP or portal adapters.

| Named source guarantee | Status | Actual .NET test method(s) and evidence limit |
|---|---|---|
| `test_the_catalogs_own_filters_are_exactly_the_declared_ones` | P | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` proves the model projection's exact expected membership. It does not independently prove every canonical catalog filter/tag/kind relation. |
| `test_the_gateways_rest_list_and_mcp_list_are_the_catalogs_offered_tools_in_its_order` | X | No cross-surface list/order test mapped. `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` checks the model projection only. |
| `test_the_api_list_is_the_catalog_less_plumbing` | X | No API capability-list/plumbing comparison mapped in this handoff. |
| `test_the_maf_tools_are_the_tools_a_model_may_name_sorted_by_name_and_no_commit_is_among_them` | P | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` checks exact model membership, including the inventory's exclusions. Its per-name lookup does not assert definition ordering or independently derive exclusions from commit kinds. |
| `test_every_surface_says_what_the_catalog_says_and_the_differences_are_the_declared_ones` | P | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` proves descriptions and schemas for the model-facing projection. API/REST/MCP/portal comparisons are not established. |
| `test_the_one_declared_wording_difference_is_the_write_sentence` | X | No per-kind cross-surface description/write-sentence comparison mapped. |
| `test_a_model_is_shown_the_catalogs_schema_less_exactly_what_the_reader_owns` | P | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` compares the complete offered model schemas to the pinned inventory. It does not independently recompute them from canonical `reader_owned` declarations. |
| `test_behaviour_hints_follow_the_kind_and_nothing_else` | X | No MCP behavior-hint/kind matrix test mapped. |
| `test_the_portals_intents_run_catalog_tools_and_the_parity_cases_name_real_ones` | X | No portal intent-to-capability/parity-case matrix assertion mapped. |

## `test_parity_figures.py`

The source suite uses the real synthetic-payroll engine and multiple adapters.
The tests below establish the orchestrator's retention and guard boundaries
using synthetic envelopes/fake gateway responses. They do not establish that
all other doors return the same engine result.

| Named source guarantee | Status | Actual .NET test method(s) and evidence limit |
|---|---|---|
| `test_the_matrix_covers_what_the_brief_asks_and_every_gap_says_why` | X | No equivalent all-surface parity-case matrix/minimum coverage assertion mapped. |
| `test_every_door_returns_the_same_envelope` | X | No REST API/gateway/MCP/framework/portal envelope equality matrix mapped. `GatewayReplyTests.Full_envelope_and_unknown_fields_survive_without_model_projection_at_transport_boundary` proves transport retention only. |
| `test_a_capped_result_says_so_and_an_employee_result_travels_in_the_persons_lane` | P | `ModelLaneTests.Aggregate_rows_are_narratable_but_only_the_first_fifty_are_advertised` proves the model-view cap without truncating full reader facts; `ModelLaneTests.Every_model_request_projection_contains_names_and_structure_never_person_values` proves the employee lane. This is not the source capability's query `truncated`/`row_limit` metadata or cross-door equality assertion. |
| `test_the_text_cowork_reads_is_the_platforms_blocks_and_no_other_number` | X | No MCP/Cowork text rendering test mapped. `ExactnessTests.Many_scripted_narrators_cannot_change_exact_synthetic_figures` guards orchestrator bodies, not MCP text. |
| `test_a_teams_turn_shows_the_platforms_blocks_and_the_engines_figures_only` | P | `ScriptedTurnsTests.Actual_agent_keeps_canonical_figures_and_audits_the_guard`; `ExactnessTests.Many_scripted_narrators_cannot_change_exact_synthetic_figures`; `GuardedReplyTests.Clean_narration_precedes_independently_validated_blocks_and_trusted_footer`. These prove pipeline retention and independent synthetic-envelope guarding, not parity against a real engine-backed REST response. |
| `test_an_unnamed_method_runs_both_certified_methods_and_each_is_the_rest_answer` | P | `ScriptedTurnsTests.Split_calls_share_one_reader_resolution_overwrite_model_scope_and_deduplicate` asserts both method calls and reader-owned arguments; `ModelLaneTests.Multiple_methods_keep_independent_paths_and_headings` asserts separate paths/headings. Neither compares both envelopes to real REST engine answers. |
| `test_a_model_is_shown_the_names_of_the_persons_rows_and_never_the_rows` | E | `ScriptedTurnsTests.Every_model_request_excludes_person_rows_while_the_reader_keeps_them`; `ModelLaneTests.Every_model_request_projection_contains_names_and_structure_never_person_values`. Evidence uses a synthetic person envelope, not private payroll. |
| `test_the_portal_shows_the_same_blocks_and_facts_and_tells_its_narrators_only_those_figures` | X | No portal evidence-event/narrator-brief parity assertion mapped. This composer is not the portal's weaker page-summary or unchecked streaming-chat guard. |
| `test_a_prepared_write_changes_nothing_on_any_door` | P | `CheckpointTurnsTests.Actual_agent_prepare_pauses_then_confirm_resumes_once_with_current_attribution` asserts zero fake-gateway mutations after prepare and one only after confirmation, plus token exclusion. It does not prepare through every source surface or inspect a real repository's claim history. |
| `test_a_door_that_changes_one_figure_fails_the_check` | P | `GuardedReplyTests.Unverified_blocks_are_withheld_even_if_narration_is_clean`; `GuardedReplyTests.Full_finished_output_is_checked_independently_of_each_valid_placeholder` demonstrate genuine failing numeric checks. No injected-liar matrix across API, MCP and portal adapters is claimed. |
| `test_a_portal_pipeline_that_adds_up_figures_of_its_own_fails_the_check` | X | No portal-pipeline mutation/negative-control test mapped. The analogous local output negative control is `GuardedReplyTests.Full_finished_output_is_checked_independently_of_each_valid_placeholder`, which must not be reported as portal evidence. |

## Handoff limitations and ownership

- Person verification, conversation attribution and gateway audit submission are
  outside the pure composer. The composed guard exposes only safe rule codes.
  `GatewayTests.Audit_uses_the_same_identity_context_and_returns_gateway_errors_without_retry`
  and `ScriptedTurnsTests.Actual_agent_keeps_canonical_figures_and_audits_the_guard`
  provide adjacent injected-boundary evidence, not a live durable audit proof.
- Unknown audiences, explicit person-only paths, private token copies and model
  row limits have local tests. This is not a claim that every possible producer
  payload has been classified correctly, or that unstructured prose has semantic
  fact-checking.
- Knowledge has bounded synthetic provider tests plus production opt-in
  configuration/local model-request evidence. A separate framework
  knowledge-context provider hook and a live retrieval deployment remain
  unverified; unsupported live `foundry-iq` configuration is refused.
- The source diagnostic-line assertions, complete Python golden corpus, and
  cross-surface parity matrices have deliberately not been relabelled as
  covered by smaller composer tests.
- No live Fabric, Foundry, Entra, customer data, private payroll or remote
  deployment was accessed to produce this handoff. Existing certified engine
  gates are not re-certified by composition tests.
