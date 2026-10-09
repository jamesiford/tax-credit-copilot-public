# Inputs. Empty strings (what azd substitutes for an unset environment value)
# are treated as "not set" throughout. Defaults that differ by profile are null
# here and resolved in locals.tf from the D25 profile matrix.

# --- environment ---------------------------------------------------------------

variable "profile" {
  description = "Deployment profile (D25): public (creates everything, synthetic data, no auth) or enterprise (BYO network and Fabric, Entra)."
  type        = string
  default     = "public"
  validation {
    condition     = contains(["public", "enterprise"], var.profile)
    error_message = "profile must be 'public' or 'enterprise'."
  }
}

variable "environment_name" {
  description = "azd environment name; used in resource names and the azd-env-name tag."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,40}$", var.environment_name))
    error_message = "environment_name must be lowercase letters, digits and hyphens (2-41 chars)."
  }
}

variable "location" {
  description = "Azure region for every resource."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group to create. Empty uses rg-<environment_name>."
  type        = string
  default     = ""
}

variable "subscription_id" {
  description = "Target subscription. Empty defers to ARM_SUBSCRIPTION_ID / the Azure CLI default."
  type        = string
  default     = ""
}

variable "tenant_id" {
  description = "Entra tenant for Easy Auth and API token validation. Empty uses the deploying principal's tenant."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Extra tags merged onto every resource."
  type        = map(string)
  default     = {}
}

variable "git_commit" {
  description = "Commit the deployed code was built from; recorded in the calculation trail."
  type        = string
  default     = ""
}

# --- profile overrides (null = take the profile default) ------------------------

variable "auth_mode" {
  description = "API auth: none | entra. Null takes the profile default (public none, enterprise entra)."
  type        = string
  default     = null
  validation {
    condition     = var.auth_mode == null || contains(["none", "entra"], coalesce(var.auth_mode, "none"))
    error_message = "auth_mode must be none or entra."
  }
}

variable "data_classification" {
  description = "synthetic | customer (D26). Never inferred at runtime; set here per profile."
  type        = string
  default     = null
  validation {
    condition     = var.data_classification == null || contains(["synthetic", "customer"], coalesce(var.data_classification, "synthetic"))
    error_message = "data_classification must be synthetic or customer."
  }
}

variable "create_fabric" {
  description = "Create an F2 capacity, workspace, Lakehouse and Warehouse (D17). Null: public true, enterprise false."
  type        = bool
  default     = null
}

variable "manage_fabric_access" {
  description = "Grant the API identity its Fabric workspace role with the fabric provider (D13). Null: public true, enterprise false."
  type        = bool
  default     = null
}

variable "create_network" {
  description = "Create the VNet, subnets, private endpoints and DNS zones. Null: public true, enterprise false (BYO)."
  type        = bool
  default     = null
}

variable "web_inbound" {
  description = "Inbound to the web app (D6): private_endpoint | access_restriction | public. Null: public 'public', enterprise 'private_endpoint'."
  type        = string
  default     = null
  validation {
    condition     = var.web_inbound == null || contains(["private_endpoint", "access_restriction", "public"], coalesce(var.web_inbound, "public"))
    error_message = "web_inbound must be private_endpoint, access_restriction or public."
  }
}

variable "enable_key_vault" {
  description = "Create a Key Vault (off: the stack holds no secrets)."
  type        = bool
  default     = false
}

# --- app service -----------------------------------------------------------------

variable "app_service_sku" {
  description = "Linux App Service plan SKU shared by both apps (D4)."
  type        = string
  default     = "P1v3"
}

variable "api_worker_count" {
  description = "Gunicorn workers (WEB_CONCURRENCY) for the API."
  type        = number
  default     = 2
}

variable "web_allowed_ip_ranges" {
  description = "CIDR ranges allowed to reach the web app when web_inbound = access_restriction."
  type        = list(string)
  default     = []
}

# --- identity (enterprise: app registrations are created by the customer, D12) --

variable "web_client_id" {
  description = "Client id of the web app registration (Easy Auth). Required for enterprise."
  type        = string
  default     = ""
  validation {
    condition     = var.profile != "enterprise" || length(trimspace(var.web_client_id)) > 0
    error_message = "web_client_id is required when profile = enterprise."
  }
}

variable "api_client_id" {
  description = "Client id of the API app registration (exposes user_impersonation and app role TCC.User). Required for enterprise."
  type        = string
  default     = ""
  validation {
    condition     = var.profile != "enterprise" || length(trimspace(var.api_client_id)) > 0
    error_message = "api_client_id is required when profile = enterprise."
  }
}

variable "api_audience" {
  description = "Audience the API validates. Empty uses api://<api_client_id>."
  type        = string
  default     = ""
}

# --- network (enterprise: bring your own) --------------------------------------

variable "vnet_address_space" {
  description = "Address space of the VNet the public profile creates."
  type        = string
  default     = "10.40.0.0/16"
}

