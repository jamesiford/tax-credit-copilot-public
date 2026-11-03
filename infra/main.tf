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

  # AI-03: a setting is emitted only when its variable is set, so the defaults
  # leave an existing deployment's plan unchanged. Nothing here is a secret.
  ai_plain_settings = {
    AI_GATEWAY_ENDPOINT        = trimspace(var.ai_gateway_endpoint)
    AI_PROVIDER_CHAIN          = join(",", [for p in split(",", var.ai_provider_chain) : trimspace(p)])
    AI_GATEWAY_AUTH            = trimspace(var.ai_gateway_auth)
    AI_GATEWAY_API_STYLE       = trimspace(var.ai_gateway_api_style)
    AI_GATEWAY_ENTRA_AUDIENCE  = trimspace(var.ai_gateway_entra_audience)
    AI_GATEWAY_OAUTH_TOKEN_URL = trimspace(var.ai_gateway_oauth_token_url)
    AI_GATEWAY_OAUTH_CLIENT_ID = trimspace(var.ai_gateway_oauth_client_id)
    AI_GATEWAY_OAUTH_SCOPE     = trimspace(var.ai_gateway_oauth_scope)
    AI_GATEWAY_TIMEOUT_SECONDS = trimspace(var.ai_gateway_timeout_seconds)
    AI_EGRESS_POLICY           = trimspace(var.ai_egress_policy)
    AI_MODEL_ROUTER            = trimspace(var.ai_model_router)
    AI_MODEL_NARRATOR          = trimspace(var.ai_model_narrator)
    AI_MODEL_ANALYSIS          = trimspace(var.ai_model_analysis)
    AI_FOUNDRY_CONNECTION_NAME = trimspace(var.ai_foundry_connection_name)
  }

  # Key Vault references, never values: App Service resolves them at runtime
  # with the API identity (key_vault_reference_identity_id), which the keyvault
  # module grants Key Vault Secrets User. The secret must already exist.
  ai_secret_names = {
    AI_GATEWAY_API_KEY             = trimspace(var.ai_gateway_api_key_secret_name)
    AI_GATEWAY_OAUTH_CLIENT_SECRET = trimspace(var.ai_gateway_oauth_secret_name)
  }

  api_ai_settings = merge(
    { for k, v in local.ai_plain_settings : k => v if v != "" },
    var.enable_key_vault ? {
      for k, v in local.ai_secret_names : k => "@Microsoft.KeyVault(VaultName=${module.keyvault.name};SecretName=${v})" if v != ""
    } : {},
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
  public_network_access      = var.foundry_public_network_access
  allowed_ip_ranges          = local.foundry_ip_ranges

  depends_on = [terraform_data.foundry_network_inputs]
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
  } : {}, local.api_ai_settings)

  web_app_settings = {}
}

# PoC only. Creates the App Service and its settings; deploying
# scripts/mock-ai-gateway.py (copied as mock_ai_gateway.py) is a separate manual
# step, as the module comment explains. Refused for the enterprise profile.
module "mock_ai_gateway" {
  source                = "./modules/mock_ai_gateway"
  enabled               = var.enable_mock_ai_gateway
  name_suffix           = local.token
  resource_group_name   = azurerm_resource_group.this.name
  location              = var.location
  tags                  = local.tags
  service_plan_id       = module.app_service.plan_id
  integration_subnet_id = module.network.app_subnet_id
  mock_auth             = var.mock_ai_gateway_auth
  entra_audience        = var.mock_ai_gateway_entra_audience
}

# CH-07: the Microsoft 365 channel gateway. Count 0 unless enable_m365_channel,
# so the default plan is unchanged. A third App Service on the same plan and in
# the same integration subnet as the API, which is why the API's access
# restriction needs no change.
module "channel" {
  source                         = "./modules/channel"
  enabled                        = var.enable_m365_channel
  name_suffix                    = local.token
  resource_group_name            = azurerm_resource_group.this.name
  location                       = var.location
  tags                           = local.tags
  service_plan_id                = module.app_service.plan_id
  integration_subnet_id          = module.network.app_subnet_id
  tenant_id                      = local.tenant_id
  gateway_audience               = trimspace(var.channel_gateway_audience)
  api_base_url                   = module.app_service.api_url
  api_audience                   = local.api_audience
  data_classification            = local.data_classification
  allowed_caller_app_ids         = var.channel_allowed_caller_app_ids
  writer_source                  = var.channel_writer_source
  writer_group_id                = var.channel_writer_group_id
  allowed_ip_ranges              = var.channel_allowed_ip_ranges
  git_commit                     = var.git_commit
  app_insights_id                = module.monitoring.app_insights_id
  app_insights_connection_string = module.monitoring.app_insights_connection_string
  log_analytics_workspace_id     = module.monitoring.log_analytics_workspace_id

  warehouse = {
    server    = module.fabric.warehouse_server
    database  = module.fabric.warehouse_database
    workspace = module.fabric.workspace_name
  }
}
