# Microsoft Foundry (AI-1): account + project + one model deployment, via azapi
# because the project resource is not in azurerm. Local auth is off and public
# network access is off; the API reaches it over a private endpoint as its
# managed identity with Azure AI User.

variable "name_suffix" {
  type = string
}

variable "resource_group_id" {
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

variable "model" {
  type = string
}

variable "model_version" {
  type = string
}

variable "deployment_sku" {
  type = string
}

variable "capacity" {
  type = number
}

variable "private_endpoint_subnet_id" {
  type = string
}

variable "private_dns_zone_ids" {
  description = "Zone ids for cognitiveservices, openai and aiservices."
  type        = list(string)
}

variable "user_principal_id" {
  description = "The API identity (Azure AI User)."
  type        = string
}

variable "log_analytics_workspace_id" {
  type = string
}

locals {
  account_name    = "aif-tcc-${var.name_suffix}"
  project_name    = "proj-tcc"
  subscription_id = split("/", var.resource_group_id)[2]
}

# A deleted AIServices account sits in soft-delete for 48 hours and holds its
# custom subdomain. azurerm's purge_soft_delete_on_destroy does not reach an
# azapi resource, so the purge is an explicit destroy-time action. The account
# depends on THIS, so on destroy the account goes first and the purge runs after.
resource "azapi_resource_action" "purge_on_destroy" {
  type        = "Microsoft.CognitiveServices/locations/resourceGroups/deletedAccounts@2025-06-01"
  resource_id = "/subscriptions/${local.subscription_id}/providers/Microsoft.CognitiveServices/locations/${var.location}/resourceGroups/${var.resource_group_name}/deletedAccounts/${local.account_name}"
  method      = "DELETE"
  when        = "destroy"
}

resource "azapi_resource" "account" {
  type      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name      = local.account_name
  parent_id = var.resource_group_id
  location  = var.location
  tags      = var.tags

  depends_on = [azapi_resource_action.purge_on_destroy]

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "AIServices"
    sku = {
      name = "S0"
    }
    properties = {
      customSubDomainName    = local.account_name
      allowProjectManagement = true
      disableLocalAuth       = true
      publicNetworkAccess    = "Disabled"
      networkAcls = {
        defaultAction = "Deny"
      }
    }
  }

  response_export_values = ["properties.endpoint"]
}

resource "azapi_resource" "project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name      = local.project_name
  parent_id = azapi_resource.account.id
  location  = var.location
  tags      = var.tags

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {}
  }
}

resource "azapi_resource" "deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  name      = var.model
  parent_id = azapi_resource.account.id

  # The account accepts one write at a time: a project, a deployment, a private
  # endpoint and a diagnostic setting created in parallel race to 409
  # RequestConflict (A13 cycle 3). Each waits for the previous one.
  depends_on = [azapi_resource.project]

  body = {
    sku = {
      name     = var.deployment_sku
      capacity = var.capacity
    }
    properties = {
      model = {
        format  = "OpenAI"
        name    = var.model
        version = var.model_version
      }
    }
  }
}

resource "azurerm_private_endpoint" "account" {
  name                = "pe-aif-${var.name_suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint_subnet_id
  tags                = var.tags

  depends_on = [azapi_resource.deployment]

  private_service_connection {
    name                           = "account"
    private_connection_resource_id = azapi_resource.account.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "foundry"
    private_dns_zone_ids = var.private_dns_zone_ids
  }
}

# Pinned by GUID: Microsoft renamed "Azure AI User" to "Foundry User" and a
# name lookup fails on tenants that only carry the new name.
locals {
  azure_ai_user_role_id = "53ca6127-db72-4b80-b1b0-d745d6d5456d"
}

resource "azurerm_role_assignment" "ai_user" {
  scope              = azapi_resource.account.id
  role_definition_id = "/subscriptions/${split("/", azapi_resource.account.id)[2]}/providers/Microsoft.Authorization/roleDefinitions/${local.azure_ai_user_role_id}"
  principal_id       = var.user_principal_id
  principal_type     = "ServicePrincipal"
}

resource "azurerm_monitor_diagnostic_setting" "account" {
  name                       = "diag-aif"
  target_resource_id         = azapi_resource.account.id
  depends_on                 = [azurerm_private_endpoint.account]
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category_group = "allLogs"
  }

  enabled_metric {
    category = "AllMetrics"
  }
}

output "account_id" {
  value = azapi_resource.account.id
}

output "project_endpoint" {
  # The code expects <account endpoint>api/projects/<project>.
  value = "https://${local.account_name}.services.ai.azure.com/api/projects/${local.project_name}"
}

output "model" {
  value = var.model
}

output "role_assignments" {
  value = [{ principal = "api", role = "Azure AI User", scope = "foundry_account" }]
}
