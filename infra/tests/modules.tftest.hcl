# Module-level security assertions (BLOB-1, HOST-1, HOST-2, AUTH-2, FAB-1),
# run against each module directly so its resources can be inspected.

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
  name_suffix                = "test0001"
  resource_group_name        = "rg-test"
  location                   = "westus3"
  tags                       = {}
  log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.OperationalInsights/workspaces/log"
  private_endpoint_subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/v/subnets/pe"
}

run "storage_is_closed_and_managed_on_the_management_plane" {
  command = apply
  module {
    source = "./modules/storage"
  }
  variables {
    blob_private_dns_zone_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
    data_principal_id        = "00000000-0000-0000-0000-0000000000bb"
    outputs_retention_days   = 2555
  }

  assert {
    condition = (
      azurerm_storage_account.this.public_network_access_enabled == false &&
      azurerm_storage_account.this.shared_access_key_enabled == false &&
      azurerm_storage_account.this.allow_nested_items_to_be_public == false
    )
    error_message = "public network access, shared key and anonymous access must all be off"
  }

  assert {
    condition     = azurerm_storage_account.this.min_tls_version == "TLS1_2" && azurerm_storage_account.this.https_traffic_only_enabled
    error_message = "TLS 1.2 and HTTPS only"
  }

  assert {
    condition     = azurerm_storage_account.this.blob_properties[0].versioning_enabled
    error_message = "blob versioning must be on"
  }

  assert {
    condition = alltrue([
      for c in azurerm_storage_container.this :
      c.storage_account_id == azurerm_storage_account.this.id && c.storage_account_name == null
    ])
    error_message = "containers must be created through storage_account_id (management plane), never storage_account_name"
  }

  assert {
    condition     = toset(keys(azurerm_storage_container.this)) == toset(["artifacts", "outputs"])
    error_message = "containers are exactly artifacts and outputs (BLOB-2)"
  }

  assert {
    condition     = azurerm_storage_management_policy.outputs.rule[0].actions[0].base_blob[0].delete_after_days_since_creation_greater_than == 2555
    error_message = "the outputs lifecycle follows outputs_retention_days (D9)"
  }

  assert {
    condition     = contains(azurerm_private_endpoint.blob.private_service_connection[0].subresource_names, "blob")
    error_message = "blob is reached over a private endpoint"
  }
}

run "apps_are_hardened_and_easy_auth_is_on_when_configured" {
  command = apply
  module {
    source = "./modules/app_service"
  }
  variables {
    sku_name                       = "P1v3"
    app_subnet_id                  = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/v/subnets/app"
    sites_private_dns_zone_id      = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/privateDnsZones/privatelink.azurewebsites.net"
    web_inbound                    = "private_endpoint"
    web_allowed_ip_ranges          = []
    api_identity                   = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/api", client_id = "11111111-1111-1111-1111-111111111111" }
    web_identity                   = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/web", client_id = "22222222-2222-2222-2222-222222222222" }
    api_app_settings               = { ENVIRONMENT = "azure" }
    web_app_settings               = {}
    app_insights_connection_string = "InstrumentationKey=00000000-0000-0000-0000-000000000000"
    easy_auth = {
      tenant_id     = "00000000-0000-0000-0000-0000000000aa"
      web_client_id = "00000000-0000-0000-0000-000000000001"
      api_scope     = "api://00000000-0000-0000-0000-000000000002/user_impersonation"
    }
  }

  assert {
    condition     = azurerm_linux_web_app.api.https_only && azurerm_linux_web_app.web.https_only
    error_message = "both apps are HTTPS only"
  }

  assert {
    condition     = azurerm_linux_web_app.api.site_config[0].minimum_tls_version == "1.2" && azurerm_linux_web_app.web.site_config[0].minimum_tls_version == "1.2"
    error_message = "TLS 1.2 minimum"
  }

  assert {
    condition     = azurerm_linux_web_app.api.site_config[0].application_stack[0].python_version == "3.12" && azurerm_linux_web_app.web.site_config[0].application_stack[0].node_version == "24-lts"
    error_message = "runtimes are Python 3.12 and Node 24 LTS (D19)"
  }

  assert {
    condition     = azurerm_linux_web_app.api.site_config[0].always_on && azurerm_linux_web_app.api.site_config[0].health_check_path == "/api/health"
    error_message = "the API is Always On with a health check (HOST-1)"
  }

  assert {
    condition     = tonumber(azurerm_linux_web_app.api.app_settings["WEBSITES_CONTAINER_START_TIME_LIMIT"]) >= 230
    error_message = "startup time limit at least 230 s (HOST-1)"
  }

  assert {
    condition = (
      azurerm_linux_web_app.api.site_config[0].ip_restriction_default_action == "Deny" &&
      azurerm_linux_web_app.api.site_config[0].ip_restriction[0].virtual_network_subnet_id == var.app_subnet_id
    )
    error_message = "the API accepts traffic only from the web app's subnet (NET-2)"
  }

  assert {
    condition = (
      length(azurerm_linux_web_app.web.auth_settings_v2) == 1 &&
      azurerm_linux_web_app.web.auth_settings_v2[0].require_authentication &&
      azurerm_linux_web_app.web.auth_settings_v2[0].login[0].token_store_enabled
    )
    error_message = "Easy Auth requires authentication and keeps the token store on (AUTH-2)"
  }

  assert {
    condition     = endswith(azurerm_linux_web_app.web.auth_settings_v2[0].active_directory_v2[0].tenant_auth_endpoint, "/v2.0")
    error_message = "Easy Auth uses the v2 issuer"
  }

  assert {
    condition     = azurerm_linux_web_app.web.public_network_access_enabled == false && length(azurerm_private_endpoint.web) == 1
    error_message = "web_inbound = private_endpoint closes public access and adds an endpoint (D6)"
  }

  assert {
    condition     = azurerm_linux_web_app.api.tags["azd-service-name"] == "api" && azurerm_linux_web_app.web.tags["azd-service-name"] == "web"
    error_message = "azd finds the apps by azd-service-name"
  }
}

