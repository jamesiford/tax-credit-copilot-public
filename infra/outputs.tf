# Outputs azd writes into the environment (UPPER_CASE names become azd env
# values) and the post-provision hooks read.

output "AZURE_LOCATION" {
  value = var.location
}

output "AZURE_RESOURCE_GROUP" {
  value = azurerm_resource_group.this.name
}

output "TCC_PROFILE" {
  value = var.profile
}

output "API_APP_NAME" {
  value = module.app_service.api_name
}

output "WEB_APP_NAME" {
  value = module.app_service.web_name
}

output "API_BASE_URL" {
  value = module.app_service.api_url
}

output "WEB_BASE_URL" {
  value = module.app_service.web_url
}

output "API_IDENTITY_NAME" {
  description = "Display name of the API identity; the T-SQL grant script grants to it."
  value       = module.identity.api.name
}

output "API_IDENTITY_CLIENT_ID" {
  value = module.identity.api.client_id
}

output "API_IDENTITY_PRINCIPAL_ID" {
  value = module.identity.api.principal_id
}

output "FOUNDRY_PROJECT_ENDPOINT" {
  value = module.foundry.project_endpoint
}

output "ARTIFACT_BLOB_ACCOUNT_URL" {
  value = module.storage.blob_endpoint
}

output "FABRIC_WORKSPACE_ID" {
  value = module.fabric.workspace_id
}

output "FABRIC_WORKSPACE" {
  value = module.fabric.workspace_name
}

output "FABRIC_LAKEHOUSE" {
  value = module.fabric.lakehouse_name
}

output "FABRIC_WAREHOUSE_ID" {
  value = module.fabric.warehouse_id
}

output "WAREHOUSE_SERVER" {
  value = module.fabric.warehouse_server
}

output "WAREHOUSE_DATABASE" {
  value = module.fabric.warehouse_database
}

output "SOURCE_SCHEMA" {
  value = var.source_schema
}

output "TCC_FABRIC_CREATED" {
  description = "'true' only when this deployment created the Warehouse: the one case the destructive bootstrap may run (D22)."
  value       = tostring(module.fabric.created)
}

output "AUTH_MODE" {
  value = local.auth_mode
}

output "DATA_CLASSIFICATION" {
  value = local.data_classification
}

output "api_role_assignments" {
  description = "Every role the API identity holds, for review against REQUIREMENTS section 6."
  value = concat(
    module.storage.role_assignments,
    module.foundry.role_assignments,
    module.keyvault.role_assignments,
    [for r in module.monitoring.role_assignments : r if r.principal == "api"],
  )
}

output "web_role_assignments" {
  value = [for r in module.monitoring.role_assignments : r if r.principal == "web"]
}

output "easy_auth_enabled" {
  value = module.app_service.easy_auth_enabled
}
