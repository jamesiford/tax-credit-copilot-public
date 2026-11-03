# CH-07: the Microsoft 365 channel gateway, under mock providers.
#
# Two promises are tested. With the toggle off (the default) the module creates
# nothing and nothing else changes: every existing test in this directory runs with
# it off and is unedited. With it on, exactly the gateway's resources appear, the
# gateway is HTTPS-only, shares the integration subnet and holds no secret, and the
# API's inbound restriction is exactly what it was.

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

run "off_creates_nothing_and_says_so" {
  command = apply

  assert {
    condition     = length(module.channel.resource_types) == 0
    error_message = "with enable_m365_channel off the channel module creates no resource"
  }

  assert {
    condition     = module.channel.app == null && output.CHANNEL_APP_NAME == "" && output.CHANNEL_BASE_URL == ""
    error_message = "with the channel off there is no gateway app and its outputs are empty"
  }

  assert {
    condition     = output.GATEWAY_IDENTITY_NAME == "" && output.GATEWAY_IDENTITY_PRINCIPAL_ID == "" && output.GATEWAY_IDENTITY_CLIENT_ID == ""
    error_message = "with the channel off there is no gateway identity to grant"
  }
}

run "off_leaves_the_api_restriction_as_it_was" {
  command = apply

  assert {
    condition = module.app_service.api_access_restriction == {
      default_action = "Deny"
      allowed = [{
        name      = "web-app-subnet"
        priority  = 100
        action    = "Allow"
        subnet_id = module.network.app_subnet_id
      }]
    }
    error_message = "the API admits only the integration subnet, default deny"
  }
}

run "on_creates_exactly_the_gateway" {
  command = apply
  variables {
    enable_m365_channel      = true
    channel_gateway_audience = "api://00000000-0000-0000-0000-0000000000c1"
    auth_mode                = "entra"
    api_client_id            = "00000000-0000-0000-0000-0000000000a1"
  }

  assert {
    condition = toset(module.channel.resource_types) == toset([
      "azurerm_linux_web_app",
      "azurerm_monitor_diagnostic_setting",
      "azurerm_role_assignment",
      "azurerm_user_assigned_identity",
    ]) && length(module.channel.resource_types) == 4
    error_message = "the gateway is one identity, one app, one telemetry role and one diagnostic setting, and nothing else"
  }

  assert {
    condition     = startswith(output.CHANNEL_APP_NAME, "app-tcc-channel-") && startswith(output.GATEWAY_IDENTITY_NAME, "id-tcc-channel-")
    error_message = "the names follow the other apps"
  }

  assert {
    condition     = output.CHANNEL_BASE_URL != "" && output.GATEWAY_IDENTITY_PRINCIPAL_ID != ""
    error_message = "the URL and the principal the operator grants roles to are emitted"
  }
}

run "on_is_https_only_keyless_and_in_the_shared_subnet" {
  command = apply
  variables {
    enable_m365_channel      = true
    channel_gateway_audience = "api://00000000-0000-0000-0000-0000000000c1"
    auth_mode                = "entra"
    api_client_id            = "00000000-0000-0000-0000-0000000000a1"
  }

  assert {
    condition = (
      module.channel.app.https_only
      && module.channel.app.minimum_tls_version == "1.2"
      && module.channel.app.ftps_state == "Disabled"
      && !module.channel.app.ftp_basic_auth
      && !module.channel.app.webdeploy_basic_auth
      && module.channel.app.always_on
    )
    error_message = "HTTPS only, TLS 1.2, FTPS off, basic-auth publishing off, always on"
  }

  assert {
    condition = (
      module.channel.app.virtual_network_subnet_id == module.network.app_subnet_id
      && module.channel.app.vnet_route_all_enabled
    )
    error_message = "the gateway integrates with the API's own subnet and routes everything through it"
  }

  assert {
    condition = (
      module.channel.app.app_command_line == "sh startup-channel.sh"
      && module.channel.app.python_version == "3.12"
      && !contains(keys(module.channel.app.tags), "azd-service-name")
    )
    error_message = "Python 3.12, startup-channel.sh, and no azd-service-name tag: azd has no channel service, the deploy-channel hook deploys it"
  }

  assert {
    condition     = module.channel.app.ip_restriction_default_action == "Allow" && length(module.channel.app.ip_restriction_ranges) == 0
    error_message = "with no ranges given inbound is open: callers are authenticated by token, in the app"
  }

  assert {
    condition = alltrue([
      for k, v in module.channel.settings :
      !can(regex("(?i)(secret|password|api_?key|access_?key|private|credential)", k))
      && !can(regex("(?i)(secret|password|accountkey|sharedaccess|sig=|instrumentationkey|@Microsoft\\.KeyVault)", v))
    ])
    error_message = "no setting name or value looks like a secret"
  }

  assert {
    condition = sort(keys(module.channel.settings)) == sort([
      "API_AUDIENCE", "API_BASE_URL", "CHANNEL_STORE", "CHANNEL_WRITER_SOURCE", "DATA_CLASSIFICATION",
      "ENVIRONMENT", "FABRIC_WORKSPACE", "GATEWAY_AUDIENCE", "TENANT_ID", "WAREHOUSE_DATABASE",
      "WAREHOUSE_SERVER", "WEB_CONCURRENCY",
    ])
    error_message = "exactly the documented settings, and no optional one that was not set"
  }

  assert {
    condition = (
      module.channel.settings["CHANNEL_STORE"] == "warehouse"
      && module.channel.settings["GATEWAY_AUDIENCE"] == "api://00000000-0000-0000-0000-0000000000c1"
      && module.channel.settings["API_AUDIENCE"] == "api://00000000-0000-0000-0000-0000000000a1"
      && module.channel.settings["WEB_CONCURRENCY"] == "1"
      && module.channel.settings["API_BASE_URL"] == module.app_service.api_url
    )
    error_message = "the store is the Warehouse, the audiences are the two registrations, and the API is reached at its own hostname"
  }

  assert {
    condition     = alltrue([for n in ["APPLICATIONINSIGHTS_CONNECTION_STRING", "APPLICATIONINSIGHTS_AUTHENTICATION_STRING", "AZURE_CLIENT_ID"] : contains(module.channel.app.app_setting_names, n)])
    error_message = "telemetry uses the gateway's own managed identity, as the other apps do"
  }
}