variable "app_integration_subnet_id" {
  description = "BYO subnet for App Service VNet integration (delegated to Microsoft.Web/serverFarms, service endpoint Microsoft.Web). Required when create_network = false."
  type        = string
  default     = ""
  validation {
    condition     = (var.create_network == true || (var.create_network == null && var.profile == "public")) || trimspace(var.app_integration_subnet_id) != ""
    error_message = "app_integration_subnet_id is required when the network is brought (create_network = false)."
  }
}

variable "private_endpoint_subnet_id" {
  description = "BYO subnet for private endpoints. Required when create_network = false."
  type        = string
  default     = ""
  validation {
    condition     = (var.create_network == true || (var.create_network == null && var.profile == "public")) || trimspace(var.private_endpoint_subnet_id) != ""
    error_message = "private_endpoint_subnet_id is required when the network is brought (create_network = false)."
  }
}

variable "private_dns_zone_ids" {
  description = "BYO private DNS zone ids, keyed blob | cognitiveservices | openai | aiservices | vault | sites. Required when create_network = false."
  type        = map(string)
  default     = {}
  validation {
    condition     = (var.create_network == true || (var.create_network == null && var.profile == "public")) || alltrue([for k in ["blob", "cognitiveservices", "openai", "aiservices"] : trimspace(lookup(var.private_dns_zone_ids, k, "")) != ""])
    error_message = "private_dns_zone_ids needs blob, cognitiveservices, openai and aiservices when the network is brought."
  }
}

# --- fabric --------------------------------------------------------------------

variable "fabric_capacity_admin" {
  description = "UPN made administrator of the F2 capacity. Required when create_fabric = true (TF-7); the preflight sets it to the deploying user."
  type        = string
  default     = ""
  validation {
    condition     = !(var.create_fabric == true || (var.create_fabric == null && var.profile == "public")) || trimspace(var.fabric_capacity_admin) != ""
    error_message = "fabric_capacity_admin is required when create_fabric = true (TF-7)."
  }
}

variable "fabric_capacity_sku" {
  description = "SKU of the capacity create_fabric provisions."
  type        = string
  default     = "F2"
}

variable "fabric_workspace_role" {
  description = "Workspace role the API identity receives when manage_fabric_access = true. Contributor covers OneLake ReadAll and Warehouse writes; item-level ReadAll is not expressible in the provider."
  type        = string
  default     = "Contributor"
}

variable "fabric_workspace_id" {
  description = "BYO workspace id (create_fabric = false)."
  type        = string
  default     = ""
  validation {
    condition     = (var.create_fabric == true || (var.create_fabric == null && var.profile == "public")) || trimspace(var.fabric_workspace_id) != ""
    error_message = "fabric_workspace_id is required when Fabric is brought (create_fabric = false)."
  }
}

variable "fabric_workspace_name" {
  description = "BYO workspace display name (OneLake paths). Empty with create_fabric uses the created workspace."
  type        = string
  default     = ""
}

variable "fabric_lakehouse_name" {
  description = "BYO Lakehouse display name holding the source schema."
  type        = string
  default     = ""
}

variable "fabric_warehouse_id" {
  description = "BYO Warehouse item id."
  type        = string
  default     = ""
  validation {
    condition     = (var.create_fabric == true || (var.create_fabric == null && var.profile == "public")) || trimspace(var.fabric_warehouse_id) != ""
    error_message = "fabric_warehouse_id is required when Fabric is brought (create_fabric = false)."
  }
}

variable "warehouse_server" {
  description = "BYO Warehouse SQL endpoint host."
  type        = string
  default     = ""
  validation {
    condition     = (var.create_fabric == true || (var.create_fabric == null && var.profile == "public")) || trimspace(var.warehouse_server) != ""
    error_message = "warehouse_server is required when Fabric is brought (create_fabric = false)."
  }
}

variable "warehouse_database" {
  description = "BYO Warehouse database (item display name)."
  type        = string
  default     = ""
  validation {
    condition     = (var.create_fabric == true || (var.create_fabric == null && var.profile == "public")) || trimspace(var.warehouse_database) != ""
    error_message = "warehouse_database is required when Fabric is brought (create_fabric = false)."
  }
}

variable "source_schema" {
  description = "Lakehouse schema holding the source payroll (D14)."
  type        = string
  default     = "tcc_source"
}

# --- AI --------------------------------------------------------------------------

variable "foundry_model" {
  description = "Model deployed for the narrating agents (AI-1)."
  type        = string
  default     = "gpt-4.1-mini"
}

variable "foundry_model_version" {
  type    = string
  default = "2025-04-14"
}

variable "foundry_deployment_sku" {
  type    = string
  default = "GlobalStandard"
}

variable "foundry_capacity" {
  description = "Deployment capacity in thousands of tokens per minute."
  type        = number
  default     = 20
}

variable "ai_gateway_endpoint" {
  description = "Optional AI gateway (AI-2). Must carry the Foundry Agents protocol. Empty calls Foundry directly."
  type        = string
  default     = ""
}

# --- storage ---------------------------------------------------------------------

variable "outputs_retention_days" {
  description = "Lifecycle retention on the outputs container (D9)."
  type        = number
  default     = 2555
}
