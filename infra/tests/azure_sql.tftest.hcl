# Azure SQL as the Warehouse (prompt 09): off by default, Entra-only and closed when on.
# Mock providers throughout: nothing here reaches Azure, and nothing is applied.

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

run "azure_sql_is_off_by_default" {
  command = apply

  assert {
    condition     = output.WAREHOUSE_PLATFORM == "fabric" && output.SQL_SERVER_FQDN == "" && output.SQL_CREATED == "false"
    error_message = "the default platform is Fabric and creates no Azure SQL server"
  }

  assert {
    condition     = output.WAREHOUSE_SERVER == module.fabric.warehouse_server
    error_message = "on Fabric the warehouse server is still the Fabric endpoint"
  }
}

run "azure_sql_feeds_the_warehouse_settings" {
  command = apply

  variables {
    warehouse_platform              = "azure_sql"
    azure_sql_admin_group_object_id = "00000000-0000-0000-0000-0000000000ad"
    azure_sql_admin_group_name      = "tcc-sql-admins"
  }

  assert {
    condition     = output.WAREHOUSE_PLATFORM == "azure_sql" && output.SQL_CREATED == "true"
    error_message = "the platform output says azure_sql and that this deployment created the database"
  }

  assert {
    condition     = output.WAREHOUSE_SERVER == output.SQL_SERVER_FQDN && output.WAREHOUSE_DATABASE == output.SQL_DATABASE_NAME
    error_message = "WAREHOUSE_SERVER and WAREHOUSE_DATABASE come from the Azure SQL module"
  }

  assert {
    condition     = contains(keys(module.network.private_dns_zone_ids), "sql")
    error_message = "a private-endpoint deployment gets the privatelink.database.windows.net zone"
  }
}

run "azure_sql_needs_an_entra_admin_group" {
  command = plan

  variables {
    warehouse_platform = "azure_sql"
  }

  expect_failures = [
    var.azure_sql_admin_group_object_id,
    var.azure_sql_admin_group_name,
  ]
}

run "azure_sql_server_is_entra_only_closed_and_audited" {
  command = apply
  module {
    source = "./modules/azure_sql"
  }

  variables {
    enabled                    = true
    name_suffix                = "test0001"
    resource_group_name        = "rg-test"
    location                   = "westus3"
    tags                       = {}
    tenant_id                  = "00000000-0000-0000-0000-0000000000aa"
    admin_group_object_id      = "00000000-0000-0000-0000-0000000000ad"
    admin_group_name           = "tcc-sql-admins"
    private_endpoint_subnet_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/v/subnets/pe"
    sql_private_dns_zone_id    = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/privateDnsZones/privatelink.database.windows.net"
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.OperationalInsights/workspaces/log"
  }

  assert {
    condition     = azurerm_mssql_server.this[0].azuread_administrator[0].azuread_authentication_only
    error_message = "Entra authentication only: no SQL logins"
  }

  assert {
    condition     = azurerm_mssql_server.this[0].minimum_tls_version == "1.2"
    error_message = "TLS 1.2"
  }

  assert {
    condition     = azurerm_mssql_server.this[0].public_network_access_enabled == false && length(azurerm_private_endpoint.sql) == 1 && length(azurerm_mssql_firewall_rule.this) == 0
    error_message = "the default is a private endpoint and no public access or firewall rule"
  }

  assert {
    condition     = azurerm_mssql_server_extended_auditing_policy.this[0].log_monitoring_enabled && azurerm_monitor_diagnostic_setting.audit[0].log_analytics_workspace_id != ""
    error_message = "auditing goes to Log Analytics"
  }
}

run "azure_sql_public_access_opens_only_the_listed_ranges" {
  command = apply
  module {
    source = "./modules/azure_sql"
  }

  variables {
    enabled                    = true
    name_suffix                = "test0001"
    resource_group_name        = "rg-test"
    location                   = "westus3"
    tags                       = {}
    tenant_id                  = "00000000-0000-0000-0000-0000000000aa"
    admin_group_object_id      = "00000000-0000-0000-0000-0000000000ad"
    admin_group_name           = "tcc-sql-admins"
    public_network_access      = true
    firewall_rules             = { office = { start = "203.0.113.10", end = "203.0.113.20" } }
    log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.OperationalInsights/workspaces/log"
  }

  assert {
    condition     = azurerm_mssql_server.this[0].public_network_access_enabled && toset(keys(azurerm_mssql_firewall_rule.this)) == toset(["office"]) && length(azurerm_private_endpoint.sql) == 0
    error_message = "public access is limited to the named firewall rules and has no private endpoint"
  }
}

run "azure_sql_module_creates_nothing_when_disabled" {
  command = apply
  module {
    source = "./modules/azure_sql"
  }

  variables {
    enabled                    = false
    name_suffix                = "test0001"
    resource_group_name        = "rg-test"
    location                   = "westus3"
    tags                       = {}
    tenant_id                  = "00000000-0000-0000-0000-0000000000aa"
    admin_group_object_id      = ""
    admin_group_name           = ""
    log_analytics_workspace_id = ""
  }

  assert {
    condition     = length(azurerm_mssql_server.this) == 0 && length(azurerm_mssql_database.this) == 0 && output.created == false
    error_message = "disabled means no server and no database"
  }
}
