# Public profile (D25) under mock providers: no Easy Auth, synthetic data, a
# created network and private endpoints, and Fabric only when create_fabric.

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
  profile               = "public"
  environment_name      = "tcc-test"
  location              = "westus3"
  fabric_capacity_admin = "admin@example.com"
}

run "public_profile" {
  command = apply

  assert {
    condition     = !output.easy_auth_enabled && output.AUTH_MODE == "none"
    error_message = "the public profile runs without Easy Auth and with AUTH_MODE=none"
  }

  assert {
    condition     = output.DATA_CLASSIFICATION == "synthetic"
    error_message = "the public profile serves synthetic data only"
  }

  assert {
    condition     = module.network.vnet_id != null && module.network.app_subnet_id != "" && module.network.private_endpoint_subnet_id != ""
    error_message = "the public profile creates its own VNet and subnets (NET-5)"
  }

  assert {
    condition     = alltrue([for k in ["blob", "cognitiveservices", "openai", "aiservices"] : contains(keys(module.network.private_dns_zone_ids), k)])
    error_message = "the public profile creates the private DNS zones its endpoints need"
  }

  assert {
    condition     = output.TCC_FABRIC_CREATED == "true" && module.fabric.capacity_id != null
    error_message = "create_fabric defaults to true for public and creates the capacity"
  }
}

run "public_without_fabric" {
  command = apply
  variables {
    create_fabric        = false
    manage_fabric_access = false
    fabric_workspace_id  = "00000000-0000-0000-0000-000000000003"
    fabric_warehouse_id  = "00000000-0000-0000-0000-000000000004"
    warehouse_server     = "example.datawarehouse.fabric.microsoft.com"
    warehouse_database   = "wh"
  }

  assert {
    condition     = output.TCC_FABRIC_CREATED == "false" && module.fabric.capacity_id == null
    error_message = "create_fabric = false creates no Fabric resources"
  }
}

run "capacity_admin_is_required_when_creating_fabric" {
  command = plan
  variables {
    fabric_capacity_admin = ""
  }
  expect_failures = [var.fabric_capacity_admin]
}
