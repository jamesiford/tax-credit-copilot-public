locals {
  name_suffix = "tcc-dotnet-${var.environment_name}"
  tags = merge({ for key, value in var.tags : key => value if !contains([
    "azd-service-name", "azd-env-name", "tcc-runtime", "tcc-ownership", "tcc-component"
    ], key) }, {
    "azd-env-name"  = var.environment_name
    "tcc-runtime"   = "dotnet"
    "tcc-ownership" = "infra-dotnet"
    "tcc-component" = "runtime"
  })

  services = merge({
    api = { dll = "TaxCredit.Api.dll" }
    }, var.enable_gateway ? {
    gateway = { dll = "TaxCredit.Gateway.dll" }
  } : {})

  runtime_settings = merge({
    ENVIRONMENT                      = "azure"
    DATA_CLASSIFICATION              = var.data_classification
    DATA_SOURCE                      = "lakehouse"
    PERSISTENCE_PROVIDER             = "warehouse"
    FABRIC_SQL_SERVER                = var.warehouse.server
    FABRIC_SQL_DATABASE              = var.warehouse.database
    SOURCE_SQL_SERVER                = var.payroll_source.server
    SOURCE_SQL_DATABASE              = var.payroll_source.database
    SOURCE_SCHEMA                    = var.payroll_source.schema
    ARTIFACT_STORE                   = "blob"
    ARTIFACT_BLOB_ACCOUNT_URL        = var.blob.account_url
    REPOSITORY_ROOT                  = var.resource_root
    AUTH_MODE                        = "entra"
    AUTH_TENANT_ID                   = var.tenant_id
    API_AUDIENCE                     = var.api_audience
    CLIENT_ALLOWLIST                 = jsonencode(var.client_allowlist)
    CHANNEL_ENFORCE_WRITER_FOR_USERS = "true"
    CHANNEL_WRITER_SOURCE            = var.writer_source
    CONTRACT_HOOKS                   = "0"
    GIT_COMMIT                       = var.git_commit
    PAY_CODE_POLICY                  = "strict"
    FISCAL_RULES_POLICY              = "strict"
  }, var.data_map_file == "" ? {} : { DATA_MAP_FILE = var.data_map_file })

  gateway_settings = {
    TENANT_ID                      = var.tenant_id
    GATEWAY_AUDIENCE               = var.gateway_audience
    CHANNEL_DEBUG_WHOAMI           = "false"
    CHANNEL_ALLOWED_CALLER_APP_IDS = join(",", sort(keys(var.channel_callers)))
    CHANNEL_CALLER_CHANNELS        = join(",", [for app in sort(keys(var.channel_callers)) : "${app}=${join("|", sort(tolist(var.channel_callers[app])))}"])
    CHANNEL_RATE_LIMIT_PER_MINUTE  = "60"
  }

  blob_container_scopes = {
    artifacts = var.blob.artifacts_container_resource_id
    outputs   = var.blob.outputs_container_resource_id
  }
  blob_grants = {
    for pair in setproduct(keys(local.services), keys(local.blob_container_scopes)) :
    "${pair[0]}-${pair[1]}" => { service = pair[0], container = pair[1] }
  }
}
