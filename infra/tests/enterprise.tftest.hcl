# Enterprise profile (D25) under mock providers: Entra on, customer data, BYO
# network and Fabric, and the API identity holding exactly the roles in
# REQUIREMENTS section 6. No Key Vault unless asked for.

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

run "enterprise_profile" {
  command = apply

  assert {
    condition     = output.AUTH_MODE == "entra" && output.DATA_CLASSIFICATION == "customer"
    error_message = "enterprise must run AUTH_MODE=entra with DATA_CLASSIFICATION=customer"
  }

  assert {
    condition     = output.easy_auth_enabled
    error_message = "Easy Auth must be on for the enterprise web app"
  }

  assert {
    condition     = output.TCC_FABRIC_CREATED == "false" && output.FABRIC_WAREHOUSE_ID == var.fabric_warehouse_id
    error_message = "enterprise brings its own Fabric and must never be bootstrapped"
  }

  assert {
    condition = toset([for r in output.api_role_assignments : "${r.role}@${r.scope}"]) == toset([
      "Storage Blob Data Contributor@container:artifacts",
      "Storage Blob Data Contributor@container:outputs",
      "Azure AI User@foundry_account",
      "Monitoring Metrics Publisher@app_insights",
    ])
    error_message = "the API identity's roles must be exactly REQUIREMENTS section 6"
  }

  assert {
    condition     = length(output.web_role_assignments) == 1 && output.web_role_assignments[0].role == "Monitoring Metrics Publisher"
    error_message = "the web identity may only publish telemetry"
  }

  assert {
    condition     = module.keyvault.id == null
    error_message = "no Key Vault unless enable_key_vault"
  }

  assert {
    condition     = module.network.vnet_id == null && module.network.app_subnet_id == var.app_integration_subnet_id
    error_message = "enterprise must not create a network"
  }
}

run "a_missing_app_registration_fails" {
  command = plan
  variables {
    api_client_id = ""
  }
  expect_failures = [var.api_client_id]
}

run "a_missing_byo_subnet_fails" {
  command = plan
  variables {
    private_endpoint_subnet_id = ""
  }
  expect_failures = [var.private_endpoint_subnet_id]
}

run "key_vault_when_asked_for" {
  command = apply
  variables {
    enable_key_vault = true
    private_dns_zone_ids = {
      blob              = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-d/providers/Microsoft.Network/privateDnsZones/b"
      cognitiveservices = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-d/providers/Microsoft.Network/privateDnsZones/c"
      openai            = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-d/providers/Microsoft.Network/privateDnsZones/o"
      aiservices        = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-d/providers/Microsoft.Network/privateDnsZones/a"
      vault             = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-d/providers/Microsoft.Network/privateDnsZones/v"
      sites             = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-d/providers/Microsoft.Network/privateDnsZones/s"
    }
  }

  assert {
    condition     = contains([for r in output.api_role_assignments : r.role], "Key Vault Secrets User")
    error_message = "with a vault, the API reads secrets as Key Vault Secrets User"
  }
}
