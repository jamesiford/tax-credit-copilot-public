# Two Linux App Services on one plan (HOST-1..5, NET-1, NET-2, AUTH-2).
#
# API: Python 3.12, code deploy, gunicorn via backend/startup.sh, VNet
#   integration with all outbound routed through the VNet (private endpoints),
#   inbound restricted to the web app's integration subnet.
# Web: Node 24 LTS serving dist/ and proxying /api (frontend/server), inbound
#   per web_inbound, Easy Auth when the profile uses Entra.
# Every setting comes from Terraform; none is a secret.

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

variable "sku_name" {
  type = string
}

variable "app_subnet_id" {
  type = string
}

variable "private_endpoint_subnet_id" {
  type = string
}

variable "sites_private_dns_zone_id" {
  type    = string
  default = ""
}

variable "web_inbound" {
  type = string
}

variable "web_allowed_ip_ranges" {
  type = list(string)
}

variable "api_identity" {
  type = object({ id = string, client_id = string })
}

variable "web_identity" {
  type = object({ id = string, client_id = string })
}

variable "api_app_settings" {
  description = "Settings the API reads (HOST-5). Merged over the platform settings below."
  type        = map(string)
}

variable "web_app_settings" {
  type = map(string)
}

variable "app_insights_connection_string" {
  type      = string
  sensitive = true
}

variable "easy_auth" {
  description = "Easy Auth (AUTH-2) when non-null."
  type = object({
    tenant_id     = string
    web_client_id = string
    api_scope     = string
  })
  default = null
}

variable "log_analytics_workspace_id" {
  type = string
}

locals {
  api_name = "app-tcc-api-${var.name_suffix}"
  web_name = "app-tcc-web-${var.name_suffix}"

  telemetry = {
    APPLICATIONINSIGHTS_CONNECTION_STRING = var.app_insights_connection_string
  }

  # Easy Auth with a managed-identity federated credential instead of a client
  # secret (AUTH-2): the platform reads the identity's client id from this
  # setting name.
  easy_auth_setting = "OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID"
}

resource "azurerm_service_plan" "this" {
  name                = "asp-tcc-${var.name_suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  os_type             = "Linux"
  sku_name            = var.sku_name
  tags                = var.tags
}

