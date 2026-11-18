variable "service_name" {
  description = "Distinct .NET azd service tag."
  type        = string
  validation {
    condition     = contains(["dotnet-api", "dotnet-gateway"], var.service_name)
    error_message = "Only the HTTP .NET API/gateway topology is supported."
  }
}
variable "name" {
  description = "New application name, never a Python app name."
  type        = string
  validation {
    condition     = startswith(var.name, "app-tcc-dotnet-")
    error_message = "Application names must have the app-tcc-dotnet- ownership prefix."
  }
}
variable "resource_group_name" {
  description = "Dedicated new .NET resource group."
  type        = string
}
variable "location" {
  description = "Application Azure region."
  type        = string
}
variable "tags" {
  description = "Base tags, overridden by the authoritative runtime/service tags."
  type        = map(string)
}
variable "service_plan_id" {
  description = "New dedicated .NET single-instance Linux plan."
  type        = string
}
variable "dll" {
  description = "Published HTTP host entry point; no shell, image or Python startup."
  type        = string
  validation {
    condition = (
      var.service_name == "dotnet-api" && var.dll == "TaxCredit.Api.dll" ||
      var.service_name == "dotnet-gateway" && var.dll == "TaxCredit.Gateway.dll"
    )
    error_message = "The service tag must match its published HTTP DLL."
  }
}
variable "integration_subnet_id" {
  description = "Existing delegated App Service integration subnet."
  type        = string
}
variable "private_endpoint_subnet_id" {
  description = "Existing distinct private endpoint subnet."
  type        = string
}
variable "sites_private_dns_zone_id" {
  description = "Existing linked privatelink.azurewebsites.net DNS zone."
  type        = string
}
variable "identity_id" {
  description = "This service's distinct user-assigned managed identity ARM ID."
  type        = string
}
variable "identity_client_id" {
  description = "DefaultAzureCredential managed-identity selection."
  type        = string
}
variable "app_settings" {
  description = "Consumer-verified settings built by the root, never free-form legacy environment passthrough."
  type        = map(string)
  sensitive   = true
  validation {
    condition = try(
      var.app_settings.ENVIRONMENT == "azure" &&
      var.app_settings.PERSISTENCE_PROVIDER == "warehouse" &&
      var.app_settings.DATA_SOURCE == "lakehouse" &&
      var.app_settings.ARTIFACT_STORE == "blob" &&
      var.app_settings.AUTH_MODE == "entra" &&
      var.app_settings.CONTRACT_HOOKS == "0" &&
      var.app_settings.CHANNEL_ENFORCE_WRITER_FOR_USERS == "true", false
    )
    error_message = "HTTP services require deployed Warehouse/SQL/Blob, Entra, acting-person writer enforcement and disabled replay controls."
  }
  validation {
    condition = length(setsubtract(toset(keys(var.app_settings)), toset([
      "ENVIRONMENT", "DATA_CLASSIFICATION", "DATA_SOURCE", "PERSISTENCE_PROVIDER",
      "FABRIC_SQL_SERVER", "FABRIC_SQL_DATABASE", "SOURCE_SQL_SERVER", "SOURCE_SQL_DATABASE", "SOURCE_SCHEMA",
      "ARTIFACT_STORE", "ARTIFACT_BLOB_ACCOUNT_URL", "REPOSITORY_ROOT", "AUTH_MODE", "AUTH_TENANT_ID",
      "API_AUDIENCE", "CLIENT_ALLOWLIST", "CHANNEL_ENFORCE_WRITER_FOR_USERS", "CHANNEL_WRITER_SOURCE",
      "CHANNEL_WRITER_GROUP_ID", "CONTRACT_HOOKS", "GIT_COMMIT", "PAY_CODE_POLICY", "FISCAL_RULES_POLICY",
      "TENANT_ID", "GATEWAY_AUDIENCE", "CHANNEL_DEBUG_WHOAMI", "CHANNEL_ALLOWED_CALLER_APP_IDS",
      "CHANNEL_CALLER_CHANNELS", "CHANNEL_RATE_LIMIT_PER_MINUTE"
    ]))) == 0
    error_message = "Only consumer-verified TaxCredit runtime settings are supported; no legacy/unsupported passthrough."
  }
}
variable "log_analytics_workspace_id" {
  description = "Existing workspace for platform metrics only."
  type        = string
}
