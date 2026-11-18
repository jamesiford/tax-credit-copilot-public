# Runbook: standing the app up behind private link, with your own identity

For a developer or platform engineer who has to run the application against a Fabric lakehouse that is reached over private
link, and (optionally) an Azure SQL operational store. Every value in `<angle brackets>` is yours to supply. Commands are for
Windows PowerShell and are safe to copy. Nothing here contains a secret, a token or a connection string with a credential.

Related: [CONNECTIVITY-MATRIX.md](CONNECTIVITY-MATRIX.md) (what talks to what), [ENV-VARS.md](ENV-VARS.md) (every setting),
[SOURCE-MAPPING.md](SOURCE-MAPPING.md) (a source with a different table or column shape),
[ADR-011](ADR-011-azure-sql-operational-store.md) (Azure SQL).

## 1. Prerequisites

| Need | Check |
|---|---|
| Python 3.12 or later | `python --version` |
| Node 24 (the web tier's runtime; the frontend builds and tests on it) | `node --version` |
| **ODBC Driver 18 for SQL Server.** The `pyodbc` wheel alone is not enough: it needs the driver installed on the machine | `Get-OdbcDriver -Name "ODBC Driver 18 for SQL Server"`; none listed means install it from Microsoft |
| Azure CLI | `az --version` |
| Network path to the private names (VPN or a jumpbox that resolves the private zone) | section 3 |

Failure looks like: `pyodbc.InterfaceError ... Data source name not found and no default driver specified` (no driver), or a
connection that times out on every call (no network path).

## 2. Identity

The app uses `DefaultAzureCredential` through one shared credential. Locally that resolves to your `az login`.

```powershell
az login --tenant <tenant-id>
az account set --subscription <subscription-id>
az account show --query "{tenant:tenantId, subscription:id, user:user.name}" -o table
az ad signed-in-user show --query "{name:displayName, upn:userPrincipalName, objectId:id}" -o table
```

- **Set `ENVIRONMENT=local`.** The shared credential then skips the managed-identity probe, which otherwise makes the first read
  wait minutes for an endpoint that does not exist on a laptop. To force a credential, set `AZURE_TOKEN_CREDENTIALS` to `dev`,
  `prod` or one credential name (`AzureCliCredential`).
- **The Fabric workspace role must be held by this identity**, the one `az account show` prints, in the tenant that owns the
  workspace. A role granted to a colleague, or to the same person in another tenant, fails with a 403 that reads like a network
  problem.
- Confirm a token can be issued for each audience you will use:

```powershell
az account get-access-token --resource https://storage.azure.com/ --query expiresOn -o tsv        # OneLake
az account get-access-token --resource https://database.windows.net/ --query expiresOn -o tsv     # SQL endpoints, Azure SQL
```

## 3. Private link at the Fabric workspace level

With workspace-level private link, Fabric **denies the public host** for that workspace (`403 DeniedByPolicy: Private link
validation failed`) and does not translate the public name into the private one. You address the workspace-specific host
yourself.

The host is built from the workspace id, with the dashes removed:

```
<workspaceid-no-dashes>.z<first two characters of the workspace id>.blob.fabric.microsoft.com
```

The same stem exists with `.dfs.` and for the SQL endpoint. For a workspace id `aabbccdd-...` the stem is `aabbccdd....zaa`.

1. **DNS.** From the machine that will run the app:
   ```powershell
   nslookup <workspaceid-no-dashes>.z<xy>.blob.fabric.microsoft.com
   ```
   A **private address** (for example `10.x.x.x`) is correct. A public address means the private DNS zone is not linked to
   your network, or you are not on the VPN. Fix that before anything else; no setting in the app can compensate.
2. **Point the app at it** (`backend/.env`):
   ```
   ONELAKE_ENDPOINT=https://<workspaceid-no-dashes>.z<xy>.blob.fabric.microsoft.com
   ONELAKE_PATH_STYLE=name
   ```
   `name` addresses `<workspace-name>` and `<lakehouse>.Lakehouse`. Use `guid` if your platform team addresses by ids; then
   `FABRIC_WORKSPACE` is the workspace id and `FABRIC_LAKEHOUSE` the lakehouse item id.
3. **Use the blob host, not dfs.** The Delta reader lists files through the Blob API; a `.dfs.` host answers `400
   IncorrectEndpointError: Operation not supported on the specified endpoint`.

## 4. Workspace roles and permissions

| Role / setting | What it allows |
|---|---|
| Workspace **Contributor** (or Member, Admin) | Read OneLake files, which the row-level payroll read needs today |
| Workspace **Viewer** | Only the SQL analytics endpoint, with object-level `SELECT` you grant; **no file access** |
| Tenant setting "Users can access data stored in OneLake with apps external to Fabric" | Required for any app outside Fabric to open OneLake |
| OneLake data access roles | Optional, narrower than workspace roles; inspect them if a Contributor still gets a 403 |

Template request to the Fabric administrator:

> Please grant `<identity>` the **Contributor** role on workspace `<workspace-name>` (`<workspace-id>`), confirm the tenant
> setting that allows apps external to Fabric to access OneLake is enabled for `<security group>`, and confirm the workspace's
> private link allows blob access from `<network range>`. For the SQL endpoint we need `SELECT` on the source tables only.

Failure looks like: `403 User is not authorized ... workspace ... artifact` (role missing, or held by another identity).

## 5. Configuration

`backend/.env` (copy `backend/.env.example`; address-like values are commented out there). A worked example:

```
ENVIRONMENT=local
DATA_SOURCE=lakehouse
DATA_CLASSIFICATION=customer
FABRIC_WORKSPACE=<workspace-name>
FABRIC_LAKEHOUSE=<lakehouse-name>
SOURCE_SCHEMA=<schema>                  # blank means a lakehouse with no schemas
ONELAKE_ENDPOINT=https://<workspaceid-no-dashes>.z<xy>.blob.fabric.microsoft.com
SOURCE_MAPPING_FILE=<path to your mapping file>   # when the tables or columns differ from the default
LAKEHOUSE_SQL_SERVER=<sql-endpoint-host>          # the lakehouse's own host
LAKEHOUSE_SQL_DATABASE=<lakehouse-name>
CLAIM_STORE=warehouse                  # or leave the local defaults for a development run
WAREHOUSE_SERVER=<warehouse-or-azure-sql-host>
WAREHOUSE_DATABASE=<database>
TELEMETRY_ENABLED=false
```

- **An inherited OS environment variable overrides `.env`.** If a value "does not take", check
  `Get-ChildItem Env: | Where-Object Name -like "FABRIC*"` and clear it with `Remove-Item Env:<NAME>`.
- `DATA_CLASSIFICATION=customer` makes pay-code mapping strict: nothing calculates until the codes are mapped
  ([APP-OWNED-LOOKUPS.md](APP-OWNED-LOOKUPS.md)).
- Restart the backend after any change; it does not reload.

## 6. The access check

```powershell
python scripts/check-onelake-access.py --table Account
python scripts/check-onelake-access.py --probe-layout       # tries the schema-enabled and flat layouts
python scripts/validate-source-schema.py                    # the source against the mapping in force
```

`check-onelake-access.py` prints the host it will call, whether the name resolves to a private address, whether a token can be
acquired (never shown), and the Delta version and file count of one small table. Each step is `ok` or `FAIL` with what it
usually means. Exit 0 only when every step passed. `--probe-layout` sets `SOURCE_SCHEMA` for you: the layout that opens is the
one to use. `validate-source-schema.py` exits 0 when every required column resolves; warnings name optional tables or columns
that are absent (they read as empty) and unused columns.

## 7. Azure SQL as the operational store

Skip this unless `WAREHOUSE_PLATFORM=azure_sql`. See [ADR-011](ADR-011-azure-sql-operational-store.md).

1. **Server and database** exist; note the server FQDN (`<server>.database.windows.net`) and the database name.
2. **An Entra admin** (a group) is set on the server, and Entra-only authentication is on.
3. **Network:** a firewall rule for your address, or a private endpoint and its DNS zone (`privatelink.database.windows.net`).
   `nslookup <server>.database.windows.net` must return the private address when a private endpoint is used.
4. **Token check:** `az account get-access-token --resource https://database.windows.net/ --query expiresOn -o tsv`.
5. **Settings:** `WAREHOUSE_PLATFORM=azure_sql`, `WAREHOUSE_SERVER=<server>.database.windows.net`, `WAREHOUSE_DATABASE=<database>`,
   and for the guarded scripts `SQL_SERVER_FQDN` and `SQL_DATABASE_NAME` (the same values, stated independently).
6. **Create users** (run by the Entra admin; no logins, no passwords):
   ```powershell
   python scripts/grant-sql.py --platform azure_sql --target deployed --principal <api-identity-name> --dry-run
   python scripts/grant-sql.py --platform azure_sql --target deployed --principal <api-identity-name>
   ```
7. **Load the schema with the migration tool, never by hand:**
   ```powershell
   $env:SQL_CREATED = "true"      # only on a database nothing has been loaded into
   python scripts/apply-migrations.py --target deployed --bootstrap
   Remove-Item Env:SQL_CREATED
   python scripts/apply-migrations.py --target deployed          # must report 0 pending
   ```
8. **Check:** `python scripts/check-operational-store.py` prints `ok`, or the first problem and its remedy.

Failure looks like: `Login failed for user '<token-identified principal>'` (the user was not created from the external
provider), `Cannot open server ... requested by the login. Client with IP address ... is not allowed` (firewall or private
endpoint), `GUARD REFUSED` (the configured server or database is not the one allowed).

## 8. Telemetry

Switch it off for a local run: `TELEMETRY_ENABLED=false`. To use it, the Application Insights resource needs Entra
authentication on, and the identity the app runs as needs **Monitoring Metrics Publisher** on that resource. Role assignments can
take up to 15 minutes to propagate. A `403 Forbidden` from the exporter means one of those is missing, or the app is running as a
different identity than you granted. The startup log says whether the connection string came from the environment.

## 9. Running the backend and frontend locally

```powershell
cd backend ; python -m venv .venv ; .\.venv\Scripts\Activate.ps1 ; pip install -r requirements.txt
python -m uvicorn main:app --port 8000
# in a second terminal
cd frontend ; npm install --legacy-peer-deps ; npm run dev       # http://localhost:5173, /api proxied to 127.0.0.1:8000
```

Keep `VITE_API_BASE` unset so the page calls the local API. **A deployed API returns 403 to a direct call from your machine:**
it accepts only the web app's subnet and an Entra token. Browse through the deployed web app, or run the API locally.

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `403 DeniedByPolicy: Private link validation failed` | The public host was used for a private-link workspace | Set `ONELAKE_ENDPOINT` to the workspace-specific blob host (section 3) |
| `403 User is not authorized ... workspace ... artifact` | The identity has no workspace role, or the role is held by another identity | Section 2 and 4: check `az account show`, then request the role |
| `400 IncorrectEndpointError: Operation not supported on the specified endpoint` | A `.dfs.` host where the blob host is needed | Use `.blob.` |
| "Workspace unavailable: Reference workspace inputs missing One.csv ..." | The sealed reference views need the partner extract, which is not in this checkout | Expected without the extract; the other pages are unaffected. Set `REFERENCE_ACCOUNT_ID` only for a client you hold |
| "Opening the calculation workspace" never finishes | The sealed run cannot be built, or the source read is slow | Check `/api/workspace`: it answers `available: false` with a reason and a remedy; check the source (section 6) |
| `DefaultAzureCredential failed to retrieve a token`, or a multi-minute wait on the first call | A chain credential waiting on a managed-identity endpoint | `ENVIRONMENT=local`; `az login`; or `AZURE_TOKEN_CREDENTIALS=AzureCliCredential` |
| Application Insights exporter `403 Forbidden` | Entra auth off on the resource, role missing, or wrong identity | Section 8, or `TELEMETRY_ENABLED=false` |
| "invalid object name" / table not found | A table-name difference (prefix, case, or a name map) | `SOURCE_TABLE_PREFIX`, `SOURCE_TABLE_CASE`, `SOURCE_TABLE_MAP` or a mapping file; `validate-source-schema.py` names the table |
| Looks like a missing lakehouse; every read times out | The Fabric capacity is paused | Resume it in the Azure portal; wait for it to become Active |
| `/api/v2/portfolio` fails, or the book is empty, or has no figures | The claims store is unreachable, `tcc_ops` is missing or not migrated, store settings are mixed, or the server name is a placeholder | See below |
| `Login failed` / firewall errors against Azure SQL | User not created, or no network path | Section 7 |

**The portfolio and the claims store.** There is deliberately no fallback to the lakehouse for claims: a figure that came from
the wrong place is worse than a figure that is missing. When the claims store cannot be read, `GET /api/v2/portfolio` still
answers 200 with the book's clients **without figures**, and a `degraded` list names each dependency that failed, why, and the
remedy; the page shows a banner, and an affected client reads "unavailable", never "not assessed". `GET /api/ready` lists the
operational stores under `stores` (it reports them but does not flip `ready`), and
`python scripts/check-operational-store.py` prints the first problem with its remedy: a placeholder or missing server, a missing
`tcc_ops.schema_migration`, a missing claim table, pending migrations, or a missing grant. A monitor that watches status codes
will not see this; watch `/api/ready` and the `degraded` list.

## 11. What is verified and what is not

Exercised offline by the test suite: the endpoint redirect (against a local HTTP server and the real Delta library), every
combination of the table-name settings, a source missing optional tables, the portfolio under each failure state, the mapping
and its validation, the migration and grant statements for Azure SQL, and the Terraform module under mock providers.

**Not exercised here, and needing your environment:** private DNS and a real token; a real private blob host and real Delta
tables; whether the GUID path form matches your platform's working one; whether `HAS_PERMS_BY_NAME` answers on your SQL endpoint;
that Entra authentication is on for Application Insights; and every step of section 7 against a real Azure SQL database.
