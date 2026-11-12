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

### Changed

- A blank or unset `DATA_SOURCE` now resolves to `lakehouse` everywhere (the reference workspace used to treat blank as the local CSV fixture and failed with "Reference workspace inputs missing"). Set `DATA_SOURCE=csv` explicitly for the local test fixture. If the source is the lakehouse but `FABRIC_WORKSPACE` and `FABRIC_LAKEHOUSE` are not set, the API now answers `503` with a body naming the dependency and the settings to set (typed error `SourceNotConfigured`).
- With `ENVIRONMENT=local` (the default) the Azure credential no longer includes the managed-identity probe, which removes the long wait on a developer machine. Deployed behaviour (managed identity selected by `AZURE_CLIENT_ID`) is unchanged. To restore the probe locally set `AZURE_TOKEN_CREDENTIALS=managedidentitycredential`.
### Deprecated

### Removed

### Fixed

### Security
