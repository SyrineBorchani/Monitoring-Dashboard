from __future__ import annotations

from urllib.parse import quote_plus

import pytest

from App.config import _normalize_database_url, get_settings


def _set_minimum_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_ID", "tenant-id")
    monkeypatch.setenv("CLIENT_ID", "client-id")
    monkeypatch.setenv("CLIENT_SECRET", "client-secret")


@pytest.mark.parametrize(
    ("raw_url", "expected_url"),
    [
        (
            "postgres://user:pass@localhost:5432/appdb",
            "postgresql+pg8000://user:pass@localhost:5432/appdb",
        ),
        (
            "postgresql://user:pass@localhost:5432/appdb",
            "postgresql+pg8000://user:pass@localhost:5432/appdb",
        ),
        (
            "postgresql+psycopg2://user:pass@localhost:5432/appdb",
            "postgresql+pg8000://user:pass@localhost:5432/appdb",
        ),
        (
            "postgresql+pg8000://user:pass@localhost:5432/appdb",
            "postgresql+pg8000://user:pass@localhost:5432/appdb",
        ),
    ],
)
def test_normalize_database_url_rewrites_supported_schemes(
    raw_url: str,
    expected_url: str,
) -> None:
    assert _normalize_database_url(raw_url) == expected_url


def test_get_settings_prefers_database_url_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_minimum_environment(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:pass@localhost:5432/monitoring_dashboard",
    )
    monkeypatch.setenv("POWERBI_BASE_URL", "https://api.powerbi.com/v1.0/myorg/")

    settings = get_settings()

    assert settings.database_url == (
        "postgresql+pg8000://user:pass@localhost:5432/monitoring_dashboard"
    )
    assert settings.powerbi_base_url == "https://api.powerbi.com/v1.0/myorg"
    assert settings.token_url == (
        "https://login.microsoftonline.com/tenant-id/oauth2/v2.0/token"
    )


def test_get_settings_assembles_database_url_from_postgres_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_minimum_environment(monkeypatch)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "monitoring")
    monkeypatch.setenv("POSTGRES_USER", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss word")

    settings = get_settings()

    assert settings.database_url == (
        "postgresql+pg8000://postgres:"
        f"{quote_plus('p@ss word')}@db.internal:5433/monitoring"
    )


def test_get_settings_raises_when_required_values_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TENANT_ID", raising=False)
    monkeypatch.setenv("CLIENT_ID", "client-id")
    monkeypatch.setenv("CLIENT_SECRET", "client-secret")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+pg8000://user:pass@localhost:5432/monitoring_dashboard",
    )

    with pytest.raises(RuntimeError, match="TENANT_ID"):
        get_settings()