run "no_easy_auth_when_not_configured" {
  command = apply
  module {
    source = "./modules/app_service"
  }
  variables {
    sku_name                       = "P1v3"
    app_subnet_id                  = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/v/subnets/app"
    web_inbound                    = "public"
    web_allowed_ip_ranges          = []
    api_identity                   = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/api", client_id = "11111111-1111-1111-1111-111111111111" }
    web_identity                   = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/web", client_id = "22222222-2222-2222-2222-222222222222" }
    api_app_settings               = {}
    web_app_settings               = {}
    app_insights_connection_string = "InstrumentationKey=00000000-0000-0000-0000-000000000000"
    easy_auth                      = null
  }

  assert {
    condition     = length(azurerm_linux_web_app.web.auth_settings_v2) == 0 && azurerm_linux_web_app.web.public_network_access_enabled
    error_message = "public profile: no Easy Auth, public web app"
  }
}

run "fabric_is_created_only_when_asked" {
  command = apply
  module {
    source = "./modules/fabric"
  }
  variables {
    create           = false
    manage_access    = false
    environment_name = "tcc-test"
    capacity_sku     = "F2"
    capacity_admin   = ""
    api_principal_id = "00000000-0000-0000-0000-0000000000bb"
    workspace_role   = "Contributor"
    byo = {
      workspace_id     = "w", workspace_name = "w", lakehouse_name = "l", warehouse_id = "wh",
      warehouse_server = "s", warehouse_database = "d"
    }
  }

  assert {
    condition = (
      length(azurerm_fabric_capacity.this) == 0 && length(fabric_workspace.this) == 0 &&
      length(fabric_lakehouse.this) == 0 && length(fabric_warehouse.this) == 0 &&
      length(fabric_workspace_role_assignment.api) == 0
    )
    error_message = "create = false and manage_access = false create nothing in Fabric"
  }
}

run "fabric_created_for_the_public_profile" {
  command = apply
  module {
    source = "./modules/fabric"
  }
  variables {
    create           = true
    manage_access    = true
    environment_name = "tcc-test"
    capacity_sku     = "F2"
    capacity_admin   = "admin@example.com"
    api_principal_id = "00000000-0000-0000-0000-0000000000bb"
    workspace_role   = "Contributor"
    byo = {
      workspace_id     = "", workspace_name = "", lakehouse_name = "", warehouse_id = "",
      warehouse_server = "", warehouse_database = ""
    }
  }

  assert {
    condition = (
      azurerm_fabric_capacity.this[0].sku[0].name == "F2" &&
      length(fabric_lakehouse.this) == 1 && fabric_lakehouse.this[0].configuration.enable_schemas &&
      length(fabric_warehouse.this) == 1 && length(fabric_workspace_role_assignment.api) == 1
    )
    error_message = "create_fabric makes an F2 capacity, a schema-enabled Lakehouse, a Warehouse and the API's workspace role"
  }
}
