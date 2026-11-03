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
  description = "Optional model gateway (AI-2, AI-03): an https:// base URL without a path. It must expose an OpenAI-compatible chat-completions API with streaming and tool calling (not the Foundry Agents protocol). Empty calls Foundry directly."
  type        = string
  default     = ""
}

# Everything below is non-secret and emitted to the API only when set, so the
# defaults leave an existing deployment's plan a no-op (AI-03).

variable "ai_provider_chain" {
  description = "Ordered model providers (AI_PROVIDER_CHAIN), comma separated from foundry | foundry_connection | gateway, e.g. 'foundry,gateway'. Empty keeps the application default (foundry)."
  type        = string
  default     = ""
  validation {
    condition     = trimspace(var.ai_provider_chain) == "" || alltrue([for p in split(",", var.ai_provider_chain) : contains(["foundry", "foundry_connection", "gateway"], trimspace(p))])
    error_message = "ai_provider_chain must be a comma-separated list of foundry, foundry_connection or gateway."
  }
}

variable "ai_gateway_auth" {
  description = "How the API authenticates to the gateway (AI_GATEWAY_AUTH): none | api_key | oauth_client_credentials | entra_token. Empty leaves it unset."
  type        = string
  default     = ""
  validation {
    condition     = var.ai_gateway_auth == "" || contains(["none", "api_key", "oauth_client_credentials", "entra_token"], var.ai_gateway_auth)
    error_message = "ai_gateway_auth must be empty, none, api_key, oauth_client_credentials or entra_token."
  }
}

variable "ai_gateway_api_style" {
  description = "Gateway URL shape (AI_GATEWAY_API_STYLE): openai_v1 | azure_deployments. Empty leaves the application default (openai_v1)."
  type        = string
  default     = ""
  validation {
    condition     = var.ai_gateway_api_style == "" || contains(["openai_v1", "azure_deployments"], var.ai_gateway_api_style)
    error_message = "ai_gateway_api_style must be empty, openai_v1 or azure_deployments."
  }
}

variable "ai_gateway_entra_audience" {
  description = "Audience the API's managed identity requests a token for when ai_gateway_auth = entra_token (AI_GATEWAY_ENTRA_AUDIENCE)."
  type        = string
  default     = ""
}

variable "ai_gateway_oauth_token_url" {
  description = "Token endpoint for ai_gateway_auth = oauth_client_credentials (AI_GATEWAY_OAUTH_TOKEN_URL)."
  type        = string
  default     = ""
}

variable "ai_gateway_oauth_client_id" {
  description = "Client id for ai_gateway_auth = oauth_client_credentials (AI_GATEWAY_OAUTH_CLIENT_ID). An identifier, not a secret."
  type        = string
  default     = ""
}

variable "ai_gateway_oauth_scope" {
  description = "Scope for ai_gateway_auth = oauth_client_credentials (AI_GATEWAY_OAUTH_SCOPE)."
  type        = string
  default     = ""
}

variable "ai_gateway_timeout_seconds" {
  description = "Gateway read timeout in seconds (AI_GATEWAY_TIMEOUT_SECONDS). A string so empty means unset."
  type        = string
  default     = ""
  validation {
    condition     = trimspace(var.ai_gateway_timeout_seconds) == "" || can(regex("^[0-9]+(\\.[0-9]+)?$", trimspace(var.ai_gateway_timeout_seconds)))
    error_message = "ai_gateway_timeout_seconds must be empty or a positive number of seconds."
  }
}

variable "ai_egress_policy" {
  description = "What may leave Microsoft's boundary in a prompt (AI_EGRESS_POLICY): allow_all | aggregates_only | block. Empty leaves the application default."
  type        = string
  default     = ""
  validation {
    condition     = var.ai_egress_policy == "" || contains(["allow_all", "aggregates_only", "block"], var.ai_egress_policy)
    error_message = "ai_egress_policy must be empty, allow_all, aggregates_only or block."
  }
}

variable "ai_model_router" {
  description = "Model for the router role on every provider (AI_MODEL_ROUTER)."
  type        = string
  default     = ""
}