run "on_does_not_widen_the_api_restriction" {
  command = apply
  variables {
    enable_m365_channel      = true
    channel_gateway_audience = "api://00000000-0000-0000-0000-0000000000c1"
    auth_mode                = "entra"
    api_client_id            = "00000000-0000-0000-0000-0000000000a1"
  }

  assert {
    condition = module.app_service.api_access_restriction == {
      default_action = "Deny"
      allowed = [{
        name      = "web-app-subnet"
        priority  = 100
        action    = "Allow"
        subnet_id = module.network.app_subnet_id
      }]
    }
    error_message = "the API restriction is exactly what it was: default deny, the integration subnet only. The gateway is admitted because it shares that subnet"
  }
}

run "optional_settings_appear_only_when_set" {
  command = apply
  variables {
    enable_m365_channel            = true
    channel_gateway_audience       = "api://00000000-0000-0000-0000-0000000000c1"
    auth_mode                      = "entra"
    api_client_id                  = "00000000-0000-0000-0000-0000000000a1"
    channel_allowed_caller_app_ids = ["00000000-0000-0000-0000-0000000000d1", "00000000-0000-0000-0000-0000000000d2"]
    channel_writer_source          = "either"
    channel_writer_group_id        = "00000000-0000-0000-0000-0000000000e1"
    git_commit                     = "0123456789abcdef"
  }

  assert {
    condition = (
      module.channel.settings["CHANNEL_ALLOWED_CALLER_APP_IDS"] == "00000000-0000-0000-0000-0000000000d1,00000000-0000-0000-0000-0000000000d2"
      && module.channel.settings["CHANNEL_WRITER_SOURCE"] == "either"
      && module.channel.settings["CHANNEL_WRITER_GROUP_ID"] == "00000000-0000-0000-0000-0000000000e1"
      && module.channel.settings["GIT_COMMIT"] == "0123456789abcdef"
    )
    error_message = "the allow-list, the writer source and group and the commit reach the gateway as given"
  }
}

run "ip_ranges_close_inbound_to_those_ranges" {
  command = apply
  variables {
    enable_m365_channel       = true
    channel_gateway_audience  = "api://00000000-0000-0000-0000-0000000000c1"
    auth_mode                 = "entra"
    api_client_id             = "00000000-0000-0000-0000-0000000000a1"
    channel_allowed_ip_ranges = ["203.0.113.0/24", "198.51.100.7/32"]
  }

  assert {
    condition     = module.channel.app.ip_restriction_default_action == "Deny" && module.channel.app.ip_restriction_ranges == ["203.0.113.0/24", "198.51.100.7/32"]
    error_message = "a non-empty range list denies everything else"
  }
}

run "the_audience_is_required_when_the_channel_is_on" {
  command = plan
  variables {
    enable_m365_channel = true
    auth_mode           = "entra"
    api_client_id       = "00000000-0000-0000-0000-0000000000a1"
  }
  expect_failures = [var.channel_gateway_audience]
}

run "a_group_source_needs_a_group" {
  command = plan
  variables {
    channel_writer_source = "entra_group"
  }
  expect_failures = [var.channel_writer_group_id]
}

run "an_unknown_writer_source_is_refused" {
  command = plan
  variables {
    channel_writer_source = "everyone"
  }
  expect_failures = [var.channel_writer_source]
}

run "the_api_must_validate_tokens" {
  command = plan
  variables {
    enable_m365_channel      = true
    channel_gateway_audience = "api://00000000-0000-0000-0000-0000000000c1"
  }
  expect_failures = [output.CHANNEL_APP_NAME]
}

run "the_enterprise_profile_refuses_the_channel" {
  command = plan
  variables {
    profile                    = "enterprise"
    enable_m365_channel        = true
    channel_gateway_audience   = "api://00000000-0000-0000-0000-0000000000c1"
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
  expect_failures = [var.enable_m365_channel]
}

run "enterprise_with_the_channel_off_is_unchanged" {
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
    condition     = length(module.channel.resource_types) == 0 && output.CHANNEL_APP_NAME == "" && output.GATEWAY_IDENTITY_NAME == ""
    error_message = "enterprise with the toggle off has no gateway"
  }

  assert {
    condition = (
      output.easy_auth_enabled
      && output.AUTH_MODE == "entra"
      && module.app_service.api_access_restriction.default_action == "Deny"
      && length(module.app_service.api_access_restriction.allowed) == 1
    )
    error_message = "the enterprise posture is as it was: Easy Auth on, Entra, an API that admits one subnet"
  }
}
