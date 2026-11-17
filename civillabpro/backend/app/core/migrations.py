"""Helpers for comparing the database with the models (Alembic autogenerate and ``alembic check``).

On PostgreSQL, extensions install tables of their own: PostGIS adds ``spatial_ref_sys``,
``postgis_topology`` adds the ``topology`` schema and ``postgis_tiger_geocoder`` some forty
tables, and both add their schemas to the database ``search_path``. SQLAlchemy reflects every
table visible on the search path, so without a filter Alembic proposes to drop all of them.

The filter below asks PostgreSQL which relations belong to an extension (``pg_depend`` rows
with ``deptype = 'e'``) and leaves those out, unless a model defines a table of the same name.
Tables that belong to no extension are still compared, so real drift is still reported.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import Connection, MetaData

_EXTENSION_RELATIONS = """
SELECT c.relname
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_depend d
  ON d.classid = 'pg_catalog.pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e'
WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
"""


def extension_owned_tables(connection: Connection) -> set[str]:
    """Names of tables and views that belong to an installed extension (PostgreSQL only)."""
    if connection.dialect.name != "postgresql":
        return set()
    return {row[0] for row in connection.exec_driver_sql(_EXTENSION_RELATIONS)}


def include_name_filter(connection: Connection, metadata: MetaData) -> Callable[[str | None, str, dict[str, Any]], bool]:
    """An Alembic ``include_name`` hook that skips extension-owned tables the models do not define.

    The catalogue is read on the first call, which Alembic makes only while comparing schemas,
    inside its own transaction. Reading it earlier would open a transaction on the connection
    before Alembic does; Alembic then leaves committing to the caller, and an ``upgrade`` run
    through ``env.py`` would be rolled back when the connection closes.
    """
    model_tables = {t.name for t in metadata.tables.values()}
    skip: set[str] | None = None

    def include_name(name: str | None, type_: str, parent_names: dict[str, Any]) -> bool:
        nonlocal skip
        if type_ != "table":
            return True
        if skip is None:
            skip = extension_owned_tables(connection) - model_tables
        return name not in skip

    return include_name
