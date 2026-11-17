output "DOTNET_RESOURCE_GROUP_NAME" {
  description = "Dedicated .NET deployment resource group; never the Python resource group."
  value       = azurerm_resource_group.dotnet.name
}
output "DOTNET_SERVICE_PLAN_ID" {
  description = "New independent single-instance Linux plan."
  value       = azurerm_service_plan.dotnet.id
}
output "DOTNET_API_APP_NAME" {
  description = "azd dotnet-api code target."
  value       = module.http_service["api"].name
}
output "DOTNET_API_APP_ID" {
  description = "Target assertion for package deployment."
  value       = module.http_service["api"].id
}
output "DOTNET_API_URL" {
  description = "Private-only HTTPS API origin; /api/health is liveness, /api/ready is readiness."
  value       = module.http_service["api"].url
}
output "DOTNET_GATEWAY_APP_NAME" {
  description = "azd dotnet-gateway code target; empty when disabled."
  value       = try(module.http_service["gateway"].name, "")
}
output "DOTNET_GATEWAY_APP_ID" {
  description = "Gateway target assertion; empty when disabled."
  value       = try(module.http_service["gateway"].id, "")
}
output "DOTNET_GATEWAY_URL" {
  description = "Private-only gateway origin; /channel/ready is constant metadata, not dependency readiness."
  value       = try(module.http_service["gateway"].url, "")
}
output "DOTNET_IDENTITIES" {
  description = "Per-service IDs for Python operator grants, Entra assignments and managed-identity selection."
  value = {
    for service, identity in azurerm_user_assigned_identity.service :
    service => { resource_id = identity.id, client_id = identity.client_id, principal_id = identity.principal_id }
  }
}
output "DOTNET_PRIVATE_ENDPOINT_IDS" {
  description = "New app/SCM private endpoint targets."
  value       = { for service, app in module.http_service : service => app.private_endpoint_id }
}
output "DOTNET_WORKER_TOPOLOGY" {
  description = "Explicitly unavailable, never a success-shaped web health endpoint."
  value = {
    available = var.enable_worker
    startup   = "dotnet TaxCredit.Worker.dll"
    health    = null
    reason    = "Generic Host has no HTTP listener; App Service supervision seam is missing."
  }
}
output "DOTNET_ORCHESTRATOR_TOPOLOGY" {
  description = "No orchestrator app, public ingress, identity or role is provisioned."
  value = {
    available = var.enable_orchestrator
    reason    = "Verified upstream/acting-person ingress and employer binding are not supplied."
  }
}
output "DOTNET_STATE_KEY" {
  description = "Backend key default; operator backend configuration must not override this with Python state."
  value       = "tax-credit-copilot-dotnet.tfstate"
}
