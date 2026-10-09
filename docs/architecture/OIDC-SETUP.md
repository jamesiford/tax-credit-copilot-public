# OIDC setup for `deploy.yml` (HOST-6, D23)

`deploy.yml` deploys with GitHub's OIDC token: **no Azure secret is stored in
the repository or in GitHub secrets.** It runs only on `workflow_dispatch`.
Push-to-deploy is a later, human decision.

This is a one-time setup per target environment, done by someone with rights
in the customer's Entra tenant and subscription. Nothing here is automated by
the programme.

## 1. An Entra application for the workflow

1. Create an app registration (e.g. `tcc-github-deploy-<env>`). It needs no
   client secret and no certificate.
2. Add a **federated credential**:
   - Scenario: GitHub Actions deploying Azure resources
   - Organization / repository: the repository that holds this code
   - Entity type: **Environment**, name = the GitHub environment you will pass
     as the `environment` input (e.g. `production`)
   - Audience: `api://AzureADTokenExchange`

## 2. Azure roles (resource-group scope)

On the target resource group (create it first if Terraform should not):

| Role | Why |
|---|---|
| Contributor | create and update the resources Terraform manages |
| Role Based Access Control Administrator, **constrained** to Storage Blob Data Contributor, Foundry User, Monitoring Metrics Publisher and Key Vault Secrets User | Terraform assigns those roles to the app identities |

On the **state** storage account: Storage Blob Data Contributor on the state
container (state is read and written with Entra auth, no key).

The required resource providers (`Microsoft.Web`, `Microsoft.Storage`,
`Microsoft.CognitiveServices`, `Microsoft.Network`, `Microsoft.OperationalInsights`,
`Microsoft.Insights`, `Microsoft.ManagedIdentity`, `Microsoft.Fabric` when
creating Fabric, `Microsoft.KeyVault` when enabled) must already be registered:
Terraform is configured never to register providers itself.

## 3. Fabric

- The tenant setting **"Service principals can use Fabric APIs"** must allow
  the workflow's application (FAB-3).
- With `create_fabric = false` (enterprise), the workflow's application needs
  a workspace role that lets it run T-SQL on the Warehouse (Admin or Member)
  for `apply-migrations.py` and `grant-warehouse-sql.py`.

## 4. GitHub variables (not secrets)

Set these as **environment variables** on the GitHub environment (so each
environment has its own target and its own approval rules):

| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID` | the app registration's client id |
| `AZURE_TENANT_ID` | the tenant id |
| `AZURE_SUBSCRIPTION_ID` | the target subscription; the run fails if the login lands anywhere else |
| `AZURE_RESOURCE_GROUP` | the target resource group; an existing group tagged for another environment is refused |
| `AZURE_ENV_NAME` | environment name used in resource names and the state key |
| `AZURE_LOCATION` | region |
| `TF_BACKEND_RESOURCE_GROUP`, `TF_BACKEND_STORAGE_ACCOUNT`, `TF_BACKEND_CONTAINER` | remote state (D7). The run fails fast without them |
| `TF_VARS_JSON` | enterprise BYO inputs as one JSON object (subnet ids, `private_dns_zone_ids`, Fabric ids, app registration client ids). No secrets belong in it |

## 5. Running it

Actions → *Deploy to Azure* → **Run workflow** → choose `profile` and the
`environment`. The run: tests (the CI gate) → asserts the subscription and
resource group → `terraform plan` / `apply` against remote state → schema
migrations (bootstrap only if this run created the Warehouse) → T-SQL grants
→ zip deploy of both apps → a health check through the web app (public
profile only; an enterprise web app is private).
