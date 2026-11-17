output "name" {
  description = "Code-deployment target selected by its dotnet-only azd service tag."
  value       = azurerm_linux_web_app.this.name
}
output "id" {
  description = "App ARM ID for target assertions."
  value       = azurerm_linux_web_app.this.id
}
output "url" {
  description = "Private-only HTTPS origin; DNS/network reachability is an external prerequisite."
  value       = "https://${azurerm_linux_web_app.this.default_hostname}"
}
output "private_endpoint_id" {
  description = "New service private endpoint, not the external Blob/Fabric endpoints."
  value       = azurerm_private_endpoint.this.id
}
output "deployment_contract" {
  description = "Actual resource configuration for root contract tests; not republished as a root output."
  sensitive   = true
  value = {
    settings          = azurerm_linux_web_app.this.app_settings
    startup           = azurerm_linux_web_app.this.site_config[0].app_command_line
    runtime           = azurerm_linux_web_app.this.site_config[0].application_stack[0].dotnet_version
    identity_ids      = azurerm_linux_web_app.this.identity[0].identity_ids
    tags              = azurerm_linux_web_app.this.tags
    public_ingress    = azurerm_linux_web_app.this.public_network_access_enabled
    integration       = azurerm_linux_web_app.this.virtual_network_subnet_id
    endpoint_subnet   = azurerm_private_endpoint.this.subnet_id
    dns_zone_ids      = azurerm_private_endpoint.this.private_dns_zone_group[0].private_dns_zone_ids
    metric_categories = [for metric in azurerm_monitor_diagnostic_setting.this.enabled_metric : metric.category]
    log_categories    = azurerm_monitor_diagnostic_setting.this.enabled_log
  }
}
