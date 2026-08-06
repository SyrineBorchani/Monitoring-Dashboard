from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from App import main
from App.routes import ui


def test_lifespan_initializes_database_once(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(main, "init_db", lambda: calls.append("called"))
    monkeypatch.setattr(main, "check_database_connection", lambda: (True, None))
    monkeypatch.setattr(
        main,
        "check_external_dependencies",
        lambda: {
            "entra": {"status": "ok"},
            "powerbi": {"status": "ok", "workspaceCount": 1},
        },
    )

    with TestClient(main.app):
        pass

    assert calls == ["called"]


def test_dashboard_returns_404_when_asset_is_missing(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "check_database_connection", lambda: (True, None))
    monkeypatch.setattr(
        main,
        "check_external_dependencies",
        lambda: {
            "entra": {"status": "ok"},
            "powerbi": {"status": "ok", "workspaceCount": 1},
        },
    )
    monkeypatch.setattr(ui, "STATIC_DIR", tmp_path / "missing")

    with TestClient(main.app) as client:
        response = client.get("/dashboard")

    assert response.status_code == 404
    assert response.json() == {"detail": "Dashboard asset not found."}


def test_dashboard_returns_503_when_asset_is_not_readable(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "check_database_connection", lambda: (True, None))
    monkeypatch.setattr(
        main,
        "check_external_dependencies",
        lambda: {
            "entra": {"status": "ok"},
            "powerbi": {"status": "ok", "workspaceCount": 1},
        },
    )
    monkeypatch.setattr(ui, "STATIC_DIR", tmp_path)
    dashboard_path = tmp_path / "dashboard.html"
    dashboard_path.write_text("<html></html>", encoding="utf-8")

    original_open = Path.open

    def fake_open(self, *args, **kwargs):
        if self == dashboard_path:
            raise PermissionError("denied")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)

    with TestClient(main.app) as client:
        response = client.get("/dashboard")

    assert response.status_code == 503
    assert response.json() == {"detail": "Dashboard asset is not readable."}


def test_static_assets_are_served_even_if_working_directory_changes(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "check_database_connection", lambda: (True, None))
    monkeypatch.setattr(
        main,
        "check_external_dependencies",
        lambda: {
            "entra": {"status": "ok"},
            "powerbi": {"status": "ok", "workspaceCount": 1},
        },
    )
    monkeypatch.chdir(tmp_path)

    with TestClient(main.app) as client:
        response = client.get("/static/dashboard.js")

    assert response.status_code == 200
    assert "fetch(" in response.text


def test_health_returns_503_when_database_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(
        main,
        "check_database_connection",
        lambda: (False, "connection refused"),
    )
    monkeypatch.setattr(
        main,
        "check_external_dependencies",
        lambda: {
            "entra": {"status": "ok"},
            "powerbi": {"status": "ok", "workspaceCount": 1},
        },
    )

    with TestClient(main.app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "database": "unavailable",
        "detail": "connection refused",
    }


def test_dependency_health_returns_503_when_external_dependency_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "check_database_connection", lambda: (True, None))
    monkeypatch.setattr(
        main,
        "check_external_dependencies",
        lambda: {
            "entra": {
                "status": "error",
                "detail": "Microsoft Entra token request failed.",
                "upstreamStatus": 401,
            },
            "powerbi": {
                "status": "skipped",
                "detail": "Power BI check skipped because Entra authentication failed.",
            },
        },
    )

    with TestClient(main.app) as client:
        response = client.get("/health/dependencies")

    assert response.status_code == 503
    assert response.json()["entra"]["status"] == "error"
    assert response.json()["powerbi"]["status"] == "skipped"