variable "ai_model_narrator" {
  description = "Model for the narrator role on every provider (AI_MODEL_NARRATOR)."
  type        = string
  default     = ""
}

variable "ai_model_analysis" {
  description = "Model for the analysis role on every provider (AI_MODEL_ANALYSIS)."
  type        = string
  default     = ""
}

variable "ai_foundry_connection_name" {
  description = "Foundry model connection used by the foundry_connection provider (AI_FOUNDRY_CONNECTION_NAME)."
  type        = string
  default     = ""
}

# Key Vault REFERENCE inputs: the NAME of a secret that already exists in the
# vault. Terraform never sees the value; App Service resolves it at runtime
# through the API identity, which the keyvault module grants Key Vault Secrets User.

variable "ai_gateway_api_key_secret_name" {
  description = "Name of an existing Key Vault secret holding the gateway API key (surfaced as AI_GATEWAY_API_KEY, a Key Vault reference). Needs enable_key_vault."
  type        = string
  default     = ""
  validation {
    condition     = trimspace(var.ai_gateway_api_key_secret_name) == "" || var.enable_key_vault
    error_message = "ai_gateway_api_key_secret_name is a Key Vault reference and needs enable_key_vault = true."
  }
  validation {
    condition     = trimspace(var.ai_gateway_api_key_secret_name) == "" || can(regex("^[A-Za-z0-9-]{1,127}$", trimspace(var.ai_gateway_api_key_secret_name)))
    error_message = "ai_gateway_api_key_secret_name must be a Key Vault secret name (letters, digits and hyphens)."
  }
}

variable "ai_gateway_oauth_secret_name" {
  description = "Name of an existing Key Vault secret holding the OAuth client secret (surfaced as AI_GATEWAY_OAUTH_CLIENT_SECRET, a Key Vault reference). Needs enable_key_vault."
  type        = string
  default     = ""
  validation {
    condition     = trimspace(var.ai_gateway_oauth_secret_name) == "" || var.enable_key_vault
    error_message = "ai_gateway_oauth_secret_name is a Key Vault reference and needs enable_key_vault = true."
  }
  validation {
    condition     = trimspace(var.ai_gateway_oauth_secret_name) == "" || can(regex("^[A-Za-z0-9-]{1,127}$", trimspace(var.ai_gateway_oauth_secret_name)))
    error_message = "ai_gateway_oauth_secret_name must be a Key Vault secret name (letters, digits and hyphens)."
  }
}

# --- Foundry network posture (DEMO ONLY) -------------------------------------------

variable "foundry_public_network_access" {
  description = "DEMO ONLY. false (default) keeps the Foundry data plane private. true enables its public endpoint (Entra-only; local auth stays off; the private endpoint and DNS stay) so an operator's workstation can deploy and smoke-test the hosted agent. Synthetic data only: refused with the enterprise profile and with data_classification = customer. See docs/architecture/HARDENING-PLAN.md."
  type        = bool
  default     = false
  validation {
    condition     = !var.foundry_public_network_access || var.profile != "enterprise"
    error_message = "foundry_public_network_access is a demo posture and is refused in the enterprise profile: the Foundry data plane would be reachable from the internet."
  }
  validation {
    condition     = !var.foundry_public_network_access || var.data_classification != "customer"
    error_message = "foundry_public_network_access is refused when data_classification = customer: customer data never sits behind a publicly reachable data plane."
  }
}

variable "foundry_allowed_ip_ranges" {
  description = "With foundry_public_network_access, the IPv4 CIDR ranges allowed through the account firewall (default action then Deny). A list of strings, or one comma-separated string (what azd passes from TCC_FOUNDRY_ALLOWED_IP_RANGES). Empty allows any address. A /32 is sent as a bare address; /31 is not supported."
  type        = any
  default     = []
}

variable "foundry_allow_any_ip" {
  description = "Permit 0.0.0.0/0 (or any /0) in foundry_allowed_ip_ranges. A second, deliberate switch, because an open range defeats the point of listing ranges."
  type        = bool
  default     = false
}

# --- Microsoft 365 channel gateway (proof of concept) -------------------------------

