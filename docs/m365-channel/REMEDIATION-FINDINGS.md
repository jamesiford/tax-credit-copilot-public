# Remediation findings

Customer-neutral. Findings from the remediation run (RM) that need an owner or a framework feature, appended per work package. The run's final summary
(what was fixed, deliberately not done, residual risks, owner decisions) is written at the end of the run.

## RM-06: Microsoft Agent Framework alignment spike

Source and evidence: [MAF-ALIGNMENT.md](MAF-ALIGNMENT.md); decision [D-124](DECISIONS.md). Framework versions: core 1.24.0, foundry 1.16.0, openai 1.18.0, hosting `1.0.0b261030`, `mcp` 2.3.0.

| Id | Kind | Finding | What is missing or open | Handling |
| --- | --- | --- | --- | --- |
| F-01 | Framework | `agent-framework-foundry-hosting` has only alpha and beta releases and no Activity protocol handler (nor do `azure-ai-agentserver-core/-responses/-invocations`) | A GA hosting package; an Activity host | RM-12 is NO-GO: keep the host behind `app/main.py`. Teams works through the Responses bridge (D-100). Revisit at GA |
| F-02 | Framework | `FoundryChatClient` calls `project_client.get_openai_client()` and exposes no `base_url`; from the hosted runtime the project host did not resolve and the account's OpenAI host did (D-101) | An endpoint override on `FoundryChatClient` | RM-09: use `OpenAIChatClient` or `OpenAIChatCompletionClient` with the account host; try `FoundryChatClient` only if `/modelprobe` shows the project host resolves |
| F-03 | Framework | Function middleware never sees a call to a tool that is not registered (`_tools.py` answers "not found" first) | A middleware hook for unknown calls | RM-08: record a refused tool name (including a `*_commit`) in a `ChatMiddleware`; never register a refusing stub, which would put a commit in the model's set |
| F-04 | Framework | A mapping `input_model` is validated only for top-level `required`, `additionalProperties: false`, `enum` and primitive `type` | Full JSON-schema validation | Keep `jsonschema` against the catalog schema in a middleware step |
| F-05 | Framework | No multi-provider failover chat client | A failover client | Keep `ModelChain` for a multi-provider or customer-gateway chain only (RM-09) |
| F-06 | Framework | MAF tool approval needs a structured reply; Teams and Copilot Chat send text | An approval path for a free-text channel | Confirmation is a Workflow `request_info` whose reply our exact-word gate produces (RM-10b) |
| F-07 | Repository | The catalog does not say which arguments the reader owns (`client_id`, year keys, what-if sizes) or which tools a model may name; the orchestrator hard-codes both (`CLIENT_PLACEHOLDER`, `YEAR_KEYS`, `SCENARIO_NUMBERS`, `_NOT_FOR_MODELS`). `channel/tools.py` defines `channel_ping` by hand outside the catalog, and `channel/mcp.py` `describe()` edits descriptions of prepare and commit tools | Catalog metadata; a stated rule for the description edits | RM-07 adds the metadata and an architecture test with a named allow-list; RM-13's conformance test states the allowed description delta. **Done in RM-07 (D-125):** `CapabilitySpec.reader_owned`, `code-only`/`debug` tags, `catalog.model_schema`, `catalog.channel_description`/`behaviour_hints` and `catalog.CHANNEL_PING` replace every hand-written copy; the allowed description delta is exactly `channel_description` (a prepare tool carries `PREVIEW_SENTENCE`, a commit tool `COMMIT_SENTENCE`; the MAF tools carry the catalog's own description unchanged) |
| F-08 | Repository | D-65's blocker for the MCP SDK (handlers run away from the request that carries the token) no longer holds in `mcp` 2.3.0: `ServerRequestContext.request` carries the request's headers in stateless and stateful mode. The SDK does not bind a session to its user | A session-owner check in the SDK | RM-14: time-boxed spike; keep the facade and add a conformance test if the spike does not preserve one pipeline, user-bound sessions, error codes and the description shape |

## RM-08: tool rules as MAF middleware

Source: [MAF-ALIGNMENT.md](MAF-ALIGNMENT.md) (Outcome cells R1-R11, H7), decision [D-126](DECISIONS.md). Nothing here weakens a guarantee; two framework limits were met and worked around.

| Id | Kind | Finding | What is missing or open | Handling |
| --- | --- | --- | --- | --- |
| F-09 | Framework | `FunctionMiddlewarePipeline`, the object that runs function middleware, is not exported by `agent_framework` (only from the private `agent_framework._middleware`). Nothing public runs a function-middleware chain outside an `Agent` loop | A public way to invoke a tool through middleware without a model | The json and keyword modes (no tool-calling model) send each named tool through a one-shot `Agent` whose chat client asks for exactly that call (`maf_tool_run.OneCall`), so the same middleware runs and no private import is made. If the pipeline becomes public, `OneCall` can go |
| F-10 | Framework | The framework deep-copies an agent's `default_options`, including `additional_function_arguments`, so a per-turn object placed there is copied (here it holds an HTTP client and locks) | A way to mark a default as shared rather than copied | `ToolRunner.__deepcopy__` returns itself (a turn is an identity, and a copy would split the budget and the ledger). A per-run `function_invocation_kwargs` is not copied; the default is used so an `Agent` built per turn needs no argument at each `run` |
| F-11 | Framework | `ChatMiddleware` reaches a custom chat client only if the client's bases include `ChatMiddlewareLayer` (the built-in clients do; `PortChatClient` did not) | Documented in `ChatMiddlewareLayer`'s docstring only | `PortChatClient(FunctionInvocationLayer, ChatMiddlewareLayer, BaseChatClient)`; a test fails if the recorder is not wired |

## RM-09: the foundry provider on MAF's chat client

Source: [MAF-ALIGNMENT.md](MAF-ALIGNMENT.md) (P4, P6, G8, F-02, F-05), decision [D-127](DECISIONS.md). Nothing here weakens a guarantee.

| Id | Kind | Finding | What is missing or open | Handling |
| --- | --- | --- | --- | --- |
| F-12 | Framework | `OpenAIChatCompletionClient` takes no timeout, retry count or HTTP client; those can be set only by handing it a ready `AsyncOpenAI` (`async_client`), which needs the `openai` SDK imported in our code. The SDK defaults are a 600 s read timeout and two automatic retries | Client-level `timeout` and `max_retries` parameters | A `Deadline` chat middleware bounds each call at `AI_TOTAL_DEADLINE_SECONDS`, so the SDK's retries happen inside it; the SDK stays unimported in our code |
| F-13 | Live check owed | The framework path was verified in process only. Whether the account's OpenAI host answers the framework's request (including a `gpt-5` family deployment), whether the remote build installs `agent-framework-openai` and `openai`, and the per-turn client creation cost are unmeasured | A live run | RM-16 checklist in D-127 |
