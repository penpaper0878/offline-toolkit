"""The Alembic history must build exactly the schema the models describe."""

import os
import pathlib

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from alembic import command
from app.core.database import Base, make_engine
from app.core.migrations import include_name_filter
from app.modules import models_registry  # noqa: F401

BACKEND = pathlib.Path(__file__).resolve().parents[2]


def test_migrations_match_the_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = make_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []
    command.downgrade(cfg, "base")
    with engine.connect() as conn:
        tables = {r[0] for r in conn.exec_driver_sql("select name from sqlite_master where type='table'")}
    engine.dispose()
    assert tables <= {"alembic_version"}


PG_URL = os.environ.get("CLP_TEST_DATABASE_URL", "")


@pytest.mark.skipif(not PG_URL.startswith("postgresql"), reason="needs CLP_TEST_DATABASE_URL pointing at PostgreSQL")
def test_extension_tables_are_ignored_but_real_drift_is_not():
    """PostGIS and its geocoder install tables of their own; they are not drift, a stray table of ours is."""
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", PG_URL)
    engine = make_engine(PG_URL)
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    command.upgrade(cfg, "head")
    try:
        with engine.begin() as conn:
            # A table that belongs to an extension (plpgsql is always installed), as PostGIS tables do...
            conn.exec_driver_sql("CREATE TABLE clp_probe_extension_owned (id int)")
            conn.exec_driver_sql("ALTER EXTENSION plpgsql ADD TABLE clp_probe_extension_owned")
            # ...and one that belongs to nothing: a table left behind by a removed model.
            conn.exec_driver_sql("CREATE TABLE clp_probe_stray (id int)")
        with engine.connect() as conn:
            opts = {"compare_type": True, "include_name": include_name_filter(conn, Base.metadata)}
            diff = compare_metadata(MigrationContext.configure(conn, opts=opts), Base.metadata)
        removed = {d[1].name for d in diff if d[0] == "remove_table"}
        # Only the stray table is reported: not the probe, and on a PostGIS database not
        # spatial_ref_sys, the topology tables or the geocoder tables either.
        assert removed == {"clp_probe_stray"}
        assert [d for d in diff if d[0] != "remove_table"] == []
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER EXTENSION plpgsql DROP TABLE clp_probe_extension_owned")
            conn.exec_driver_sql("DROP TABLE clp_probe_extension_owned")
            conn.exec_driver_sql("DROP TABLE clp_probe_stray")
        command.downgrade(cfg, "base")
        with engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
        engine.dispose()
