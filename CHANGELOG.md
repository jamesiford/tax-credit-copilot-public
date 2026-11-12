# Changelog

All notable changes to this project are recorded here, so changes can be followed without reading git history. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/) once it is released.

**How to use this file**

- Add an entry under `## [Unreleased]` in the same commit as the change. One line per change, in plain language.
- Use the groups `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed` and `Security`.
- Say what an operator has to do: new setting names and defaults, migrations to run, behaviour that now differs.
- Keep entries customer-neutral. This is a public repository: no customer names, hostnames or identifiers.
- Never rewrite or delete an earlier entry. If one was wrong, add a correcting entry.
- When a release is cut, rename `Unreleased` to the version and date, and start a new `Unreleased` section.

## [Unreleased]

### Added

- Typed failures (`application/errors.py`): `DependencyUnavailable(dependency, reason, remedy)` and `SourceNotConfigured`. The API turns one into a `503` whose body names the dependency, the reason and the remedy.
- `GET /api/v2/portfolio` now carries a `degraded` list (`[{dependency, impact, remedy}]`, empty when everything answered) and the portfolio page shows a banner for it. Dependencies named: `claims_store`, `source_lakehouse`, `source_sql`, `rule_packs`. An empty claims table is still normal (every client reads as not yet assessed); an unreachable or uninitialised store is degraded.
- Operational-store readiness: `/api/ready` carries a `stores` object, the startup log states the first problem with its remedy, and `scripts/check-operational-store.py` verifies connectivity, the `tcc_ops` schema and migration table, pending migrations and grants. Settings that are probably mistakes (a placeholder-looking server name, SQLite stores while a warehouse is configured) are warned about. `/api/ready` never turns `ready` false for a store problem.
- `TELEMETRY_ENABLED` (default: on only when `APPLICATIONINSIGHTS_CONNECTION_STRING` is set). An empty connection string disables telemetry; the startup log says whether the value came from `.env` or an OS variable (an OS variable overrides `.env`). A refused export (403) logs one warning with the likely causes instead of repeating.
- `SOURCE_FALLBACK=delta` (default unset): opt-in fallback of a client's fiscal-rules read from SQL to a bounded lakehouse read.
- `CHANGELOG.md`: this file.
- `infrastructure/azure_credential.py`: one shared Azure credential (and a token cache) used by every backend component that talks to Azure. New optional setting `AZURE_TOKEN_CREDENTIALS` (`dev`, `prod` or one credential name, as accepted by `azure-identity`) is honoured when set.
- `ONELAKE_ENDPOINT` (default unset): the workspace-specific private-link **blob** host (`https://<workspaceid-no-dashes>.z<xy>.blob.fabric.microsoft.com`) for a workspace that blocks public access. `ONELAKE_PATH_STYLE=name|guid` (default `name`) selects name-based or GUID-based OneLake paths. One shared builder (`data/source/onelake.py`) now serves the reader and the writer.
- `scripts/check-onelake-access.py`: prints the host it will call, checks DNS (flags a public address), gets a token (never shown), opens one small Delta table and explains the usual errors (`DeniedByPolicy`, `403`, `IncorrectEndpointError`).
- Interim source table-name settings: `SOURCE_TABLE_PREFIX` (default empty), `SOURCE_TABLE_CASE=as_is|lower|upper` (default `as_is`) and `SOURCE_TABLE_MAP` (JSON object, logical to physical name; wins over prefix and case). Applied to the Delta paths and to every SQL statement in `source_sql.py`. A later release replaces these with the full data-model mapping.

### Changed

- **Silent fallbacks removed.** A client's fiscal rules no longer fall from a failing SQL read to the ten-table Delta load (every payroll row, about 132 s cold at demo size); a failure is logged and the window is the flagged calendar-year assumption, unless `SOURCE_FALLBACK=delta` is set (then a bounded read of `Entity` and `EntityFiscalYearRules`). The client book, the payroll footprint and the rule-pack reader no longer swallow every exception: an outage is a typed failure reported as `degraded`, and a bug in our own code now propagates instead of being shown as an empty page. A failed footprint scan is not retried for 60 seconds. An unconfigured lakehouse source is now reported as `source_lakehouse` degraded rather than as an empty client book. **Operators:** read the `degraded` list or the banner; nothing is read from another store for claims, engagements, findings or manifests.
- `backend/.env.example` is rewritten in sections, with every address-like placeholder commented out so leaving it cannot cause a connection attempt.
- The portal now opens when the certified reference run is not available (the source holds no reference client, account 1001, or the run cannot be built). `GET /api/workspace` and `POST /api/workspace/refresh` answer `200` with `available: false`, the reason and the remedy instead of an error, and the three views tied to the sealed run (Audit trail, Back-test, Calculations) say so; every other view reads the data that is present. A source that is not configured at all is still a `503` naming the settings to set.
- A source lakehouse that lacks the `PayFrequency`, `EntityFiscalYearRules` or `Employment` tables now loads: an absent optional table is read as "no rows", logged once with its consequence, and recorded on the dataset (`missing_tables`). A missing `EntityFiscalYearRules` keeps the flagged calendar-year assumption for the fiscal window; a missing `PayCode` table is still an error; a table that exists but cannot be read still raises.
- A blank or unset `DATA_SOURCE` now resolves to `lakehouse` everywhere (the reference workspace used to treat blank as the local CSV fixture and failed with "Reference workspace inputs missing"). Set `DATA_SOURCE=csv` explicitly for the local test fixture. If the source is the lakehouse but `FABRIC_WORKSPACE` and `FABRIC_LAKEHOUSE` are not set, the API now answers `503` with a body naming the dependency and the settings to set (typed error `SourceNotConfigured`).
- `SOURCE_SCHEMA` may now be set to an empty value, meaning a lakehouse that is not schema-enabled (`Tables/<table>`, and `[lakehouse]..[table]` in SQL). **A `SOURCE_SCHEMA=` line that is present but blank used to mean the default `tcc_source`; it now means no schema.** Remove the line (or set the name) if you want the default.
- With `ENVIRONMENT=local` (the default) the Azure credential no longer includes the managed-identity probe, which removes the long wait on a developer machine. Deployed behaviour (managed identity selected by `AZURE_CLIENT_ID`) is unchanged. To restore the probe locally set `AZURE_TOKEN_CREDENTIALS=managedidentitycredential`.
### Deprecated

### Removed

### Fixed

### Security

