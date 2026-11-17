variable "subscription_id" {
  description = "Explicit target subscription; never discovered from an ambient CLI account."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be a subscription GUID."
  }
}

variable "environment_name" {
  description = "Dedicated .NET environment suffix; names always contain tcc-dotnet."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,19}$", var.environment_name))
    error_message = "environment_name must be 3-20 lowercase letters, digits or hyphens, beginning with a letter."
  }
}

variable "location" {
  description = "Azure region for the new .NET resources, compatible with the referenced subnets."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9]+$", var.location))
    error_message = "location must be an Azure region name."
  }
}

variable "tags" {
  description = "Additional customer-neutral tags; ownership and azd tags cannot be overridden."
  type        = map(string)
  default     = {}
}

variable "app_service_sku" {
  description = "Dedicated single-instance Linux code-deployment plan; no autoscale resource is created."
  type        = string
  default     = "P1v3"
  validation {
    condition     = contains(["P1v3", "P2v3", "P3v3"], var.app_service_sku)
    error_message = "Use a supported dedicated Premium v3 plan."
  }
}

variable "enable_gateway" {
  description = "Create the independent in-process gateway, including its identity and private endpoint."
  type        = bool
  default     = true
}

variable "enable_worker" {
  description = "Unavailable: Generic Host has no HTTP listener or App Service supervision seam."
  type        = bool
  default     = false
  validation {
    condition     = !var.enable_worker
    error_message = "App Service Worker topology is unavailable: TaxCredit.Worker is a Generic Host with no HTTP health listener. Do not deploy a dummy health server."
  }
}

variable "enable_orchestrator" {
  description = "Unavailable until authenticated upstream/acting-person ingress and employer binding are supplied."
  type        = bool
  default     = false
  validation {
    condition     = !var.enable_orchestrator
    error_message = "Orchestrator deployment is disabled: verified ingress, assertion stripping/replacement and direct-origin bypass protection are not implemented."
  }
}
