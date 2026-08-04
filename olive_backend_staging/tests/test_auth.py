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

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error

    def json(self) -> dict:
        return self.payload


def _settings() -> Settings:
    return Settings(
        tenant_id="tenant-id",
        client_id="client-id",
        client_secret="client-secret",
        powerbi_base_url="https://api.powerbi.com/v1.0/myorg",
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
