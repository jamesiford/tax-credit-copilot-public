"""Where the source tables live and how to open them. [03.1, 03.2]

One place builds the OneLake storage options and the Delta table address, so the reader
(`from_fabric.py`) and the writer (`to_delta.py`) cannot drift, and the SQL path
(`infrastructure/persistence/source_sql.py`) names tables through the same `physical_table`.

**Private-link workspaces.** The public host `onelake.dfs.fabric.microsoft.com` is refused by a
workspace that blocks public access. Its blob host is `https://<workspaceid-no-dashes>.z<xy>.blob.fabric.microsoft.com`
(`ONELAKE_ENDPOINT`). The Delta reader lists files over the **Blob** API, so the endpoint must be
the blob host; the host is never derived from a workspace name. It is passed as the `azure_endpoint`
storage option and the `abfss://` URL keeps the public host: `deltalake` 1.6.6 rejects a private
host inside the URL and honours the option (proved offline in `tests/test_onelake_endpoint.py`).

**Path style.** `ONELAKE_PATH_STYLE=name` (default) addresses `<workspace-name>` and
`<lakehouse>.Lakehouse`; `guid` addresses `<workspace-id>` and `<lakehouse-item-id>`, with
`FABRIC_WORKSPACE` and `FABRIC_LAKEHOUSE` holding the ids.

**Table names (interim, replaced by the mapping in prompt 06).** A logical table (`Payroll`) maps
to a physical one through `SOURCE_TABLE_MAP` (verbatim, wins), else `SOURCE_TABLE_PREFIX` + the
logical name with `SOURCE_TABLE_CASE` applied to the whole result. With none set the physical name
is the logical one. An empty `SOURCE_SCHEMA` is a lakehouse that is not schema-enabled:
`Tables/<table>`, and `[lakehouse]..[table]` in SQL.

No function here logs a token.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from config import SOURCE_SCHEMA, get_settings

ONELAKE_PUBLIC_HOST = "onelake.dfs.fabric.microsoft.com"
STORAGE_SCOPE = "https://storage.azure.com/.default"

#: A physical name becomes a path segment and a bracket-quoted SQL identifier.
_PHYSICAL = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-]{0,127}$")


def storage_token() -> str:
    """A storage-scope bearer token from the shared credential, cached until near expiry."""
    from infrastructure.azure_credential import cached_token

    return cached_token(STORAGE_SCOPE)


def physical_table(logical: str) -> str:
    """The physical name of a logical source table, under the current settings."""
    source = get_settings().data_source
    mapped = source.table_map.get(logical)
    if mapped is not None:
        name = mapped
    else:
        name = f"{source.table_prefix}{logical}"
        if source.table_case == "lower":
            name = name.lower()
        elif source.table_case == "upper":
            name = name.upper()
    if not _PHYSICAL.match(name):
        raise ValueError(
            f"physical table name {name!r} for {logical!r} is not a plain identifier; "
            "check SOURCE_TABLE_PREFIX, SOURCE_TABLE_CASE and SOURCE_TABLE_MAP"
        )
    return name


def sql_table_name(lakehouse: str, schema: str, logical: str) -> str:
    """`[lakehouse].[schema].[physical]`, or `[lakehouse]..[physical]` for a lakehouse with no schema."""
    return f"[{lakehouse}].{f'[{schema}]' if schema else ''}.[{physical_table(logical)}]"


def table_uri(table: str, *, workspace: str, lakehouse: str, schema: str = SOURCE_SCHEMA) -> str:
    """OneLake presents as ADLS Gen2, so a Delta table is a directory path.

    The host stays the public one even for a private-link workspace; `storage_options` redirects it.
    """
    item = lakehouse if get_settings().data_source.onelake_path_style == "guid" else f"{lakehouse}.Lakehouse"
    folder = f"{schema}/" if schema else ""
    return f"abfss://{workspace}@{ONELAKE_PUBLIC_HOST}/{item}/Tables/{folder}{physical_table(table)}"


def storage_options(token: str, transport: Mapping[str, str] | None = None) -> dict[str, str]:
    """`deltalake` storage options: the bearer token, the Fabric endpoint flag, the private host if set."""
    options = {"bearer_token": token, "use_fabric_endpoint": "true", **(transport or {})}
    endpoint = get_settings().data_source.onelake_endpoint
    if endpoint:
        options["azure_endpoint"] = endpoint
        if endpoint.startswith("http://"):
            options["allow_http"] = "true"
    return options
