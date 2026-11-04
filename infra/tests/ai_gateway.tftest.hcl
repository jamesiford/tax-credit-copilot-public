# AI-03: the model gateway settings and the PoC mock gateway, under mock
# providers. Two promises are tested: a default plan adds nothing (every new
# setting is emitted only when its variable is set), and nothing secret is ever
# written - a credential reaches the app only as a Key Vault reference.

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

run "public_defaults_add_no_ai_settings_and_no_mock" {
  command = apply

  assert {
    condition     = length(module.app_service.api_ai_settings) == 0
    error_message = "with no AI variable set the API receives no AI_* setting"
  }

  assert {
    condition     = output.mock_ai_gateway_url == "" && module.mock_ai_gateway.default_hostname == ""
    error_message = "no mock gateway unless enable_mock_ai_gateway"
  }
}

run "enterprise_defaults_add_no_ai_settings_and_no_mock" {
  command = apply
  variables {
    profile                    = "enterprise"
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

  assert {
    condition     = length(module.app_service.api_ai_settings) == 0
    error_message = "with no AI variable set the API receives no AI_* setting"
  }

  assert {
    condition     = output.mock_ai_gateway_url == "" && module.mock_ai_gateway.default_hostname == ""
    error_message = "no mock gateway unless enable_mock_ai_gateway"
  }
}

run "gateway_settings_reach_the_api_exactly_as_given" {
  command = apply
  variables {
    ai_provider_chain          = "foundry, gateway"
    ai_gateway_endpoint        = "https://gateway.example.com"
    ai_gateway_auth            = "entra_token"
    ai_gateway_entra_audience  = "api://00000000-0000-0000-0000-000000000000"
    ai_gateway_api_style       = "azure_deployments"
    ai_gateway_timeout_seconds = "45"
    ai_egress_policy           = "aggregates_only"
    ai_model_router            = "router-model"
    ai_model_narrator          = "narrator-model"
    ai_model_analysis          = "analysis-model"
    ai_foundry_connection_name = "byom"
  }

  assert {
    condition = nonsensitive(module.app_service.api_ai_settings) == {
      AI_PROVIDER_CHAIN          = "foundry,gateway"
      AI_GATEWAY_ENDPOINT        = "https://gateway.example.com"
      AI_GATEWAY_AUTH            = "entra_token"
      AI_GATEWAY_ENTRA_AUDIENCE  = "api://00000000-0000-0000-0000-000000000000"
      AI_GATEWAY_API_STYLE       = "azure_deployments"
      AI_GATEWAY_TIMEOUT_SECONDS = "45"
      AI_EGRESS_POLICY           = "aggregates_only"
      AI_MODEL_ROUTER            = "router-model"
      AI_MODEL_NARRATOR          = "narrator-model"
      AI_MODEL_ANALYSIS          = "analysis-model"
      AI_FOUNDRY_CONNECTION_NAME = "byom"
    }
    error_message = "exactly the variables that were set become settings, and nothing else"
  }
}

run "oauth_settings_carry_identifiers_and_no_secret" {
  command = apply
  variables {
    ai_gateway_endpoint        = "https://gateway.example.com"
    ai_gateway_auth            = "oauth_client_credentials"
    ai_gateway_oauth_token_url = "https://login.example.com/oauth2/token"
    ai_gateway_oauth_client_id = "00000000-0000-0000-0000-000000000005"
    ai_gateway_oauth_scope     = "api://gateway/.default"
  }

  assert {
    condition     = nonsensitive(module.app_service.api_ai_settings["AI_GATEWAY_OAUTH_TOKEN_URL"]) == "https://login.example.com/oauth2/token" && nonsensitive(module.app_service.api_ai_settings["AI_GATEWAY_OAUTH_CLIENT_ID"]) == "00000000-0000-0000-0000-000000000005"
    error_message = "the token endpoint and client id are plain settings"
  }

  assert {
    condition = alltrue([
      for k, v in module.app_service.api_ai_settings :
      !can(regex("KEY|SECRET|PASSWORD|TOKEN", k)) || startswith(v, "@Microsoft.KeyVault(") || (k == "AI_GATEWAY_OAUTH_TOKEN_URL" && startswith(v, "https://"))
    ])
    error_message = "a setting named like a credential may only be a Key Vault reference (or the token endpoint URL)"
  }

  assert {
    condition     = !contains(keys(module.app_service.api_ai_settings), "AI_GATEWAY_OAUTH_CLIENT_SECRET") && !contains(keys(module.app_service.api_ai_settings), "AI_GATEWAY_API_KEY")
    error_message = "without a vault and a secret name there is no credential setting"
  }
}

run "key_vault_references_need_a_vault_and_a_secret_name" {
  command = apply
  variables {
    enable_key_vault               = true
    ai_gateway_endpoint            = "https://gateway.example.com"
    ai_gateway_auth                = "api_key"
    ai_gateway_api_key_secret_name = "gateway-api-key"
  }

  assert {
    condition     = module.app_service.api_ai_settings["AI_GATEWAY_API_KEY"] == "@Microsoft.KeyVault(VaultName=${module.keyvault.name};SecretName=gateway-api-key)"
    error_message = "the key is a Key Vault reference to the vault the keyvault module created"
  }

  assert {
    condition     = !contains(keys(module.app_service.api_ai_settings), "AI_GATEWAY_OAUTH_CLIENT_SECRET")
    error_message = "a secret with no name set gets no setting"
  }

  assert {
    condition = alltrue([
      for k, v in module.app_service.api_ai_settings :
      !can(regex("KEY|SECRET|PASSWORD|TOKEN", k)) || startswith(v, "@Microsoft.KeyVault(")
    ])
    error_message = "a setting named like a credential may only be a Key Vault reference"
  }
}

run "both_references_when_both_names_are_set" {
  command = apply
  variables {
    enable_key_vault               = true
    ai_gateway_api_key_secret_name = "gateway-api-key"
    ai_gateway_oauth_secret_name   = "gateway-oauth-secret"
  }

  assert {
    condition = (
      module.app_service.api_ai_settings["AI_GATEWAY_API_KEY"] == "@Microsoft.KeyVault(VaultName=${module.keyvault.name};SecretName=gateway-api-key)" &&
      module.app_service.api_ai_settings["AI_GATEWAY_OAUTH_CLIENT_SECRET"] == "@Microsoft.KeyVault(VaultName=${module.keyvault.name};SecretName=gateway-oauth-secret)"
    )
    error_message = "each secret name becomes its own Key Vault reference"
  }
}

run "a_key_vault_with_no_secret_name_adds_nothing" {
  command = apply
  variables {
    enable_key_vault = true
  }

  assert {
    condition     = length(module.app_service.api_ai_settings) == 0
    error_message = "enabling the vault alone adds no AI setting"
  }
}

run "an_api_key_secret_name_without_a_vault_fails" {
  command = plan
  variables {
    ai_gateway_api_key_secret_name = "gateway-api-key"
  }
  expect_failures = [var.ai_gateway_api_key_secret_name]
}

run "an_oauth_secret_name_without_a_vault_fails" {
  command = plan
  variables {
    ai_gateway_oauth_secret_name = "gateway-oauth-secret"
  }
  expect_failures = [var.ai_gateway_oauth_secret_name]
}

run "an_unknown_gateway_auth_fails" {
  command = plan
  variables {
    ai_gateway_auth = "basic"
  }
  expect_failures = [var.ai_gateway_auth]
}

run "an_unknown_provider_fails" {
  command = plan
  variables {
    ai_provider_chain = "foundry,openai"
  }
  expect_failures = [var.ai_provider_chain]
}

run "an_unknown_egress_policy_fails" {
  command = plan
  variables {
    ai_egress_policy = "open"
  }
  expect_failures = [var.ai_egress_policy]
}

run "an_unknown_api_style_fails" {
  command = plan
  variables {
    ai_gateway_api_style = "v2"
  }
  expect_failures = [var.ai_gateway_api_style]
}

run "the_mock_gateway_is_created_on_public_when_asked" {
  command = apply
  variables {
    enable_mock_ai_gateway = true
    mock_ai_gateway_auth   = "entra"
  }

  assert {
    condition     = output.mock_ai_gateway_url == "https://app-test.azurewebsites.net"
    error_message = "the mock's URL is output when it is enabled"
  }
}

run "the_mock_gateway_refuses_the_enterprise_profile" {
  command = plan
  variables {
    profile                    = "enterprise"
    enable_mock_ai_gateway     = true
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
  expect_failures = [var.enable_mock_ai_gateway]
}

run "an_unknown_mock_auth_fails" {
  command = plan
  variables {
    mock_ai_gateway_auth = "basic"
  }
  expect_failures = [var.mock_ai_gateway_auth]
}

run "the_mock_module_creates_nothing_when_disabled" {
  command = apply
  module {
    source = "./modules/mock_ai_gateway"
  }
  variables {
    enabled               = false
    name_suffix           = "test0001"
    resource_group_name   = "rg-test"
    location              = "westus3"
    tags                  = {}
    service_plan_id       = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Web/serverFarms/asp-test"
    integration_subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/v/subnets/app"
    mock_auth             = "none"
    entra_audience        = "api://mock-gateway"
  }

  assert {
    condition     = length(azurerm_linux_web_app.this) == 0 && output.default_hostname == ""
    error_message = "enabled = false creates nothing"
  }
}

run "the_mock_module_is_one_locked_down_poc_app_when_enabled" {
  command = apply
  module {
    source = "./modules/mock_ai_gateway"
  }
  variables {
    enabled               = true
    name_suffix           = "test0001"
    resource_group_name   = "rg-test"
    location              = "westus3"
    tags                  = { application = "tax-credit-copilot" }
    service_plan_id       = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Web/serverFarms/asp-test"
    integration_subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/v/subnets/app"
    mock_auth             = "api_key"
    entra_audience        = "api://mock-gateway"
  }

  assert {
    condition     = length(azurerm_linux_web_app.this) == 1 && azurerm_linux_web_app.this[0].tags["purpose"] == "poc-mock" && azurerm_linux_web_app.this[0].tags["application"] == "tax-credit-copilot"
    error_message = "exactly one app, tagged purpose = poc-mock on top of the common tags"
  }

  assert {
    condition = (
      azurerm_linux_web_app.this[0].https_only &&
      azurerm_linux_web_app.this[0].site_config[0].minimum_tls_version == "1.2" &&
      azurerm_linux_web_app.this[0].site_config[0].application_stack[0].python_version == "3.12"
    )
    error_message = "HTTPS only, TLS 1.2, Python 3.12"
  }

  assert {
    condition = (
      azurerm_linux_web_app.this[0].site_config[0].ip_restriction_default_action == "Deny" &&
      length(azurerm_linux_web_app.this[0].site_config[0].ip_restriction) == 1 &&
      azurerm_linux_web_app.this[0].site_config[0].ip_restriction[0].virtual_network_subnet_id == var.integration_subnet_id &&
      azurerm_linux_web_app.this[0].virtual_network_subnet_id == var.integration_subnet_id
    )
    error_message = "inbound is denied except from the integration subnet the API shares"
  }

  assert {
    condition     = azurerm_linux_web_app.this[0].app_settings["MOCK_AUTH"] == "api_key" && azurerm_linux_web_app.this[0].app_settings["WEBSITES_PORT"] == "8000"
    error_message = "the mock reads its auth scheme and port from settings"
  }

  assert {
    condition     = !anytrue([for k, v in azurerm_linux_web_app.this[0].app_settings : can(regex("KEY|SECRET|PASSWORD|TOKEN", k))])
    error_message = "the mock carries no secret setting"
  }
}
