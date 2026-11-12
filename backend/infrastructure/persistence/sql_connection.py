"""The platform-neutral name for the Warehouse connection. [09]

`FabricWarehouseConnection` already speaks plain ODBC with an Entra token for the
`database.windows.net` audience, which is also Azure SQL's. The name stays for every existing import;
new code that is not about Fabric imports `SqlWarehouseConnection`.
"""
from __future__ import annotations

from infrastructure.persistence.fabric_warehouse import FabricWarehouseConnection as SqlWarehouseConnection

__all__ = ["SqlWarehouseConnection"]
