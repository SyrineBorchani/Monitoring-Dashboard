from __future__ import annotations

import requests

from App import dependency_checks
from tests.support import build_http_error


class FakeAuthClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = []

    def get_access_token(self, force_refresh: bool = False) -> str:
        self.calls.append(force_refresh)
        if self.error is not None:
            raise self.error
        return "token"


class FakePowerBIClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def list_workspaces(self):
        if self.error is not None:
            raise self.error
        return [{"id": "workspace-1"}]


def test_check_external_dependencies_reports_success(monkeypatch) -> None:
    monkeypatch.setattr(
        dependency_checks,
        "get_auth_client",
        lambda: FakeAuthClient(),
    )
    monkeypatch.setattr(
        dependency_checks,
        "get_powerbi_client",
        lambda: FakePowerBIClient(),
    )

    payload = dependency_checks.check_external_dependencies()

    assert payload == {
        "entra": {"status": "ok"},
        "powerbi": {"status": "ok", "workspaceCount": 1},
    }


def test_check_external_dependencies_reports_entra_auth_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        dependency_checks,
        "get_auth_client",
        lambda: FakeAuthClient(
            build_http_error(
                401,
                {
                    "error": {
                        "code": "Unauthorized",
                        "message": "invalid client",
                    }
                },
            )
        ),
    )
    monkeypatch.setattr(
        dependency_checks,
        "get_powerbi_client",
        lambda: FakePowerBIClient(),
    )

    payload = dependency_checks.check_external_dependencies()

    assert payload["entra"]["status"] == "error"
    assert payload["entra"]["upstreamStatus"] == 401
    assert payload["powerbi"]["status"] == "skipped"


def test_check_external_dependencies_reports_powerbi_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        dependency_checks,
        "get_auth_client",
        lambda: FakeAuthClient(),
    )
    monkeypatch.setattr(
        dependency_checks,
        "get_powerbi_client",
        lambda: FakePowerBIClient(requests.Timeout("request timed out")),
    )

    payload = dependency_checks.check_external_dependencies()

    assert payload["entra"] == {"status": "ok"}
    assert payload["powerbi"] == {
        "status": "error",
        "detail": "request timed out",
    }
