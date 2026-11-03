# Copilot Cowork: setup, install and known gaps

How to put the Tax Credit Copilot plugin in front of people in Copilot Cowork. The plugin is built
from [`channels/cowork/`](../../channels/cowork/README.md); this page is everything around it.
Nothing here needs a secret in the repository: the OAuth client secret lives in the Microsoft
token store, and the package carries only a registration id.

## What you need first

| Need | Why |
| --- | --- |
| The channel gateway deployed and reachable over HTTPS at `https://<gateway-host>/mcp` | Cowork calls it from Microsoft's cloud, so it needs a public HTTPS address. In the demo posture the gateway is public and Entra-only; in the hardened posture Cowork is off. See [HARDENING-PLAN](../architecture/HARDENING-PLAN.md). |
| The gateway's Entra app registration, with the delegated scope `Channel.Access` | The scope Cowork's sign-in asks for. The gateway accepts a delegated token only when it carries it. |
| A person with the Cowork licence and access in the tenant | A Copilot licence and Cowork enabled for them. |
| People who may **write** on the writer list | Anyone can read; only a writer's commit is accepted. See [Who can write](#who-can-write). |

## 1. Register the OAuth client for the gateway

Cowork signs each person in with OAuth 2.0 authorisation code and PKCE, through a registration in the
Microsoft token store. Two registrations are involved, and they are easy to confuse:

- an **Entra app registration for the client** (the identity Cowork presents), and
- an **OAuth client registration in the Teams Developer Portal** that points at it and yields the
  `referenceId` the manifest needs.

### In Microsoft Entra

1. Create an app registration for the client (for example "Tax Credit Copilot Cowork client"), single
   tenant. It is not the gateway's registration.
2. Add a **Web** redirect URI `https://teams.microsoft.com/api/platform/v1.0/oAuthRedirect`. This is
   the same for every plugin.
3. Under **API permissions**, add the gateway's delegated permission `Channel.Access` and grant admin
   consent for the tenant, so no person is asked to consent.
4. Create a client secret, or use a public client (a single-page application platform) and let PKCE
   protect the exchange, if the tenant forbids secrets. Keep the value out of the repository.

### In the Teams Developer Portal

1. Open `https://dev.teams.microsoft.com/tools`, **Tools**, **OAuth client registration**, then
   **Register client** (or **New OAuth client registration**).
