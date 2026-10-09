# Realistic id shapes for mocked resources: azurerm validates resource ids that
# flow from one resource into another, even under a mock provider.

mock_data "azurerm_client_config" {
  defaults = {
    subscription_id = "00000000-0000-0000-0000-000000000000"
    tenant_id       = "00000000-0000-0000-0000-0000000000aa"
    client_id       = "00000000-0000-0000-0000-0000000000cc"
    object_id       = "00000000-0000-0000-0000-0000000000dd"
  }
}

mock_resource "azurerm_resource_group" {
  defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test" }
}

mock_resource "azurerm_user_assigned_identity" {
  defaults = {
    id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-test"
    principal_id = "00000000-0000-0000-0000-0000000000bb"
    client_id    = "00000000-0000-0000-0000-0000000000ee"
  }
}

mock_resource "azurerm_log_analytics_workspace" {
  defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.OperationalInsights/workspaces/log-test" }
}

mock_resource "azurerm_application_insights" {
  defaults = {
    id                = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Insights/components/appi-test"
    connection_string = "InstrumentationKey=00000000-0000-0000-0000-000000000000"
  }
}

mock_resource "azurerm_virtual_network" {
  defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-test" }
}

mock_resource "azurerm_subnet" {
  defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-test/subnets/snet-test" }
}

mock_resource "azurerm_private_dns_zone" {
  defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/privateDnsZones/privatelink.test" }
}

mock_resource "azurerm_storage_account" {
  defaults = {
    id                    = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Storage/storageAccounts/sttest"
    primary_blob_endpoint = "https://sttest.blob.core.windows.net/"
  }
}

mock_resource "azurerm_storage_container" {
  defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Storage/storageAccounts/sttest/blobServices/default/containers/c" }
}

mock_resource "azurerm_service_plan" {
  defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Web/serverFarms/asp-test" }
}

mock_resource "azurerm_linux_web_app" {
  defaults = {
    id               = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Web/sites/app-test"
    default_hostname = "app-test.azurewebsites.net"
  }
}

mock_resource "azurerm_key_vault" {
  defaults = {
    id        = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.KeyVault/vaults/kv-test"
    vault_uri = "https://kv-test.vault.azure.net/"
  }
}

mock_resource "azurerm_fabric_capacity" {
  defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Fabric/capacities/fctest" }
}
