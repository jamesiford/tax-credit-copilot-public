# Log Analytics + workspace-based Application Insights with Entra-only
# ingestion (OBS-1): local authentication is disabled, so the connection
# string alone cannot write telemetry; each app's identity needs Monitoring
# Metrics Publisher.

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

variable "publisher_principal_ids" {
  description = "Identities allowed to publish telemetry, keyed by a stable name."
  type        = map(string)
}

variable "retention_in_days" {
  type    = number
  default = 30
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "log-tcc-${var.name_suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "PerGB2018"
  retention_in_days   = var.retention_in_days
  tags                = var.tags
}

resource "azurerm_application_insights" "this" {
  name                         = "appi-tcc-${var.name_suffix}"
  resource_group_name          = var.resource_group_name
  location                     = var.location
  workspace_id                 = azurerm_log_analytics_workspace.this.id
  application_type             = "web"
  local_authentication_enabled = false
  tags                         = var.tags
}

resource "azurerm_role_assignment" "publisher" {
  for_each             = var.publisher_principal_ids
  scope                = azurerm_application_insights.this.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = each.value
  principal_type       = "ServicePrincipal"
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.this.id
}

output "app_insights_id" {
  value = azurerm_application_insights.this.id
}

output "app_insights_connection_string" {
  value     = azurerm_application_insights.this.connection_string
  sensitive = true
}

output "role_assignments" {
  value = [for k, r in azurerm_role_assignment.publisher : { principal = k, role = r.role_definition_name, scope = "app_insights" }]
}
