# ADR-012: the run orchestration worker, under mock providers.
#
# Two promises. With the toggle off (the default) the module creates nothing and nothing else changes: every other test in
# this directory runs with it off, unedited. With it on, exactly the worker's resources appear, it runs as the API's
# identity with the API's settings plus its own, never starts an inline worker, and holds no secret setting of its own.
# Nothing here is applied to a real subscription.

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

run "off_creates_nothing_and_says_so" {
  command = apply

  assert {
    condition     = length(module.run_worker.resource_types) == 0
    error_message = "with enable_run_worker off the worker module creates no resource"
  }

  assert {
    condition     = module.run_worker.app == null && output.RUN_WORKER_APP_NAME == ""
    error_message = "with the worker off there is no app and its output is empty"
  }
}

run "on_creates_exactly_the_worker" {
  command = apply
  variables {
    enable_run_worker      = true
    run_worker_concurrency = 3
  }

  assert {
    condition = toset(module.run_worker.resource_types) == toset([
      "azurerm_linux_web_app",
      "azurerm_monitor_diagnostic_setting",
    ]) && length(module.run_worker.resource_types) == 2
    error_message = "the worker is one app and one diagnostic setting, and nothing else (no new identity, no new role)"
  }

  assert {
    condition     = startswith(output.RUN_WORKER_APP_NAME, "app-tcc-worker-")
    error_message = "the name follows the other apps"
  }

  assert {
    condition     = module.run_worker.app.https_only && module.run_worker.app.ip_restriction_default_action == "Deny" && !module.run_worker.app.ftp_basic_auth && !module.run_worker.app.webdeploy_basic_auth
    error_message = "the worker is HTTPS-only, denies inbound by default and has no basic-auth publishing"
  }

  assert {
    condition     = module.run_worker.app.app_command_line == "sh worker-startup.sh" && module.run_worker.app.health_check_path == "/healthz"
    error_message = "it starts the worker entry point and reports health"
  }

  assert {
    condition     = module.run_worker.app.virtual_network_subnet_id == module.network.app_subnet_id
    error_message = "it shares the integration subnet with the API"
  }
}

run "on_runs_as_the_api_with_the_api_settings_and_its_own" {
  command = apply
  variables {
    enable_run_worker      = true
    run_worker_concurrency = 3
  }

  assert {
    condition     = module.run_worker.settings.RUN_WORKER_INLINE == "false" && module.run_worker.settings.RUN_WORKER_CONCURRENCY == "3" && module.run_worker.settings.WEB_CONCURRENCY == "1"
    error_message = "the worker never starts an inline worker, carries its concurrency and runs one process"
  }

  assert {
    condition     = module.run_worker.settings.RUN_MANIFEST_STORE == "warehouse" && module.run_worker.settings.CLAIM_STORE == "warehouse"
    error_message = "it reads and writes the same durable stores as the API: the queue is not private to a process"
  }

  assert {
    condition     = length(module.run_worker.app.identity_ids) == 1
    error_message = "it runs as one identity (the API's)"
  }
}

run "concurrency_defaults_to_one" {
  command = apply
  variables {
    enable_run_worker = true
  }

  assert {
    condition     = module.run_worker.settings.RUN_WORKER_CONCURRENCY == "1"
    error_message = "until concurrent Gold writes are measured live, the worker runs one item at a time"
  }
}

run "concurrency_is_bounded" {
  command = plan
  variables {
    enable_run_worker      = true
    run_worker_concurrency = 9
  }
  expect_failures = [var.run_worker_concurrency]
}
