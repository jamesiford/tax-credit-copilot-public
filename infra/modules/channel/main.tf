# The Microsoft 365 channel gateway (CH-07): one Linux App Service (Python 3.12)
# on the EXISTING plan, with its own user-assigned identity. Everything here is
# count 0 unless `enabled`, so with the channel off the module adds nothing to
# the plan (a test proves it).
#
# Network. The app integrates with the SAME subnet as the api and web apps
# (vnet_route_all_enabled, like the API), which is what lets the API's access
# restriction ("web-app-subnet") admit it WITHOUT being widened. Inbound is public:
# the orchestrator and Cowork are outside the VNet, and a caller is authenticated
# in the app by token validation (channel/auth.py), not by Easy Auth or by network.
# `allowed_ip_ranges` narrows it; empty allows every address.
#
# Identity and secrets. No secret exists. The identity is what the app calls the
# API and the Warehouse as; telemetry is Entra-authenticated like the other apps.
# The role the API needs to accept it (TCC.Agent) and the Warehouse grant are NOT
# Terraform's: an app role assignment needs directory permissions Terraform's
# principal usually lacks, and the T-SQL grant is scripts/grant-warehouse-sql.py.
#
# Code is deployed by scripts/deploy-channel.ps1 (azd postdeploy hook and deploy.yml), NOT by an
# azd service: azd cannot make a service conditional and resolves each service by its
# azd-service-name tag, so a `channel` service would break `azd up` whenever this app is
# absent. Hence the app carries no azd-service-name tag.

variable "enabled" {
  type = bool
}

variable "name_suffix" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "tags" {
  type = map(string)
}

variable "service_plan_id" {
  type = string
}

variable "integration_subnet_id" {
  description = "The subnet the api and web apps integrate with. The API's access restriction already admits it."
  type        = string
}

variable "tenant_id" {
  type = string
}

variable "gateway_audience" {
  type = string
}

variable "api_base_url" {
  description = "https://<API default hostname>, as the web app uses."
  type        = string
}

variable "api_audience" {
  type = string
}

variable "data_classification" {
  type = string
}

variable "allowed_caller_app_ids" {
  type = list(string)
}

variable "writer_source" {
  type = string
}

variable "writer_group_id" {
  type = string
}

variable "allowed_ip_ranges" {
  type = list(string)
}

variable "warehouse" {
  description = "The Warehouse the audit trail is written to (the same one the API uses)."
  type = object({
    server    = string
    database  = string
    workspace = string
  })
}

variable "git_commit" {
  type    = string
  default = ""
}

variable "app_insights_id" {
  type = string
}

variable "app_insights_connection_string" {
  type      = string
  sensitive = true
}

variable "log_analytics_workspace_id" {
  type = string
}

locals {
  instances = var.enabled ? 1 : 0

  # Every setting the gateway reads (docs/architecture/ENV-VARS.md section 9a).
  # None is a secret. Optional ones are emitted only when set, so an unset
  # variable adds nothing.
  plain_settings = merge({
    ENVIRONMENT         = "azure"
    DATA_CLASSIFICATION = var.data_classification
    TENANT_ID           = var.tenant_id
    GATEWAY_AUDIENCE    = var.gateway_audience
    API_BASE_URL        = var.api_base_url
    API_AUDIENCE        = var.api_audience
    CHANNEL_STORE       = "warehouse"
    WAREHOUSE_SERVER    = var.warehouse.server
    WAREHOUSE_DATABASE  = var.warehouse.database
    FABRIC_WORKSPACE    = var.warehouse.workspace
    # One worker: the fact ledger and the rate limiter are per process.
    WEB_CONCURRENCY       = "1"
    CHANNEL_WRITER_SOURCE = var.writer_source
    },
    length(var.allowed_caller_app_ids) > 0 ? { CHANNEL_ALLOWED_CALLER_APP_IDS = join(",", var.allowed_caller_app_ids) } : {},
    trimspace(var.writer_group_id) != "" ? { CHANNEL_WRITER_GROUP_ID = trimspace(var.writer_group_id) } : {},
    trimspace(var.git_commit) != "" ? { GIT_COMMIT = var.git_commit } : {},
  )
}

resource "azurerm_user_assigned_identity" "this" {
  count               = local.instances
  name                = "id-tcc-channel-${var.name_suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
}

