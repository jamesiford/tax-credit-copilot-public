mock_data "fabric_capacity" {
  defaults = { id = "00000000-0000-0000-0000-0000000000f1" }
}

mock_resource "fabric_workspace" {
  defaults = { id = "00000000-0000-0000-0000-0000000000f2" }
}

mock_resource "fabric_warehouse" {
  defaults = {
    id         = "00000000-0000-0000-0000-0000000000f3"
    properties = { connection_string = "test.datawarehouse.fabric.microsoft.com" }
  }
}
