from __future__ import annotations

from sqlalchemy import inspect, text

import App.database as database_module
from App.config import Settings
from App.database import _get_session_factory, get_db_session, init_db


def _settings(database_url: str) -> Settings:
    return Settings(
        tenant_id="tenant-id",
        client_id="client-id",
        client_secret="client-secret",
        powerbi_base_url="https://api.powerbi.com/v1.0/myorg",
        fabric_base_url="https://api.fabric.microsoft.com/v1",
        database_url=database_url,
    )


def test_init_db_creates_schema_and_get_db_session_returns_working_session(
    monkeypatch,
    postgres_test_db_url: str,
) -> None:
    monkeypatch.setattr(
        database_module,
        "get_settings",
        lambda: _settings(postgres_test_db_url),
    )
    _get_session_factory.cache_clear()

    init_db()
    session = get_db_session()

    try:
        assert inspect(session.bind).has_table("workspaces")
        assert inspect(session.bind).has_table("refresh_history")
        assert inspect(session.bind).has_table("dataset_measurements")
        assert inspect(session.bind).has_table("fabric_items")
        assert inspect(session.bind).has_table("fabric_executions")
        assert inspect(session.bind).has_table("fabric_sql_executions")
        assert inspect(session.bind).has_table("app_schema_version")
        assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        session.close()
