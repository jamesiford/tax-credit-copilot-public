# The Foundry network posture the demo needs, and the checks around it. [CH-12b]
#
# `modules/foundry` creates the account private (public access off, default deny). That
# blocks everything outside the VNet from the Foundry data plane: the operator's
# `azd ai agent` deploy, scripts/publish-m365.ps1, scripts/create-model-connection.ps1 and
# any workstation smoke test. foundry_public_network_access is the one switch for the demo.
# Default false is today's behaviour exactly.
#
# The range checks live here, not in variable validation, because the input may arrive as
# a list or as the comma-separated string azd substitutes, and a validation can only read
# the raw variable. The resource below exists only when somebody asked for the demo posture
# or named a range, so the default plan gains nothing.

locals {
  foundry_ip_ranges = [
    for r in(can(tolist(var.foundry_allowed_ip_ranges)) ? tolist(var.foundry_allowed_ip_ranges) : split(",", tostring(var.foundry_allowed_ip_ranges))) :
    trimspace(tostring(r)) if trimspace(tostring(r)) != ""
  ]

  ipv4_cidr = "^((25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\\.){3}(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])/(3[0-2]|[12]?[0-9])$"

  foundry_network_inputs_given = var.foundry_public_network_access || length(local.foundry_ip_ranges) > 0 || var.foundry_allow_any_ip
  network_posture              = var.foundry_public_network_access ? "demo-public-foundry" : "private"
}

resource "terraform_data" "foundry_network_inputs" {
  count = local.foundry_network_inputs_given ? 1 : 0

  lifecycle {
    precondition {
      condition     = var.foundry_public_network_access
      error_message = "foundry_allowed_ip_ranges and foundry_allow_any_ip only apply with foundry_public_network_access = true; set it, or remove them. A firewall rule that is silently ignored is worse than none."
    }

    precondition {
      condition     = alltrue([for r in local.foundry_ip_ranges : can(regex(local.ipv4_cidr, r))])
      error_message = "every foundry_allowed_ip_ranges entry must be an IPv4 CIDR such as 203.0.113.0/24 (the account firewall takes IPv4 only)."
    }

    precondition {
      condition     = alltrue([for r in local.foundry_ip_ranges : !endswith(r, "/31")])
      error_message = "the account firewall does not support a /31 range: list the two addresses as /32."
    }

    precondition {
      condition     = alltrue([for r in local.foundry_ip_ranges : !endswith(r, "/0") || var.foundry_allow_any_ip])
      error_message = "0.0.0.0/0 (any /0) opens the Foundry data plane to the internet and needs foundry_allow_any_ip = true, set deliberately."
    }

    precondition {
      condition     = local.data_classification != "customer" && var.profile != "enterprise"
      error_message = "the demo Foundry posture is refused for customer data and for the enterprise profile."
    }
  }
}

# A failed check is a warning in the plan, which is the point: it cannot be missed and does not block the demo.
check "foundry_demo_posture" {
  assert {
    condition     = !var.foundry_public_network_access
    error_message = "WARNING: network_posture = demo-public-foundry. The Foundry data plane is reachable from the internet (Entra-only, local auth off, ${length(local.foundry_ip_ranges) > 0 ? "firewalled to the listed ranges" : "no address restriction"}). Synthetic data only. Say so in any demo, and run the hardening plan before real data: docs/architecture/HARDENING-PLAN.md."
  }
}
