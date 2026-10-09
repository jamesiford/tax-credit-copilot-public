# The D25 profile matrix, resolved once. Every module reads these locals rather
# than the raw variables, so a profile difference lives in exactly one place.

data "azurerm_client_config" "current" {}

locals {
  profile_defaults = {
    public = {
      auth_mode            = "none"
      easy_auth            = false
      data_classification  = "synthetic"
      create_fabric        = true
      manage_fabric_access = true
      create_network       = true
      web_inbound          = "public"
    }
    enterprise = {
      auth_mode            = "entra"
      easy_auth            = true
      data_classification  = "customer"
      create_fabric        = false
      manage_fabric_access = false
      create_network       = false
      web_inbound          = "private_endpoint"
    }
  }
  d = local.profile_defaults[var.profile]

  subscription_id = trimspace(var.subscription_id) == "" ? null : trimspace(var.subscription_id)
  tenant_id       = trimspace(var.tenant_id) != "" ? trimspace(var.tenant_id) : data.azurerm_client_config.current.tenant_id

  auth_mode            = var.auth_mode != null ? var.auth_mode : local.d.auth_mode
  easy_auth            = local.auth_mode == "entra" ? local.d.easy_auth || var.profile == "enterprise" : false
  data_classification  = var.data_classification != null ? var.data_classification : local.d.data_classification
  create_fabric        = var.create_fabric != null ? var.create_fabric : local.d.create_fabric
  manage_fabric_access = var.manage_fabric_access != null ? var.manage_fabric_access : local.d.manage_fabric_access
  create_network       = var.create_network != null ? var.create_network : local.d.create_network
  web_inbound          = var.web_inbound != null ? var.web_inbound : local.d.web_inbound

  api_audience = trimspace(var.api_audience) != "" ? trimspace(var.api_audience) : (
    trimspace(var.api_client_id) != "" ? "api://${trimspace(var.api_client_id)}" : ""
  )

  # Short, stable, globally-unique-enough suffix for names that must be unique.
  token               = substr(sha1("${coalesce(local.subscription_id, data.azurerm_client_config.current.subscription_id)}/${var.environment_name}/${var.location}"), 0, 8)
  resource_group_name = trimspace(var.resource_group_name) != "" ? trimspace(var.resource_group_name) : "rg-${var.environment_name}"

  tags = merge(var.tags, {
    "azd-env-name" = var.environment_name
    "application"  = "tax-credit-copilot"
    "profile"      = var.profile
  })
}
