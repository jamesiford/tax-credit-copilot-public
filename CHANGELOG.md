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

- `CHANGELOG.md`: this file.
- `infrastructure/azure_credential.py`: one shared Azure credential (and a token cache) used by every backend component that talks to Azure. New optional setting `AZURE_TOKEN_CREDENTIALS` (`dev`, `prod` or one credential name, as accepted by `azure-identity`) is honoured when set.
- `ONELAKE_ENDPOINT` (default unset): the workspace-specific private-link **blob** host (`https://<workspaceid-no-dashes>.z<xy>.blob.fabric.microsoft.com`) for a workspace that blocks public access. `ONELAKE_PATH_STYLE=name|guid` (default `name`) selects name-based or GUID-based OneLake paths. One shared builder (`data/source/onelake.py`) now serves the reader and the writer.
- `scripts/check-onelake-access.py`: prints the host it will call, checks DNS (flags a public address), gets a token (never shown), opens one small Delta table and explains the usual errors (`DeniedByPolicy`, `403`, `IncorrectEndpointError`).
- Interim source table-name settings: `SOURCE_TABLE_PREFIX` (default empty), `SOURCE_TABLE_CASE=as_is|lower|upper` (default `as_is`) and `SOURCE_TABLE_MAP` (JSON object, logical to physical name; wins over prefix and case). Applied to the Delta paths and to every SQL statement in `source_sql.py`. A later release replaces these with the full data-model mapping.

### Changed

- A blank or unset `DATA_SOURCE` now resolves to `lakehouse` everywhere (the reference workspace used to treat blank as the local CSV fixture and failed with "Reference workspace inputs missing"). Set `DATA_SOURCE=csv` explicitly for the local test fixture. If the source is the lakehouse but `FABRIC_WORKSPACE` and `FABRIC_LAKEHOUSE` are not set, the API now answers `503` with a body naming the dependency and the settings to set (typed error `SourceNotConfigured`).
- `SOURCE_SCHEMA` may now be set to an empty value, meaning a lakehouse that is not schema-enabled (`Tables/<table>`, and `[lakehouse]..[table]` in SQL). **A `SOURCE_SCHEMA=` line that is present but blank used to mean the default `tcc_source`; it now means no schema.** Remove the line (or set the name) if you want the default.
- With `ENVIRONMENT=local` (the default) the Azure credential no longer includes the managed-identity probe, which removes the long wait on a developer machine. Deployed behaviour (managed identity selected by `AZURE_CLIENT_ID`) is unchanged. To restore the probe locally set `AZURE_TOKEN_CREDENTIALS=managedidentitycredential`.
### Deprecated

### Removed

### Fixed

### Security
