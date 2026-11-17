resource "azurerm_resource_group" "dotnet" {
  name     = "rg-${local.name_suffix}"
  location = var.location
  tags     = local.tags
}

resource "azurerm_service_plan" "dotnet" {
  name                = "asp-${local.name_suffix}"
  resource_group_name = azurerm_resource_group.dotnet.name
  location            = azurerm_resource_group.dotnet.location
  os_type             = "Linux"
  sku_name            = var.app_service_sku
  worker_count        = 1
  tags                = local.tags
}

resource "azurerm_user_assigned_identity" "service" {
  for_each            = local.services
  name                = "id-${local.name_suffix}-${each.key}"
  resource_group_name = azurerm_resource_group.dotnet.name
  location            = azurerm_resource_group.dotnet.location
  tags                = merge(local.tags, { "tcc-component" = each.key })
}

resource "azurerm_role_assignment" "blob" {
  for_each           = local.blob_grants
  scope              = local.blob_container_scopes[each.value.container]
  role_definition_id = "/subscriptions/${split("/", local.blob_container_scopes[each.value.container])[2]}/providers/Microsoft.Authorization/roleDefinitions/ba92f5b4-2d11-453d-a403-e96b0029c9fe"
  principal_id       = azurerm_user_assigned_identity.service[each.value.service].principal_id
  principal_type     = "ServicePrincipal"
}

module "http_service" {
  for_each = local.services
  source   = "./modules/http_service"

  service_name               = "dotnet-${each.key}"
  name                       = "app-${local.name_suffix}-${each.key}"
  resource_group_name        = azurerm_resource_group.dotnet.name
  location                   = azurerm_resource_group.dotnet.location
  tags                       = local.tags
  service_plan_id            = azurerm_service_plan.dotnet.id
  dll                        = each.value.dll
  integration_subnet_id      = var.network.integration_subnet_id
  private_endpoint_subnet_id = var.network.private_endpoint_subnet_id
  sites_private_dns_zone_id  = var.network.sites_private_dns_zone_id
  log_analytics_workspace_id = var.log_analytics_workspace_id
  identity_id                = azurerm_user_assigned_identity.service[each.key].id
  identity_client_id         = azurerm_user_assigned_identity.service[each.key].client_id
  app_settings = merge(
    local.runtime_settings,
    var.writer_source == "allowlist" ? {} : { CHANNEL_WRITER_GROUP_ID = var.writer_group_id },
    each.key == "gateway" ? local.gateway_settings : {}
  )
}

resource "azurerm_monitor_diagnostic_setting" "plan" {
  name                       = "diag-${local.name_suffix}-metrics"
  target_resource_id         = azurerm_service_plan.dotnet.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_metric {
    category = "AllMetrics"
  }
}
