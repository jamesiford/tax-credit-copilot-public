# The private path (NET-1, NET-3, NET-5). The public profile creates a VNet with
# an App Service integration subnet and a private-endpoint subnet, plus the
# private DNS zones the endpoints register in. The enterprise profile brings
# its own (create = false) and this module passes the ids straight through.

variable "create" {
  type = bool
}

variable "name_suffix" {
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

variable "address_space" {
  type = string
}

variable "zones" {
  description = "Private DNS zones this deployment needs, keyed blob | cognitiveservices | openai | aiservices | vault | sites."
  type        = map(string)
}

variable "byo_app_subnet_id" {
  type = string
}

variable "byo_private_endpoint_subnet_id" {
  type = string
}

variable "byo_private_dns_zone_ids" {
  type = map(string)
}

resource "azurerm_virtual_network" "this" {
  count               = var.create ? 1 : 0
  name                = "vnet-tcc-${var.name_suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  address_space       = [var.address_space]
  tags                = var.tags
}

resource "azurerm_subnet" "app" {
  count                = var.create ? 1 : 0
  name                 = "snet-app"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this[0].name
  address_prefixes     = [cidrsubnet(var.address_space, 8, 1)]
  # Microsoft.Web lets the API restrict inbound to this subnet (NET-2).
  service_endpoints = ["Microsoft.Web"]

  delegation {
    name = "appservice"
    service_delegation {
      name    = "Microsoft.Web/serverFarms"
      actions = ["Microsoft.Network/virtualNetworks/subnets/action"]
    }
  }
}

resource "azurerm_subnet" "private_endpoints" {
  count                             = var.create ? 1 : 0
  name                              = "snet-pe"
  resource_group_name               = var.resource_group_name
  virtual_network_name              = azurerm_virtual_network.this[0].name
  address_prefixes                  = [cidrsubnet(var.address_space, 8, 2)]
  private_endpoint_network_policies = "Disabled"
}

resource "azurerm_private_dns_zone" "this" {
  for_each            = var.create ? var.zones : {}
  name                = each.value
  resource_group_name = var.resource_group_name
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "this" {
  for_each              = var.create ? var.zones : {}
  name                  = "link-${each.key}"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.this[each.key].name
  virtual_network_id    = azurerm_virtual_network.this[0].id
  registration_enabled  = false
  tags                  = var.tags
}

output "app_subnet_id" {
  value = var.create ? azurerm_subnet.app[0].id : var.byo_app_subnet_id
}

output "private_endpoint_subnet_id" {
  value = var.create ? azurerm_subnet.private_endpoints[0].id : var.byo_private_endpoint_subnet_id
}

output "private_dns_zone_ids" {
  value = var.create ? { for k, z in azurerm_private_dns_zone.this : k => z.id } : var.byo_private_dns_zone_ids
}

output "vnet_id" {
  value = var.create ? azurerm_virtual_network.this[0].id : null
}
