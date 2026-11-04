# CH-16f: the governed data query's API settings, under mock providers. Two promises:
# a default plan adds nothing (every setting is emitted only when its variable is set), and
# enabling the lakehouse source or tuning a limit adds exactly those non-secret settings to
# the API app and to no other app.

mock_provider "azurerm" {
  source = "./tests/mocks"
}
mock_provider "azapi" {
  source = "./tests/mocks"
}
mock_provider "fabric" {
  source = "./tests/mocks"
}

variables {
  profile               = "public"
  environment_name      = "tcc-test"
  location              = "westus3"
  fabric_capacity_admin = "admin@example.com"
}

run "defaults_add_no_data_query_setting" {
  command = apply

  assert {
    condition     = length(module.app_service.api_data_query_settings) == 0
    error_message = "with no data-query variable set the API receives no DATA_QUERY_* or LAKEHOUSE_SQL_* setting"
  }
}

run "source_flag_alone_adds_one_setting" {
  command = apply
  variables {
    data_query_source_enabled = true
  }

  assert {
    condition     = nonsensitive(module.app_service.api_data_query_settings) == { DATA_QUERY_SOURCE_ENABLED = "true" }
    error_message = "enabling the source datasets adds DATA_QUERY_SOURCE_ENABLED and nothing else"
  }
}

run "every_setting_reaches_the_api" {
  command = apply
  variables {
    data_query_source_enabled  = true
    data_query_timeout_seconds = "30"
    data_query_max_rows        = "200"
    data_query_rate_per_minute = "12"
    data_query_max_concurrency = "2"
    lakehouse_sql_server       = "example.datawarehouse.fabric.microsoft.com"
    lakehouse_sql_database     = "example_lakehouse"
  }

  assert {
    condition = nonsensitive(module.app_service.api_data_query_settings) == {
      DATA_QUERY_SOURCE_ENABLED  = "true"
      DATA_QUERY_TIMEOUT_SECONDS = "30"
      DATA_QUERY_MAX_ROWS        = "200"
      DATA_QUERY_RATE_PER_MINUTE = "12"
      DATA_QUERY_MAX_CONCURRENCY = "2"
      LAKEHOUSE_SQL_SERVER       = "example.datawarehouse.fabric.microsoft.com"
      LAKEHOUSE_SQL_DATABASE     = "example_lakehouse"
    }
    error_message = "each data-query variable becomes its own API app setting, with the value as given"
  }

  assert {
    condition     = !anytrue([for k, v in nonsensitive(module.app_service.api_data_query_settings) : can(regex("KEY|SECRET|PASSWORD|TOKEN", k))])
    error_message = "no data-query setting is a credential"
  }
}

run "the_source_flag_false_is_the_default_and_emits_nothing" {
  command = apply
  variables {
    data_query_source_enabled = false
    data_query_max_rows       = "100"
  }

  assert {
    condition     = nonsensitive(module.app_service.api_data_query_settings) == { DATA_QUERY_MAX_ROWS = "100" }
    error_message = "an explicit false is the same as absent: the application default (off) applies"
  }
}

run "the_channel_gateway_gets_no_data_query_setting" {
  command = apply
  variables {
    enable_m365_channel       = true
    auth_mode                 = "entra"
    api_client_id             = "00000000-0000-0000-0000-000000000002"
    tenant_id                 = "00000000-0000-0000-0000-0000000000aa"
    channel_gateway_audience  = "api://00000000-0000-0000-0000-000000000009"
    data_query_source_enabled = true
    data_query_max_rows       = "100"
  }

  assert {
    condition     = !anytrue([for k, v in module.channel.settings : startswith(k, "DATA_QUERY_") || startswith(k, "LAKEHOUSE_SQL_")])
    error_message = "the gateway never touches data, so it receives no data-query setting"
  }
}

run "an_out_of_range_limit_is_refused" {
  command = plan
  variables {
    data_query_max_rows = "501"
  }
  expect_failures = [var.data_query_max_rows]
}

run "a_non_numeric_timeout_is_refused" {
  command = plan
  variables {
    data_query_timeout_seconds = "soon"
  }
  expect_failures = [var.data_query_timeout_seconds]
}
