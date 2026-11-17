resource "azurerm_linux_web_app" "this" {
  name                                           = var.name
  resource_group_name                            = var.resource_group_name
  location                                       = var.location
  service_plan_id                                = var.service_plan_id
  https_only                                     = true
  public_network_access_enabled                  = false
  virtual_network_subnet_id                      = var.integration_subnet_id
  ftp_publish_basic_authentication_enabled       = false
  webdeploy_publish_basic_authentication_enabled = false
  client_affinity_enabled                        = false
  tags = merge(var.tags, {
    "azd-service-name" = var.service_name
    "tcc-runtime"      = "dotnet"
    "tcc-ownership"    = "infra-dotnet"
    "tcc-component"    = var.service_name
  })

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  site_config {
    always_on                         = true
    app_command_line                  = "dotnet ${var.dll}"
    health_check_path                 = "/api/health"
    health_check_eviction_time_in_min = 10
    ftps_state                        = "Disabled"
    minimum_tls_version               = "1.2"
    scm_minimum_tls_version           = "1.2"
    http2_enabled                     = true
    vnet_route_all_enabled            = true
    ip_restriction_default_action     = "Deny"
    scm_ip_restriction_default_action = "Deny"
    scm_use_main_ip_restriction       = true
    worker_count                      = 1

    application_stack {
      dotnet_version = "10.0"
    }
  }

  # These are App Service/.NET platform consumers, not invented TaxCredit flags.
  app_settings = merge(var.app_settings, {
    AZURE_CLIENT_ID                     = var.identity_client_id
    ASPNETCORE_ENVIRONMENT              = "Production"
    ASPNETCORE_URLS                     = "http://0.0.0.0:8080"
    SCM_DO_BUILD_DURING_DEPLOYMENT      = "false"
    WEBSITE_RUN_FROM_PACKAGE            = "1"
    Logging__LogLevel__Default          = "None"
    Logging__LogLevel__Microsoft        = "None"
    Logging__LogLevel__System           = "None"
    Logging__Console__LogLevel__Default = "None"
  })

  logs {
    detailed_error_messages = false
    failed_request_tracing  = false
  }
}

resource "azurerm_private_endpoint" "this" {
  name                = "pe-${var.name}"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.private_endpoint_subnet_id
  tags                = merge(var.tags, { "tcc-component" = var.service_name })

  private_service_connection {
    name                           = "sites-dotnet"
    private_connection_resource_id = azurerm_linux_web_app.this.id
    subresource_names              = ["sites"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "sites-dotnet"
    private_dns_zone_ids = [var.sites_private_dns_zone_id]
  }
}

resource "azurerm_monitor_diagnostic_setting" "this" {
  name                       = "diag-${var.service_name}-metrics"
  target_resource_id         = azurerm_linux_web_app.this.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  # allLogs/AppServiceHTTPLogs can capture paths, queries and identifiers.
  enabled_metric {
    category = "AllMetrics"
  }
}
