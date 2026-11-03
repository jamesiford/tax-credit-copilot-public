# CH-12b: the enterprise profile refuses the demo Foundry posture, however it is asked.
#
# Its own file because the enterprise profile needs the bring-your-own network and Fabric
# values (see enterprise.tftest.hcl, which this mirrors and does not edit).

mock_provider "azurerm" {
  source = "./tests/mocks"
}
mock_provider "azapi" {
  source = "./tests/mocks"
}
mock_provider "fabric" {
  source = "./tests/mocks"
}

variables {
  profile                    = "enterprise"
  environment_name           = "tcc-test"
  location                   = "eastus2"
  tenant_id                  = "00000000-0000-0000-0000-0000000000aa"
  web_client_id              = "00000000-0000-0000-0000-000000000001"
  api_client_id              = "00000000-0000-0000-0000-000000000002"
  app_integration_subnet_id  = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-n/providers/Microsoft.Network/virtualNetworks/v/subnets/app"
  private_endpoint_subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-n/providers/Microsoft.Network/virtualNetworks/v/subnets/pe"
  private_dns_zone_ids = {
    blob              = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-d/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
    cognitiveservices = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-d/providers/Microsoft.Network/privateDnsZones/privatelink.cognitiveservices.azure.com"
    openai            = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-d/providers/Microsoft.Network/privateDnsZones/privatelink.openai.azure.com"
    aiservices        = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-d/providers/Microsoft.Network/privateDnsZones/privatelink.services.ai.azure.com"
    sites             = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-d/providers/Microsoft.Network/privateDnsZones/privatelink.azurewebsites.net"
  }
  fabric_workspace_id   = "00000000-0000-0000-0000-000000000003"
  fabric_workspace_name = "customer-workspace"
  fabric_lakehouse_name = "customer_lakehouse"
  fabric_warehouse_id   = "00000000-0000-0000-0000-000000000004"
  warehouse_server      = "example.datawarehouse.fabric.microsoft.com"
  warehouse_database    = "customer_warehouse"
}

run "enterprise_stays_private_by_default" {
  command = apply

  assert {
    condition = module.foundry.network_settings == {
      public_network_access = "Disabled"
      default_action        = "Deny"
      ip_rules              = []
      local_auth_disabled   = true
    }
    error_message = "the enterprise Foundry account is private, as it has always been"
  }

  assert {
    condition     = output.network_posture == "private"
    error_message = "the enterprise posture is private"
  }
}

run "enterprise_refuses_the_demo_posture" {
  command = plan

  variables {
    foundry_public_network_access = true
  }

  expect_failures = [var.foundry_public_network_access]
}
