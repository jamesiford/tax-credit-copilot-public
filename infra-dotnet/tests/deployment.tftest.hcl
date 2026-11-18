# Only a mock provider exists. "apply" below applies to Terraform's in-memory mock.
mock_provider "azurerm" {
  source = "./tests/mocks"
}

override_resource {
  target = azurerm_user_assigned_identity.service["api"]
  values = {
    id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-tcc-dotnet-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-tcc-dotnet-api"
    client_id    = "00000000-0000-0000-0000-000000000011"
    principal_id = "00000000-0000-0000-0000-000000000012"
  }
}
override_resource {
  target = azurerm_user_assigned_identity.service["gateway"]
  values = {
    id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-tcc-dotnet-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-tcc-dotnet-gateway"
    client_id    = "00000000-0000-0000-0000-000000000021"
    principal_id = "00000000-0000-0000-0000-000000000022"
  }
}

variables {
  subscription_id  = "00000000-0000-0000-0000-000000000000"
  environment_name = "test"
  location         = "westus3"
  tenant_id        = "00000000-0000-0000-0000-000000000001"
  api_audience     = "api://00000000-0000-0000-0000-000000000002"
  gateway_audience = "api://00000000-0000-0000-0000-000000000003"
  git_commit       = "0000000000000000000000000000000000c0ffee"
  client_allowlist = { "00000000-0000-0000-0000-000000000004" = [9000] }
  warehouse        = { server = "warehouse.example.test", database = "warehouse" }
  payroll_source   = { server = "source.example.test", database = "lakehouse", schema = "" }
  network = {
    integration_subnet_id       = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.Network/virtualNetworks/external/subnets/app"
    private_endpoint_subnet_id  = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.Network/virtualNetworks/external/subnets/pe"
    sites_private_dns_zone_id   = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.Network/privateDnsZones/privatelink.azurewebsites.net"
    blob_private_endpoint_id    = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.Network/privateEndpoints/blob"
    blob_private_dns_zone_id    = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
    fabric_private_endpoint_id  = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.Network/privateEndpoints/fabric"
    fabric_private_dns_zone_ids = ["/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.Network/privateDnsZones/fabric.example.test"]
  }
  blob = {
    account_url                     = "https://syntheticdotnet.blob.core.windows.net"
    artifacts_container_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.Storage/storageAccounts/syntheticdotnet/blobServices/default/containers/artifacts"
    outputs_container_resource_id   = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.Storage/storageAccounts/syntheticdotnet/blobServices/default/containers/outputs"
  }
  log_analytics_workspace_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.OperationalInsights/workspaces/log"
  tags                       = { "azd-service-name" = "python", "tcc-runtime" = "python" }
}

