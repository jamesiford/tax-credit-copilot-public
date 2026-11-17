variable "network" {
  description = "Existing externally managed network/DNS only. No subnet, VNet, zone or external private endpoint is adopted."
  type = object({
    integration_subnet_id       = string
    private_endpoint_subnet_id  = string
    sites_private_dns_zone_id   = string
    blob_private_endpoint_id    = string
    blob_private_dns_zone_id    = string
    fabric_private_endpoint_id  = string
    fabric_private_dns_zone_ids = list(string)
  })
  validation {
    condition = alltrue([
      for id in [var.network.integration_subnet_id, var.network.private_endpoint_subnet_id] :
      can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Network/virtualNetworks/[^/]+/subnets/[^/]+$", id))
    ]) && var.network.integration_subnet_id != var.network.private_endpoint_subnet_id
    error_message = "Supply distinct existing integration and private-endpoint subnet resource IDs."
  }
  validation {
    condition = alltrue([
      for id in [var.network.blob_private_endpoint_id, var.network.fabric_private_endpoint_id] :
      can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Network/privateEndpoints/[^/]+$", id))
    ])
    error_message = "Existing Blob and Fabric private endpoint references are required."
  }
  validation {
    condition = (
      can(regex("(?i)/privateDnsZones/privatelink.azurewebsites.net$", var.network.sites_private_dns_zone_id)) &&
      can(regex("(?i)/privateDnsZones/privatelink.blob.core.windows.net$", var.network.blob_private_dns_zone_id)) &&
      length(var.network.fabric_private_dns_zone_ids) > 0 &&
      alltrue([for id in var.network.fabric_private_dns_zone_ids :
        can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Network/privateDnsZones/[^/]+$", id))
      ])
    )
    error_message = "Reference the existing sites/Blob private DNS zones and Fabric private DNS zone IDs."
  }
}

variable "log_analytics_workspace_id" {
  description = "Existing diagnostic metrics destination. Request/application logs are deliberately not enabled."
  type        = string
  validation {
    condition     = can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.OperationalInsights/workspaces/[^/]+$", var.log_analytics_workspace_id))
    error_message = "log_analytics_workspace_id must reference an existing workspace."
  }
}

variable "blob" {
  description = "Existing private Blob account and the two existing container ARM IDs; no SAS, keys or storage ownership."
  type = object({
    account_url                     = string
    artifacts_container_resource_id = string
    outputs_container_resource_id   = string
  })
  validation {
    condition = (
      can(regex("^https://[a-z0-9]{3,24}\\.blob\\.core\\.windows\\.net/?$", var.blob.account_url)) &&
      can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Storage/storageAccounts/[^/]+/blobServices/default/containers/artifacts$", var.blob.artifacts_container_resource_id)) &&
      can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Storage/storageAccounts/[^/]+/blobServices/default/containers/outputs$", var.blob.outputs_container_resource_id))
    )
    error_message = "blob requires a key-free HTTPS account URL and existing artifacts/outputs container ARM IDs."
  }
  validation {
    condition = try(
      split("/", var.blob.artifacts_container_resource_id)[8] == split("/", var.blob.outputs_container_resource_id)[8] &&
      lower(split("/", var.blob.artifacts_container_resource_id)[8]) == split(".", trimprefix(var.blob.account_url, "https://"))[0], false
    )
    error_message = "The Blob URL and both container references must name the same account."
  }
}
