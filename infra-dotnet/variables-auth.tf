variable "tenant_id" {
  description = "Verified Entra tenant; emitted separately as AUTH_TENANT_ID and gateway TENANT_ID."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.tenant_id))
    error_message = "tenant_id must be a tenant GUID."
  }
}

variable "api_audience" {
  description = "API app registration audience, not the gateway audience or a managed identity client ID."
  type        = string
  validation {
    condition     = can(regex("^(api://)?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.api_audience))
    error_message = "api_audience must be an app registration GUID or api://GUID."
  }
}

variable "gateway_audience" {
  description = "Gateway app registration audience; never substitutes for the shared runtime's API_AUDIENCE."
  type        = string
  validation {
    condition     = can(regex("^(api://)?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.gateway_audience))
    error_message = "gateway_audience must be an app registration GUID or api://GUID."
  }
  validation {
    condition     = trimprefix(lower(var.gateway_audience), "api://") != trimprefix(lower(var.api_audience), "api://")
    error_message = "API and gateway app audiences must remain distinct."
  }
}

variable "client_allowlist" {
  description = "Required explicit principal-to-client binding serialized to CLIENT_ALLOWLIST; no all-clients fallback."
  type        = map(list(number))
  sensitive   = true
  validation {
    condition = length(var.client_allowlist) > 0 && alltrue(flatten([
      for principal, clients in var.client_allowlist : [
        length(trimspace(principal)) > 0,
        alltrue([for client in clients : client > 0 && floor(client) == client && client <= 9223372036854775807])
      ]
    ]))
    error_message = "client_allowlist requires an explicit nonempty binding, nonempty principals and positive Int64 client identifiers."
  }
}

variable "writer_source" {
  description = "Persisted allowlist is the baseline; group modes require separately approved Graph membership access."
  type        = string
  default     = "allowlist"
  validation {
    condition     = contains(["allowlist", "entra_group", "either"], var.writer_source)
    error_message = "writer_source must be allowlist, entra_group or either."
  }
}

variable "writer_group_id" {
  description = "Entra group identifier, required for group modes. No Graph app permission is granted by this stack."
  type        = string
  default     = ""
  validation {
    condition = var.writer_source == "allowlist" ? var.writer_group_id == "" : can(regex(
      "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.writer_group_id
    ))
    error_message = "writer_group_id must be empty for allowlist, or a GUID for group modes."
  }
}

variable "channel_callers" {
  description = "Explicit service app to channel bindings; empty allows no allowlisted service callers. Channel.Invoke roles remain an operator trust decision."
  type        = map(set(string))
  default     = {}
  validation {
    condition = alltrue([
      for app, channels in var.channel_callers :
      can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", app)) &&
      length(channels) > 0 && alltrue([for channel in channels : contains(["teams", "m365-copilot"], channel)])
    ])
    error_message = "channel_callers must map service application GUIDs to teams and/or m365-copilot."
  }
}
