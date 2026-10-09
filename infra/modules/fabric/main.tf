# Fabric (FAB-1..3, D13, D17).
#
# create = true (public profile): an F2 capacity, a workspace on it, a
# schema-enabled Lakehouse for the source payroll and a Warehouse for
# tcc_gold / tcc_ops. The post-provision hook then bootstraps DDL v2.0 on the
# NEW Warehouse and loads the synthetic dataset.
#
# create = false (enterprise): the customer's existing workspace, Lakehouse and
# Warehouse are passed in and nothing is created.
#
# manage_access = true grants the API identity a workspace role. Schema-level
# T-SQL grants are a post-deploy script, not Terraform. Prerequisite: the Fabric
# tenant setting that lets service principals use Fabric APIs.

variable "create" {
  type = bool
}

variable "manage_access" {
  type = bool
}

variable "name_suffix" {
  type = string
}

variable "environment_name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "tags" {
  type = map(string)
}

variable "capacity_sku" {
  type = string
}

variable "capacity_admin" {
  type = string
}

variable "api_principal_id" {
  type = string
}

variable "workspace_role" {
  type = string
}

variable "byo" {
  description = "Existing Fabric items when create = false."
  type = object({
    workspace_id       = string
    workspace_name     = string
    lakehouse_name     = string
    warehouse_id       = string
    warehouse_server   = string
    warehouse_database = string
  })
}

locals {
  capacity_name  = "fctcc${var.name_suffix}"
  workspace_name = "tcc-${var.environment_name}"
  lakehouse_name = "tcc_lakehouse"
  warehouse_name = "tcc_warehouse"
}

resource "azurerm_fabric_capacity" "this" {
  count                  = var.create ? 1 : 0
  name                   = local.capacity_name
  resource_group_name    = var.resource_group_name
  location               = var.location
  administration_members = [var.capacity_admin]
  tags                   = var.tags

  sku {
    name = var.capacity_sku
    tier = "Fabric"
  }
}

# The workspace needs the capacity's Fabric id, not its ARM id. Reading it
# after the capacity exists defers this lookup to apply on a first deploy.
data "fabric_capacity" "this" {
  count        = var.create ? 1 : 0
  display_name = local.capacity_name
  depends_on   = [azurerm_fabric_capacity.this]
}

resource "fabric_workspace" "this" {
  count        = var.create ? 1 : 0
  display_name = local.workspace_name
  description  = "Tax Credit Copilot (${var.environment_name})"
  capacity_id  = data.fabric_capacity.this[0].id
}

resource "fabric_lakehouse" "this" {
  count        = var.create ? 1 : 0
  display_name = local.lakehouse_name
  workspace_id = fabric_workspace.this[0].id
  configuration = {
    enable_schemas = true
  }
}

resource "fabric_warehouse" "this" {
  count        = var.create ? 1 : 0
  display_name = local.warehouse_name
  workspace_id = fabric_workspace.this[0].id
}

locals {
  workspace_id = var.create ? fabric_workspace.this[0].id : var.byo.workspace_id
}

resource "fabric_workspace_role_assignment" "api" {
  count        = var.manage_access ? 1 : 0
  workspace_id = local.workspace_id
  role         = var.workspace_role
  principal = {
    id   = var.api_principal_id
    type = "ServicePrincipal"
  }
}

output "created" {
  value = var.create
}

output "workspace_id" {
  value = local.workspace_id
}

output "workspace_name" {
  value = var.create ? local.workspace_name : var.byo.workspace_name
}

output "lakehouse_name" {
  value = var.create ? local.lakehouse_name : var.byo.lakehouse_name
}

output "warehouse_id" {
  value = var.create ? fabric_warehouse.this[0].id : var.byo.warehouse_id
}

output "warehouse_server" {
  value = var.create ? fabric_warehouse.this[0].properties.connection_string : var.byo.warehouse_server
}

output "warehouse_database" {
  value = var.create ? local.warehouse_name : var.byo.warehouse_database
}

output "capacity_id" {
  value = var.create ? azurerm_fabric_capacity.this[0].id : null
}
