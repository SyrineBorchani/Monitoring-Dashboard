from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from App.auth import get_auth_client
from App.config import get_settings
from App.database import _get_session_factory
from App.models import Base
from App.powerbi_client import get_powerbi_client
from tests.support import build_empty_snapshot, install_test_doubles


@pytest.fixture(autouse=True)
def clear_cached_singletons():
    get_settings.cache_clear()
    get_auth_client.cache_clear()
    get_powerbi_client.cache_clear()
    _get_session_factory.cache_clear()
    yield
    get_settings.cache_clear()
    get_auth_client.cache_clear()
    get_powerbi_client.cache_clear()
    _get_session_factory.cache_clear()


@pytest.fixture
def test_client(monkeypatch: pytest.MonkeyPatch):
    with install_test_doubles(monkeypatch) as client:
        yield client


@pytest.fixture
def empty_test_client(monkeypatch: pytest.MonkeyPatch):
    with install_test_doubles(monkeypatch, seed=build_empty_snapshot()) as client:
        yield client


@pytest.fixture(scope="session")
def postgres_test_db_url() -> str:
    url = make_url(get_settings().database_url)
    admin_url = url.set(database="postgres")
    test_db_name = f"codex_test_{uuid.uuid4().hex[:10]}"
    test_url = url.set(database=test_db_name)

    admin_engine = create_engine(
        admin_url.render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    try:
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{test_db_name}"'))
        yield test_url.render_as_string(hide_password=False)
    finally:
        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": test_db_name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db_name}"'))
        admin_engine.dispose()


@pytest.fixture(scope="session")
def postgres_engine(postgres_test_db_url: str):
    engine = create_engine(postgres_test_db_url)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(postgres_engine) -> Session:
    Base.metadata.drop_all(bind=postgres_engine)
    Base.metadata.create_all(bind=postgres_engine)
    session = Session(bind=postgres_engine, autoflush=False, autocommit=False)
    try:
        yield session
    finally:
        session.close()
