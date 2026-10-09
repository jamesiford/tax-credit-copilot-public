# Optional Key Vault (count 0 by default). The stack holds no secrets; this
# exists for a customer whose policy requires one (e.g. to hold a future
# third-party credential as a Key Vault reference, HOST-5).

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

variable "tenant_id" {
  type = string
}

variable "tags" {
  type = map(string)
}

variable "private_endpoint_subnet_id" {
  type = string
}

variable "vault_private_dns_zone_id" {
  type = string
}

variable "reader_principal_id" {
  type = string
}

variable "log_analytics_workspace_id" {
  type = string
}

resource "azurerm_key_vault" "this" {
  count                         = var.enabled ? 1 : 0
  name                          = "kv-tcc-${var.name_suffix}"
  resource_group_name           = var.resource_group_name
  location                      = var.location
  tenant_id                     = var.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 7
  public_network_access_enabled = false
  tags                          = var.tags

  network_acls {
    default_action = "Deny"
    bypass         = "None"
  }
}

resource "azurerm_private_endpoint" "vault" {
  count               = var.enabled ? 1 : 0
  name                = "pe-kv-${var.name_suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "vault"
    private_connection_resource_id = azurerm_key_vault.this[0].id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "vault"
    private_dns_zone_ids = [var.vault_private_dns_zone_id]
  }
}

resource "azurerm_role_assignment" "secrets_user" {
  count                = var.enabled ? 1 : 0
  scope                = azurerm_key_vault.this[0].id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = var.reader_principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_monitor_diagnostic_setting" "vault" {
  count                      = var.enabled ? 1 : 0
  name                       = "diag-kv"
  target_resource_id         = azurerm_key_vault.this[0].id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category_group = "allLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}

output "id" {
  value = var.enabled ? azurerm_key_vault.this[0].id : null
}

output "uri" {
  value = var.enabled ? azurerm_key_vault.this[0].vault_uri : null
}

output "role_assignments" {
  value = [for r in azurerm_role_assignment.secrets_user : { principal = "api", role = r.role_definition_name, scope = "key_vault" }]
}