run "independent_private_http_hosts" {
  command = apply

  assert {
    condition = (
      output.DOTNET_RESOURCE_GROUP_NAME == "rg-tcc-dotnet-test" &&
      output.DOTNET_API_APP_NAME == "app-tcc-dotnet-test-api" &&
      output.DOTNET_GATEWAY_APP_NAME == "app-tcc-dotnet-test-gateway" &&
      output.DOTNET_STATE_KEY == "tax-credit-copilot-dotnet.tfstate" &&
      azurerm_service_plan.dotnet.os_type == "Linux" && azurerm_service_plan.dotnet.worker_count == 1
    )
    error_message = "Names, state and the single-instance Linux plan must be independent of Python."
  }
  assert {
    condition = (
      length(azurerm_user_assigned_identity.service) == 2 &&
      azurerm_user_assigned_identity.service["api"].id != azurerm_user_assigned_identity.service["gateway"].id &&
      length(azurerm_role_assignment.blob) == 4 &&
      alltrue([for key, grant in azurerm_role_assignment.blob :
        contains([var.blob.artifacts_container_resource_id, var.blob.outputs_container_resource_id], grant.scope) &&
        grant.principal_id == azurerm_user_assigned_identity.service[split("-", key)[0]].principal_id &&
        endswith(grant.role_definition_id, "/ba92f5b4-2d11-453d-a403-e96b0029c9fe")
      ])
    )
    error_message = "Services need separate identities with only container-scoped Blob Data Contributor Azure grants."
  }
  assert {
    condition = alltrue([for name, service in module.http_service :
      service.deployment_contract.runtime == "10.0" &&
      service.deployment_contract.startup == (name == "api" ? "dotnet TaxCredit.Api.dll" : "dotnet TaxCredit.Gateway.dll") &&
      service.deployment_contract.tags["azd-service-name"] == "dotnet-${name}" &&
      service.deployment_contract.tags["tcc-runtime"] == "dotnet" &&
      toset(service.deployment_contract.identity_ids) == toset([azurerm_user_assigned_identity.service[name].id]) &&
      service.deployment_contract.settings.AZURE_CLIENT_ID == azurerm_user_assigned_identity.service[name].client_id
    ])
    error_message = "Actual apps must have the .NET 10 DLL, their own identity and non-overridable .NET service tags."
  }
  assert {
    condition = alltrue([for service in module.http_service :
      !service.deployment_contract.public_ingress &&
      service.deployment_contract.integration == var.network.integration_subnet_id &&
      service.deployment_contract.endpoint_subnet == var.network.private_endpoint_subnet_id &&
      toset(service.deployment_contract.dns_zone_ids) == toset([var.network.sites_private_dns_zone_id]) &&
      length(service.deployment_contract.log_categories) == 0 &&
      service.deployment_contract.metric_categories == ["AllMetrics"]
    ])
    error_message = "Apps must be private, VNet-integrated and DNS-bound, exporting metrics but no request/application logs."
  }
  assert {
    condition = alltrue([for service in module.http_service :
      service.deployment_contract.settings.PERSISTENCE_PROVIDER == "warehouse" &&
      service.deployment_contract.settings.DATA_SOURCE == "lakehouse" &&
      service.deployment_contract.settings.FABRIC_SQL_SERVER == var.warehouse.server &&
      service.deployment_contract.settings.FABRIC_SQL_DATABASE == var.warehouse.database &&
      service.deployment_contract.settings.SOURCE_SQL_SERVER == var.payroll_source.server &&
      service.deployment_contract.settings.SOURCE_SQL_DATABASE == var.payroll_source.database &&
      service.deployment_contract.settings.SOURCE_SCHEMA == "" &&
      service.deployment_contract.settings.ARTIFACT_STORE == "blob" &&
      service.deployment_contract.settings.ARTIFACT_BLOB_ACCOUNT_URL == var.blob.account_url &&
      service.deployment_contract.settings.REPOSITORY_ROOT == "/home/site/wwwroot/resources"
    ])
    error_message = "Actual emitted settings must use native Warehouse/lakehouse SQL/Blob consumers and preserve an empty schema."
  }
  assert {
    condition = alltrue([for service in module.http_service :
      service.deployment_contract.settings.ENVIRONMENT == "azure" &&
      service.deployment_contract.settings.AUTH_MODE == "entra" &&
      service.deployment_contract.settings.AUTH_TENANT_ID == var.tenant_id &&
      service.deployment_contract.settings.API_AUDIENCE == var.api_audience &&
      service.deployment_contract.settings.CLIENT_ALLOWLIST == jsonencode(var.client_allowlist) &&
      service.deployment_contract.settings.CHANNEL_WRITER_SOURCE == "allowlist" &&
      service.deployment_contract.settings.CHANNEL_ENFORCE_WRITER_FOR_USERS == "true" &&
      service.deployment_contract.settings.CONTRACT_HOOKS == "0" &&
      service.deployment_contract.settings.GIT_COMMIT == var.git_commit &&
      service.deployment_contract.settings.Logging__Console__LogLevel__Default == "None"
    ])
    error_message = "Apps must explicitly use deployed Entra/acting-person controls, no contract hooks, no raw console telemetry and the revision."
  }
  assert {
    condition = (
      module.http_service["gateway"].deployment_contract.settings.TENANT_ID == var.tenant_id &&
      module.http_service["gateway"].deployment_contract.settings.GATEWAY_AUDIENCE == var.gateway_audience &&
      module.http_service["gateway"].deployment_contract.settings.CHANNEL_DEBUG_WHOAMI == "false" &&
      module.http_service["gateway"].deployment_contract.settings.CHANNEL_ALLOWED_CALLER_APP_IDS == "" &&
      module.http_service["gateway"].deployment_contract.settings.CHANNEL_CALLER_CHANNELS == "" &&
      alltrue([for service in module.http_service :
        length(setintersection(toset(keys(service.deployment_contract.settings)), toset([
          "CLAIM_STORE", "RUN_MANIFEST_STORE", "FINDING_STORE", "API_BASE_URL", "RESOURCE_ROOT",
          "RUN_LEASE_SECONDS", "RUN_WORKER_INLINE", "RUN_WORKER_CONCURRENCY", "SOURCE_MAPPING_FILE",
          "AI_EGRESS_POLICY", "AI_PROVIDER_CHAIN", "APPLICATIONINSIGHTS_CONNECTION_STRING", "WEBSITES_PORT"
        ]))) == 0
      ])
    )
    error_message = "Gateway trust must remain distinct and unsupported/Python-only settings must not be emitted."
  }
  assert {
    condition = (
      !output.DOTNET_WORKER_TOPOLOGY.available && output.DOTNET_WORKER_TOPOLOGY.health == null &&
      output.DOTNET_WORKER_TOPOLOGY.startup == "dotnet TaxCredit.Worker.dll" &&
      !output.DOTNET_ORCHESTRATOR_TOPOLOGY.available
    )
    error_message = "A non-HTTP Worker or untrusted orchestrator must not look healthy/deployable."
  }
}

