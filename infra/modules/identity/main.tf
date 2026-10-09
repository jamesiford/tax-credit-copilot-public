# Two user-assigned identities (SEC-1): the API holds every data permission;
# the web app may only publish telemetry. Apps pin them with AZURE_CLIENT_ID.

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

resource "azurerm_user_assigned_identity" "api" {
  name                = "id-tcc-api-${var.name_suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
}

resource "azurerm_user_assigned_identity" "web" {
  name                = "id-tcc-web-${var.name_suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
}

output "api" {
  value = {
    id           = azurerm_user_assigned_identity.api.id
    name         = azurerm_user_assigned_identity.api.name
    principal_id = azurerm_user_assigned_identity.api.principal_id
    client_id    = azurerm_user_assigned_identity.api.client_id
  }
}

output "web" {
  value = {
    id           = azurerm_user_assigned_identity.web.id
    name         = azurerm_user_assigned_identity.web.name
    principal_id = azurerm_user_assigned_identity.web.principal_id
    client_id    = azurerm_user_assigned_identity.web.client_id
  }
}
