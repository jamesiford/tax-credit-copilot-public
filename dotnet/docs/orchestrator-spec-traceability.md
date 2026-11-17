# Orchestrator: complete named source-guarantee index

Source: `contract\docs\ORCHESTRATOR-SPEC.md`, **32 groups / 313 named
functions**. Each source file/function pair appears once in a table below.
Theory cases, iterations, package-backed calls and combined passing test counts
are not interchangeable with source-guarantee equivalence.

Index validation: **313 unique pairs, 32 groups; E 156 / P 103 / U 15 / X 39**.
There are no missing, extra or duplicated pairs. The 72 C row/status links,
17 W row links and the direct test references in this index plus C
were checked against their documents and existing test files. This is index
validation, not a claim that 313 equivalent .NET tests passed.

## Status and evidence rules

| Status | Meaning |
|---|---|
| E | A real named .NET test directly exercises the relevant guarantee, using the explicitly stated local/injected boundary. Not a live deployment claim. |
| P | Partial or narrower evidence. The row identifies what is not independently asserted. |
| U | No equivalent named assertion mapped. A nearby test may be identified, but does not close the gap. |
| X | Source-specific deployment, copy-tool, or other-surface evidence outside the .NET orchestrator boundary; the reason is explicit. |

Test identifiers are `Class.Method` under
`dotnet\tests\TaxCredit.Orchestrator.Tests\`. Class files live in:

- `Boundary\`: `IdentityTests`, `DebugCommandTests`, `GatewayTests`,
  `GatewayReplyTests`, `NetcheckTests`, `ModelDiagnosticTests`.
- `Composition\`: `ModelLaneTests`, `PlaceholderTests`, `GuardedReplyTests`,
  `ExactnessTests`, `ReferenceTests`.
- `Framework\`: `CatalogProjectionTests`, `PackageLoopTests`,
  `FoundryWireTests`, `ModelRoutingTests`, `RuntimeWireTests`,
  `ResponsesWireTests`, `ArchitectureTests`, `KnowledgeWiringTests`.
- `Planning\`: `ReaderWordsTests`, `JsonPlanningTests`, `ReviewPackTests`.
- `Turns\`: `RecordedTurnsTests`, `ScriptedTurnsTests`,
  `CheckpointTurnsTests`, `ConversationStoreTests`, `RunnerBoundaryTests`.
- `Workflow\`: `WriteWorkflowTests`, `WritePostCommitTests`.

Two explicit row-reference abbreviations avoid duplicating previously inspected
evidence:

- **C** = `dotnet\docs\orchestrator-composition-traceability.md`, the
  **same source-file heading and exact named function row**. That row supplies
  real `Class.Method` names and its full evidence limit. The status here is not
  stronger than that row. Its 72 entries are enumerated individually below.
- **W** = `dotnet\docs\orchestrator-workflow-traceability.md`, table
  **Every named source write-flow guarantee**, exact named function row.
  That row supplies methods, SDK boundary and limitations; unqualified methods
  there are `WriteWorkflowTests` methods. All 17 entries are enumerated below.

The boundary contract was also read:
`dotnet\src\TaxCredit.Orchestrator\Boundary\README.md`. Documentation and
implementation statements alone are not substituted for missing tests.

## Non-equivalence boundaries

- The 39 deterministic records are checked by
  `RecordedTurnsTests.All_thirty_nine_source_records_are_compared_by_id`.
  They are not the separate Python model-scripted golden/data-golden corpus.
- Package-backed tests use installed .NET SDKs and local transports. They do
  not prove live Foundry, Fabric, Entra, durable gateway audit, production
  deployment or private reference-payroll equivalence.
- API, gateway REST, MCP and portal cross-surface matrices are not certified by
  an orchestrator fake gateway. Existing certified engine gates are not
  re-certified by this index.
- `ComposedReply.Body` is independently guarded against engine facts.
  References are separately labelled quotes, never numeric authority; the
  trusted identifier footer is appended without model rewriting. No claim is
  made that reference text and identifier footers are ordinary engine figures.
- Python copying/folder-layout and W4 manifest assertions are replaced only
  where an actual .NET reference/isolation/runtime test is named. Otherwise
  they remain explicitly X, not implicit passes.
- This is documentation indexing, not an implementation review or a new test
  run. The individual handoff documents retain their own execution evidence.

The principal unverified functional areas are the full model-scripted
golden/data-golden corpus, some planner instruction assertions, names-only
projection diagnostics, complete environment/documentation inventories and
whole-source rule/caller ownership assertions. Production opt-in knowledge
wiring, custom-host preservation, tool spans, schema refusal, client switching,
review-pack interruption, SDK iteration exhaustion and model-attempt timeout
now have the named local evidence below. No live retrieval/deployment or
runtime debug-probe evidence is claimed; enabled `foundry-iq` is refused.
The rows distinguish U gaps from narrower P evidence and X exclusions.

## Named mapping

### test_orch_agent_definition.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_the_reader_understands_the_shapes_the_file_uses` | X | Python agent-deployment file parser; no .NET W4 manifest/parser equivalent is claimed. |
| `test_the_project_and_the_agent_are_the_documented_service_hosts` | P | `ResponsesWireTests.Installed_host_extracts_input_and_frames_one_complete_text_response_and_readiness` proves the installed Responses service host, not deployment project/agent declarations. |
| `test_the_extension_floor_is_declared_at_the_documented_minimum` | X | W4 deployment extension metadata; runtime package compatibility does not assert an extension floor. |
| `test_the_code_deployment_is_source_not_an_image_and_points_at_a_real_entry_point` | X | W4 deployment packaging/image/source metadata is not certified by a local runtime test. |
| `test_the_container_resources_are_inside_the_documented_range` | X | W4 resource sizing; no deployed container resource declaration is tested. |
| `test_the_endpoint_authorisation_includes_the_scheme_activity_requires` | X | Python Activity endpoint metadata is not the .NET Responses transport; no W4 endpoint authorization declaration is certified. |
| `test_there_is_no_identity_block_and_no_legacy_manifest` | X | Deployment-manifest shape assertion; identity resolver tests are not manifest validation. |
| `test_python_startup_is_pinned_as_the_runtime_documentation_requires` | X | Python/W4 startup declaration does not apply to the .NET executable. `ArchitectureTests.The_root_pins_net10_and_all_orchestrator_modules_stay_within_the_documented_size_limit` proves the .NET target pin, not a deployed startup/runtime declaration. |
| `test_no_reserved_platform_variable_and_no_secret_is_declared` | X | No W4 deployment-variable inventory test mapped. Sanitized diagnostic metadata is a different boundary. |
| `test_the_one_known_exception_is_still_declared_so_the_list_cannot_go_stale` | X | Python manifest-specific exception inventory; no .NET deployment manifest exception list is certified. |
| `test_every_value_is_an_azd_reference_or_a_plain_literal` | X | W4 azd substitution grammar, not runtime configuration validation. |
| `test_the_file_names_no_endpoint_tenant_or_secret_outside_its_comments` | X | W4 declaration-content scan; local synthetic endpoint tests do not establish deployment-file content. |
| `test_every_declared_variable_is_documented_and_read_somewhere` | X | Complete W4 environment declaration/documentation/read inventory is not mapped. |
| `test_the_variable_rule_flags_a_reserved_or_secret_name` | X | Negative control for the Python deployment scanner; no equivalent .NET deployment scanner is claimed. |

### test_orch_catalog_tools.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_there_is_one_tool_per_tool_a_model_may_name_in_the_catalogs_own_words` | E | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` compares exact membership, descriptions and schemas. |
| `test_no_generated_tool_is_a_commit_a_resolver_or_plumbing` | E | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory`; `PackageLoopTests.Scripted_call_crosses_real_agent_function_middleware_and_generated_body` additionally rejects generated commit definitions. |
| `test_the_tools_are_built_once_and_carry_no_turn` | P | `CatalogProjectionTests.Returned_specification_cannot_mutate_the_shared_definitions`; `ArchitectureTests.Singleton_tool_definitions_hold_no_verified_reader_selection_or_workflow_state`. Definition exposure and declared instance-field types are inspected. No independent construction-count or transitive closure-state assertion. |
| `test_the_body_forwards_as_the_person_the_request_names_and_the_same_tools_serve_two_people` | P | `PackageLoopTests.Scripted_call_crosses_real_agent_function_middleware_and_generated_body`; `GatewayTests.Shared_infrastructure_has_no_cross_person_headers_and_acquires_each_token_per_call`. Real generated forwarding and per-call identity isolation are separately tested, not a two-person invocation through the same generated definition in one assertion. |
| `test_a_body_is_logic_free_and_returns_the_gateways_reply_untouched` | P | `PackageLoopTests.Scripted_call_crosses_real_agent_function_middleware_and_generated_body`; `GatewayReplyTests.Full_envelope_and_unknown_fields_survive_without_model_projection_at_transport_boundary`. No AST assertion proves every generated body is logic-free or compares every returned field through that body. |

### test_orch_data_goldens.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_there_are_at_least_twenty_five_nuanced_data_questions` | U | No equivalent minimum-size data-golden corpus assertion mapped. |
| `test_every_kind_the_work_package_names_is_covered` | U | No complete data-golden question-kind inventory assertion mapped. |
| `test_every_turn_asserts_its_tool_sequence_and_a_kind` | P | `RecordedTurnsTests.All_thirty_nine_source_records_are_compared_by_id` compares captured calls/mode; `JsonPlanningTests.Lookup_only_plan_gets_one_replan_then_a_shared_placeholder_brief` checks a data sequence. Neither enumerates every Python data-golden turn. |
| `test_the_three_data_tools_are_each_asked_for_and_each_lane_is_exercised` | P | `JsonPlanningTests.Lookup_only_plan_gets_one_replan_then_a_shared_placeholder_brief`; `ScriptedTurnsTests.Every_model_request_excludes_person_rows_while_the_reader_keeps_them`. Catalog/query and the person lane are exercised; the complete three-tool golden matrix is not. |
| `test_a_case_that_says_a_model_never_sees_something_it_does_see_fails` | P | `ScriptedTurnsTests.Every_model_request_excludes_person_rows_while_the_reader_keeps_them` inspects every request for private content. No deliberately falsified golden expectation is injected as a negative control. |
| `test_a_case_that_names_the_wrong_tool_sequence_fails` | P | `RecordedTurnsTests.All_thirty_nine_source_records_are_compared_by_id` asserts exact sequences, but no intentionally wrong data-golden sequence is injected to test the harness. |

