# Optional Azure SQL Database for tcc_ops and tcc_gold (count 0 unless warehouse_platform = "azure_sql").
# Fabric stays the home of the payroll lakehouse; this replaces only the Warehouse.
#
# Entra authentication only: there is no SQL login, no administrator password and no secret in this
# module. Database users for the API and gateway identities are T-SQL, not Terraform, and are created
# by scripts/grant-sql.py (run by the Entra admin named below).

variable "enabled" {
  type = bool
}

variable "name_suffix" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "tags" {
  type = map(string)
}

variable "tenant_id" {
  type = string
}

variable "admin_group_object_id" {
  description = "Object id of the Entra group that administers the server (it creates the database users)."
  type        = string
}

variable "admin_group_name" {
  description = "Display name of that group."
  type        = string
}

variable "database_name" {
  type    = string
  default = "tcc"
}

variable "sku_name" {
  description = "Database SKU, e.g. GP_S_Gen5_2 (serverless), GP_Gen5_2 or S3."
  type        = string
  default     = "GP_S_Gen5_2"
}

variable "max_size_gb" {
  type    = number
  default = 32
}

variable "public_network_access" {
  description = "false (the default) closes the public endpoint and uses a private endpoint; true opens it to firewall_rules only."
  type        = bool
  default     = false
}

variable "firewall_rules" {
  description = "Public access only: name => { start, end } IPv4 ranges. Ignored when public_network_access is false."
  type        = map(object({ start = string, end = string }))
  default     = {}
}

variable "private_endpoint_subnet_id" {
  type    = string
  default = ""
}

variable "sql_private_dns_zone_id" {
  type    = string
  default = ""
}

variable "log_analytics_workspace_id" {
  type = string
}

resource "azurerm_mssql_server" "this" {
  count                         = var.enabled ? 1 : 0
  name                          = "sql-tcc-${var.name_suffix}"
  resource_group_name           = var.resource_group_name
  location                      = var.location
  version                       = "12.0"
  minimum_tls_version           = "1.2"
  public_network_access_enabled = var.public_network_access
  tags                          = var.tags

  azuread_administrator {
    login_username              = var.admin_group_name
    object_id                   = var.admin_group_object_id
    tenant_id                   = var.tenant_id
    azuread_authentication_only = true
  }
}

resource "azurerm_mssql_database" "this" {
  count          = var.enabled ? 1 : 0
  name           = var.database_name
  server_id      = azurerm_mssql_server.this[0].id
  sku_name       = var.sku_name
  max_size_gb    = var.max_size_gb
  collation      = "SQL_Latin1_General_CP1_CI_AS"
  zone_redundant = false
  tags           = var.tags
}

resource "azurerm_mssql_firewall_rule" "this" {
  for_each         = var.enabled && var.public_network_access ? var.firewall_rules : {}
  name             = each.key
  server_id        = azurerm_mssql_server.this[0].id
  start_ip_address = each.value.start
  end_ip_address   = each.value.end
}

resource "azurerm_private_endpoint" "sql" {
  count               = var.enabled && !var.public_network_access ? 1 : 0
  name                = "pe-sql-${var.name_suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint_subnet_id
  tags                = var.tags

  private_service_connection {
    name                           = "sql"
    private_connection_resource_id = azurerm_mssql_server.this[0].id
    subresource_names              = ["sqlServer"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "sql"
    private_dns_zone_ids = [var.sql_private_dns_zone_id]
  }
}

# Auditing to Log Analytics: the server policy turns auditing on, and the diagnostic setting on `master`
# is what routes the SQLSecurityAuditEvents category to the workspace.
resource "azurerm_mssql_server_extended_auditing_policy" "this" {
  count                  = var.enabled ? 1 : 0
  server_id              = azurerm_mssql_server.this[0].id
  log_monitoring_enabled = true
}

resource "azurerm_monitor_diagnostic_setting" "audit" {
  count                      = var.enabled ? 1 : 0
  name                       = "diag-sql-audit"
  target_resource_id         = "${azurerm_mssql_server.this[0].id}/databases/master"
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log {
    category = "SQLSecurityAuditEvents"
  }
}

output "id" {
  value = var.enabled ? azurerm_mssql_server.this[0].id : null
}

output "server_fqdn" {
  description = "The server's fully qualified name: WAREHOUSE_SERVER (and SQL_SERVER_FQDN for the migration guard)."
  value       = var.enabled ? azurerm_mssql_server.this[0].fully_qualified_domain_name : null
}

output "database_name" {
  value = var.enabled ? azurerm_mssql_database.this[0].name : null
}

output "created" {
  description = "true when this deployment created the database: the one case the destructive bootstrap may run."
  value       = var.enabled
}
