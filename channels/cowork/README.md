# Copilot Cowork plugin

An M365 app package that gives Copilot Cowork two realistic workflows over the channel gateway's
`/mcp` endpoint. Nothing here is customer-specific: the committed tree holds placeholders, and a
real build takes its values from a gitignored `overlays/<name>/` folder.

```
channels/cowork/
  manifest.template.json   the app manifest (1.29, URL-only connector); {{placeholders}} only
  config.example.json      the shape of the deployment values, all placeholders
  skills/
    tcc-figures-and-writes/   the standing rules: verbatim figures, verify, two-step writes, errors, scope
    tcc-book-review/          W1  Monday book review and call plan (account and sales teams)
    tcc-client-review-pack/   W2  client credit review pack (tax consultants)
  assets/                  SVG sources of the icon mark (PNGs are drawn at build time, never committed)
scripts/build-cowork-plugin.py   render, validate, zip -> dist/tcc-cowork-plugin.zip
```

Setup, registration and install steps are in
[docs/m365-channel/COWORK-SETUP.md](../../docs/m365-channel/COWORK-SETUP.md). Read its "Known gaps"
before a demo.

## Build

```pwsh
.venv\Scripts\python.exe scripts\build-cowork-plugin.py --config overlays\<name>\cowork.json
.venv\Scripts\python.exe scripts\build-cowork-plugin.py --config channels\cowork\config.example.json   # a dry run with placeholders
.venv\Scripts\python.exe scripts\build-cowork-plugin.py --config ... --strict                          # refuse placeholder values
```

| Config key | Meaning |
| --- | --- |
| `developer_name`, `developer_website_url`, `developer_privacy_url`, `developer_terms_url` | The listing's developer block. The three URLs must be HTTPS. |
| `gateway_mcp_url` | `https://<gateway-host>/mcp`, the channel gateway's MCP endpoint. |
| `oauth_reference_id` | The OAuth client registration id created in the Teams Developer Portal (see the setup guide). It becomes `authorization.referenceId`; the secret never enters the package. |
| `app_id_seed` | Seed for the app id, a UUID v5. Same seed, same id, for every version: an update installs over the old one. Change it only to get a second, separate plugin. `app_id` overrides it with an explicit id. |
| `version`, `manifest_version`, `accent_color` | Package version (`1.0.0`), manifest `1.29` (default) or `1.28`, and `#RRGGBB`. |

Every key can also come from an environment variable `TCC_COWORK_<KEY>`, which wins over the file.

The build is reproducible: sorted entries, fixed timestamps and permissions, LF line endings, and
icons drawn deterministically. Two builds of the same inputs have the same SHA-256, which the script
prints. Keep the hash with the review record; an admin can recompute it from the sources.

`manifest_version` `1.28` adds `tools/tcc-channel-tools.json`, generated from the live catalog by the
same code that answers `tools/list`. Cowork discovers tools from the server and ignores the file; it
exists only because 1.28 requires one. Never hand-write it.

## What validation checks

Offline, on every build and in CI (`backend/tests/channel/test_cowork_package.py`):

- **Manifest.** Only keys this builder generates; a UUID id; HTTPS developer and connector URLs;
  field lengths; both icons present and the right size; `authorization.referenceId` present unless
  the type is `None`, and absent when it is; the 1.28 tool file present.
- **Skills** (the platform's ASKILL rules). Folder exists, has a `SKILL.md`, valid frontmatter,
  `name` and `description` (1-1024 characters), `name` equals the folder and is kebab-case, no
  duplicates, at most 20 companion files, 5 MB each and 10 MB in all, safe relative paths, no hidden
  files, no reserved names. Our own: the body stays under about 5,000 tokens.
- **Tools.** Every backticked tool a skill names is in `catalog.py`, is `implemented: true` and is
  offered to callers; every write appears as a `_prepare` / `_commit` pair. A skill that names an
  unknown, unbuilt or internal tool fails the build.
- **Neutrality.** No deny-listed customer term, GUID (other than the all-zero placeholder) or real
  email address in any shipped skill file.

The Microsoft tools remain the authority: run `wiqd plugin validate --mode deep` on the package, and
`atk package` to build it with the Agents Toolkit, before uploading.

## The two workflows

| Skill | Steps and the tool each uses |
| --- | --- |
| `tcc-book-review` (W1) | 1 `book_rank` (top 8) · 2 `client_resolve`, `client_situation`, `client_trend` per client · 3 Cowork's own mail, Teams and calendar (read-only) · 4 Excel call plan, Outlook **drafts**, To Do · 5 `engagement_set_prepare` then `engagement_set_commit`, one client at a time · 6 `verify_figures` over the workbook and each draft · 7 summary of what was written and what was only drafted |
| `tcc-client-review-pack` (W2) | 1 `client_resolve` · 2 `client_eligibility`, `client_trend`, `client_at_risk`, `client_discovery` (and `client_situation` for the programme and years) · 3 `simulate` for the what-ifs the user names · 4 `findings_list` · 5 `finding_resolve_prepare` then `finding_resolve_commit` per decision · 6 `claim_transition_prepare` then `claim_transition_commit` to `proposed` · 7 `calc_walkthrough` for the appendix · 8 Word briefing and a deck of at most six slides · 9 `claim_package_create_prepare`, `claim_package_create_commit`, `claim_package_link` · 10 `verify_figures` over every artifact · 11 a calendar hold with no figures |
| `tcc-figures-and-writes` | Shared rules both workflows depend on; names every tool pair and the error codes |

## What this cannot promise

Cowork's own model composes what it says and writes. The skills tell it to quote verbatim, the
tool text starts with `VERBATIM — quote figures exactly as written.`, and `verify_figures` lets it
check a draft against the conversation's results before anything is shared. That is a weaker
guarantee than the hosted orchestrator's, which assembles replies in code and rejects a figure it
cannot trace. Say so when demonstrating it.