resource "azurerm_linux_web_app" "api" {
  name                                           = local.api_name
  resource_group_name                            = var.resource_group_name
  location                                       = var.location
  service_plan_id                                = azurerm_service_plan.this.id
  https_only                                     = true
  public_network_access_enabled                  = true
  virtual_network_subnet_id                      = var.app_subnet_id
  key_vault_reference_identity_id                = var.api_identity.id
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false
  tags                                           = merge(var.tags, { "azd-service-name" = "api" })

  identity {
    type         = "UserAssigned"
    identity_ids = [var.api_identity.id]
  }

  site_config {
    always_on                         = true
    app_command_line                  = "sh startup.sh"
    health_check_path                 = "/api/health"
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

    # NET-2: only the web app's integration subnet reaches the API.
    ip_restriction {
      name                      = "web-app-subnet"
      priority                  = 100
      action                    = "Allow"
      virtual_network_subnet_id = var.app_subnet_id
    }
  }

  app_settings = merge(local.telemetry, {
    AZURE_CLIENT_ID                           = var.api_identity.client_id
    APPLICATIONINSIGHTS_AUTHENTICATION_STRING = "Authorization=AAD;ClientId=${var.api_identity.client_id}"
    SCM_DO_BUILD_DURING_DEPLOYMENT            = "true"
    # HOST-1: a cold start builds the venv and warms the read paths.
    WEBSITES_CONTAINER_START_TIME_LIMIT = "1800"
  }, var.api_app_settings)

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

resource "azurerm_linux_web_app" "web" {
  name                                           = local.web_name
  resource_group_name                            = var.resource_group_name
  location                                       = var.location
  service_plan_id                                = azurerm_service_plan.this.id
  https_only                                     = true
  public_network_access_enabled                  = var.web_inbound != "private_endpoint"
  virtual_network_subnet_id                      = var.app_subnet_id
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false
  tags                                           = merge(var.tags, { "azd-service-name" = "web" })

  identity {
    type         = "UserAssigned"
    identity_ids = [var.web_identity.id]
  }

  site_config {
    always_on                         = true
    app_command_line                  = "npm start"
    health_check_path                 = "/healthz"
    health_check_eviction_time_in_min = 10
    ftps_state                        = "Disabled"
    minimum_tls_version               = "1.2"
    http2_enabled                     = true
    vnet_route_all_enabled            = true
    ip_restriction_default_action     = var.web_inbound == "access_restriction" ? "Deny" : "Allow"
    scm_ip_restriction_default_action = "Allow"

    application_stack {
      node_version = "24-lts"
    }

    dynamic "ip_restriction" {
      for_each = var.web_inbound == "access_restriction" ? var.web_allowed_ip_ranges : []
      content {
        name       = "allow-${ip_restriction.key}"
        priority   = 100 + ip_restriction.key
        action     = "Allow"
        ip_address = ip_restriction.value
      }
    }
  }

  app_settings = merge(local.telemetry, {
    AZURE_CLIENT_ID                           = var.web_identity.client_id
    APPLICATIONINSIGHTS_AUTHENTICATION_STRING = "Authorization=AAD;ClientId=${var.web_identity.client_id}"
    SCM_DO_BUILD_DURING_DEPLOYMENT            = "true"
    API_BASE_URL                              = "https://${azurerm_linux_web_app.api.default_hostname}"
    }, var.easy_auth == null ? {} : {
    (local.easy_auth_setting) = var.web_identity.client_id
  }, var.web_app_settings)

  dynamic "auth_settings_v2" {
    for_each = var.easy_auth == null ? [] : [var.easy_auth]
    content {
      auth_enabled           = true
      require_authentication = true
      unauthenticated_action = "RedirectToLoginPage"
      default_provider       = "azureactivedirectory"
      excluded_paths         = ["/healthz"]

      active_directory_v2 {
        client_id                  = auth_settings_v2.value.web_client_id
        tenant_auth_endpoint       = "https://login.microsoftonline.com/${auth_settings_v2.value.tenant_id}/v2.0"
        client_secret_setting_name = local.easy_auth_setting
        login_parameters = {
          scope = "openid profile email offline_access ${auth_settings_v2.value.api_scope}"
        }
      }

      login {
        token_store_enabled = true
      }
    }
  }
}

resource "azurerm_private_endpoint" "web" {
  count               = var.web_inbound == "private_endpoint" ? 1 : 0
  name                = "pe-web-${var.name_suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "sites"
    private_connection_resource_id = azurerm_linux_web_app.web.id
    subresource_names              = ["sites"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "sites"
    private_dns_zone_ids = [var.sites_private_dns_zone_id]
  }
}

resource "azurerm_monitor_diagnostic_setting" "app" {
  for_each = {
    api = azurerm_linux_web_app.api.id
    web = azurerm_linux_web_app.web.id
  }
  name                       = "diag-${each.key}"
  target_resource_id         = each.value
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category_group = "allLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}

resource "azurerm_monitor_diagnostic_setting" "plan" {
  name                       = "diag-plan"
  target_resource_id         = azurerm_service_plan.this.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_metric {
    category = "AllMetrics"
  }
}

output "api_name" {
  value = azurerm_linux_web_app.api.name
}

output "web_name" {
  value = azurerm_linux_web_app.web.name
}

output "api_url" {
  value = "https://${azurerm_linux_web_app.api.default_hostname}"
}

output "web_url" {
  value = "https://${azurerm_linux_web_app.web.default_hostname}"
}

output "plan_id" {
  value = azurerm_service_plan.this.id
}

output "easy_auth_enabled" {
  value = length(azurerm_linux_web_app.web.auth_settings_v2) > 0
}
