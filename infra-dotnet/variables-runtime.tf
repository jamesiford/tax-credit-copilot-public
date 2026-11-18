variable "warehouse" {
  description = "Python WAREHOUSE_SERVER/DATABASE translated to FABRIC_SQL_SERVER/DATABASE; one Gold/ops destination."
  type = object({
    server   = string
    database = string
  })
  validation {
    condition = (
      can(regex("^[A-Za-z0-9][A-Za-z0-9.-]+\\.[A-Za-z]{2,}$", var.warehouse.server)) &&
      length(trimspace(var.warehouse.database)) > 0 &&
      !can(regex("[;\\r\\n]", var.warehouse.database))
    )
    error_message = "warehouse requires a SQL DNS hostname and nonempty database name, not a connection string."
  }
}

variable "payroll_source" {
  description = "Lakehouse SQL endpoint, not OneLake. An explicitly empty schema stays empty."
  type = object({
    server   = string
    database = string
    schema   = optional(string, "tcc_source")
  })
  validation {
    condition = (
      can(regex("^[A-Za-z0-9][A-Za-z0-9.-]+\\.[A-Za-z]{2,}$", var.payroll_source.server)) &&
      length(trimspace(var.payroll_source.database)) > 0 &&
      !can(regex("[;\\r\\n]", var.payroll_source.database)) &&
      can(regex("^([A-Za-z_][A-Za-z0-9_]*|)$", var.payroll_source.schema))
    )
    error_message = "source requires a SQL DNS hostname, database and a valid identifier or explicitly empty schema."
  }
}

variable "data_classification" {
  description = "Explicit classification; even synthetic deployments always use Entra, Warehouse, SQL and Blob."
  type        = string
  default     = "customer"
  validation {
    condition     = contains(["customer", "synthetic"], var.data_classification)
    error_message = "data_classification must be customer or synthetic."
  }
}

variable "git_commit" {
  description = "Full revision stamped on runs; no working-tree fallback in deployed assets."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.git_commit))
    error_message = "git_commit must be a full lowercase 40-character commit hash."
  }
}

variable "data_map_file" {
  description = "Optional path to a complete data map (docs/DATA-MAP.md) that renames the databases, schemas, tables and Lakehouse columns the application uses. Empty keeps the embedded shipped map and emits no DATA_MAP_FILE setting."
  type        = string
  default     = ""
  validation {
    condition     = var.data_map_file == "" || can(regex("^/[A-Za-z0-9_./-]+\\.json$", var.data_map_file))
    error_message = "data_map_file must be empty or an absolute Linux path to a .json file."
  }
}

variable "resource_root" {
  description = "RuntimePaths product resource root packaged by deployment staging; exact case-sensitive Linux path."
  type        = string
  default     = "/home/site/wwwroot/resources"
  validation {
    condition     = var.resource_root == "/home/site/wwwroot/resources"
    error_message = "App Service code packages must stage resources at /home/site/wwwroot/resources."
  }
}
