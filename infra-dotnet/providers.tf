terraform {
  required_version = ">= 1.11.0, < 2.0.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 4.81.0"
    }
  }

  # Configure the remaining fields using a dedicated .NET backend configuration.
  # Never migrate/import Python state into this backend.
  backend "azurerm" {
    key              = "tax-credit-copilot-dotnet.tfstate"
    use_azuread_auth = true
  }
}

provider "azurerm" {
  features {}
  subscription_id                 = var.subscription_id
  resource_provider_registrations = "none"
  storage_use_azuread             = true
}
