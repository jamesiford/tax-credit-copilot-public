# channel_orchestrator

The Foundry hosted agent behind the Microsoft 365 channel: Teams and Copilot Chat in, the platform's own
figures out. Read [docs/m365-channel/ORCHESTRATOR.md](../docs/m365-channel/ORCHESTRATOR.md) first; this file
is the working notes.

```
main.py              entry point at the zip root (python main.py)
app/main.py          the Responses host: one handler (the only module that imports the hosting package)
app/host.py          what the handler decides: identity, /whoami, hand-off to the turn pipeline
app/wiring.py        settings in, a TurnPipeline out
app/core/            framework-free logic: identity, state, tools (the turn), reader_arguments, planner, composer, writes, replies
app/core/maf_*.py    the Microsoft Agent Framework layer, the only modules that import it: maf_agent (the Agent and its
                     client), maf_catalog_tools (a FunctionTool per catalog capability), maf_tool_rules and
                     maf_tool_call (the turn's tool rules as function middleware), maf_tool_run (one tool through them)
app/vendor/tcc_shared/ the platform's shared modules, copied verbatim (generated; gitignored)
Dockerfile, azure.yaml, requirements.txt
```

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
