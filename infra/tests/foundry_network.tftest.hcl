# CH-12b: the demo network posture for the Foundry data plane, under mock providers.
#
# The promises tested. Default: nothing changes (the account is created exactly as it always
# was, no extra resource appears, the posture reads "private"). Toggle on: only the two network
# properties differ, local auth stays off, the private endpoint stays, and the posture says
# so. The refusals fire for the right reason: enterprise, customer data, a bad or open range,
# and a range given without the toggle. Every existing test in this directory is unedited.

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

run "default_is_private_and_adds_nothing" {
  command = apply

  assert {
    condition = module.foundry.network_settings == {
      public_network_access = "Disabled"
      default_action        = "Deny"
      ip_rules              = []
      local_auth_disabled   = true
    }
    error_message = "with the toggle off the account is created exactly as before: public access disabled, default deny, no rules, local auth off"
  }

  assert {
    condition     = output.network_posture == "private"
    error_message = "the default posture is private"
  }

  assert {
    condition     = length(terraform_data.foundry_network_inputs) == 0
    error_message = "with nothing asked for, the posture's check resource is not created, so the default plan gains nothing"
  }

  assert {
    condition     = module.foundry.private_endpoint_id != ""
    error_message = "the private endpoint exists in every posture"
  }
}

run "toggle_on_changes_only_the_network_properties" {
  command = apply

  variables {
    foundry_public_network_access = true
  }

  assert {
    condition = module.foundry.network_settings == {
      public_network_access = "Enabled"
      default_action        = "Allow"
      ip_rules              = []
      local_auth_disabled   = true
    }
    error_message = "the demo posture enables the public endpoint, allows any address, and keeps local auth off"
  }

  assert {
    condition     = output.network_posture == "demo-public-foundry"
    error_message = "the posture names itself"
  }

  assert {
    condition     = module.foundry.private_endpoint_id != ""
    error_message = "the private endpoint and DNS stay: the API's private path is unchanged"
  }

  assert {
    condition     = length(terraform_data.foundry_network_inputs) == 1
    error_message = "asking for the demo posture creates the check resource that holds the refusals"
  }

  # The warning check fires by design: it is how the plan says what it is doing.
  expect_failures = [check.foundry_demo_posture]
}

run "ranges_firewall_the_account_and_a_single_address_is_sent_bare" {
  command = apply

  variables {
    foundry_public_network_access = true
    foundry_allowed_ip_ranges     = ["203.0.113.0/24", "198.51.100.7/32"]
  }

  assert {
    condition = module.foundry.network_settings == {
      public_network_access = "Enabled"
      default_action        = "Deny"
      ip_rules              = [{ value = "203.0.113.0/24" }, { value = "198.51.100.7" }]
      local_auth_disabled   = true
    }
    error_message = "with ranges the default action is Deny and each range is a rule; a /32 is sent as a bare address"
  }

  expect_failures = [check.foundry_demo_posture]
}

run "azd_passes_ranges_as_one_comma_separated_string" {
  command = apply

  variables {
    foundry_public_network_access = true
    foundry_allowed_ip_ranges     = "203.0.113.0/24, 198.51.100.0/25 ,"
  }

  assert {
    condition     = module.foundry.network_settings.ip_rules == [{ value = "203.0.113.0/24" }, { value = "198.51.100.0/25" }]
    error_message = "the string form is split, trimmed and stripped of empties"
  }

  expect_failures = [check.foundry_demo_posture]
}

run "an_empty_azd_value_is_the_default" {
  command = apply

  variables {
    foundry_allowed_ip_ranges = ""
  }

  assert {
    condition     = output.network_posture == "private" && length(terraform_data.foundry_network_inputs) == 0
    error_message = "azd substitutes an empty string for an unset value; that is no ranges, not an error"
  }
}

run "any_address_range_needs_the_second_switch" {
  command = plan

  variables {
    foundry_public_network_access = true
    foundry_allowed_ip_ranges     = ["0.0.0.0/0"]
  }

  expect_failures = [terraform_data.foundry_network_inputs, check.foundry_demo_posture]
}

run "any_address_range_is_allowed_when_deliberately_switched_on" {
  command = apply

  variables {
    foundry_public_network_access = true
    foundry_allowed_ip_ranges     = ["0.0.0.0/0"]
    foundry_allow_any_ip          = true
  }

  assert {
    condition     = module.foundry.network_settings.default_action == "Deny" && module.foundry.network_settings.ip_rules == [{ value = "0.0.0.0/0" }]
    error_message = "with the switch set the range is accepted as written"
  }

  expect_failures = [check.foundry_demo_posture]
}

run "a_malformed_range_is_refused" {
  command = plan

  variables {
    foundry_public_network_access = true
    foundry_allowed_ip_ranges     = ["203.0.113.0/24", "not-a-range"]
  }

  expect_failures = [terraform_data.foundry_network_inputs, check.foundry_demo_posture]
}

run "an_address_without_a_prefix_is_refused" {
  command = plan

  variables {
    foundry_public_network_access = true
    foundry_allowed_ip_ranges     = ["203.0.113.7"]
  }

  expect_failures = [terraform_data.foundry_network_inputs, check.foundry_demo_posture]
}

run "a_slash_31_is_refused" {
  command = plan

  variables {
    foundry_public_network_access = true
    foundry_allowed_ip_ranges     = ["203.0.113.6/31"]
  }

  expect_failures = [terraform_data.foundry_network_inputs, check.foundry_demo_posture]
}

run "ranges_without_the_toggle_are_refused_not_ignored" {
  command = plan

  variables {
    foundry_allowed_ip_ranges = ["203.0.113.0/24"]
  }

  expect_failures = [terraform_data.foundry_network_inputs]
}

run "customer_data_refuses_the_demo_posture" {
  command = plan

  variables {
    foundry_public_network_access = true
    data_classification           = "customer"
  }

  expect_failures = [var.foundry_public_network_access]
}