### test_orch_data_lanes.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_the_person_gets_the_rows_and_no_model_is_sent_one` | E | C, same file/function row. |
| `test_what_a_model_is_told_about_the_rows_is_the_count_and_the_column_names` | P | C, same file/function row; complete column-path set is not independently asserted. |
| `test_an_aggregate_is_shown_to_the_model_by_name_so_it_can_be_narrated` | E | C, same file/function row. |
| `test_the_catalog_and_the_distinct_values_are_the_declared_exception_and_nothing_else_is` | P | C, same file/function row; no separate distinct-values/classification matrix. |
| `test_the_catalog_blocks_are_left_out_of_a_reply_that_something_else_answered` | E | C, same file/function row. |
| `test_a_catalog_question_is_answered_with_the_catalog` | E | C, same file/function row. |
| `test_a_names_only_diagnostic_line_says_what_the_model_was_handed` | U | C, same file/function row; no named diagnostic-line assertion. |
| `test_the_diagnostic_for_an_aggregate_reports_no_withheld_lane` | U | C, same file/function row; no aggregate diagnostic-line assertion. |
| `test_the_projection_the_model_reads_drops_the_persons_lane_and_the_reply_keeps_it` | E | C, same file/function row. |
| `test_every_field_of_every_data_tool_envelope_is_either_the_persons_or_free_of_row_values` | P | C, same file/function row; not a matrix over all canonical producer fields. |
| `test_a_model_cannot_choose_a_data_tool_that_writes_or_a_commit_and_the_data_tools_are_named_for_it` | P | C, same file/function row; inventory exposure/whitelist evidence, not independent data-tool-kind derivation. |

### test_orch_data_planning.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_the_planner_instructions_carry_the_decision_rule` | U | No named planner-instruction content assertion mapped; successful scripted plans do not prove instruction text. |
| `test_the_planner_orders_the_tools_and_names_the_authority` | P | `JsonPlanningTests.Lookup_only_plan_gets_one_replan_then_a_shared_placeholder_brief` proves lookup/query order; no complete planner instruction/authority assertion. |
| `test_the_data_tool_descriptions_tell_the_model_when_and_how` | P | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` compares descriptions exactly to inventory, not an independent semantic rubric over those descriptions. |
| `test_the_json_catalogue_and_the_tool_list_carry_the_same_descriptions` | P | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` proves framework definitions; no direct JSON-planner-versus-framework-description equality assertion mapped. |
| `test_json_mode_reads_the_catalog_then_plans_the_query_it_was_shown` | E | `JsonPlanningTests.Lookup_only_plan_gets_one_replan_then_a_shared_placeholder_brief`. |
| `test_json_mode_asks_again_only_once_and_only_after_lookups` | E | `JsonPlanningTests.Lookup_only_plan_gets_one_replan_then_a_shared_placeholder_brief`; `JsonPlanningTests.A_second_lookup_only_plan_cannot_create_an_unbounded_replan_loop`; `JsonPlanningTests.A_query_or_nonlookup_plan_is_not_replanned`. |
| `test_json_mode_does_not_ask_again_when_the_plan_already_holds_a_query` | E | `JsonPlanningTests.A_query_or_nonlookup_plan_is_not_replanned`, catalog-plus-query case. |
| `test_json_mode_with_no_lookup_asks_nothing_more` | E | `JsonPlanningTests.A_query_or_nonlookup_plan_is_not_replanned`, ordinary, empty and malformed-plan cases. |
| `test_the_planner_says_what_a_location_question_is_and_how_to_name_an_hours_measure` | U | No named location/hour-measure planner-instruction assertion mapped. |

### test_orch_debug_posture.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_the_orchestrator_default_is_off_and_says_nothing` | E | `DebugCommandTests.Debug_off_commands_are_inert_with_no_identity_or_diagnostic_calls`; `IdentityTests.Environment_defaults_match_the_current_platform_source_policy`. |
| `test_the_orchestrator_warns_at_startup_when_the_switch_is_on` | E | `DebugCommandTests.Enabled_startup_warns_and_whoami_resolves_header_case_without_exposing_credentials`. |
| `test_every_default_for_the_switch_is_false` | P | `IdentityTests.Environment_defaults_match_the_current_platform_source_policy`; `RuntimeWireTests.Anonymous_and_debug_off_wire_requests_never_touch_gateway_or_model`. These test runtime defaults, not every deployment/template declaration. |
| `test_the_cleanup_page_exists_and_names_the_switch_and_its_command` | P | `DebugCommandTests.Enabled_startup_warns_and_whoami_resolves_header_case_without_exposing_credentials` checks a cleanup-document reference in the warning; it does not read the page and assert its command content. |

### test_orch_degraded_planner.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_both_degraded_planners_satisfy_the_one_interface` | P | `JsonPlanningTests.Lookup_only_plan_gets_one_replan_then_a_shared_placeholder_brief`; `RecordedTurnsTests.All_thirty_nine_source_records_are_compared_by_id` exercise the two paths. No independent shared-interface type assertion mapped. |
| `test_the_agent_plans_when_a_tool_calling_model_is_reachable_and_no_degraded_planner_is_asked` | E | `ScriptedTurnsTests.Actual_agent_keeps_canonical_figures_and_audits_the_guard` asserts tools mode and actual calls; `ModelRoutingTests.Real_framework_loop_runs_inside_the_existing_W1_guard_budget_and_resilience_adapters`. |
| `test_a_model_without_tool_calling_is_the_json_planner_and_no_model_is_the_keyword_planner` | E | `JsonPlanningTests.Lookup_only_plan_gets_one_replan_then_a_shared_placeholder_brief`; `RecordedTurnsTests.All_thirty_nine_source_records_are_compared_by_id` checks keyword mode/model-called flags. |
| `test_a_message_the_injection_screen_flags_reaches_no_model_and_is_the_keyword_planners` | E | `ScriptedTurnsTests.Anonymous_and_injection_messages_do_not_reach_a_model`. |
| `test_a_model_layer_that_fails_before_any_tool_ran_falls_to_the_keywords_and_says_so` | E | `ScriptedTurnsTests.Model_failure_before_tools_falls_back_but_after_tools_never_replays_them`. |
| `test_a_model_layer_that_fails_after_tools_ran_keeps_what_they_returned` | E | `ScriptedTurnsTests.Model_failure_before_tools_falls_back_but_after_tools_never_replays_them`; `CheckpointTurnsTests.Model_failure_after_prepare_keeps_the_preview_without_preparing_again`. |
| `test_the_real_degraded_planners_are_the_default_and_answer_through_the_runners_rules` | P | `RecordedTurnsTests.All_thirty_nine_source_records_are_compared_by_id`; `JsonPlanningTests.An_invented_or_commit_tool_is_not_dispatched_in_json_mode`. Runtime behavior is checked, not exhaustive registration/default-constructor structure. |
| `test_a_json_plan_names_tools_in_order_up_to_the_limit_and_filters_nothing` | E | `JsonPlanningTests.Malformed_plan_elements_do_not_hide_unknown_names_from_the_shared_refusal`; `JsonPlanningTests.An_invented_or_commit_tool_is_not_dispatched_in_json_mode`. |
| `test_a_reply_is_composed_once_from_the_turns_results_and_again_only_after_a_new_narration` | E | `GuardedReplyTests.Composition_is_cached_and_invalidated_only_for_new_narration_or_fallback`. |
| `test_a_failed_model_layer_forgets_its_narration_and_marks_the_answer_as_the_platforms_own` | E | `GuardedReplyTests.Composition_is_cached_and_invalidated_only_for_new_narration_or_fallback`; `ScriptedTurnsTests.Model_failure_before_tools_falls_back_but_after_tools_never_replays_them`. |
| `test_compose_reply_is_called_by_the_composition_point_and_the_commit_path_and_nothing_else` | P | `ScriptedTurnsTests.Actual_agent_keeps_canonical_figures_and_audits_the_guard`; `CheckpointTurnsTests.Actual_agent_prepare_pauses_then_confirm_resumes_once_with_current_attribution`. Runtime paths are exercised, not an exhaustive call-site scan. |
| `test_the_brief_every_path_hands_a_model_names_facts_with_placeholders_and_no_value` | E | `ModelLaneTests.Every_brief_token_is_copyable_renderable_and_contains_no_value`; `JsonPlanningTests.Lookup_only_plan_gets_one_replan_then_a_shared_placeholder_brief`; `FoundryWireTests.Real_framework_loop_sends_only_projected_tools_and_fact_paths_on_the_official_wire`. Explicit lookup structural values remain the declared exception. |
| `test_the_brief_is_built_in_one_function_not_in_each_planner` | P | `ModelLaneTests.Every_model_request_projection_contains_names_and_structure_never_person_values`; `JsonPlanningTests.Lookup_only_plan_gets_one_replan_then_a_shared_placeholder_brief`. Shared payload behavior is tested; no complete call-site/AST uniqueness assertion. |
| `test_every_model_call_is_noted_the_same_way_whichever_planner_made_it` | P | `RecordedTurnsTests.All_thirty_nine_source_records_are_compared_by_id` checks model-called flags for recordings; `ScriptedTurnsTests.Actual_agent_keeps_canonical_figures_and_audits_the_guard` checks audit. No cross-planner trace-field equality matrix. |
| `test_the_facts_a_reply_is_checked_against_are_the_runs_own` | E | `ExactnessTests.Many_scripted_narrators_cannot_change_exact_synthetic_figures`; `GuardedReplyTests.Clean_narration_precedes_independently_validated_blocks_and_trusted_footer`. |

