from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from App.migrations import CURRENT_SCHEMA_VERSION, migrate_database
from App.models import Base, Workspace


def _reset_database(engine) -> None:
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS app_schema_version"))


def test_migrate_database_bootstraps_fresh_database(
    postgres_test_db_url: str,
) -> None:
    engine = create_engine(postgres_test_db_url)
    _reset_database(engine)

    try:
        migrate_database(engine)

        inspector = inspect(engine)
        assert inspector.has_table("workspaces")
        assert inspector.has_table("dataset_measurements")
        assert inspector.has_table("fabric_items")
        assert inspector.has_table("fabric_executions")
        assert inspector.has_table("fabric_sql_executions")
        assert inspector.has_table("app_schema_version")
        with engine.connect() as connection:
            version = connection.execute(
                text("SELECT version_num FROM app_schema_version WHERE id = 1")
            ).scalar_one()
        assert version == CURRENT_SCHEMA_VERSION
    finally:
        _reset_database(engine)
        engine.dispose()


def test_migrate_database_stamps_legacy_schema_without_version_table(
    postgres_test_db_url: str,
) -> None:
    engine = create_engine(postgres_test_db_url)
    _reset_database(engine)

    try:
        Base.metadata.create_all(bind=engine)

        migrate_database(engine)

        with engine.connect() as connection:
            version = connection.execute(
                text("SELECT version_num FROM app_schema_version WHERE id = 1")
            ).scalar_one()
        assert version == CURRENT_SCHEMA_VERSION
    finally:
        _reset_database(engine)
        engine.dispose()


def test_migrate_database_rejects_partial_legacy_schema(
    postgres_test_db_url: str,
) -> None:
    engine = create_engine(postgres_test_db_url)
    _reset_database(engine)

    try:
        Workspace.__table__.create(bind=engine)

        try:
            migrate_database(engine)
        except RuntimeError as error:
            assert "partially initialized database" in str(error)
        else:
            raise AssertionError("Expected migrate_database() to reject partial legacy schema.")
    finally:
        _reset_database(engine)
        engine.dispose()
