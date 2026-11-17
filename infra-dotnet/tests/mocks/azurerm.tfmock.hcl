mock_resource "azurerm_resource_group" {
  defaults = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-tcc-dotnet-test"
  }
}
mock_resource "azurerm_service_plan" {
  defaults = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-tcc-dotnet-test/providers/Microsoft.Web/serverFarms/asp-tcc-dotnet-test"
  }
}
mock_resource "azurerm_user_assigned_identity" {
  defaults = {
    id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-tcc-dotnet-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-tcc-dotnet-test"
    client_id    = "00000000-0000-0000-0000-000000000011"
    principal_id = "00000000-0000-0000-0000-000000000012"
    tenant_id    = "00000000-0000-0000-0000-000000000001"
  }
}
mock_resource "azurerm_linux_web_app" {
  defaults = {
    id               = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-tcc-dotnet-test/providers/Microsoft.Web/sites/app-tcc-dotnet-test"
    default_hostname = "app-tcc-dotnet-test.azurewebsites.net"
  }
}
mock_resource "azurerm_private_endpoint" {
  defaults = {
    id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-tcc-dotnet-test/providers/Microsoft.Network/privateEndpoints/pe-tcc-dotnet-test"
  }
}
