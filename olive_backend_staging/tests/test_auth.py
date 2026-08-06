from __future__ import annotations

from dataclasses import dataclass

import pytest
import requests

from App.auth import EntraIdAuthClient
from App.config import Settings


@dataclass
class DummyResponse:
    payload: dict
    status_code: int = 200
    error: Exception | None = None
    json_error: Exception | None = None

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error

    def json(self) -> dict:
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


def test_get_access_token_caches_valid_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_post(url, data, timeout):
        calls.append({"url": url, "data": data, "timeout": timeout})
        return DummyResponse({"access_token": "token-1", "expires_in": 3600})

    monkeypatch.setattr("App.auth.requests.post", fake_post)
    client = EntraIdAuthClient(_settings())

    first = client.get_access_token()
    second = client.get_access_token()

    assert first == "token-1"
    assert second == "token-1"
    assert len(calls) == 1
    assert calls[0]["data"]["grant_type"] == "client_credentials"


def test_get_access_token_formats_entra_request_and_uses_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def fake_post(url, data, timeout):
        captured.update({"url": url, "data": data, "timeout": timeout})
        return DummyResponse({"access_token": "token-1", "expires_in": 3600})

    monkeypatch.setattr("App.auth.requests.post", fake_post)
    client = EntraIdAuthClient(_settings())

    token = client.get_access_token()

    assert token == "token-1"
    assert captured == {
        "url": "https://login.microsoftonline.com/tenant-id/oauth2/v2.0/token",
        "data": {
            "grant_type": "client_credentials",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "scope": "https://analysis.windows.net/powerbi/api/.default",
        },
        "timeout": 30,
    }


def test_get_access_token_force_refresh_fetches_new_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued_tokens = iter(["token-1", "token-2"])

    def fake_post(url, data, timeout):
        return DummyResponse(
            {"access_token": next(issued_tokens), "expires_in": 3600}
        )

    monkeypatch.setattr("App.auth.requests.post", fake_post)
    client = EntraIdAuthClient(_settings())

    first = client.get_access_token()
    second = client.get_access_token(force_refresh=True)

    assert first == "token-1"
    assert second == "token-2"


def test_get_access_token_caches_tokens_per_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    issued_tokens = iter(["powerbi-token", "fabric-token"])

    def fake_post(url, data, timeout):
        calls.append(data["scope"])
        return DummyResponse({"access_token": next(issued_tokens), "expires_in": 3600})

    monkeypatch.setattr("App.auth.requests.post", fake_post)
    client = EntraIdAuthClient(_settings())

    assert client.get_access_token() == "powerbi-token"
    assert client.get_access_token() == "powerbi-token"
    assert client.get_access_token(scope="https://api.fabric.microsoft.com/.default") == "fabric-token"
    assert client.get_access_token(scope="https://api.fabric.microsoft.com/.default") == "fabric-token"
    assert calls == [
        "https://analysis.windows.net/powerbi/api/.default",
        "https://api.fabric.microsoft.com/.default",
    ]


def test_get_access_token_propagates_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = requests.HTTPError("invalid credentials")

    def fake_post(url, data, timeout):
        return DummyResponse({}, error=error)

    monkeypatch.setattr("App.auth.requests.post", fake_post)
    client = EntraIdAuthClient(_settings())

    with pytest.raises(requests.HTTPError, match="invalid credentials"):
        client.get_access_token()


def test_get_access_token_invalid_json_raises_request_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url, data, timeout):
        return DummyResponse({}, json_error=ValueError("bad json"))

    monkeypatch.setattr("App.auth.requests.post", fake_post)
    client = EntraIdAuthClient(_settings())

    with pytest.raises(
        requests.RequestException,
        match="Microsoft Entra token response was not valid JSON",
    ):
        client.get_access_token()


def test_get_access_token_missing_access_token_raises_request_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url, data, timeout):
        return DummyResponse({"expires_in": 3600})

    monkeypatch.setattr("App.auth.requests.post", fake_post)
    client = EntraIdAuthClient(_settings())

    with pytest.raises(
        requests.RequestException,
        match="Microsoft Entra token response missing access_token",
    ):
        client.get_access_token()
