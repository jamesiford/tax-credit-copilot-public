# backend/

The Python backend: the calculation engine, the use cases around it, the HTTP API, the Microsoft 365 channel
gateway and the adapters to Fabric, Foundry and storage. Run and test commands are in the repository
[README](../README.md); the target design is [TARGET-ARCHITECTURE.md](../docs/architecture/TARGET-ARCHITECTURE.md).

## Dependency direction

```
presentation  (api/, channel/, main.py)  ->  application/  ->  domain/
infrastructure/  implements the ports that application/ and domain/ declare
bootstrap/       composes: it is the only package that names an adapter, and nothing imports it
```

Dependencies point inward. `domain` imports the standard library and its own siblings and nothing else (no
framework, no I/O, no async). `application` imports `domain` and never `infrastructure`, a web framework or an
Azure SDK. `infrastructure` imports the ports, not the use cases. Routers translate HTTP and send a request through
the mediator; they name no adapter. A write is a command (Authorization -> Validation -> Handler -> Audit); a read is
a query.

## Folder map

| Folder | What lives there |
| --- | --- |
| `domain/` | Entities, value objects, ports and the pure calculation (`domain/calculation/`: the One/Zero methods, headcount, floors, fiscal windows, credit streams). Pure and deterministic, which is what keeps the parity gate a fast unit test. |
| `application/` | Use cases. `commands/` and `queries/` (one use case per file), the mediator, the capability catalog (`capabilities/`, the only source of tool names, schemas and kinds), the numeric guard and composer (`numeric/`, `composer/`), the knowledge port (`knowledge/`), the data service (`data/`), model-facing ports (`ai/`), and the ports Gold reads go through. |
| `infrastructure/` | Adapters behind the ports: `persistence/` (the Fabric Warehouse, SQLite and Gold reads), `payroll/` (the Lakehouse and fiscal-window sources), `ai/` (the model providers; the only place an AI SDK is imported), `auth/`, `storage/` (Blob). |
| `api/` | The portal's FastAPI routers (`api/chat/` the chat pipeline). Thin: parse, dispatch through the mediator, shape the response. The routes are pinned by `tests/route_inventory.json`. |
| `channel/` | The channel gateway, a second FastAPI app (`channel.main:app`): authentication, per-user audit, rate limit, writer check, the hand-written MCP facade (`mcp.py`) and the fact ledger around every capability call. It holds no business rule. |
| `agents/` | The agent roster (`agents.json`), one display profile per agent and the prompt files (`agents/prompts/`). Agents narrate; none holds a tool. |
| `rules/` | Statute as data: `rules/<program>/<year>.json` materialised rule packs, the flat per-programme files, and `rules/methodology/` (the immutable assumption sets and the certified-figures copy). |
| `bootstrap/` | The composition root: the `*_wiring.py` modules choose an adapter for each port (stores, AI, auth, data, artifacts, channel). The outermost ring. |
| `tools/` | Deterministic compute and services around the core: rule loading, the reference runners, trail recording, portfolio assembly, simulation, grid filters and the code-standards ratchet. It is **not** the developer-tooling folder the name suggests and is not renamed (D-143, F-42): it holds the statutory math and the calculation trail, which is the audit boundary. It never imports `api/`. |
| `data/` | Source readers (Lakehouse, Fabric, CSV fixture), the synthetic client generators used by tests and the public profile's load (`data/source/synth.py`), and ingested rule configuration. Not a layer: `domain` imports nothing from it. |
| `tests/` | The parity gates, the architecture tests, the endpoint contracts, and the channel, gateway and orchestrator suites (`tests/channel/`, `tests/channel_orchestrator/`). |

Root files: `main.py` (the API's ASGI entry), `config.py` and `config_sections.py` (typed `Settings`, the only reader
of the process environment), `telemetry.py`, `startup.sh` and `startup-channel.sh` (gunicorn launchers for the two apps),
`Dockerfile`, `.webappignore` (what the zip leaves out), `requirements*.txt`, `.env.example`.

## The architecture tests that enforce it

| Rule | Test |
| --- | --- |
| The domain is pure and imports nothing outward; tools, infrastructure and application import no router; the tenant predicate rule for Warehouse adapters | `tests/test_architecture.py` |
| The ring: nothing inside points outward, and `bootstrap/` is the only package that names an adapter | `tests/test_architecture_layers.py` |
| Routers name no adapter and route every request through the mediator | `tests/test_architecture_routers.py` |
| `backend/config.py` is the only reader of `os.environ` / `os.getenv` | `tests/test_architecture_settings.py` |
| One calculation, many adapters: tool names, schemas and descriptions exist only in the capability catalog | `tests/test_architecture_catalog_only.py`, `tests/test_architecture_adapters.py` |
| Where an Agent and where a Workflow may be used; no executor or tool body computes a figure | `tests/test_architecture_patterns.py` |
| Package grouping of `application/` and the fixture boundary | `tests/test_architecture_application_groups.py`, `tests/test_architecture_fixtures.py` |
| Modules, classes, functions, complexity and arguments stay within the standards, as a ratchet | `tests/test_code_standards.py` (`python scripts/code-standards.py --update` tightens it) |
| This map is complete | `tests/test_architecture_backend_map.py` |

The reference dataset must keep producing 10,236 employees, 539 Min-Max eligible and 656 Pay Period eligible
(`tests/test_engine_parity_reference.py`); never edit the pinned constants to make a change pass.
