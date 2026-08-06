from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    Table,
    inspect,
    select,
    update,
)
from sqlalchemy.engine import Connection, Engine

from App.models import Base


SCHEMA_VERSION_TABLE_NAME = "app_schema_version"
SCHEMA_VERSION_ROW_ID = 1

schema_version_metadata = MetaData()
schema_version_table = Table(
    SCHEMA_VERSION_TABLE_NAME,
    schema_version_metadata,
    Column("id", Integer, primary_key=True),
    Column("version_num", Integer, nullable=False),
)


@dataclass(frozen=True)
class MigrationStep:
    version: int
    description: str
    apply: Callable[[Connection], None]


def _create_initial_schema(connection: Connection) -> None:
    Base.metadata.create_all(bind=connection)


def _create_dataset_measurements_table(connection: Connection) -> None:
    Base.metadata.tables["dataset_measurements"].create(
        bind=connection,
        checkfirst=True,
    )


def _create_fabric_monitoring_tables(connection: Connection) -> None:
    for table_name in (
        "fabric_items",
        "fabric_executions",
        "fabric_sql_executions",
    ):
        Base.metadata.tables[table_name].create(
            bind=connection,
            checkfirst=True,
        )


MIGRATIONS: Sequence[MigrationStep] = (
    MigrationStep(
        version=1,
        description="Create the initial Power BI monitoring schema.",
        apply=_create_initial_schema,
    ),
    MigrationStep(
        version=2,
        description="Create the historical dataset measurements table.",
        apply=_create_dataset_measurements_table,
    ),
    MigrationStep(
        version=3,
        description="Store Fabric warehouses, lakehouses, and execution telemetry.",
        apply=_create_fabric_monitoring_tables,
    ),
)
CURRENT_SCHEMA_VERSION = MIGRATIONS[-1].version


def migrate_database(engine: Engine) -> None:
    with engine.begin() as connection:
        existing_tables = set(inspect(connection).get_table_names())
        app_tables = set(Base.metadata.tables)
        has_version_table = SCHEMA_VERSION_TABLE_NAME in existing_tables
        existing_app_tables = existing_tables.intersection(app_tables)

        if has_version_table:
            current_version = _read_schema_version(connection)
            _apply_pending_migrations(connection, current_version)
            return

        if not existing_app_tables:
            _create_version_table(connection)
            _apply_pending_migrations(connection, 0)
            return

        if app_tables.issubset(existing_tables):
            _create_version_table(connection)
            _write_schema_version(connection, CURRENT_SCHEMA_VERSION)
            return

        raise RuntimeError(
            "Detected a partially initialized database without schema versioning. "
            "Create the missing tables manually or reset the schema before starting the app."
        )


def _create_version_table(connection: Connection) -> None:
    schema_version_metadata.create_all(bind=connection, checkfirst=True)


def _read_schema_version(connection: Connection) -> int:
    row = connection.execute(
        select(schema_version_table.c.version_num).where(
            schema_version_table.c.id == SCHEMA_VERSION_ROW_ID
        )
    ).first()
    if row is None:
        _write_schema_version(connection, 0)
        return 0
    return int(row[0])


def _write_schema_version(connection: Connection, version: int) -> None:
    if connection.execute(
        select(schema_version_table.c.id).where(
            schema_version_table.c.id == SCHEMA_VERSION_ROW_ID
        )
    ).first():
        connection.execute(
            update(schema_version_table)
            .where(schema_version_table.c.id == SCHEMA_VERSION_ROW_ID)
            .values(version_num=version)
        )
        return

    connection.execute(
        schema_version_table.insert().values(
            id=SCHEMA_VERSION_ROW_ID,
            version_num=version,
        )
    )


def _apply_pending_migrations(connection: Connection, current_version: int) -> None:
    if current_version > CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            "Database schema version is newer than this application supports."
        )

    for migration in MIGRATIONS:
        if migration.version <= current_version:
            continue
        migration.apply(connection)
        _write_schema_version(connection, migration.version)