### test_orch_e2e.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_a_read_is_judged_by_the_real_guard_and_leaves_a_narration_row_under_the_person` | E | `RuntimeWireTests.Real_responses_wire_crosses_identity_framework_rest_gateway_guard_and_audit`; `GatewayTests.Audit_uses_the_same_identity_context_and_returns_gateway_errors_without_retry`. Real local wire/guard and injected audit boundary, not durable production persistence. |
| `test_prepare_then_confirm_through_the_real_stack_writes_once_and_audits_both_steps` | P | `CheckpointTurnsTests.Actual_agent_prepare_pauses_then_confirm_resumes_once_with_current_attribution` proves real framework pause/resume, identity and one fake-gateway mutation. It does not independently assert both durable source-system audit rows. |
| `test_somebody_elses_confirm_reaches_nothing_and_the_owners_still_works` | E | `CheckpointTurnsTests.Wrong_person_cannot_consume_the_preview_even_with_the_same_conversation`. |
| `test_a_person_who_may_not_write_is_refused_by_the_real_gateway_at_the_preview` | P | `CheckpointTurnsTests.Reader_authorization_is_enforced_by_the_gateway_before_a_checkpoint_can_commit`; `WriteWorkflowTests.ReaderAuthorizationIsEnforcedAtPreviewAndCannotPause`. Faithful injected gateway authorization, not a live/real API authorization stack. |

### test_orch_exactness.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_each_narrator_behaviour_gets_exactly_its_outcome` | E | C, same file/function row. |
| `test_whatever_the_model_did_the_finished_reply_passes_the_guard_on_its_own` | E | C, same file/function row; checked body excludes references/footer. |
| `test_a_figure_the_model_types_is_rejected_even_when_it_equals_a_fact` | E | C, same file/function row. |

### test_orch_folder_map.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_every_module_under_app_is_in_the_folder_map` | X | Python vendoring folder inventory is not a .NET runtime artifact; no folder-map equivalence is asserted. |
| `test_the_readme_explains_the_two_main_files` | U | No named documentation-content assertion for the .NET entry/composition split mapped. |
| `test_the_root_main_is_the_entry_point_the_deployments_name` | X | W4 deployment-to-entrypoint binding is not proved by local Responses startup. |

### test_orch_foundry_client.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_a_foundry_only_chain_is_served_by_the_frameworks_own_client` | E | `FoundryWireTests.Real_framework_loop_sends_only_projected_tools_and_fact_paths_on_the_official_wire`; `ModelRoutingTests.Real_framework_loop_runs_inside_the_existing_W1_guard_budget_and_resilience_adapters`. |
| `test_a_chain_that_names_the_gateway_keeps_the_provider_chain` | E | `ModelRoutingTests.W1_chains_preserve_fallback_and_account_for_each_actual_attempt`; `ModelRoutingTests.Narrator_override_decides_the_orchestrator_chain_without_discarding_other_roles`. |
| `test_the_narrator_role_chain_decides_not_the_default_chain` | E | `ModelRoutingTests.Narrator_override_decides_the_orchestrator_chain_without_discarding_other_roles`. |
| `test_a_foundry_chain_without_an_endpoint_fails_at_start_not_at_the_first_question` | E | `RuntimeWireTests.Selected_but_unconfigured_foundry_is_not_silently_replaced`; `ModelRoutingTests.Missing_chain_provider_is_a_configuration_error_not_a_default_client`. |
| `test_both_paths_satisfy_one_interface_the_planner_reads` | P | `ModelRoutingTests.Real_framework_loop_runs_inside_the_existing_W1_guard_budget_and_resilience_adapters`; `FoundryWireTests.Real_framework_loop_sends_only_projected_tools_and_fact_paths_on_the_official_wire` exercise the same turn path. No separate interface-shape assertion is mapped. |
| `test_an_unknown_access_object_is_refused_rather_than_given_a_default_client` | E | `ModelRoutingTests.Missing_chain_provider_is_a_configuration_error_not_a_default_client`; `RuntimeWireTests.Selected_but_unconfigured_foundry_is_not_silently_replaced`. |
| `test_the_client_is_pointed_at_the_accounts_openai_host_not_the_project_host` | E | `FoundryWireTests.Actual_openai_adapter_uses_entra_and_v1_deployment_wire_shape`. |
| `test_a_host_that_is_not_a_public_cloud_foundry_name_keeps_its_own` | E | `FoundryWireTests.Actual_openai_adapter_uses_entra_and_v1_deployment_wire_shape`, `sovereign.example.test` theory case, verifies the official SDK request preserves the configured custom host. Synthetic local HTTP handler, not sovereign-cloud deployment evidence. |
| `test_a_project_endpoint_that_is_not_https_is_refused` | E | `FoundryWireTests.Unsafe_endpoint_is_refused_before_any_credential_is_created`. |
| `test_the_built_client_carries_that_base_url_and_the_deployment_name` | E | `FoundryWireTests.Actual_openai_adapter_uses_entra_and_v1_deployment_wire_shape`. |
| `test_a_turn_runs_the_real_loop_through_the_frameworks_client_and_the_composer_still_speaks` | E | `FoundryWireTests.Real_framework_loop_sends_only_projected_tools_and_fact_paths_on_the_official_wire`; `RuntimeWireTests.Real_responses_wire_crosses_identity_framework_rest_gateway_guard_and_audit`. |
| `test_the_wire_is_chat_completions_v1_on_the_accounts_host_with_the_deployment_and_the_tools` | E | `FoundryWireTests.Actual_openai_adapter_uses_entra_and_v1_deployment_wire_shape`; `FoundryWireTests.Real_framework_loop_sends_only_projected_tools_and_fact_paths_on_the_official_wire`. |
| `test_a_deployment_that_rejects_sampling_parameters_is_sent_none` | E | `FoundryWireTests.Real_framework_loop_sends_only_projected_tools_and_fact_paths_on_the_official_wire` checks absence of temperature/top-p on all captured unsupported-deployment requests. |
| `test_the_models_text_is_never_the_replys_text` | E | `ScriptedTurnsTests.Actual_agent_keeps_canonical_figures_and_audits_the_guard`; `RuntimeWireTests.Real_responses_wire_crosses_identity_framework_rest_gateway_guard_and_audit`. |
| `test_the_request_is_authenticated_by_the_token_provider_and_by_nothing_else` | E | `FoundryWireTests.Actual_openai_adapter_uses_entra_and_v1_deployment_wire_shape` checks bearer auth, requested token scope and absence of API-key auth. |
| `test_the_access_description_has_no_key_field_and_the_default_credential_is_the_managed_identity` | P | `FoundryWireTests.Actual_openai_adapter_uses_entra_and_v1_deployment_wire_shape` proves injected Entra authentication without API key. It does not prove which production credential wins DefaultAzureCredential resolution or inspect every configuration field. |
| `test_with_no_credential_given_the_client_asks_for_the_default_credential_once_per_process` | U | No default-credential factory invocation-count/process-lifetime test mapped. |
| `test_an_employee_identifier_never_reaches_the_wire` | E | `ModelRoutingTests.An_identifier_in_the_reader_question_never_reaches_a_model_wire`; `ScriptedTurnsTests.Every_model_request_excludes_person_rows_while_the_reader_keeps_them`. Synthetic identifier/model boundary evidence, not a live provider request. |
| `test_an_injection_attempt_calls_no_model` | E | `ScriptedTurnsTests.Anonymous_and_injection_messages_do_not_reach_a_model`. |
| `test_a_model_that_does_not_answer_in_time_degrades_to_the_engines_own_answer` | E | `ModelRoutingTests.An_SDK_call_timeout_cancels_the_attempt_and_degrades_without_replaying_tools` injects a hanging SDK client, verifies cancellation and one attempt, retains the engine figure with an unavailable notice, and checks the exact single resolve/read sequence. This is model-attempt timeout, not proof of every whole-turn deadline boundary. |
| `test_a_model_error_degrades_without_hiding_the_engines_answer` | E | `ScriptedTurnsTests.Model_failure_before_tools_falls_back_but_after_tools_never_replays_them`. |
| `test_the_trace_the_audit_reads_is_filled_by_the_frameworks_client` | P | `ScriptedTurnsTests.Actual_agent_keeps_canonical_figures_and_audits_the_guard` checks audit guard and prompt hash; `ModelRoutingTests.W1_chains_preserve_fallback_and_account_for_each_actual_attempt` checks actual attempts/budget. No exhaustive framework trace-field audit assertion. |

### test_orch_golden.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_there_are_enough_golden_prompts_and_every_read_tool_is_asked_for` | U | C, same file/function row; Python model-scripted golden corpus is not enumerated. |
| `test_golden` | P | C, same file/function row; named scripted scenarios and 39 deterministic records are not the complete Python golden corpus. |

### test_orch_host.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_the_original_subject_the_platform_sends_becomes_the_acting_user` | E | `IdentityTests.Platform_subject_overrides_conflicting_headers_and_oid_case_is_normalized`; `RuntimeWireTests.Real_responses_wire_crosses_identity_framework_rest_gateway_guard_and_audit`. |
| `test_no_signal_means_a_refusal_and_not_a_single_call` | E | `RuntimeWireTests.Anonymous_and_debug_off_wire_requests_never_touch_gateway_or_model`; `ScriptedTurnsTests.Anonymous_and_injection_messages_do_not_reach_a_model`. |
| `test_the_conversation_falls_back_to_the_response_chain` | E | `IdentityTests.Conversation_prefers_explicit_then_chain`; `RecordedTurnsTests.All_thirty_nine_source_records_are_compared_by_id`, conversation-key record. |
| `test_the_signals_are_lowercased_and_the_opaque_id_is_carried_but_never_trusted` | E | `IdentityTests.Configured_sources_resolve_with_case_insensitive_header_names`; `IdentityTests.Source_order_is_configurable_and_opaque_agent_id_does_not_block_the_next_source`; `DebugCommandTests.Enabled_whoami_explains_absent_signals_but_hides_an_opaque_partition_identifier`. |
| `test_whoami_is_inert_unless_switched_on` | E | `DebugCommandTests.Debug_off_commands_are_inert_with_no_identity_or_diagnostic_calls`. |
| `test_whoami_reports_signals_and_the_resolution_when_switched_on_and_leaks_no_credential` | E | `DebugCommandTests.Enabled_startup_warns_and_whoami_resolves_header_case_without_exposing_credentials`. |
| `test_whoami_with_no_identity_says_why_which_is_the_point_of_the_spike` | E | `DebugCommandTests.Enabled_whoami_explains_absent_signals_but_hides_an_opaque_partition_identifier`. |
| `test_whoami_names_the_person_the_channel_and_the_conversation` | P | `DebugCommandTests.Enabled_startup_warns_and_whoami_resolves_header_case_without_exposing_credentials` checks person/conversation; `RecordedTurnsTests.All_thirty_nine_source_records_are_compared_by_id` compares complete recorded debug answers including channel. No independent channel-specific assertion in the former method. |
| `test_a_refused_turn_shows_what_was_received_only_when_debugging` | E | `DebugCommandTests.Debug_off_commands_are_inert_with_no_identity_or_diagnostic_calls`; `DebugCommandTests.Enabled_whoami_explains_absent_signals_but_hides_an_opaque_partition_identifier`; `RecordedTurnsTests.All_thirty_nine_source_records_are_compared_by_id`. |
| `test_a_correlation_id_is_made_safe_for_the_gateway` | E | `IdentityTests.Correlation_is_ascii_header_safe`; `IdentityTests.Correlation_is_bounded_or_new_when_nothing_safe_arrives`. |

