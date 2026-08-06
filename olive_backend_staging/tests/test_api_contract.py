from __future__ import annotations

import pytest
import requests
from fastapi.testclient import TestClient

from tests.support import ErroringPowerBIClient, build_http_error, install_test_doubles


def test_mode_endpoint_returns_static_operating_mode_metadata(
    test_client: TestClient,
) -> None:
    response = test_client.get("/api/powerbi/mode")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "live",
        "title": "Environnement connecte",
        "description": (
            "Le dashboard interroge les APIs Power BI et historise les donnees dans "
            "la base PostgreSQL configuree."
        ),
    }


@pytest.mark.parametrize(
    "path",
    [
        "/api/powerbi/refreshes?refresh_top=0",
        "/api/powerbi/refreshes?refresh_top=101",
        "/api/powerbi/incidents?refresh_top=0",
        "/api/powerbi/monitoring/sync?refresh_top=101",
        "/api/powerbi/workspaces/workspace-1/datasets/dataset-1/refreshes?top=0",
        "/api/powerbi/storage/refreshes?limit=0",
        "/api/powerbi/storage/incidents?limit=5001",
    ],
)
def test_query_validation_errors_return_422(
    test_client: TestClient,
    path: str,
) -> None:
    response = test_client.get(path) if "monitoring/sync" not in path else test_client.post(path)

    assert response.status_code == 422


def test_upstream_text_http_error_surfaces_plain_text_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text_error = build_http_error(
        503,
        None,
        text_body="powerbi unavailable",
        content_type="text/plain",
    )
    with install_test_doubles(
        monkeypatch,
        client=ErroringPowerBIClient(text_error),
    ) as client:
        response = client.get("/api/powerbi/workspaces")

    assert response.status_code == 200
    assert response.json() == {
        "value": [
            {
                "id": "workspace-1",
                "name": "Syrine",
                "type": "Workspace",
                "isReadOnly": False,
                "isOnDedicatedCapacity": False,
                "workspaceId": "workspace-1",
                "workspaceName": "Syrine",
                "workspaceType": "Workspace",
                "capacityId": None,
                "capacityMode": "Shared",
                "defaultDatasetStorageFormat": None,
            }
        ],
        "mode": "cached",
        "warning": "Live Power BI data was unavailable upstream. Returned cached data instead.",
        "upstreamStatus": 503,
    }


def test_upstream_rate_limit_error_preserves_429_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rate_limit_error = build_http_error(
        429,
        {
            "error": {
                "code": "TooManyRequests",
                "message": "Rate limit exceeded.",
            }
        },
    )
    with install_test_doubles(
        monkeypatch,
        client=ErroringPowerBIClient(rate_limit_error),
    ) as client:
        response = client.get("/api/powerbi/workspaces")

    assert response.status_code == 200
    assert response.json()["mode"] == "cached"
    assert response.json()["warning"] == (
        "Live Power BI data was rate-limited. Returned cached data instead."
    )
    assert response.json()["upstreamStatus"] == 429
    assert len(response.json()["value"]) == 1


def test_upstream_http_error_without_response_maps_to_default_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    no_response_error = build_http_error(500)
    no_response_error.response = None

    with install_test_doubles(
        monkeypatch,
        client=ErroringPowerBIClient(no_response_error),
    ) as client:
        response = client.get("/api/powerbi/workspaces")

    assert response.status_code == 502
    assert response.json() == {"detail": "Power BI API request failed."}


def test_upstream_timeout_is_translated_to_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with install_test_doubles(
        monkeypatch,
        client=ErroringPowerBIClient(requests.Timeout("request timed out")),
    ) as client:
        response = client.get("/api/powerbi/workspaces")

    assert response.status_code == 200
    assert response.json()["mode"] == "cached"
    assert response.json()["warning"] == (
        "Live Power BI data timed out. Returned cached data instead."
    )
    assert len(response.json()["value"]) == 1


def test_live_indicators_fall_back_to_cached_summary_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with install_test_doubles(
        monkeypatch,
        client=ErroringPowerBIClient(requests.Timeout("request timed out")),
    ) as client:
        response = client.get("/api/powerbi/monitoring/indicators?live=true")

    assert response.status_code == 200
    assert response.json()["mode"] == "cached"
    assert response.json()["warning"] == (
        "Live Power BI data timed out. Returned cached data instead."
    )
    assert response.json()["totals"]["refreshes"] == 2


def test_sync_endpoint_still_surfaces_upstream_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text_error = build_http_error(
        503,
        None,
        text_body="powerbi unavailable",
        content_type="text/plain",
    )
    with install_test_doubles(
        monkeypatch,
        client=ErroringPowerBIClient(text_error),
    ) as client:
        response = client.post("/api/powerbi/monitoring/sync")

    assert response.status_code == 503
    assert response.json() == {"detail": "powerbi unavailable"}


class MalformedWorkspaceClient:
    def list_workspaces(self):
        return [
            {"id": "workspace-1", "name": "Syrine", "type": "Workspace"},
            {"name": "missing-id"},
            "not-a-dict",
        ]

    def list_workspace_reports(self, workspace_id: str):
        return []

    def list_workspace_datasets(self, workspace_id: str):
        return []

    def list_dataset_datasources(self, workspace_id: str, dataset_id: str):
        return []

    def list_dataset_refresh_history(self, workspace_id: str, dataset_id: str, top: int = 10):
        return []


def test_malformed_workspace_payloads_are_skipped_instead_of_breaking_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with install_test_doubles(
        monkeypatch,
        client=MalformedWorkspaceClient(),
    ) as client:
        response = client.get("/api/powerbi/workspaces")

    assert response.status_code == 200
    assert response.json() == {
        "value": [
            {
                "id": "workspace-1",
                "name": "Syrine",
                "type": "Workspace",
                "workspaceId": "workspace-1",
                "workspaceName": "Syrine",
                "workspaceType": "Workspace",
                "capacityId": None,
                "capacityMode": "Shared",
                "defaultDatasetStorageFormat": None,
            }
        ]
    }
