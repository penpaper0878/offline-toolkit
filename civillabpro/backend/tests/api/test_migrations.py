"""The Alembic history must build exactly the schema the models describe."""

import pathlib

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from alembic import command
from app.core.database import Base, make_engine
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