resource "azurerm_linux_web_app" "this" {
  count                                          = local.instances
  name                                           = "app-tcc-channel-${var.name_suffix}"
  resource_group_name                            = var.resource_group_name
  location                                       = var.location
  service_plan_id                                = var.service_plan_id
  https_only                                     = true
  public_network_access_enabled                  = true
  virtual_network_subnet_id                      = var.integration_subnet_id
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false
  tags                                           = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.this[0].id]
  }

  site_config {
    always_on                         = true
    app_command_line                  = "sh startup-channel.sh"
    health_check_path                 = "/channel/health"
    health_check_eviction_time_in_min = 10
    ftps_state                        = "Disabled"
    minimum_tls_version               = "1.2"
    http2_enabled                     = true
    vnet_route_all_enabled            = true
    ip_restriction_default_action     = length(var.allowed_ip_ranges) == 0 ? "Allow" : "Deny"
    scm_ip_restriction_default_action = "Allow"

    application_stack {
      python_version = "3.12"
    }

    dynamic "ip_restriction" {
      for_each = var.allowed_ip_ranges
      content {
        name       = "allow-${ip_restriction.key}"
        priority   = 100 + ip_restriction.key
        action     = "Allow"
        ip_address = ip_restriction.value
      }
    }
  }

  app_settings = merge({
    APPLICATIONINSIGHTS_CONNECTION_STRING     = var.app_insights_connection_string
    AZURE_CLIENT_ID                           = azurerm_user_assigned_identity.this[0].client_id
    APPLICATIONINSIGHTS_AUTHENTICATION_STRING = "Authorization=AAD;ClientId=${azurerm_user_assigned_identity.this[0].client_id}"
    SCM_DO_BUILD_DURING_DEPLOYMENT            = "true"
  }, local.plain_settings)

  logs {
    detailed_error_messages = true
    failed_request_tracing  = false
    http_logs {
      file_system {
        retention_in_days = 7
        retention_in_mb   = 35
      }
    }
  }
}

# Telemetry is Entra-only (OBS-1): without this role the gateway writes none.
resource "azurerm_role_assignment" "publisher" {
  count                = local.instances
  scope                = var.app_insights_id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = azurerm_user_assigned_identity.this[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_monitor_diagnostic_setting" "app" {
  count                      = local.instances
  name                       = "diag-channel"
  target_resource_id         = azurerm_linux_web_app.this[0].id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category_group = "allLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}

output "app_name" {
  value = var.enabled ? azurerm_linux_web_app.this[0].name : ""
}

output "url" {
  value = var.enabled ? "https://${azurerm_linux_web_app.this[0].default_hostname}" : ""
}

output "identity_name" {
  description = "Display name of the gateway identity; scripts/grant-warehouse-sql.py --profile gateway grants to it."
  value       = var.enabled ? azurerm_user_assigned_identity.this[0].name : ""
}

output "identity_principal_id" {
  description = "Object id the operator assigns the API's TCC.Agent app role to (a directory action Terraform does not take)."
  value       = var.enabled ? azurerm_user_assigned_identity.this[0].principal_id : ""
}

output "identity_client_id" {
  value = var.enabled ? azurerm_user_assigned_identity.this[0].client_id : ""
}

# The non-secret settings as the module composed them, and the resource kinds it
# created: the root tests prove what the app holds, not what a local intended.
output "settings" {
  value = local.plain_settings
}

output "resource_types" {
  value = concat(
    [for r in azurerm_user_assigned_identity.this : "azurerm_user_assigned_identity"],
    [for r in azurerm_linux_web_app.this : "azurerm_linux_web_app"],
    [for r in azurerm_role_assignment.publisher : "azurerm_role_assignment"],
    [for r in azurerm_monitor_diagnostic_setting.app : "azurerm_monitor_diagnostic_setting"],
  )
}

output "app" {
  description = "The posture of the app as the resource holds it, for the root tests."
  value = var.enabled ? {
    https_only                    = azurerm_linux_web_app.this[0].https_only
    virtual_network_subnet_id     = azurerm_linux_web_app.this[0].virtual_network_subnet_id
    tags                          = azurerm_linux_web_app.this[0].tags
    app_command_line              = azurerm_linux_web_app.this[0].site_config[0].app_command_line
    ftps_state                    = azurerm_linux_web_app.this[0].site_config[0].ftps_state
    minimum_tls_version           = azurerm_linux_web_app.this[0].site_config[0].minimum_tls_version
    always_on                     = azurerm_linux_web_app.this[0].site_config[0].always_on
    vnet_route_all_enabled        = azurerm_linux_web_app.this[0].site_config[0].vnet_route_all_enabled
    ip_restriction_default_action = azurerm_linux_web_app.this[0].site_config[0].ip_restriction_default_action
    ip_restriction_ranges         = [for r in azurerm_linux_web_app.this[0].site_config[0].ip_restriction : r.ip_address]
    python_version                = azurerm_linux_web_app.this[0].site_config[0].application_stack[0].python_version
    ftp_basic_auth                = azurerm_linux_web_app.this[0].ftp_publish_basic_authentication_enabled
    webdeploy_basic_auth          = azurerm_linux_web_app.this[0].webdeploy_publish_basic_authentication_enabled
    app_setting_names             = nonsensitive(keys(azurerm_linux_web_app.this[0].app_settings))
  } : null
}
