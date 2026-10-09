# Blob Storage for artifacts (BLOB-1, BLOB-2, BLOB-5). Public network access,
# shared keys and anonymous access are all OFF; the API reaches it over a
# private endpoint as its managed identity.
#
# MANAGEMENT PLANE ONLY. Containers are created with `storage_account_id` and
# the lifecycle with `azurerm_storage_management_policy`, so Terraform never
# needs data-plane reach to an account it has just closed to the network.

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

variable "private_endpoint_subnet_id" {
  type = string
}

variable "blob_private_dns_zone_id" {
  type = string
}

variable "data_principal_id" {
  description = "The API identity: Storage Blob Data Contributor on each container."
  type        = string
}

variable "outputs_retention_days" {
  type = number
}

variable "log_analytics_workspace_id" {
  type = string
}

locals {
  containers = {
    artifacts = "Source documents behind rule packs (rule packs stay in Git)."
    outputs   = "Generated claim packages at {client_id}/{run_id}/..."
  }
}

resource "azurerm_storage_account" "this" {
  name                            = "sttcc${var.name_suffix}"
  resource_group_name             = var.resource_group_name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "ZRS"
  account_kind                    = "StorageV2"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  public_network_access_enabled   = false
  shared_access_key_enabled       = false
  allow_nested_items_to_be_public = false
  default_to_oauth_authentication = true
  tags                            = var.tags

  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = 30
    }
    container_delete_retention_policy {
      days = 30
    }
  }
}

resource "azurerm_storage_container" "this" {
  for_each              = local.containers
  name                  = each.key
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

resource "azurerm_storage_management_policy" "outputs" {
  storage_account_id = azurerm_storage_account.this.id

  rule {
    name    = "outputs-retention"
    enabled = true
    filters {
      blob_types   = ["blockBlob"]
      prefix_match = ["outputs/"]
    }
    actions {
      base_blob {
        delete_after_days_since_creation_greater_than = var.outputs_retention_days
      }
      version {
        delete_after_days_since_creation = var.outputs_retention_days
      }
    }
  }
}

resource "azurerm_private_endpoint" "blob" {
  name                = "pe-blob-${var.name_suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "blob"
    private_connection_resource_id = azurerm_storage_account.this.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "blob"
    private_dns_zone_ids = [var.blob_private_dns_zone_id]
  }
}

resource "azurerm_role_assignment" "blob_data" {
  for_each             = azurerm_storage_container.this
  scope                = each.value.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.data_principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_monitor_diagnostic_setting" "blob" {
  name                       = "diag-blob"
  target_resource_id         = "${azurerm_storage_account.this.id}/blobServices/default"
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category_group = "allLogs"
  }

  enabled_metric {
    category = "Transaction"
  }
}

output "account_id" {
  value = azurerm_storage_account.this.id
}

output "account_name" {
  value = azurerm_storage_account.this.name
}

output "blob_endpoint" {
  value = azurerm_storage_account.this.primary_blob_endpoint
}

output "container_ids" {
  value = { for k, c in azurerm_storage_container.this : k => c.id }
}

output "role_assignments" {
  value = [for k, r in azurerm_role_assignment.blob_data : { principal = "api", role = r.role_definition_name, scope = "container:${k}" }]
}