### test_orch_hosting_seam.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_only_the_seam_imports_a_hosting_package_anywhere_in_the_repository` | P | `ArchitectureTests.Actual_vendor_hosting_and_agent_dependencies_stay_in_their_outer_adapters` confines actual hosting using-directives to `Hosting`; `ResponsesWireTests.Installed_host_extracts_input_and_frames_one_complete_text_response_and_readiness` proves that seam executes. The lexical .NET scan is not an all-syntax Python AST scanner or whole-repository import proof. |
| `test_the_zip_root_entry_point_only_starts_the_seam` | X | Python zip-root packaging does not apply; no W4 published artifact entrypoint inspection is claimed. |
| `test_the_agent_framework_is_imported_by_the_maf_layer_and_nowhere_else_in_the_orchestrator` | P | `ArchitectureTests.Actual_vendor_hosting_and_agent_dependencies_stay_in_their_outer_adapters`; `PackageLoopTests.Scripted_call_crosses_real_agent_function_middleware_and_generated_body`. Actual .NET using-directives are confined to `Framework` and separately `Workflow`; these two adapters replace Python's single MAF layer. The scan is lexical, not every possible C# reference syntax. |
| `test_the_seam_registers_one_handler_and_hands_everything_to_the_host_and_the_wiring` | E | `ResponsesWireTests.Installed_host_extracts_input_and_frames_one_complete_text_response_and_readiness`; `RuntimeWireTests.Real_responses_wire_crosses_identity_framework_rest_gateway_guard_and_audit`. Local actual package request extraction/dispatch/framing/readiness evidence, not deployment registration. |
| `test_the_pre_release_hosting_package_is_not_a_requirement_and_no_pre_flag_is_used` | X | Python package maturity/pip-flag constraint is not the named .NET preview-package policy. No equivalence to a Python stable hosting distribution is claimed. |
| `test_the_entry_point_azure_and_the_container_image_all_start_the_same_file` | X | W4 deployment/image entrypoint convergence is not established by local host startup. |
| `test_the_import_scan_sees_a_hosting_import_in_any_form` | X | Negative control for a Python AST scanner, not an executable .NET requirement by itself. |
| `test_the_import_scan_leaves_ordinary_azure_imports_alone` | X | Python scanner discrimination; no Python scanner is shipped by this .NET host. |
| `test_the_real_azure_yaml_declares_activity_on_the_endpoint_only` | X | W4 Python Activity-manifest declaration is not the .NET Responses wire. |
| `test_the_guard_catches_each_way_teams_goes_silent` | X | Deployment/manifest failure matrix is outside local .NET hosting evidence. |
| `test_the_guard_accepts_the_known_good_shape` | X | Python deployment-manifest guard positive fixture, not runtime wire validation. |
| `test_a_missing_container_protocols_block_fails_rather_than_passes` | X | W4 container protocol metadata; no .NET deployment declaration is certified here. |
| `test_the_no_go_and_its_recheck_conditions_are_written_down` | X | Python hosting feasibility decision-document content is not a .NET runtime guarantee. The actual .NET wire is tested independently. |

### test_orch_identity.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_the_original_subject_is_the_first_source_and_is_recorded_as_such` | E | `IdentityTests.Platform_subject_overrides_conflicting_headers_and_oid_case_is_normalized`. |
| `test_the_next_configured_source_answers_when_the_first_has_nothing` | E | `IdentityTests.Configured_sources_resolve_with_case_insensitive_header_names`; `IdentityTests.Source_order_is_configurable_and_opaque_agent_id_does_not_block_the_next_source`. |
| `test_the_opaque_per_user_id_is_never_an_identity` | E | `IdentityTests.Source_order_is_configurable_and_opaque_agent_id_does_not_block_the_next_source`; `DebugCommandTests.Enabled_whoami_explains_absent_signals_but_hides_an_opaque_partition_identifier`. |
| `test_caller_supplied_headers_are_trusted_only_when_asked_for` | E | `IdentityTests.Caller_supplied_oid_is_not_trusted_by_default`; `IdentityTests.Configured_sources_resolve_with_case_insensitive_header_names`, opt-in case. |
| `test_a_missing_name_is_stated_not_invented` | E | `IdentityTests.Configured_sources_resolve_with_case_insensitive_header_names`. |
| `test_a_malformed_object_id_a_foreign_tenant_or_no_conversation_refuses` | E | `IdentityTests.Invalid_higher_precedence_oid_refuses_instead_of_downgrading`; `IdentityTests.Foreign_tenant_refuses_without_exposing_its_asserted_value`; `IdentityTests.Response_id_and_caller_conversation_header_do_not_invent_a_conversation`. |
| `test_the_gateway_headers_carry_exactly_the_acting_user_and_no_credential` | E | `IdentityTests.Gateway_assertions_are_not_backend_api_headers_or_credentials`; `GatewayTests.Calls_preserve_exact_args_workflow_metadata_and_verified_assertions`. Service authentication is separately added by the client, not forwarded inbound credentials. |
| `test_state_is_per_person_and_conversation` | E | `IdentityTests.Keys_separate_people_even_when_the_response_chain_is_reused`; `ConversationStoreTests.A_reused_response_chain_cannot_share_a_selected_client_between_verified_people`; `WriteWorkflowTests.SharedWorkflowDefinitionsKeepTwoOwnersCheckpointsIsolated`. |
| `test_the_debug_report_names_signals_and_shows_identity_values_never_a_credential` | E | `DebugCommandTests.Enabled_startup_warns_and_whoami_resolves_header_case_without_exposing_credentials`; `DebugCommandTests.Agent_guid_shape_reports_only_the_explicitly_permitted_identity_value`. |
| `test_no_identity_means_no_tool_no_model_and_a_plain_refusal` | E | `ScriptedTurnsTests.Anonymous_and_injection_messages_do_not_reach_a_model`; `RuntimeWireTests.Anonymous_and_debug_off_wire_requests_never_touch_gateway_or_model`; `RecordedTurnsTests.All_thirty_nine_source_records_are_compared_by_id`, nobody record. |
| `test_every_gateway_call_carries_the_acting_user_and_nothing_else_identifying` | E | `GatewayTests.Calls_preserve_exact_args_workflow_metadata_and_verified_assertions`; `GatewayTests.Shared_infrastructure_has_no_cross_person_headers_and_acquires_each_token_per_call`; `GatewayTests.Audit_uses_the_same_identity_context_and_returns_gateway_errors_without_retry`. |
| `test_the_agent_user_id_is_a_source_only_when_asked_for_and_only_when_it_is_an_object_id` | E | `IdentityTests.Configured_sources_resolve_with_case_insensitive_header_names`; `IdentityTests.Source_order_is_configurable_and_opaque_agent_id_does_not_block_the_next_source`. |
| `test_an_opaque_agent_user_id_is_no_signal_so_the_next_source_still_answers` | E | `IdentityTests.Source_order_is_configurable_and_opaque_agent_id_does_not_block_the_next_source`. |
| `test_the_shape_report_shows_an_object_id_and_hides_an_opaque_key` | E | `DebugCommandTests.Agent_guid_shape_reports_only_the_explicitly_permitted_identity_value`; `DebugCommandTests.Enabled_whoami_explains_absent_signals_but_hides_an_opaque_partition_identifier`. |
| `test_by_default_the_platforms_agent_user_id_is_a_source_after_the_two_platform_signals` | E | `IdentityTests.Environment_defaults_match_the_current_platform_source_policy`. |

### test_orch_knowledge.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_with_the_tier_off_the_model_is_told_no_reference_text_and_the_reply_carries_none` | E | C, same file/function row. |
| `test_the_planner_and_the_agent_builder_default_to_no_knowledge` | P | C, same file/function row; provider boundary, not planner constructor inspection. |
| `test_the_default_wiring_builds_no_knowledge_source` | P | C, same file/function row; disabled provider invocation and explicitly disabled production-wiring output, not source-construction counting or unset-setting default inspection. |
| `test_switching_it_on_in_the_environment_builds_the_fake_and_a_bad_setting_stops_the_start` | E | C, same file/function row; production runtime configuration/model requests with labelled synthetic retrieval and invalid-setting startup refusal. Unsupported live `foundry-iq` refuses rather than substituting fake retrieval. |
| `test_the_model_is_told_the_passages_as_fenced_reference_text_without_their_citations` | E | C, same file/function row; provider fence checks plus enabled production-wiring model requests without citation identifiers. No separate framework SessionContext hook claim. |
| `test_the_reader_gets_the_quoted_passages_with_their_citations_beside_a_surviving_narration` | E | C, same file/function row. |
| `test_only_as_many_passages_as_the_setting_allows_are_retrieved_and_shown` | E | C, same file/function row; explicit provider top bound plus `KNOWLEDGE_TOP=1` production runtime/synthetic corpus selection. Not live search-ranking proof. |
| `test_a_narration_that_repeats_a_figure_read_only_in_a_passage_is_dropped_and_no_reference_block_is_shown` | E | C, same file/function row. |
| `test_the_turns_facts_are_the_tools_facts_and_hold_nothing_from_a_passage` | E | C, same file/function row. |
| `test_a_placeholder_into_reference_text_drops_the_narration` | E | C, same file/function row. |
| `test_a_knowledge_source_that_fails_leaves_the_turn_exactly_as_it_was` | P | C, same file/function row; failed provider context, not full-turn SDK equality. |
| `test_a_turn_with_no_matching_passage_shows_no_reference_block` | P | C, same file/function row; empty usable set, not a dedicated successful-empty SDK turn. |
| `test_falling_back_to_the_platforms_own_answer_forgets_the_reference` | E | C, same file/function row. |
| `test_the_provider_adds_instructions_only_and_keeps_what_it_found` | P | C, same file/function row; separate context string/facts, not a framework SessionContext hook. |
| `test_the_provider_with_nothing_found_or_a_failing_source_adds_nothing` | P | C, same file/function row; failed/all-invalid provider evidence, not a framework hook. |

