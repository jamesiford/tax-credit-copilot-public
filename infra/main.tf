resource "azurerm_resource_group" "this" {
  name     = local.resource_group_name
  location = var.location
  tags     = local.tags
}

locals {
  dns_zone_names = merge(
    {
      blob              = "privatelink.blob.core.windows.net"
      cognitiveservices = "privatelink.cognitiveservices.azure.com"
      openai            = "privatelink.openai.azure.com"
      aiservices        = "privatelink.services.ai.azure.com"
    },
    var.enable_key_vault ? { vault = "privatelink.vaultcore.azure.net" } : {},
    local.web_inbound == "private_endpoint" ? { sites = "privatelink.azurewebsites.net" } : {},
  )
}

module "identity" {
  source              = "./modules/identity"
  name_suffix         = local.token
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
}

module "network" {
  source                         = "./modules/network"
  create                         = local.create_network
  name_suffix                    = local.token
  resource_group_name            = azurerm_resource_group.this.name
  location                       = var.location
  tags                           = local.tags
  address_space                  = var.vnet_address_space
  zones                          = local.dns_zone_names
  byo_app_subnet_id              = var.app_integration_subnet_id
  byo_private_endpoint_subnet_id = var.private_endpoint_subnet_id
  byo_private_dns_zone_ids       = var.private_dns_zone_ids
}

module "monitoring" {
  source              = "./modules/monitoring"
  name_suffix         = local.token
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
  publisher_principal_ids = {
    api = module.identity.api.principal_id
    web = module.identity.web.principal_id
  }
}

module "storage" {
  source                     = "./modules/storage"
  name_suffix                = local.token
  resource_group_name        = azurerm_resource_group.this.name
  location                   = var.location
  tags                       = local.tags
  private_endpoint_subnet_id = module.network.private_endpoint_subnet_id
  blob_private_dns_zone_id   = module.network.private_dns_zone_ids["blob"]
  data_principal_id          = module.identity.api.principal_id
  outputs_retention_days     = var.outputs_retention_days
  log_analytics_workspace_id = module.monitoring.log_analytics_workspace_id
}

module "keyvault" {
  source                     = "./modules/keyvault"
  enabled                    = var.enable_key_vault
  name_suffix                = local.token
  resource_group_name        = azurerm_resource_group.this.name
  location                   = var.location
  tenant_id                  = local.tenant_id
  tags                       = local.tags
  private_endpoint_subnet_id = module.network.private_endpoint_subnet_id
  vault_private_dns_zone_id  = lookup(module.network.private_dns_zone_ids, "vault", "")
  reader_principal_id        = module.identity.api.principal_id
  log_analytics_workspace_id = module.monitoring.log_analytics_workspace_id
}

module "foundry" {
  source                     = "./modules/foundry"
  name_suffix                = local.token
  resource_group_id          = azurerm_resource_group.this.id
  resource_group_name        = azurerm_resource_group.this.name
  location                   = var.location
  tags                       = local.tags
  model                      = var.foundry_model
  model_version              = var.foundry_model_version
  deployment_sku             = var.foundry_deployment_sku
  capacity                   = var.foundry_capacity
  private_endpoint_subnet_id = module.network.private_endpoint_subnet_id
  private_dns_zone_ids = [
    module.network.private_dns_zone_ids["cognitiveservices"],
    module.network.private_dns_zone_ids["openai"],
    module.network.private_dns_zone_ids["aiservices"],
  ]
  user_principal_id          = module.identity.api.principal_id
  log_analytics_workspace_id = module.monitoring.log_analytics_workspace_id
}

module "fabric" {
  source              = "./modules/fabric"
  create              = local.create_fabric
  manage_access       = local.manage_fabric_access
  name_suffix         = local.token
  environment_name    = var.environment_name
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
  capacity_sku        = var.fabric_capacity_sku
  capacity_admin      = var.fabric_capacity_admin
  api_principal_id    = module.identity.api.principal_id
  workspace_role      = var.fabric_workspace_role
  byo = {
    workspace_id       = var.fabric_workspace_id
    workspace_name     = var.fabric_workspace_name
    lakehouse_name     = var.fabric_lakehouse_name
    warehouse_id       = var.fabric_warehouse_id
    warehouse_server   = var.warehouse_server
    warehouse_database = var.warehouse_database
  }
}

module "app_service" {
  source                         = "./modules/app_service"
  name_suffix                    = local.token
  resource_group_name            = azurerm_resource_group.this.name
  location                       = var.location
  tags                           = local.tags
  sku_name                       = var.app_service_sku
  app_subnet_id                  = module.network.app_subnet_id
  private_endpoint_subnet_id     = module.network.private_endpoint_subnet_id
  sites_private_dns_zone_id      = lookup(module.network.private_dns_zone_ids, "sites", "")
  web_inbound                    = local.web_inbound
  web_allowed_ip_ranges          = var.web_allowed_ip_ranges
  api_identity                   = { id = module.identity.api.id, client_id = module.identity.api.client_id }
  web_identity                   = { id = module.identity.web.id, client_id = module.identity.web.client_id }
  app_insights_connection_string = module.monitoring.app_insights_connection_string
  log_analytics_workspace_id     = module.monitoring.log_analytics_workspace_id

  easy_auth = local.easy_auth ? {
    tenant_id     = local.tenant_id
    web_client_id = var.web_client_id
    api_scope     = "${local.api_audience}/user_impersonation"
  } : null

  # HOST-5: every setting the API reads, from Terraform. None is a secret.
  api_app_settings = merge({
    ENVIRONMENT               = "azure"
    DATA_CLASSIFICATION       = local.data_classification
    AUTH_MODE                 = local.auth_mode
    CLAIM_STORE               = "warehouse"
    FINDING_STORE             = "warehouse"
    RUN_MANIFEST_STORE        = "warehouse"
    OVERRIDE_STORE            = "warehouse"
    ARTIFACT_STORE            = "blob"
    ARTIFACT_REPOSITORY       = "warehouse"
    ARTIFACT_BLOB_ACCOUNT_URL = module.storage.blob_endpoint
    OUTPUTS_RETENTION_DAYS    = tostring(var.outputs_retention_days)
    DATA_SOURCE               = "lakehouse"
    SOURCE_SCHEMA             = var.source_schema
    FABRIC_WORKSPACE          = module.fabric.workspace_name
    FABRIC_LAKEHOUSE          = module.fabric.lakehouse_name
    WAREHOUSE_SERVER          = module.fabric.warehouse_server
    WAREHOUSE_DATABASE        = module.fabric.warehouse_database
    FOUNDRY_PROJECT_ENDPOINT  = module.foundry.project_endpoint
    FOUNDRY_MODEL             = module.foundry.model
    WEB_CONCURRENCY           = tostring(var.api_worker_count)
    GIT_COMMIT                = var.git_commit
    }, local.auth_mode == "entra" ? {
    AUTH_TENANT_ID = local.tenant_id
    API_AUDIENCE   = local.api_audience
    } : {}, trimspace(var.ai_gateway_endpoint) != "" ? {
    AI_GATEWAY_ENDPOINT = trimspace(var.ai_gateway_endpoint)
  } : {})

  web_app_settings = {}
}
