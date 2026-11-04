# channel_orchestrator

The Foundry hosted agent behind the Microsoft 365 channel: Teams and Copilot Chat in, the platform's own
figures out. Read [docs/m365-channel/ORCHESTRATOR.md](../docs/m365-channel/ORCHESTRATOR.md) first; this file
is the working notes.

## Folder map

```
main.py                  zip-root entry point: imports app.main and calls main(). Nothing else (see "Two main.py files")
azure.yaml               the agent's declarative definition for azd (entryPoint, protocols, env)
Dockerfile               the container path (COPY main.py + app, CMD python main.py)
requirements.txt         what the zip and the image install
app/
  main.py                the seam: the one Responses handler, and the only module that imports a hosting package
  host.py                what that handler decides: identity, /whoami, /netcheck, /modelprobe, hand-off to the turn
  wiring.py              composition: settings in, a TurnPipeline out
  vendor/tcc_shared/     the platform's shared modules, copied verbatim by scripts/vendor-orchestrator.py (generated, gitignored)
  core/                  everything else; framework-free unless the file is named maf_*
    turn, planned, planner, degraded, compose, replies, prompts
                         one turn end to end: attribute, decide, run, compose, audit; the words the orchestrator writes itself;
                         the degraded (no-model) planners
    tools, toolset, reader_arguments, writes, state, review_pack
                         the turn's tool state, what a model may name, the reader's words settling client / year / method,
                         the confirm-a-change words and the one commit call, per-conversation state, what asks for the review pack
    identity, gateway_client, settings, audit, telemetry
                         who is asking, the one outbound dependency (the channel gateway), configuration, the narration
                         report, spans that carry no payroll
    model_access, models, placeholders
                         which model path serves a turn, the provider chain and egress rule, placeholders a model can copy
    modelprobe, netcheck the two diagnostic endpoints
    maf_*                the Microsoft Agent Framework layer, the only modules that import it:
                         maf_agent (the Agent and its client), maf_catalog_tools (a FunctionTool per catalog capability),
                         maf_tool_rules + maf_tool_call + maf_tool_run (the tool rules as function middleware),
                         maf_foundry_client + maf_chat (the framework's Foundry client and what both clients share),
                         maf_write_flow + maf_write_steps (the write path as a Workflow), maf_review_pack (the review pack
                         as a Workflow), maf_knowledge (reference text as a context provider)
```

Tests are in `backend/tests/channel_orchestrator/` (goldens in `golden/`); `test_orch_folder_map.py` fails if a module
here is missing from the map above.

## Two `main.py` files

| File | Role |
| --- | --- |
| `main.py` (zip root) | Nine lines: `from app.main import main`. It exists because the source-code deployment runs `entryPoint: main.py` from the root of the uploaded zip (`azure.yaml`) and the container runs `CMD ["python", "main.py"]` with `COPY main.py ./` (Dockerfile). The two deployment paths therefore share one launcher. |
| `app/main.py` | The hosting seam: builds the Responses host, registers exactly one handler and hands everything to `app.host` and `app.wiring`. The only module in the repository that may import a hosting package. |

The root file stays. Removing it would mean changing `entryPoint` in `azure.yaml` and the Dockerfile together, and
`test_orch_hosting_seam.py` pins the pair: the root file imports `app.main` and nothing else, and `app/main.py` is the one
seam. The split is what lets the host be swapped (RM-12: the hosting package cannot serve `activity`, so it was not adopted)
without touching the entry point Teams depends on.
## Build and test

```pwsh
python scripts/vendor-orchestrator.py            # required before any build, zip or image
python scripts/vendor-orchestrator.py --check    # does the copy still match backend/?
cd backend; ..\.venv\Scripts\python.exe -m pytest tests/channel_orchestrator -q
docker build --platform linux/amd64 -t tcc-channel-orchestrator channel_orchestrator
```

Rules that fail the build (`test_orch_structure.py`): imports stay inside `app`, `application`, `domain`,
`infrastructure.ai` and four named third-party packages; only `main.py` imports the hosting package and only
the `maf_*` modules the agent framework; a commit is built in one module and called from one place; nothing logs a
token, a header or a secret; modules stay under 250 lines and functions under 40. Elsewhere,
`test_architecture_catalog_only.py` fails if anything outside the catalog defines a tool.

## Adding a tool

Nothing to add here: the orchestrator reads the platform's catalog and generates the framework tools from it
(`maf_catalog_tools`). A new read tool in `backend/application/capabilities/catalog.py` is offered to the model after
`scripts/vendor-orchestrator.py` runs again, and the gateway must offer it too. Add a golden case in
`backend/tests/channel_orchestrator/golden/`. A tool whose client, year or method are the reader's declares them by
having `client_id` / `tax_year` / `method` in its schema (`CapabilitySpec.reader_owned` is derived from it); the middleware
in `maf_tool_rules` settles them.

## Never

- Never register a `*_commit` tool, call `commit_pending` from anywhere but `turn.py`, or retry a commit.
- Never put a figure in a prompt, a record token in a message, or a credential in a log line.
- Never default a user. No identity, no turn.