### test_orch_maf.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_the_agent_result_is_the_composers_output_never_the_models_text` | E | `ScriptedTurnsTests.Actual_agent_keeps_canonical_figures_and_audits_the_guard`; `RuntimeWireTests.Real_responses_wire_crosses_identity_framework_rest_gateway_guard_and_audit`. |
| `test_an_agent_with_a_middleware_is_the_shape_that_ships` | E | `PackageLoopTests.Scripted_call_crosses_real_agent_function_middleware_and_generated_body`; `ModelRoutingTests.Real_framework_loop_runs_inside_the_existing_W1_guard_budget_and_resilience_adapters`. |
| `test_the_tool_loop_is_bounded_by_the_turn_budget` | E | `ScriptedTurnsTests.Refusals_and_duplicate_attempts_cannot_evade_the_call_budget`; `JsonPlanningTests.An_invented_or_commit_tool_is_not_dispatched_in_json_mode`. |
| `test_the_frameworks_stop_message_is_never_handed_to_the_composer_as_narration` | E | `ScriptedTurnsTests.Actual_framework_iteration_exhaustion_cannot_become_narration_or_repeat_a_read` drives the real framework to iteration exhaustion, checks no narration, retained engine figure, bounded model requests, one read and absence of the framework maximum-limit wording. |

### test_orch_models.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_a_tool_call_crosses_the_wire_into_the_maf_loop_and_back` | E | `FoundryWireTests.Real_framework_loop_sends_only_projected_tools_and_fact_paths_on_the_official_wire`. |
| `test_a_failing_provider_falls_through_to_the_next_before_any_text` | E | `ModelRoutingTests.W1_chains_preserve_fallback_and_account_for_each_actual_attempt`. |
| `test_a_provider_without_tool_calling_is_skipped_when_tools_are_needed` | E | `ModelRoutingTests.A_text_only_provider_is_skipped_for_framework_calls_but_preserved_for_json_planning`. |
| `test_every_provider_failing_degrades_to_the_engines_own_answer` | P | `ScriptedTurnsTests.Model_failure_before_tools_falls_back_but_after_tools_never_replays_them` tests the model boundary failing. A multi-provider all-fail-to-keywords case is not separately asserted. |
| `test_a_prompt_carrying_an_employee_identifier_never_reaches_a_model` | E | `ModelRoutingTests.A_guard_refusal_happens_before_transport_and_never_selects_an_unconfigured_default`; `ModelRoutingTests.An_identifier_in_the_reader_question_never_reaches_a_model_wire`. |
| `test_the_gateway_provider_is_external_so_aggregates_only_refuses_a_free_text_question` | P | `ModelRoutingTests.A_guard_refusal_happens_before_transport_and_never_selects_an_unconfigured_default` tests external-provider blocking with BlockExternal. The source's specific aggregates-only/free-text policy combination is not separately asserted. |
| `test_a_foundry_project_endpoint_gives_the_accounts_openai_v1_base_on_the_host_the_hosted_runtime_can_resolve` | E | `FoundryWireTests.Actual_openai_adapter_uses_entra_and_v1_deployment_wire_shape` proves endpoint transformation and outbound target, not live DNS resolution. |
| `test_a_host_that_is_not_a_public_cloud_foundry_name_keeps_its_own` | E | `FoundryWireTests.Actual_openai_adapter_uses_entra_and_v1_deployment_wire_shape`, custom `sovereign.example.test` theory case, checks host preservation on the actual official SDK request. No live sovereign-cloud reachability claim. |

### test_orch_netcheck.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_addresses_are_classified` | E | `NetcheckTests.Address_classification_matches_source_including_special_exceptions`. |
| `test_a_name_that_does_not_resolve_stops_at_resolve` | E | `NetcheckTests.Resolve_failure_stops_that_host_before_connect_and_sanitizes_exception_details`; `NetcheckTests.Empty_dns_results_stop_before_connect`. |
| `test_a_private_address_that_cannot_be_connected_is_reported_as_private_and_failed` | E | `NetcheckTests.Tcp_failure_preserves_private_classification_and_stops_before_tls`. |
| `test_a_reachable_host_reports_tls_and_the_httpx_result_separately` | E | `NetcheckTests.Tls_and_http_client_results_are_independent_and_do_not_return_response_bodies`; `NetcheckTests.Tls_failure_does_not_skip_the_independent_http_client_check`. Equivalent .NET client field is `http_client_status`, not the Python-library name. |
| `test_the_accounts_other_names_are_derived_from_the_project_endpoint` | E | `NetcheckTests.Account_hosts_derive_the_three_source_targets_and_invalid_configuration_adds_nothing`. |
| `test_the_environment_report_gives_names_and_only_the_listed_values` | E | `NetcheckTests.Full_report_has_every_target_safe_environment_projection_and_no_proxy_credentials`. |
| `test_the_full_report_covers_every_target_and_leaks_nothing` | E | `NetcheckTests.Full_report_has_every_target_safe_environment_projection_and_no_proxy_credentials`; `NetcheckTests.Addresses_are_bounded_deduplicated_and_ipv4_is_preferred_without_echoing_invalid_values`. Synthetic probes only. |
| `test_modelprobe_reports_success_without_the_reply` | E | `ModelDiagnosticTests.Model_success_exposes_only_metadata_and_strips_credentials_queries_and_fragments_from_base_uri`. |
| `test_modelprobe_reports_a_failure_by_type_and_cause_and_does_not_raise` | E | `ModelDiagnosticTests.Model_failure_reports_exception_and_cause_types_but_neither_exception_message`. |
| `test_modelprobe_without_configuration_says_so` | E | `ModelDiagnosticTests.Missing_model_configuration_and_missing_probe_are_distinct_and_never_implicitly_call_a_model`. |
| `test_the_commands_are_not_offered_without_the_debug_flag` | E | `DebugCommandTests.Debug_off_commands_are_inert_with_no_identity_or_diagnostic_calls`; `RuntimeWireTests.Anonymous_and_debug_off_wire_requests_never_touch_gateway_or_model`. |
| `test_with_the_flag_a_command_is_answered_by_the_diagnostics_and_runs_no_tool` | E | `DebugCommandTests.Enabled_diagnostics_use_only_injected_local_collaborators` invokes the injected diagnostics seam directly; no live diagnostic is run. |

### test_orch_numeric_lanes.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_the_wages_exist_only_in_the_persons_lane` | E | C, same file/function row. |
| `test_the_readers_allowed_numerals_never_include_a_figure_from_the_rows` | P | C, same file/function row; behavioral refusal, not direct internal allowed-set inspection. |
| `test_a_narration_that_types_a_wage_only_the_rows_hold_is_rejected_and_the_person_still_gets_the_rows` | E | C, same file/function row. |
| `test_a_placeholder_pointing_into_the_persons_lane_is_rejected` | E | C, same file/function row. |
| `test_the_rejection_is_audited_as_a_code_never_naming_the_path` | E | C, same file/function row. |
| `test_a_placeholder_for_a_fact_the_model_was_shown_is_still_rendered` | E | C, same file/function row. |
| `test_the_rule_is_about_the_lane_not_about_rows_an_aggregate_is_narratable` | E | C, same file/function row. |
| `test_rows_past_the_models_cut_are_not_a_placeholder_target_either` | E | C, same file/function row. |
| `test_a_path_that_does_not_exist_is_still_the_composers_to_reject` | E | C, same file/function row. |
| `test_a_reply_with_no_narration_is_unchanged_and_verifies_its_own_blocks` | E | C, same file/function row. |
| `test_a_figure_a_data_tool_did_not_return_is_rejected` | P | C, same file/function row; common guard, not all-three-data-tool matrix. |
| `test_a_figure_a_data_tool_did_return_is_still_not_the_models_to_type` | P | C, same file/function row; query/public copied-figure proof, not three-tool matrix. |
| `test_an_invented_path_on_a_data_tool_is_rejected` | P | C, same file/function row; common rejection, not three named capability cases. |
| `test_the_one_way_a_data_tool_figure_reaches_the_reader_is_a_placeholder_the_platform_renders` | P | C, same file/function row; aggregate query/general token proof. |
| `test_a_data_tools_facts_are_the_guards_facts` | P | C, same file/function row; synthetic envelopes, not canonical producer integration. |
| `test_the_composer_is_reached_only_through_compose_reply` | P | C, same file/function row; runtime/cache evidence, not exhaustive call-site assertion. |
| `test_every_data_tool_is_an_ordinary_read_the_guard_sees` | P | C, same file/function row; exact exposure/query path, not all-tool kind/tag assertion. |

### test_orch_placeholders.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_a_placeholder_names_the_path_and_the_format_hint` | E | C, same file/function row. |
| `test_entries_keep_their_own_keys_and_gain_a_placeholder` | P | C, same file/function row; fixed .NET entry shape, no generic dictionary-enrichment contract. |
| `test_every_placeholder_the_model_is_given_resolves_to_the_engines_figure` | E | C, same file/function row. |
| `test_the_path_without_the_facts_prefix_is_still_refused_not_loosened` | E | C, same file/function row. |

