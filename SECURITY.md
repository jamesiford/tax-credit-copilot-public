# Security

## Reporting a vulnerability

**Do not report security vulnerabilities through public GitHub issues.**

Report them to the Microsoft Security Response Center (MSRC) at
[https://msrc.microsoft.com/create-report](https://aka.ms/opensource/security/create-report),
or by email to [secure@microsoft.com](mailto:secure@microsoft.com). If possible,
encrypt with the [PGP key](https://aka.ms/opensource/security/pgpkey).

Include as much of the following as you can: the type of issue, the file paths
involved, the location of the affected source, any special configuration
required to reproduce, step-by-step reproduction instructions, proof-of-concept
code if you have it, and the impact as you see it.

More at [aka.ms/opensource/security/policy](https://aka.ms/opensource/security/policy).

## Security posture

Stated plainly so nobody has to infer it from the code. **This software has not
been through an independent security review. Do not connect it to real payroll
data until you have reviewed it against your own requirements.**

| Area | State today | Needed before production |
| --- | --- | --- |
| **Authentication** | `AUTH_MODE=entra`: Easy Auth on the web app, and the API validates every bearer token (issuer, audience, scope and the `TCC.User` app role) in `backend/api/auth.py`. Network position alone is never trusted. The `public` profile runs `AUTH_MODE=none` with synthetic data only; the API **refuses to start** with `none` when `DATA_CLASSIFICATION=customer` outside local development (`backend/application/deployment.py`) | The customer's two app registrations. Entra mode is unit-tested; it has not yet been exercised end to end in a deployed environment |
| **Authorization** | Every client id named in a path, query or JSON body is checked by the request guard before the route runs. The deployed entitlement is `AllClientsAuthorizer`: any `TCC.User` may act on every client | A per-user client entitlement source behind the same `ClientAuthorizer` port, if analysts must be restricted to some clients |
| **Tenant isolation in the store** | Every Warehouse statement binds `client_id` as its first predicate (`tenant_sql.py`); `tests/test_architecture.py` fails the build otherwise | Unchanged |
| **Ingress** | The API accepts traffic only from the web app's integration subnet (access restriction, default deny); a direct call returns 403. The web app is public in the `public` profile; the `enterprise` profile chooses an access restriction or a private endpoint | Per the customer's network design |
| **CORS** | The API allows any origin (`backend/main.py`), but browsers never reach it: the web app's server proxies `/api` on the same origin | Restrict to the web origin if the API is ever exposed directly |
| **Secrets** | **None.** Every dependency authenticates with a managed identity | No change — see below |
| **Downloads** | Files are streamed by the API after an authorization check; no SAS URL ever reaches a browser; every attempt is recorded in `tcc_ops.artifact_access` | Unchanged |
| **Transport** | HTTPS only, TLS 1.2 minimum, FTPS disabled, on both App Service apps | Unchanged |
| **Data at rest** | Azure platform encryption | Customer-managed keys if required by policy |

## Key Vault is optional, and off by default

Nothing in either app's environment is a secret, so a vault would hold nothing.
Terraform creates one only when `enable_key_vault = true`. Every dependency
authenticates as a user-assigned managed identity:

| Dependency | How | Key auth |
| --- | --- | --- |
| Fabric Warehouse | Workspace role + T-SQL schema grants on the API identity | Entra-only; no SQL logins |
| Fabric / OneLake | Workspace role on the API identity | — |
| Foundry | `Azure AI User` (shown as *Foundry User*), assigned by role id | Local auth disabled |
| Storage | `Storage Blob Data Contributor` on the API identity | Shared key disabled |
| Application Insights | `Monitoring Metrics Publisher` per identity | Entra-authorised ingestion |
| App Service logs | Diagnostic settings to Log Analytics | No shared key |

Application Insights ingestion passes a credential, so the InstrumentationKey in
the connection string is not sufficient on its own.

`backend/tests/test_architecture.py` fails the build if a key is reintroduced,
which is the moment to ask whether the dependency supports Entra before reaching
for a vault. Add Key Vault only when something genuinely requires a secret, such
as a third-party API that does not support Entra.
## Data handling

All payroll data committed to this repository is synthetic — see
[DISCLAIMER.md](DISCLAIMER.md) for how that is verifiable rather than asserted.

If you connect this software to real payroll data, you are responsible for its
protection, and the gaps in the table above become your gaps.

## Dependencies

Python dependencies are pinned in `backend/requirements.txt`; JavaScript
dependencies in `frontend/package-lock.json`. Neither has been through a formal
supply-chain review. Run your own scanning before deploying into your
environment.