run "gateway_off_removes_its_entire_footprint" {
  command = apply
  variables {
    enable_gateway = false
  }
  assert {
    condition = (
      keys(module.http_service) == ["api"] &&
      keys(azurerm_user_assigned_identity.service) == ["api"] &&
      length(azurerm_role_assignment.blob) == 2 &&
      output.DOTNET_GATEWAY_APP_NAME == "" &&
      output.DOTNET_GATEWAY_APP_ID == "" && output.DOTNET_GATEWAY_URL == "" &&
      keys(output.DOTNET_PRIVATE_ENDPOINT_IDS) == ["api"]
    )
    error_message = "Disabling gateway must remove its app, private endpoint, identity, grants and deploy target."
  }
}

run "worker_cannot_be_enabled" {
  command = plan
  variables {
    enable_worker = true
  }
  expect_failures = [var.enable_worker]
}

run "orchestrator_cannot_be_enabled" {
  command = plan
  variables {
    enable_orchestrator = true
  }
  expect_failures = [var.enable_orchestrator]
}

run "audiences_cannot_be_conflated" {
  command = plan
  variables {
    gateway_audience = "00000000-0000-0000-0000-000000000002"
  }
  expect_failures = [var.gateway_audience]
}

run "group_mode_requires_a_real_group_binding" {
  command = plan
  variables {
    writer_source = "entra_group"
  }
  expect_failures = [var.writer_group_id]
}

run "unbound_clients_are_rejected" {
  command = plan
  variables {
    client_allowlist = {}
  }
  expect_failures = [var.client_allowlist]
}

run "sql_source_endpoint_is_required" {
  command = plan
  variables {
    payroll_source = { server = "", database = "lakehouse" }
  }
  expect_failures = [var.payroll_source]
}

run "blob_sas_is_not_configuration" {
  command = plan
  variables {
    blob = {
      account_url                     = "https://syntheticdotnet.blob.core.windows.net?sig=synthetic"
      artifacts_container_resource_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.Storage/storageAccounts/syntheticdotnet/blobServices/default/containers/artifacts"
      outputs_container_resource_id   = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-external/providers/Microsoft.Storage/storageAccounts/syntheticdotnet/blobServices/default/containers/outputs"
    }
  }
  expect_failures = [var.blob]
}