### test_orch_planning.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_book_rank_says_it_is_for_the_whole_book_only` | P | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` checks the pinned description, not an independent scope-language assertion. |
| `test_the_client_tools_are_found_and_every_one_says_it_needs_a_client` | P | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` verifies exact model definitions; no per-client-tool scope-language inventory assertion. |
| `test_a_tool_that_needs_no_client_does_not_claim_to` | P | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` checks descriptions; no separate negative scope-language test. |
| `test_the_maf_tools_and_the_json_catalogue_carry_the_same_words` | P | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory` checks framework descriptions. No direct JSON-planner/framework description comparison. |
| `test_the_planner_instructions_send_one_client_questions_to_client_tools` | U | No named one-client planner-instruction text assertion mapped. Scripted model tool choices cannot prove those instructions. |
| `test_the_planner_says_how_to_tell_the_two_apart_and_who_resolves_the_client` | P | `ScriptedTurnsTests.Split_calls_share_one_reader_resolution_overwrite_model_scope_and_deduplicate` proves resolver authority in execution, not planner instruction wording. |

### test_orch_requirements.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_every_shared_dependency_is_pinned_to_the_version_the_platform_runs` | P | `ArchitectureTests.The_root_pins_net10_and_all_orchestrator_modules_stay_within_the_documented_size_limit`; `PackageLoopTests.Scripted_call_crosses_real_agent_function_middleware_and_generated_body`; `ResponsesWireTests.Installed_host_extracts_input_and_frames_one_complete_text_response_and_readiness` prove target pin and installed-package runtime compatibility, not exhaustive package pin/lock inspection. Python exact-version equality is not a .NET requirement. |
| `test_the_agent_framework_pin_is_the_one_the_backends_foundry_package_resolves_to` | X | Python backend dependency-resolution equality is not a .NET package graph invariant; no cross-language version-string equivalence claimed. |
| `test_the_frameworks_openai_client_and_its_sdk_are_pinned_to_what_is_installed` | P | `FoundryWireTests.Real_framework_loop_sends_only_projected_tools_and_fact_paths_on_the_official_wire` proves installed adapter/SDK operation; no separate central-pin versus installed-version assertion. |
| `test_the_orchestrator_does_not_install_the_backend_and_names_a_stable_hosting_package` | P | `ArchitectureTests.The_executable_references_shared_ports_and_defaults_not_a_vendored_backend` asserts exact project references and no Python sources; `ResponsesWireTests.Installed_host_extracts_input_and_frames_one_complete_text_response_and_readiness` proves actual .NET hosting. .NET's named preview-package policy differs from Python stable-package wording. |
| `test_every_variable_the_orchestrator_reads_is_in_the_environment_reference` | U | No complete runtime-variable/documentation inventory assertion mapped. |
| `test_the_decisions_the_docs_cite_exist` | U | No ADR/documentation link-existence assertion mapped. |

### test_orch_resilience.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_a_turn_past_its_deadline_says_so_and_changes_nothing` | P | `GatewayTests.Timeout_is_explicit_unknown_outcome_and_never_automatically_retried` proves the gateway timeout boundary, not an expired whole-turn deadline before any mutation. |
| `test_a_confirm_that_runs_out_of_time_is_unknown_never_retried_and_not_confirmable_again` | E | `CheckpointTurnsTests.Lost_commit_response_is_unknown_and_cannot_reconfirm_or_retry`; `WriteWorkflowTests.CancellationAfterCommitDispatchLeavesExplicitUnknownAndCannotRetry`. |
| `test_the_turn_deadline_is_bounded_and_documented_in_the_settings` | P | `RuntimeWireTests.Invalid_runtime_settings_fail_before_credentials_or_transports` checks rejected out-of-range turn timeout. It does not read documentation or prove every bound. |
| `test_a_span_per_tool_call_carries_the_tool_and_its_outcome_and_no_payroll` | E | `RunnerBoundaryTests.Tool_spans_report_controlled_outcomes_without_reader_text_arguments_or_person_fields` listens to real tool ActivitySource events, requires one span, exact tool/outcome and an allowlisted tag set, with reader name/person ID absent. Both success and failure cases are local injected-gateway reads. |
| `test_a_failed_call_is_a_span_with_an_error_code_and_still_no_content` | E | `RunnerBoundaryTests.Tool_spans_report_controlled_outcomes_without_reader_text_arguments_or_person_fields`, failure case, asserts controlled `dependency_unavailable` error code and tag privacy without copying tool arguments/reader text. |
| `test_the_readers_numbers_are_digits_or_the_words_one_to_twelve` | P | `ReaderWordsTests.Model_scenario_values_are_removed_and_missing_size_is_asked_not_inferred` covers the word five and numeric reader-owned size. No complete one-through-twelve extraction table. |
| `test_a_what_if_number_the_model_chose_is_dropped_and_the_readers_is_kept` | E | `ReaderWordsTests.Model_scenario_values_are_removed_and_missing_size_is_asked_not_inferred`. |

### test_orch_review_pack.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_the_pack_is_asked_for_by_name` | E | `ReviewPackTests.Named_pack_has_fixed_read_only_order_and_its_own_six_call_budget`, four named-invocation cases. |
| `test_an_ordinary_question_is_not_the_pack` | P | `ScriptedTurnsTests.Actual_agent_keeps_canonical_figures_and_audits_the_guard` proves ordinary tools mode; no complete negative review-pack phrase table. |
| `test_the_steps_are_catalog_tools_that_only_read_and_the_sequence_has_its_own_budget` | E | `ReviewPackTests.Named_pack_has_fixed_read_only_order_and_its_own_six_call_budget` asserts exact calls, no prepare and full sequence despite agent maxCalls=1. |
| `test_the_pack_runs_every_step_in_order_through_the_gateway_with_no_model` | E | `ReviewPackTests.Named_pack_has_fixed_read_only_order_and_its_own_six_call_budget`. |
| `test_the_reply_passes_the_numeric_guard_against_the_runs_own_facts` | P | `ReviewPackTests.Named_pack_has_fixed_read_only_order_and_its_own_six_call_budget` exercises ordinary composition; `ExactnessTests.Many_scripted_narrators_cannot_change_exact_synthetic_figures` independently checks bodies. No independent post-pack guard over that pack's own complete run set. |
| `test_each_step_sends_the_gateway_what_an_agents_call_for_the_same_words_would` | P | `ReviewPackTests.Named_pack_has_fixed_read_only_order_and_its_own_six_call_budget`; `ScriptedTurnsTests.Split_calls_share_one_reader_resolution_overwrite_model_scope_and_deduplicate`. Exact sequence and ordinary settling are tested separately, not full per-step argument equality against an agent-driven pack. |
| `test_a_configured_tool_calling_model_is_not_asked_for_the_pack` | E | `ReviewPackTests.Named_pack_has_fixed_read_only_order_and_its_own_six_call_budget` injects a model and requires no requests. |
| `test_the_sequence_has_its_own_budget_whatever_the_agents_is` | E | `ReviewPackTests.Named_pack_has_fixed_read_only_order_and_its_own_six_call_budget`. |
| `test_the_pack_changes_nothing_and_asks_for_no_confirmation` | P | `ReviewPackTests.Named_pack_has_fixed_read_only_order_and_its_own_six_call_budget` checks exact read-only call sequence/no prepare. It does not explicitly inspect mutation count and absence of confirmation wording. |
| `test_a_missing_year_is_asked_for_and_the_next_message_may_be_only_the_year` | E | `ReviewPackTests.Bare_year_follow_up_reuses_the_original_named_pack`. |
| `test_an_ambiguous_client_is_asked_for_and_the_numbered_reply_runs_the_pack_for_the_one_chosen` | E | `ReviewPackTests.Numbered_choice_keeps_the_pack_and_uses_the_reader_selected_client`. |
| `test_a_year_is_not_taken_from_a_message_that_is_not_answering_a_pack` | E | `RunnerBoundaryTests.An_unrelated_message_cannot_become_a_pending_review_packs_year_answer` interrupts a missing-year pack with another client's dated trend, then asserts the exact subsequent ordinary keyword/two-method eligibility calls for the new client and year. The bare year is not ignored or turned into help: it must not resurrect the old pack. |
| `test_a_step_that_fails_is_reported_and_the_others_still_answer` | E | `ReviewPackTests.A_partial_failure_does_not_hide_other_reads`. |
| `test_when_nothing_answers_the_check_stops_the_pack_and_the_reader_is_told_so_without_a_figure` | E | `ReviewPackTests.If_all_steps_fail_no_trusted_numeric_answer_is_invented`. |
| `test_the_workflow_is_one_chain_from_resolve_to_compose_with_a_step_per_catalog_tool` | P | `ReviewPackTests.Named_pack_has_fixed_read_only_order_and_its_own_six_call_budget` proves execution order, not an SDK review-pack graph/edge-inventory assertion. Write checkpoint tests concern a different workflow. |

### test_orch_runner.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_years_are_read_from_the_readers_words` | E | `ReaderWordsTests.Reader_overrides_model_year_and_method`; `ReaderWordsTests.Data_years_keep_only_the_reader_and_never_a_neighbor`. |
| `test_commit_tools_plumbing_and_the_resolver_are_not_tools_a_model_may_name` | E | `CatalogProjectionTests.Every_model_tool_description_and_schema_match_the_inventory`; `PackageLoopTests.Unlisted_name_never_executes_a_body`. |
| `test_no_maf_tool_is_a_commit_and_the_model_is_shown_no_client_id` | E | `PackageLoopTests.Scripted_call_crosses_real_agent_function_middleware_and_generated_body`; `FoundryWireTests.Real_framework_loop_sends_only_projected_tools_and_fact_paths_on_the_official_wire`. |
| `test_what_the_model_sees_of_a_result_names_the_facts_and_holds_no_value` | E | `FoundryWireTests.Real_framework_loop_sends_only_projected_tools_and_fact_paths_on_the_official_wire`; `ModelLaneTests.Every_brief_token_is_copyable_renderable_and_contains_no_value`. Declared lookups separately receive structural data. |
| `test_a_prepared_changes_token_is_kept_by_the_runner_and_never_shown_to_anyone_else` | E | `CheckpointTurnsTests.Actual_agent_prepare_pauses_then_confirm_resumes_once_with_current_attribution`; `ModelLaneTests.Confirmation_tokens_are_neither_placeholder_authority_nor_reader_or_model_content`. In .NET the owner is the actual SDK checkpoint, not a second runner token copy. |
| `test_the_tool_budget_is_enforced_and_a_refused_name_is_recorded_not_run` | P | `ScriptedTurnsTests.Refusals_and_duplicate_attempts_cannot_evade_the_call_budget`; `PackageLoopTests.Unlisted_name_never_executes_a_body`. No exhaustive assertion of every refusal-ledger field. |
| `test_the_client_is_resolved_once_per_turn_not_once_per_tool` | E | `ScriptedTurnsTests.Split_calls_share_one_reader_resolution_overwrite_model_scope_and_deduplicate`. |
| `test_one_named_client_selects_it_even_when_the_conversation_was_about_another` | E | `RunnerBoundaryTests.Naming_another_client_overrides_the_same_persons_existing_selection` runs two real-framework turns for the same person/conversation and asserts the exact switched client IDs on successive trend calls. |
| `test_the_method_is_the_readers_and_defaults_to_both_certified_methods` | E | `ReaderWordsTests.Reader_overrides_model_year_and_method`; `ScriptedTurnsTests.Split_calls_share_one_reader_resolution_overwrite_model_scope_and_deduplicate`. |
| `test_the_same_tool_under_two_methods_has_two_labels_so_no_path_collides` | E | `ModelLaneTests.Multiple_methods_keep_independent_paths_and_headings`. |
| `test_an_argument_the_catalog_does_not_know_is_refused_before_the_gateway` | E | `RunnerBoundaryTests.Unknown_arguments_reach_the_common_schema_refusal_not_the_gateway` covers tools and JSON planning, asserts failure naming the unknown argument, no successful runs and only the permitted client resolver call: the requested capability is never dispatched. |
| `test_the_settings_refuse_half_a_configuration_and_name_every_gap` | P | `RuntimeWireTests.Selected_but_unconfigured_foundry_is_not_silently_replaced`; `ModelRoutingTests.Missing_chain_provider_is_a_configuration_error_not_a_default_client`; `IdentityTests.Settings_are_validated_and_sources_snapshot_the_callers_list`. No assertion that all missing configuration names are reported together. |
| `test_the_settings_reject_values_that_would_weaken_a_control` | E | `RuntimeWireTests.Invalid_runtime_settings_fail_before_credentials_or_transports`; `IdentityTests.Settings_are_validated_and_sources_snapshot_the_callers_list`. |
| `test_a_repeated_identical_call_returns_the_earlier_answer_and_runs_once` | P | `ScriptedTurnsTests.Split_calls_share_one_reader_resolution_overwrite_model_scope_and_deduplicate` proves one actual call for repeated trend requests; it does not independently compare both model-facing returned payloads. |
| `test_a_different_call_is_not_mistaken_for_a_repeat` | E | `ScriptedTurnsTests.Split_calls_share_one_reader_resolution_overwrite_model_scope_and_deduplicate` retains eligibility under both methods and trend while deduplicating only repeated trend. |