variable "enable_m365_channel" {
  description = "Create the channel gateway: a third App Service on the existing plan, its identity and its settings. Off by default; with it off the plan is unchanged. Public profile only (PoC): the gateway is the one new public surface."
  type        = bool
  default     = false
  validation {
    condition     = !var.enable_m365_channel || var.profile != "enterprise"
    error_message = "enable_m365_channel is a proof-of-concept feature and is refused in the enterprise profile: the gateway is a public surface."
  }
}

variable "channel_gateway_audience" {
  description = "The gateway's app registration: api://<client id> or the bare client id (GATEWAY_AUDIENCE). Required when enable_m365_channel."
  type        = string
  default     = ""
  validation {
    condition     = !var.enable_m365_channel || length(trimspace(var.channel_gateway_audience)) > 0
    error_message = "channel_gateway_audience is required when enable_m365_channel is true."
  }
}

variable "channel_allowed_caller_app_ids" {
  description = "App ids that may call the gateway as the orchestrator without holding the Channel.Invoke role (CHANNEL_ALLOWED_CALLER_APP_IDS). Empty = role only."
  type        = list(string)
  default     = []
}

variable "channel_writer_source" {
  description = "Who may make changes through the channel (CHANNEL_WRITER_SOURCE): allowlist | entra_group | either."
  type        = string
  default     = "allowlist"
  validation {
    condition     = contains(["allowlist", "entra_group", "either"], var.channel_writer_source)
    error_message = "channel_writer_source must be allowlist, entra_group or either."
  }
}

variable "channel_writer_group_id" {
  description = "Object id of the Entra group whose members may write (CHANNEL_WRITER_GROUP_ID). Required unless channel_writer_source is allowlist."
  type        = string
  default     = ""
  validation {
    condition     = var.channel_writer_source == "allowlist" || length(trimspace(var.channel_writer_group_id)) > 0
    error_message = "channel_writer_group_id is required when channel_writer_source is entra_group or either."
  }
}

variable "channel_allowed_ip_ranges" {
  description = "CIDR ranges allowed to reach the gateway. Empty (default) allows every address: callers are authenticated in the app by token validation, not by Easy Auth or by network."
  type        = list(string)
  default     = []
}

variable "channel_debug_whoami" {
  description = "Turn on the gateway's diagnostic tool channel_ping (CHANNEL_DEBUG_WHOAMI). Demo and identity spikes only: it echoes the acting-user headers as received. Never a token."
  type        = bool
  default     = false
}

variable "channel_resolve_display_names" {
  description = "Let the gateway look a Teams user's display name and UPN up in Microsoft Graph (CHANNEL_RESOLVE_DISPLAY_NAMES), so audit rows and writes name a person rather than an object id. Needs the Graph application role User.ReadBasic.All on the gateway identity (an admin action: scripts/assign-channel-roles.ps1 -GrantUserReadBasic). Without the role the lookup fails soft and the request is unaffected."
  type        = bool
  default     = false
}

# --- mock AI gateway (proof of concept only) --------------------------------------

variable "enable_mock_ai_gateway" {
  description = "Create a mock OpenAI-compatible gateway App Service on the existing plan (scripts/mock-ai-gateway.py) for a proof of concept. Never in the enterprise profile."
  type        = bool
  default     = false
  validation {
    condition     = !var.enable_mock_ai_gateway || var.profile != "enterprise"
    error_message = "enable_mock_ai_gateway must never be true in the enterprise profile: the mock validates token shape, not signatures."
  }
}

variable "mock_ai_gateway_auth" {
  description = "Auth scheme the mock enforces (MOCK_AUTH): none | api_key | oauth | entra."
  type        = string
  default     = "none"
  validation {
    condition     = contains(["none", "api_key", "oauth", "entra"], var.mock_ai_gateway_auth)
    error_message = "mock_ai_gateway_auth must be none, api_key, oauth or entra."
  }
}

variable "mock_ai_gateway_entra_audience" {
  description = "Audience the mock expects in an Entra token (MOCK_ENTRA_AUDIENCE)."
  type        = string
  default     = "api://mock-gateway"
}

# --- storage ---------------------------------------------------------------------

variable "outputs_retention_days" {
  description = "Lifecycle retention on the outputs container (D9)."
  type        = number
  default     = 2555
}
