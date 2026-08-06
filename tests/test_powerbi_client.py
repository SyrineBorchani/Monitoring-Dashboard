from __future__ import annotations

from dataclasses import dataclass

import pytest
import requests

from App.config import Settings
from App.powerbi_client import PowerBIClient


class FakeAuthClient:
    def __init__(self) -> None:
        self.calls = []

    def get_access_token(
        self,
        force_refresh: bool = False,
        scope: str | None = None,
    ) -> str:
        self.calls.append({"force_refresh": force_refresh, "scope": scope})
        return "token-refresh" if force_refresh else "token-initial"


@dataclass
class DummyResponse:
    status_code: int
    payload: object
    error: Exception | None = None
    json_error: Exception | None = None

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error

    def json(self) -> object:
        if self.json_error is not None:
            raise self.json_error
        return self.payload


def _settings() -> Settings:
    return Settings(
        tenant_id="tenant-id",
        client_id="client-id",
        client_secret="client-secret",
        powerbi_base_url="https://api.powerbi.com/v1.0/myorg",
        fabric_base_url="https://api.fabric.microsoft.com/v1",
        database_url="postgresql+pg8000://postgres:postgres@localhost:5432/db",
    )


def test_request_retries_once_after_401(monkeypatch) -> None:
    auth_client = FakeAuthClient()
    captured_calls = []
    responses = iter(
        [
            DummyResponse(401, {"error": "expired token"}),
            DummyResponse(200, {"value": [{"id": "workspace-1"}]}),
        ]
    )

    def fake_request(method, url, headers, params, timeout):
        captured_calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "params": params,
                "timeout": timeout,
            }
        )
        return next(responses)

    monkeypatch.setattr("App.powerbi_client.requests.request", fake_request)
    client = PowerBIClient(_settings(), auth_client)

    payload = client.list_workspaces()

    assert payload == [{"id": "workspace-1"}]
    assert auth_client.calls == [
        {"force_refresh": False, "scope": None},
        {"force_refresh": True, "scope": None},
    ]
    assert captured_calls[0]["headers"]["Authorization"] == "Bearer token-initial"
    assert captured_calls[1]["headers"]["Authorization"] == "Bearer token-refresh"


def test_request_formats_headers_path_and_timeout(monkeypatch) -> None:
    auth_client = FakeAuthClient()
    captured_calls = []

    def fake_request(method, url, headers, params, timeout):
        captured_calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "params": params,
                "timeout": timeout,
            }
        )
        return DummyResponse(200, {"value": [{"id": "report-1"}]})

    monkeypatch.setattr("App.powerbi_client.requests.request", fake_request)
    client = PowerBIClient(_settings(), auth_client)

    payload = client.list_workspace_reports("workspace-1")

    assert payload == [{"id": "report-1"}]
    assert captured_calls == [
        {
            "method": "GET",
            "url": "https://api.powerbi.com/v1.0/myorg/groups/workspace-1/reports",
            "headers": {
                "Authorization": "Bearer token-initial",
                "Content-Type": "application/json",
            },
            "params": None,
            "timeout": 30,
        }
    ]


def test_list_dataset_refresh_history_passes_top_query_parameter(monkeypatch) -> None:
    auth_client = FakeAuthClient()
    captured_calls = []

    def fake_request(method, url, headers, params, timeout):
        captured_calls.append({"url": url, "params": params})
        return DummyResponse(200, {"value": [{"requestId": "refresh-1"}]})

    monkeypatch.setattr("App.powerbi_client.requests.request", fake_request)
    client = PowerBIClient(_settings(), auth_client)

    payload = client.list_dataset_refresh_history("workspace-1", "dataset-1", top=5)

    assert payload == [{"requestId": "refresh-1"}]
    assert captured_calls == [
        {
            "url": (
                "https://api.powerbi.com/v1.0/myorg/"
                "groups/workspace-1/datasets/dataset-1/refreshes"
            ),
            "params": {"$top": 5},
        }
    ]


def test_request_propagates_request_exceptions(monkeypatch) -> None:
    auth_client = FakeAuthClient()

    def fake_request(method, url, headers, params, timeout):
        raise requests.RequestException("socket timeout")

    monkeypatch.setattr("App.powerbi_client.requests.request", fake_request)
    client = PowerBIClient(_settings(), auth_client)

    try:
        client.list_workspaces()
    except requests.RequestException as error:
        assert str(error) == "socket timeout"
    else:
        raise AssertionError("Expected a RequestException to be raised.")


def test_request_invalid_json_raises_request_exception(monkeypatch) -> None:
    auth_client = FakeAuthClient()

    def fake_request(method, url, headers, params, timeout):
        return DummyResponse(200, {}, json_error=ValueError("bad json"))

    monkeypatch.setattr("App.powerbi_client.requests.request", fake_request)
    client = PowerBIClient(_settings(), auth_client)

    with pytest.raises(
        requests.RequestException,
        match="Power BI/Fabric API returned invalid JSON",
    ):
        client.list_workspaces()


def test_request_unexpected_payload_shape_raises_request_exception(monkeypatch) -> None:
    auth_client = FakeAuthClient()

    def fake_request(method, url, headers, params, timeout):
        return DummyResponse(200, {"value": {"id": "workspace-1"}})

    monkeypatch.setattr("App.powerbi_client.requests.request", fake_request)
    client = PowerBIClient(_settings(), auth_client)

    with pytest.raises(
        requests.RequestException,
        match="Power BI API returned an unexpected value payload",
    ):
        client.list_workspaces()


def test_list_workspace_warehouses_uses_fabric_base_url_and_scope(monkeypatch) -> None:
    auth_client = FakeAuthClient()
    captured_calls = []

    def fake_request(method, url, headers, params, timeout):
        captured_calls.append({"url": url, "params": params, "headers": headers})
        return DummyResponse(200, {"value": [{"id": "warehouse-1"}]})

    monkeypatch.setattr("App.powerbi_client.requests.request", fake_request)
    client = PowerBIClient(_settings(), auth_client)

    payload = client.list_workspace_warehouses("workspace-1")

    assert payload == [{"id": "warehouse-1"}]
    assert captured_calls == [
        {
            "url": "https://api.fabric.microsoft.com/v1/workspaces/workspace-1/warehouses",
            "params": None,
            "headers": {
                "Authorization": "Bearer token-initial",
                "Content-Type": "application/json",
            },
        }
    ]
    assert auth_client.calls == [
        {
            "force_refresh": False,
            "scope": "https://api.fabric.microsoft.com/.default",
        }
    ]