### test_orch_structure.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_there_are_modules_to_check` | P | `PackageLoopTests.Scripted_call_crosses_real_agent_function_middleware_and_generated_body`; `ResponsesWireTests.Installed_host_extracts_input_and_frames_one_complete_text_response_and_readiness` prove executable compiled modules, not a source-scanner nonempty inventory. |
| `test_imports_stay_inside_the_allowed_layers_and_packages` | P | `ArchitectureTests.The_executable_references_shared_ports_and_defaults_not_a_vendored_backend`; `ArchitectureTests.Actual_vendor_hosting_and_agent_dependencies_stay_in_their_outer_adapters`. Exact project references, selected reverse assembly-reference exclusions and actual SDK using-directives are checked, not every intra-project namespace/dependency edge. |
| `test_only_main_imports_the_hosting_package` | P | `ArchitectureTests.Actual_vendor_hosting_and_agent_dependencies_stay_in_their_outer_adapters`; `ResponsesWireTests.Installed_host_extracts_input_and_frames_one_complete_text_response_and_readiness`. .NET confines the tested using-directives to the `Hosting` adapter folder, not a single Python main module or all possible C# reference syntax. |
| `test_only_the_maf_layer_imports_the_agent_framework` | P | `ArchitectureTests.Actual_vendor_hosting_and_agent_dependencies_stay_in_their_outer_adapters`; `PackageLoopTests.Scripted_call_crosses_real_agent_function_middleware_and_generated_body`; `WriteWorkflowTests.GraphUsesSdkRequestPortAndProducesACheckpoint`. .NET deliberately has separate `Framework` and `Workflow` SDK adapters. Actual using-directives are checked lexically, not every possible C# reference syntax. |
| `test_the_model_path_is_chosen_in_one_place_and_each_client_is_built_in_one_module` | P | `ModelRoutingTests.Narrator_override_decides_the_orchestrator_chain_without_discarding_other_roles`; `RuntimeWireTests.Selected_but_unconfigured_foundry_is_not_silently_replaced`. Routing behavior is tested, not all construction call sites. |
| `test_the_selection_and_the_shared_adapters_import_no_sdk` | P | `ArchitectureTests.Actual_vendor_hosting_and_agent_dependencies_stay_in_their_outer_adapters`; `ArchitectureTests.The_executable_references_shared_ports_and_defaults_not_a_vendored_backend`. The tested SDK using-directives cannot occur in selection/shared paths; selected assembly dependencies are also excluded. No all-SDK/all-syntax closure proof. |
| `test_the_commit_path_is_one_module_called_from_one_place` | P | `CheckpointTurnsTests.Actual_agent_prepare_pauses_then_confirm_resumes_once_with_current_attribution` proves one commit invocation and no repeat, not a static single-caller/module assertion. |
| `test_nothing_logs_a_token_a_header_or_a_secret` | P | `DebugCommandTests.Enabled_startup_warns_and_whoami_resolves_header_case_without_exposing_credentials`; `ModelLaneTests.A_person_only_path_or_copied_row_is_rejected_without_private_audit_material`; `GatewayTests.Network_and_credential_failures_never_reflect_exception_messages`. Named output/audit/error boundaries are tested, not every log call in the process. |
| `test_nothing_prints_and_nothing_catches_without_saying_why` | U | No exhaustive print/catch/source-scan assertion mapped initially. Sanitized failure tests are not a whole-source proof. |
| `test_modules_stay_small_and_documented` | P | `ArchitectureTests.The_root_pins_net10_and_all_orchestrator_modules_stay_within_the_documented_size_limit` asserts every orchestrator C# source file is at most 250 lines. It does not independently inspect explanatory module documentation, function/class bounds or complexity. |

### test_orch_tool_rules.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_the_rules_run_in_the_order_the_guarantees_need_inside_the_models_loop` | P | `PackageLoopTests.Scripted_call_crosses_real_agent_function_middleware_and_generated_body` proves middleware precedes forwarding; `ScriptedTurnsTests.Split_calls_share_one_reader_resolution_overwrite_model_scope_and_deduplicate` proves settling. No full per-rule ordered trace assertion. |
| `test_every_rule_is_framework_middleware_built_once_and_carrying_no_turn` | P | `PackageLoopTests.Scripted_call_crosses_real_agent_function_middleware_and_generated_body`; `CatalogProjectionTests.Returned_specification_cannot_mutate_the_shared_definitions`; `ArchitectureTests.Singleton_tool_definitions_hold_no_verified_reader_selection_or_workflow_state`. Actual middleware, immutable definitions and excluded definition-field types are checked, not every rule closure/lifetime or a build-count invariant. |
| `test_the_budget_is_counted_by_the_first_rule_and_a_call_over_it_never_reaches_the_gateway` | P | `ScriptedTurnsTests.Refusals_and_duplicate_attempts_cannot_evade_the_call_budget`; `JsonPlanningTests.An_invented_or_commit_tool_is_not_dispatched_in_json_mode`. Attempt accounting/output is proved; first-rule structural placement is not separately traced. |
| `test_a_commit_the_model_asks_for_is_recorded_and_refused_and_nothing_is_called` | P | `PackageLoopTests.Unlisted_name_never_executes_a_body`; `JsonPlanningTests.An_invented_or_commit_tool_is_not_dispatched_in_json_mode`. Refusal/no dispatch is tested; complete common refusal-ledger contents are not. |
| `test_an_invented_tool_is_recorded_too_and_a_listed_one_is_not` | P | `JsonPlanningTests.Malformed_plan_elements_do_not_hide_unknown_names_from_the_shared_refusal`; `JsonPlanningTests.An_invented_or_commit_tool_is_not_dispatched_in_json_mode`. Unknown-name preservation/refusal, not an exhaustive allowed-versus-refused ledger comparison. |
| `test_the_client_the_model_passes_is_written_over_by_the_readers` | E | `ScriptedTurnsTests.Split_calls_share_one_reader_resolution_overwrite_model_scope_and_deduplicate`. |
| `test_a_question_back_stops_the_call_and_the_model_is_told_to_wait` | P | `ConversationStoreTests.A_reused_response_chain_cannot_share_a_selected_client_between_verified_people` asserts clarification and no wrong-person call; `ReaderWordsTests.Write_year_cannot_come_from_conversation_state` asserts required clarification. Exact model-facing wait message is not independently checked. |
| `test_a_year_the_reader_did_not_say_is_replaced_and_the_method_defaults_to_both_runs` | E | `ReaderWordsTests.Reader_overrides_model_year_and_method`; `ScriptedTurnsTests.Split_calls_share_one_reader_resolution_overwrite_model_scope_and_deduplicate`; `ReaderWordsTests.Write_year_cannot_come_from_conversation_state`. |
| `test_the_schema_check_stops_what_the_catalog_would_refuse_and_records_it` | P | `RunnerBoundaryTests.Unknown_arguments_reach_the_common_schema_refusal_not_the_gateway` covers unknown-argument refusal in tools and JSON modes, failure text and no capability dispatch. It does not independently assert every refusal-ledger field or all schema violation kinds. |
| `test_a_prepared_changes_token_is_held_by_the_turn_and_never_in_what_the_model_reads` | E | `CheckpointTurnsTests.Actual_agent_prepare_pauses_then_confirm_resumes_once_with_current_attribution`; `ModelLaneTests.Confirmation_tokens_are_neither_placeholder_authority_nor_reader_or_model_content`. Framework checkpoint ownership replaces a second turn token copy. |
| `test_the_degraded_modes_run_the_same_middleware_not_a_copy_of_it` | P | `JsonPlanningTests.An_invented_or_commit_tool_is_not_dispatched_in_json_mode`; `RecordedTurnsTests.All_thirty_nine_source_records_are_compared_by_id`. Comparable execution behavior, not a uniqueness/type/call-site assertion for the rules. |
| `test_a_name_a_model_may_not_call_is_refused_before_any_rule_in_the_degraded_modes_too` | P | `JsonPlanningTests.An_invented_or_commit_tool_is_not_dispatched_in_json_mode`; `PackageLoopTests.Unlisted_name_never_executes_a_body`. No gateway dispatch is asserted, but exact before-any-rule ordering is not. |
| `test_what_is_left_of_the_tool_runner_is_the_turns_state_not_its_rules` | U | No direct runner-state-versus-rule ownership architecture assertion mapped initially. |
| `test_each_rule_is_written_once_and_only_the_framework_layer_calls_it` | U | No exhaustive per-rule definition/caller uniqueness assertion mapped initially. |

