# The run orchestration worker (ADR-012): one Linux App Service on the EXISTING plan that leases queued batch items
# and runs them. Count 0 unless `enabled` (default off), so with it off the plan and every other resource are unchanged.
#
# It runs as the API's identity, not a new one. A worker calls the same run and assess commands as the API, so it needs
# exactly the API's access (the Warehouse grants, the lakehouse role, telemetry); a second identity would need the same
# grants made again and could drift from them. Its settings are the API's settings, merged with the worker's own.
#
# Network. Same integration subnet as the API. There is no inbound surface to protect: the worker serves one health
# endpoint so the platform can tell it is alive, and inbound is restricted to the integration subnet like the API's.
#
# Code is deployed like the channel gateway's, not by an azd service (azd cannot make a service conditional): zip the
# backend with scripts/package-app.py and `az webapp deploy` it; docs/architecture/RUN-ORCHESTRATION.md has the commands.
# Hence no azd-service-name tag. This build only validates and tests the module; it never applies it.

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
  description = "The subnet the api and web apps integrate with."
  type        = string
}

variable "identity" {
  description = "The API's user-assigned identity, which the worker runs as."
  type        = object({ id = string, client_id = string })
}

variable "api_app_settings" {
  description = "The API's settings. None is a secret."
  type        = map(string)
}

variable "concurrency" {
  description = "RUN_WORKER_CONCURRENCY: items in flight in this worker."
  type        = number
  default     = 2
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

  # The worker must never also start an inline worker, and it needs no web workers: it runs one process.
  worker_settings = merge(var.api_app_settings, {
    RUN_WORKER_INLINE      = "false"
    RUN_WORKER_CONCURRENCY = tostring(var.concurrency)
    WEB_CONCURRENCY        = "1"
  })
}

resource "azurerm_linux_web_app" "this" {
  count                                          = local.instances
  name                                           = "app-tcc-worker-${var.name_suffix}"
  resource_group_name                            = var.resource_group_name
  location                                       = var.location
  service_plan_id                                = var.service_plan_id
  https_only                                     = true
  public_network_access_enabled                  = true
  virtual_network_subnet_id                      = var.integration_subnet_id
  key_vault_reference_identity_id                = var.identity.id
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false
  tags                                           = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity.id]
  }

  site_config {
    always_on                         = true
    app_command_line                  = "sh worker-startup.sh"
    health_check_path                 = "/healthz"
    health_check_eviction_time_in_min = 10
    ftps_state                        = "Disabled"
    minimum_tls_version               = "1.2"
    http2_enabled                     = true
    vnet_route_all_enabled            = true
    ip_restriction_default_action     = "Deny"
    scm_ip_restriction_default_action = "Allow"

    application_stack {
      python_version = "3.12"
    }

    ip_restriction {
      name                      = "integration-subnet"
      priority                  = 100
      action                    = "Allow"
      virtual_network_subnet_id = var.integration_subnet_id
    }
  }

  app_settings = merge({
    APPLICATIONINSIGHTS_CONNECTION_STRING     = var.app_insights_connection_string
    AZURE_CLIENT_ID                           = var.identity.client_id
    APPLICATIONINSIGHTS_AUTHENTICATION_STRING = "Authorization=AAD;ClientId=${var.identity.client_id}"
    SCM_DO_BUILD_DURING_DEPLOYMENT            = "true"
    WEBSITES_CONTAINER_START_TIME_LIMIT       = "1800"
  }, local.worker_settings)

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

resource "azurerm_monitor_diagnostic_setting" "app" {
  count                      = local.instances
  name                       = "diag-worker"
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
  description = "Name of the worker App Service; empty unless enabled."
  value       = var.enabled ? azurerm_linux_web_app.this[0].name : ""
}

# The non-secret settings as the module composed them, and the resource kinds it created: the root tests prove what the
# app holds, not what a local intended.
output "settings" {
  value = local.worker_settings
}

output "resource_types" {
  value = concat(
    [for r in azurerm_linux_web_app.this : "azurerm_linux_web_app"],
    [for r in azurerm_monitor_diagnostic_setting.app : "azurerm_monitor_diagnostic_setting"],
  )
}

output "app" {
  description = "The posture of the app as the resource holds it, for the root tests."
  value = var.enabled ? {
    https_only                    = azurerm_linux_web_app.this[0].https_only
    virtual_network_subnet_id     = azurerm_linux_web_app.this[0].virtual_network_subnet_id
    app_command_line              = azurerm_linux_web_app.this[0].site_config[0].app_command_line
    health_check_path             = azurerm_linux_web_app.this[0].site_config[0].health_check_path
    ip_restriction_default_action = azurerm_linux_web_app.this[0].site_config[0].ip_restriction_default_action
    identity_ids                  = azurerm_linux_web_app.this[0].identity[0].identity_ids
    ftp_basic_auth                = azurerm_linux_web_app.this[0].ftp_publish_basic_authentication_enabled
    webdeploy_basic_auth          = azurerm_linux_web_app.this[0].webdeploy_publish_basic_authentication_enabled
  } : null
}
