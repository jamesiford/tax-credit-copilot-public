terraform {
  required_version = ">= 1.9.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.81.0"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.13.0"
    }
    fabric = {
      source  = "microsoft/fabric"
      version = "~> 1.14.0"
    }
  }
}

provider "azurerm" {
  features {
    resource_group {
      # Application Insights adds smart-detection rules to the group; a teardown
      # must not be blocked by resources Terraform did not create.
      prevent_deletion_if_contains_resources = false
    }
    cognitive_account {
      purge_soft_delete_on_destroy = true
    }
    key_vault {
      purge_soft_delete_on_destroy = true
    }
    storage {
      # Storage public network access is OFF. Terraform manages containers and
      # the lifecycle policy on the management plane only and never needs to
      # reach the blob endpoint.
      data_plane_available = false
    }
  }

  # Never register resource providers: that is a subscription-wide change, and
  # a customer subscription usually forbids it. Required providers are listed
  # in the handover as a prerequisite.
  resource_provider_registrations = "none"

  # Entra auth for anything storage-related; shared keys are disabled.
  storage_use_azuread = true
  subscription_id     = local.subscription_id
}

provider "azapi" {}

# Azure CLI locally, OIDC in CI (FABRIC_USE_OIDC / ARM_* variables).
provider "fabric" {
  preview = true
}