### test_orch_vendor.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_every_seed_exists_and_the_closure_stays_inside_the_allowed_layers` | P | `ArchitectureTests.The_executable_references_shared_ports_and_defaults_not_a_vendored_backend`; `ArchitectureTests.Actual_vendor_hosting_and_agent_dependencies_stay_in_their_outer_adapters`. Equivalent compiled project/reference and adapter-isolation boundaries are asserted. There is no Python seed/copy operation or exhaustive dependency-closure traversal. |
| `test_the_closure_is_standard_library_only_outside_the_model_access_adapters` | P | `ArchitectureTests.The_executable_references_shared_ports_and_defaults_not_a_vendored_backend`; `ArchitectureTests.Actual_vendor_hosting_and_agent_dependencies_stay_in_their_outer_adapters`. Equivalent selected SDK inward-reference exclusions and adapter confinement, not literal Python stdlib-only or every transitive .NET dependency. |
| `test_write_then_check_agree_and_writing_twice_changes_nothing` | X | Python vendoring write/check idempotence has no .NET copy operation to exercise. |
| `test_check_reports_a_changed_a_missing_and_an_unneeded_file` | X | Python copied-source drift scanner is not a .NET runtime artifact. |
| `test_check_says_so_when_there_is_no_copy` | X | Python missing-vendored-copy diagnostic is inapplicable to compiled project references. |
| `test_a_module_that_reaches_a_forbidden_layer_or_package_stops_the_copy` | P | `ArchitectureTests.Actual_vendor_hosting_and_agent_dependencies_stay_in_their_outer_adapters` fails for actual scanned SDK using-directives outside their adapters. This is an equivalent reference-isolation build/test gate, not a copy failure, exhaustive import scanner or injected forbidden-source negative control. |
| `test_the_vendored_copy_runs_on_its_own_without_the_backend` | P | `ArchitectureTests.The_executable_references_shared_ports_and_defaults_not_a_vendored_backend`; `ResponsesWireTests.Installed_host_extracts_input_and_frames_one_complete_text_response_and_readiness`; `FoundryWireTests.Real_framework_loop_sends_only_projected_tools_and_fact_paths_on_the_official_wire`. Exact shared project references/no Python sources plus local runtime independence, not a Python vendored-copy test or published-artifact proof. |

### test_orch_write_flow.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_the_graph_is_prepare_then_the_request_step_then_commit_and_nothing_else` | P | W, exact named row; actual SDK graph execution/checkpoint, not exhaustive independent edge inventory. |
| `test_the_only_thing_that_can_start_the_workflow_is_a_prepare_request_so_commit_is_unreachable_from_outside` | P | W, exact named row; public allowlist/refusal, not arbitrary-message injection into the private graph. |
| `test_the_prepare_step_refuses_anything_that_is_not_a_preview` | E | W, exact named row. |
| `test_the_workflow_holds_no_model_and_no_tool_and_stores_nothing_on_disk` | P | W, exact named row; in-memory SDK/reference evidence, not a whole-source import/disk scan. |
| `test_a_prepare_pauses_the_workflow_in_memory_and_sends_nothing_but_the_preview` | E | W, exact named row. |
| `test_the_confirmation_resumes_on_a_freshly_built_graph_and_the_commit_is_sent_once_as_the_person_who_confirmed` | E | W, exact named row. |
| `test_somebody_elses_confirm_finds_nothing_and_does_not_touch_the_owners_preview` | E | W, exact named row. |
| `test_a_confirmation_at_the_expiry_is_refused_and_one_second_before_it_is_not` | E | W, exact named row. |
| `test_every_refusal_the_gateway_gives_a_commit_is_reported_and_never_retried` | E | W, exact named row. |
| `test_cancel_resumes_the_workflow_with_a_refusal_so_it_ends_and_nothing_is_sent` | E | W, exact named row. |
| `test_any_other_message_cancels_the_frameworks_pending_request_and_says_the_change_was_dropped` | E | W, exact named row; terminal request-port response is the .NET cancellation equivalent. |
| `test_a_framework_fault_while_dropping_never_blocks_the_answer_or_leaves_the_change_confirmable` | P | W, exact named row; checkpoint failure covered, broken-checkpoint-plus-next-integrated-answer not separately tested. |
| `test_a_framework_fault_while_confirming_says_the_outcome_is_unknown_and_is_not_retried` | E | W, exact named row; unknown state is recovery-only/write-blocked, not confirmable. |
| `test_a_framework_fault_while_preparing_is_an_error_and_not_a_preview_that_can_be_confirmed` | P | W, exact named row; prepare-step fault covered, no independently failing custom SDK checkpoint manager. |
| `test_a_refused_preview_never_pauses_a_workflow` | E | W, exact named row. |
| `test_the_model_can_name_a_preview_but_never_a_commit_and_a_read_never_starts_a_workflow` | E | W, exact named row. |
| `test_the_confirmation_state_is_the_frameworks_checkpoint_and_not_a_second_copy_of_the_change` | E | W, exact named row. |

### test_parity_conformance.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_the_catalogs_own_filters_are_exactly_the_declared_ones` | P | C, same file/function row; model projection, not every canonical catalog filter relation. |
| `test_the_gateways_rest_list_and_mcp_list_are_the_catalogs_offered_tools_in_its_order` | X | C, same file/function row; no REST/MCP list-order matrix. |
| `test_the_api_list_is_the_catalog_less_plumbing` | X | C, same file/function row; no API-list comparison. |
| `test_the_maf_tools_are_the_tools_a_model_may_name_sorted_by_name_and_no_commit_is_among_them` | P | C, same file/function row; exact model membership, not separate order/kind derivation. |
| `test_every_surface_says_what_the_catalog_says_and_the_differences_are_the_declared_ones` | P | C, same file/function row; model description/schema comparison only. |
| `test_the_one_declared_wording_difference_is_the_write_sentence` | X | C, same file/function row; no cross-surface wording matrix. |
| `test_a_model_is_shown_the_catalogs_schema_less_exactly_what_the_reader_owns` | P | C, same file/function row; pinned model schema, not independently recomputed reader-owned projection. |
| `test_behaviour_hints_follow_the_kind_and_nothing_else` | X | C, same file/function row; no MCP hint/kind matrix. |
| `test_the_portals_intents_run_catalog_tools_and_the_parity_cases_name_real_ones` | X | C, same file/function row; no portal intent matrix. |

### test_parity_figures.py

| Source function | Status | .NET evidence / exact limit |
|---|---|---|
| `test_the_matrix_covers_what_the_brief_asks_and_every_gap_says_why` | X | C, same file/function row; no complete cross-surface parity matrix. |
| `test_every_door_returns_the_same_envelope` | X | C, same file/function row; transport retention is not all-door equality. |
| `test_a_capped_result_says_so_and_an_employee_result_travels_in_the_persons_lane` | P | C, same file/function row; model-row cap and person projection, not source query truncation metadata parity. |
| `test_the_text_cowork_reads_is_the_platforms_blocks_and_no_other_number` | X | C, same file/function row; no MCP text proof. |
| `test_a_teams_turn_shows_the_platforms_blocks_and_the_engines_figures_only` | P | C, same file/function row; local synthetic envelope/pipeline, not real engine-backed REST parity. |
| `test_an_unnamed_method_runs_both_certified_methods_and_each_is_the_rest_answer` | P | C, same file/function row; two calls/path isolation, not real REST equality. |
| `test_a_model_is_shown_the_names_of_the_persons_rows_and_never_the_rows` | E | C, same file/function row; synthetic person envelope. |
| `test_the_portal_shows_the_same_blocks_and_facts_and_tells_its_narrators_only_those_figures` | X | C, same file/function row; no portal evidence-event/narrator parity. |
| `test_a_prepared_write_changes_nothing_on_any_door` | P | C, same file/function row; actual SDK/fake gateway preview, not every door or real repository. |
| `test_a_door_that_changes_one_figure_fails_the_check` | P | C, same file/function row; local forged-block/final-output negative controls, not adapter-liar matrix. |
| `test_a_portal_pipeline_that_adds_up_figures_of_its_own_fails_the_check` | X | C, same file/function row; no portal mutation negative control. |

## Machine-checking the index

Run this read-only PowerShell check from the repository root. Section headings
provide the file part of each key; only source-function table rows are counted.
The check rejects a missing, extra or duplicate pair instead of treating a
matching total as sufficient.

```powershell
$spec = Get-Content contract\docs\ORCHESTRATOR-SPEC.md -Raw
$map = Get-Content dotnet\docs\orchestrator-spec-traceability.md -Raw
$sections = '(?ms)^### ([^\r\n]+)\r?\n(.*?)(?=^### |^## |\z)'
$expected = @()
foreach ($section in [regex]::Matches($spec, $sections)) {
    foreach ($name in [regex]::Matches($section.Groups[2].Value, '(?m)^- `(test_[^`]+)`')) {
        $expected += $section.Groups[1].Value + '::' + $name.Groups[1].Value
    }
}
$actual = @()
$statuses = @()
foreach ($section in [regex]::Matches($map, $sections)) {
    foreach ($row in [regex]::Matches($section.Groups[2].Value, '(?m)^\| `(test_[^`]+)` \| (E|P|U|X) \|')) {
        $actual += $section.Groups[1].Value + '::' + $row.Groups[1].Value
        $statuses += $row.Groups[2].Value
    }
}
$duplicates = @($actual | Group-Object | Where-Object Count -ne 1)
$difference = @(Compare-Object ($expected | Sort-Object) ($actual | Sort-Object))
if ($expected.Count -ne 313 -or $actual.Count -ne 313 -or $duplicates.Count -or $difference.Count) {
    throw 'Named guarantee index is incomplete, duplicated or stale.'
}
$statuses | Group-Object | Sort-Object Name | Select-Object Name, Count
```

Direct method references and the C/W referenced rows were checked against
existing test files when this index was assembled. E/P status is limited to the
assertions described; an unverified functional or operational guarantee remains
unverified even when a related test passes.
