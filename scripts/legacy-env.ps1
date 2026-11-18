<#
.SYNOPSIS
  One-release fallback for the deployment settings renamed away from the product prefix.

.DESCRIPTION
  Every variable the repository emits uses only the new name. A shell, a pipeline or an azd
  environment that still carries the old `TCC_` name keeps working: when the new name is unset
  this copies the old value to it. The new name always wins when both are set, and only the
  NAME of a deprecated variable is written, never its value.

  Dot-source it from a script (`. "$PSScriptRoot/legacy-env.ps1"`) to fix the process
  environment, or run it as the azd `preprovision` hook with -AzdEnv to also persist the new
  names in the azd environment, which is where infra/main.tfvars.json reads its inputs.
  This table is the one place the old names live for the PowerShell scripts; delete the file,
  the hook in azure.yaml and the dot-sourcing lines to drop the aliases.
#>
param([switch] $AzdEnv)

$__legacyEnvAliases = [ordered]@{
    DEPLOY_PROFILE                = 'TCC_PROFILE'
    TENANT_ID                     = 'TCC_TENANT_ID'
    API_CLIENT_ID                 = 'TCC_API_CLIENT_ID'
    WEB_CLIENT_ID                 = 'TCC_WEB_CLIENT_ID'
    API_AUDIENCE                  = 'TCC_API_AUDIENCE'
    APP_SERVICE_SKU               = 'TCC_APP_SERVICE_SKU'
    APP_SUBNET_ID                 = 'TCC_APP_SUBNET_ID'
    PRIVATE_ENDPOINT_SUBNET_ID    = 'TCC_PRIVATE_ENDPOINT_SUBNET_ID'
    EXISTING_FABRIC_WORKSPACE_ID  = 'TCC_FABRIC_WORKSPACE_ID'
    EXISTING_FABRIC_WAREHOUSE_ID  = 'TCC_FABRIC_WAREHOUSE_ID'
    EXISTING_WAREHOUSE_SERVER     = 'TCC_WAREHOUSE_SERVER'
    EXISTING_WAREHOUSE_DATABASE   = 'TCC_WAREHOUSE_DATABASE'
    WAREHOUSE_PLATFORM            = 'TCC_WAREHOUSE_PLATFORM'
    FABRIC_WORKSPACE_NAME         = 'TCC_FABRIC_WORKSPACE_NAME'
    FABRIC_LAKEHOUSE_NAME         = 'TCC_FABRIC_LAKEHOUSE_NAME'
    FABRIC_CREATED                = 'TCC_FABRIC_CREATED'
    SQL_CREATED                   = 'TCC_SQL_CREATED'
    SQL_ADMIN_GROUP_NAME          = 'TCC_SQL_ADMIN_GROUP_NAME'
    SQL_ADMIN_GROUP_OBJECT_ID     = 'TCC_SQL_ADMIN_GROUP_OBJECT_ID'
    LAKEHOUSE_SQL_SERVER          = 'TCC_LAKEHOUSE_SQL_SERVER'
    LAKEHOUSE_SQL_DATABASE        = 'TCC_LAKEHOUSE_SQL_DATABASE'
    DATA_QUERY_SOURCE_ENABLED     = 'TCC_DATA_QUERY_SOURCE_ENABLED'
    DATA_QUERY_TIMEOUT_SECONDS    = 'TCC_DATA_QUERY_TIMEOUT_SECONDS'
    DATA_QUERY_MAX_ROWS           = 'TCC_DATA_QUERY_MAX_ROWS'
    DATA_QUERY_RATE_PER_MINUTE    = 'TCC_DATA_QUERY_RATE_PER_MINUTE'
    DATA_QUERY_MAX_CONCURRENCY    = 'TCC_DATA_QUERY_MAX_CONCURRENCY'
    FOUNDRY_ALLOWED_IP_RANGES     = 'TCC_FOUNDRY_ALLOWED_IP_RANGES'
    FOUNDRY_PUBLIC_NETWORK_ACCESS = 'TCC_FOUNDRY_PUBLIC_NETWORK_ACCESS'
    M365_CHANNEL_ENABLED          = 'TCC_ENABLE_M365_CHANNEL'
    CHANNEL_GATEWAY_AUDIENCE      = 'TCC_CHANNEL_GATEWAY_AUDIENCE'
    CHANNEL_WRITER_SOURCE         = 'TCC_CHANNEL_WRITER_SOURCE'
    CHANNEL_WRITER_GROUP_ID       = 'TCC_CHANNEL_WRITER_GROUP_ID'
    CHANNEL_RESOLVE_DISPLAY_NAMES = 'TCC_CHANNEL_RESOLVE_DISPLAY_NAMES'
    CHANNEL_HEALTH_CHECK          = 'TCC_CHANNEL_HEALTH_CHECK'
    DEPLOY_PYTHON                 = 'TCC_DEPLOY_PYTHON'
    DEPLOY_DOTNET_ACTIVATE        = 'TCC_DOTNET_ACTIVATE'
    AI_GATEWAY_SECRET             = 'TCC_GATEWAY_SECRET'
    ALLOW_SEED                    = 'TCC_ALLOW_SEED'
    RESOURCE_ROOT                 = 'TCC_RESOURCE_ROOT'
    ENABLE_RUN_WORKER             = 'TCC_ENABLE_RUN_WORKER'
    ORCHESTRATOR_LOCAL_PROOF      = 'TCC_ORCHESTRATOR_LOCAL_PROOF'
}

& {
    param($aliases, $persist)
    foreach ($current in $aliases.Keys) {
        $legacy = $aliases[$current]
        $value = [Environment]::GetEnvironmentVariable($legacy)
        if ([string]::IsNullOrEmpty($value) -or -not [string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($current))) { continue }
        [Environment]::SetEnvironmentVariable($current, $value)
        Write-Warning "Deprecated environment variable $legacy is in use; set $current instead."
        if ($persist) { azd env set $current $value | Out-Null }
    }
} $__legacyEnvAliases $AzdEnv