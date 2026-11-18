mock_provider "azurerm" {
  source = "./tests/mocks"
}

variables {
  service_name               = "dotnet-api"
  name                       = "app-tcc-dotnet-test-api"
  resource_group_name        = "rg-tcc-dotnet-test"
  location                   = "westus3"
  tags                       = {}
  service_plan_id            = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-tcc-dotnet-test/providers/Microsoft.Web/serverFarms/asp-tcc-dotnet-test"
  dll                        = "TaxCredit.Api.dll"
  integration_subnet_id      = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.Network/virtualNetworks/external/subnets/app"
  private_endpoint_subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.Network/virtualNetworks/external/subnets/pe"
  sites_private_dns_zone_id  = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.Network/privateDnsZones/privatelink.azurewebsites.net"
  identity_id                = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-tcc-dotnet-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-tcc-dotnet-api"
  identity_client_id         = "00000000-0000-0000-0000-000000000011"
  log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.OperationalInsights/workspaces/log"
  app_settings = {
    ENVIRONMENT                      = "azure"
    PERSISTENCE_PROVIDER             = "warehouse"
    DATA_SOURCE                      = "lakehouse"
    ARTIFACT_STORE                   = "blob"
    AUTH_MODE                        = "entra"
    CONTRACT_HOOKS                   = "0"
    CHANNEL_ENFORCE_WRITER_FOR_USERS = "true"
  }
}

run "http_host_security_is_in_the_resource" {
  command = apply
  module {
    source = "./modules/http_service"
  }
  assert {
    condition = (
      azurerm_linux_web_app.this.https_only &&
      !azurerm_linux_web_app.this.public_network_access_enabled &&
      !azurerm_linux_web_app.this.ftp_publish_basic_authentication_enabled &&
      !azurerm_linux_web_app.this.webdeploy_publish_basic_authentication_enabled &&
      !azurerm_linux_web_app.this.client_affinity_enabled &&
      azurerm_linux_web_app.this.site_config[0].minimum_tls_version == "1.2" &&
      azurerm_linux_web_app.this.site_config[0].scm_minimum_tls_version == "1.2" &&
      azurerm_linux_web_app.this.site_config[0].ftps_state == "Disabled"
    )
    error_message = "HTTPS/TLS must be enforced; public origin, basic publishing and sticky-session durability substitutes must be off."
  }
  assert {
    condition = (
      azurerm_linux_web_app.this.site_config[0].ip_restriction_default_action == "Deny" &&
      azurerm_linux_web_app.this.site_config[0].scm_ip_restriction_default_action == "Deny" &&
      azurerm_linux_web_app.this.site_config[0].scm_use_main_ip_restriction &&
      length(azurerm_linux_web_app.this.site_config[0].ip_restriction) == 0 &&
      length(azurerm_linux_web_app.this.site_config[0].scm_ip_restriction) == 0 &&
      azurerm_linux_web_app.this.site_config[0].vnet_route_all_enabled &&
      azurerm_linux_web_app.this.site_config[0].worker_count == 1
    )
    error_message = "App and SCM must deny public access with no allow exceptions; outbound must use the existing VNet."
  }
  assert {
    condition = (
      azurerm_linux_web_app.this.site_config[0].application_stack[0].dotnet_version == "10.0" &&
      azurerm_linux_web_app.this.site_config[0].app_command_line == "dotnet TaxCredit.Api.dll" &&
      azurerm_linux_web_app.this.site_config[0].health_check_path == "/api/health" &&
      azurerm_linux_web_app.this.app_settings.SCM_DO_BUILD_DURING_DEPLOYMENT == "false" &&
      azurerm_linux_web_app.this.app_settings.WEBSITE_RUN_FROM_PACKAGE == "1" &&
      azurerm_linux_web_app.this.app_settings.ASPNETCORE_URLS == "http://0.0.0.0:8080" &&
      azurerm_linux_web_app.this.app_settings.ASPNETCORE_ENVIRONMENT == "Production"
    )
    error_message = "Use .NET 10 code deployment, the real HTTP entry point, fixed listener and liveness path; no remote build."
  }
  assert {
    condition = (
      azurerm_linux_web_app.this.identity[0].type == "UserAssigned" &&
      toset(azurerm_linux_web_app.this.identity[0].identity_ids) == toset([var.identity_id]) &&
      !azurerm_linux_web_app.this.logs[0].detailed_error_messages &&
      !azurerm_linux_web_app.this.logs[0].failed_request_tracing &&
      length(azurerm_linux_web_app.this.logs[0].http_logs) == 0 &&
      length(azurerm_linux_web_app.this.logs[0].application_logs) == 0 &&
      length(azurerm_monitor_diagnostic_setting.this.enabled_log) == 0 &&
      length(azurerm_monitor_diagnostic_setting.this.enabled_metric) == 1
    )
    error_message = "Attach only the service identity and never enable request/error/application log collection."
  }
  assert {
    condition = (
      azurerm_private_endpoint.this.private_service_connection[0].private_connection_resource_id == azurerm_linux_web_app.this.id &&
      toset(azurerm_private_endpoint.this.private_service_connection[0].subresource_names) == toset(["sites"]) &&
      !azurerm_private_endpoint.this.private_service_connection[0].is_manual_connection &&
      toset(azurerm_private_endpoint.this.private_dns_zone_group[0].private_dns_zone_ids) == toset([var.sites_private_dns_zone_id])
    )
    error_message = "New app/SCM endpoints must target only their new app and the existing sites zone."
  }
}

run "wrong_dll_cannot_be_substituted" {
  command = plan
  module {
    source = "./modules/http_service"
  }
  variables {
    dll = "TaxCredit.Worker.dll"
  }
  expect_failures = [var.dll]
}

run "python_resource_name_cannot_be_adopted" {
  command = plan
  module {
    source = "./modules/http_service"
  }
  variables {
    name = "app-tcc-api-test"
  }
  expect_failures = [var.name]
}

run "deployed_local_store_cannot_be_substituted" {
  command = plan
  module {
    source = "./modules/http_service"
  }
  variables {
    app_settings = {
      ENVIRONMENT                      = "azure"
      PERSISTENCE_PROVIDER             = "sqlite"
      DATA_SOURCE                      = "csv"
      ARTIFACT_STORE                   = "local"
      AUTH_MODE                        = "none"
      CONTRACT_HOOKS                   = "1"
      CHANNEL_ENFORCE_WRITER_FOR_USERS = "false"
    }
  }
  expect_failures = [var.app_settings]
}

run "unsupported_runtime_flags_are_rejected" {
  command = plan
  module {
    source = "./modules/http_service"
  }
  variables {
    app_settings = {
      ENVIRONMENT                      = "azure"
      PERSISTENCE_PROVIDER             = "warehouse"
      DATA_SOURCE                      = "lakehouse"
      ARTIFACT_STORE                   = "blob"
      AUTH_MODE                        = "entra"
      CONTRACT_HOOKS                   = "0"
      CHANNEL_ENFORCE_WRITER_FOR_USERS = "true"
      RUN_LEASE_SECONDS                = "600"
    }
  }
  expect_failures = [var.app_settings]
}
