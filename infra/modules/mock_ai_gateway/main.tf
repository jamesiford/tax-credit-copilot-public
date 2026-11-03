# A stand-in for the customer's model gateway (AI-03), for a proof of concept
# only. One Linux App Service (Python 3.12) on the existing plan, in the same
# VNet-integration subnet as the api and web apps. Count 0 unless enabled, and
# the root refuses to enable it for the enterprise profile.
#
# Terraform creates the app and its settings and NOTHING ELSE. The code is
# scripts/mock-ai-gateway.py, deployed by hand as a separate PoC step (copy it
# as mock_ai_gateway.py next to scripts/mock-ai-gateway.requirements.txt as requirements.txt,
# then `az webapp deploy`); the startup command below imports it by that name.
#
# Inbound is restricted to the integration subnet, exactly as the API is (NET-2),
# so only the API app can reach it. No secret setting exists: the mock's API key
# is a fixed non-secret string the deployer supplies at call time.

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
  description = "The subnet the api and web apps integrate with; also the only subnet allowed inbound."
  type        = string
}

variable "mock_auth" {
  description = "MOCK_AUTH: none | api_key | oauth | entra."
  type        = string
  validation {
    condition     = contains(["none", "api_key", "oauth", "entra"], var.mock_auth)
    error_message = "mock_auth must be none, api_key, oauth or entra."
  }
}

variable "entra_audience" {
  description = "MOCK_ENTRA_AUDIENCE."
  type        = string
}

resource "azurerm_linux_web_app" "this" {
  count                                          = var.enabled ? 1 : 0
  name                                           = "app-tcc-mockgw-${var.name_suffix}"
  resource_group_name                            = var.resource_group_name
  location                                       = var.location
  service_plan_id                                = var.service_plan_id
  https_only                                     = true
  public_network_access_enabled                  = true
  virtual_network_subnet_id                      = var.integration_subnet_id
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false
  tags                                           = merge(var.tags, { purpose = "poc-mock" })

  # No roles are granted to this identity: the mock calls nothing in Azure.
  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on                         = true
    app_command_line                  = "python -m uvicorn mock_ai_gateway:app --host 0.0.0.0 --port 8000"
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

  app_settings = {
    MOCK_AUTH                      = var.mock_auth
    MOCK_ENTRA_AUDIENCE            = var.entra_audience
    WEBSITES_PORT                  = "8000"
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
  }
}

output "default_hostname" {
  description = "Default hostname of the mock, empty when disabled."
  value       = var.enabled ? azurerm_linux_web_app.this[0].default_hostname : ""
}
