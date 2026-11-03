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

output "network_posture" {
  description = "private (default) or demo-public-foundry. The second is a DEMO posture: the Foundry data plane is reachable from the internet (Entra-only). Synthetic data only."
  value       = local.network_posture
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

output "mock_ai_gateway_url" {
  description = "URL of the PoC mock model gateway; empty unless enable_mock_ai_gateway."
  value       = module.mock_ai_gateway.default_hostname == "" ? "" : "https://${module.mock_ai_gateway.default_hostname}"
}

output "CHANNEL_APP_NAME" {
  description = "Name of the channel gateway App Service; empty unless enable_m365_channel. azd deploys the `channel` service to it."
  value       = module.channel.app_name

  # The gateway calls the API with a token, so the API must validate tokens and
  # have an audience to validate them against. The public profile defaults to
  # AUTH_MODE=none, so enabling the channel there means also setting auth_mode.
  precondition {
    condition     = !var.enable_m365_channel || (local.auth_mode == "entra" && local.api_audience != "" && local.tenant_id != "")
    error_message = "enable_m365_channel needs the API to validate tokens: set auth_mode = \"entra\" and api_client_id (or api_audience). The public profile defaults to AUTH_MODE=none."
  }
}

output "CHANNEL_BASE_URL" {
  description = "https://<gateway hostname>; empty unless enable_m365_channel. The orchestrator and the Cowork connector call this."
  value       = module.channel.url
}

output "GATEWAY_IDENTITY_NAME" {
  description = "Display name of the gateway identity; scripts/grant-warehouse-sql.py --profile gateway grants to it. Empty unless enable_m365_channel."
  value       = module.channel.identity_name
}

output "GATEWAY_IDENTITY_PRINCIPAL_ID" {
  description = "Object id to assign the API's TCC.Agent app role to (an operator step). Empty unless enable_m365_channel."
  value       = module.channel.identity_principal_id
}

output "GATEWAY_IDENTITY_CLIENT_ID" {
  value = module.channel.identity_client_id
}