2. Fill in:

   | Field | Value |
   | --- | --- |
   | Registration name | `Tax Credit Copilot gateway` |
   | Base URL | `https://<gateway-host>` (the host in the manifest's `mcpServerUrl`) |
   | Restrict usage by org | **My organization only** while testing in one tenant; **Any Microsoft 365 organization** if the plugin must work across tenants |
   | Restrict usage by app | **Any Teams app**. Binding it to a specific Teams app id makes every tool call return 404 for an MCP server |
   | Client ID, Client secret | From the Entra client registration |
   | Authorization endpoint | `https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/authorize` |
   | Token endpoint and refresh endpoint | `https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token` |
   | Scope | `api://<gateway-client-id>/Channel.Access offline_access` (`offline_access` lets Cowork refresh the token) |

3. Save. Copy the **registration id**. That is `oauth_reference_id` in your overlay config. It is an
   identifier, not a secret.

## 2. Fill the overlay and build

```pwsh
Copy-Item channels\cowork\config.example.json overlays\<name>\cowork.json   # overlays/ is gitignored
# edit developer_*, gateway_mcp_url and oauth_reference_id
.venv\Scripts\python.exe scripts\build-cowork-plugin.py --config overlays\<name>\cowork.json --strict
```

`--strict` refuses any value that still looks like a placeholder. The package carries the agent icon
(`channels/branding/*.svg`, rendered to PNG in `dist/branding/`; the build renders them when absent,
needing `pip install -r scripts\requirements-icons.txt` and Cairo or Chromium, see
`channels/cowork/README.md`). Rebuild the zip whenever the icon changes: the icons are inside it. The
script prints the package's SHA-256 and each icon's hash and writes `dist\tcc-cowork-plugin.build.json`;
record them with the review. Developer, privacy and terms URLs must be HTTPS pages you own.
For a hash that never changes between builds, the app id comes from `app_id_seed`; keep the seed
stable so an update replaces the plugin instead of adding a second copy.

Optional checks with Microsoft's tools, if installed:

```pwsh
wiqd plugin validate --mode deep        # the platform's own rules, including the ASKILL codes
atk package --manifest-file <manifest.json> ...   # builds the same package with the Agents Toolkit
```

## 3. Install it for testing: Shared with me

`wiqd plugin share` places a plugin in **Shared with me**, under **Cowork**, **Sources & Skills**,
**Plugins**, without involving an admin. Provision it first, then share:

```pwsh
wiqd auth login --interactive
wiqd plugin provision
wiqd plugin package
wiqd plugin share --scope users --email <person@your-domain>
```

If you would rather not use `wiqd`, sideload the built zip for yourself with the Agents Toolkit:
`atk install --file-path dist\tcc-cowork-plugin.zip --scope Personal`, or upload it through Teams
(**Apps**, **Manage your apps**, **Upload an app**). Each person's first use of a tool opens the
OAuth sign-in once.

## 4. List it in Discover: an admin

For everyone in the tenant, an admin uploads the package: **Microsoft 365 admin center**, **Manage
apps**, **Upload custom app**, the ellipsis, **Add agent**, then the zip. The plugin then appears in
the **Discover** section of **Cowork**, **Sources & Skills**, **Plugins**. Admins can also block it, or
deploy it to named groups, with the usual allow and block lists. Org-wide listing is the admin's
decision and nothing here automates it.

## Who can write

Reads are open to any signed-in person the platform admits. A change needs the person to be on the
writer list, checked by the gateway and again by the API. Manage the list with
`scripts/channel-writers.py` (see the [runbook](../architecture/RUNBOOK.md)). A person who is not on
it can still run both workflows' read-only parts; their commit is refused and audited as `refused`.

## How Cowork is identified, and what is audited

Cowork sends `User-Agent: copilot-cowork/1.0` and a `clientInfo` of `copilot-cowork` on
`initialize`. It never carries a user, tenant or conversation id there, so the gateway does not rely
on it. The person is the delegated token's subject, the audit row's `channel` is `cowork` and
`identity_assurance` is `delegated`, and the MCP session id is the conversation id the figure check
and the audit share. `GET /api/audit/channel?user_oid=<oid>` and `scripts/channel-audit.py` show one
person's events.

Tool annotations: every read is `readOnlyHint: true`; every commit is `destructiveHint: true`; a
preview is neither, so Cowork prompts before it too. That is a second confirmation in front of the
skill's own, and is deliberate. Annotation-driven prompts for non-Microsoft servers are still rolling
out, so the skills do not rely on them: the confirmation is the skill's rule and the server's token.

## Known gaps

- **Cowork's model composes the answer.** The skills tell it to quote verbatim and `verify_figures`
  checks a draft against the conversation's results, but a model can still reword text between a tool
  result and a document. Exact wording is guaranteed by the hosted orchestrator (Teams and Copilot
  Chat), not here. Say so in any demo.
- **The figure check is per process.** It knows only the results this gateway process returned to this
  conversation. A restart or a second instance forgets them, and a figure that cannot be traced is
  reported, never waved through. See [KNOWN-LIMITATIONS](KNOWN-LIMITATIONS.md).
- **The author supplies the reader's own numbers.** Dates, counts of emails found and slide numbers
  are not engine facts, so the skills pass them as `allowed_context`. A model that omits one gets a
  failed check and fixes the draft; it cannot talk its way past it.
- **Information Barriers.** Microsoft Purview Information Barriers are not supported for plugin or
  skill management. In a tenant where they are on, embedded knowledge file uploads are blocked
  tenant-wide, which blocks uploading or publishing a plugin that carries skills.
- **No async runs from chat.** A calculation run is not started from Cowork; the tools read recorded
  or warm results. A client-year nobody has calculated says `not_calculated`.
- **Download links.** A claim package link is single use, bound to the person, and expires in minutes.
  Cowork must give it to the person as returned; a link pasted later is refused.
- **Cowork mobile and Copilot Chat.** Custom plugins are not supported in Cowork on mobile. Omitting
  the `authorization` block (dynamic client registration) works in Cowork only; this plugin uses
  `OAuthPluginVault`, which works in both.
- **A feature in motion.** The CLI is in preview and Cowork's plugin surface changes often. The build
  pins what it generates; re-read the [plugin documentation](https://learn.microsoft.com/en-us/copilot/cowork/cowork-plugin-development)
  before each release.
- **Synthetic data.** Everything the plugin returns in the demo is synthetic.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Every tool call returns 404 after sign-in | The OAuth registration is bound to a Teams app id. Set **Restrict usage by app** to **Any Teams app**. |
| Sign-in fails after the Microsoft page | The redirect URI above is missing from the Entra client registration, or admin consent for `Channel.Access` was not granted. |
| Tools list but every call says the token lacks the scope | The registration's scope omits `Channel.Access`, or the token was issued for the wrong audience. |
| "unknown session; initialise again" | The gateway restarted. Start a new request; Cowork re-initialises. |
| A commit is refused as `not_authorized` | The person is not on the writer list. |
| Upload refused with an error naming a field | The manifest holds a field the schema does not allow. Rebuild with the script; do not edit the manifest by hand. |
