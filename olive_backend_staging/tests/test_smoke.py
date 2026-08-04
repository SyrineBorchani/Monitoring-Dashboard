from __future__ import annotations

import pytest
import requests
from fastapi.testclient import TestClient

from tests.support import (
    ErroringPowerBIClient,
    build_http_error,
    install_test_doubles,
)


def test_ui_routes_smoke(test_client: TestClient) -> None:
    health = test_client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    home = test_client.get("/", follow_redirects=False)
    assert home.status_code == 307
    assert home.headers["location"] == "/dashboard"

    dashboard = test_client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Monitoring Dashboard" in dashboard.text
    assert "/static/dashboard.js" in dashboard.text


def test_stored_endpoints_and_offline_indicators_smoke(
    test_client: TestClient,
) -> None:
    workspaces = test_client.get("/api/powerbi/storage/workspaces")
    reports = test_client.get("/api/powerbi/storage/reports")
    datasets = test_client.get("/api/powerbi/storage/datasets")
    refreshes = test_client.get("/api/powerbi/storage/refreshes?limit=12")
    incidents = test_client.get("/api/powerbi/storage/incidents?limit=30")
    indicators = test_client.get("/api/powerbi/monitoring/indicators?live=false")

    assert workspaces.status_code == 200
    assert len(workspaces.json()["value"]) == 1
    assert reports.status_code == 200
    assert len(reports.json()["value"]) == 1
    assert datasets.status_code == 200
    assert len(datasets.json()["value"]) == 1
    assert refreshes.status_code == 200
    assert len(refreshes.json()["value"]) == 2
    assert incidents.status_code == 200
    assert len(incidents.json()["value"]) == 3

    indicator_payload = indicators.json()
    assert indicators.status_code == 200
    assert indicator_payload["totals"]["refreshes"] == 2
    assert indicator_payload["totals"]["failedRefreshes"] == 2
    assert indicator_payload["totals"]["incidents"] == 3
    assert indicator_payload["rates"]["failureRate"] == 1.0


@pytest.mark.parametrize(
    ("path", "expected_count"),
    [
        ("/api/powerbi/workspaces", 1),
        ("/api/powerbi/reports", 1),
        ("/api/powerbi/datasets", 1),
        ("/api/powerbi/refreshes?refresh_top=2", 2),
        ("/api/powerbi/incidents?refresh_top=2", 3),
        ("/api/powerbi/workspaces/workspace-1/reports", 1),
        ("/api/powerbi/workspaces/workspace-1/datasets", 1),
        (
            "/api/powerbi/workspaces/workspace-1/datasets/dataset-1/refreshes?top=2",
            2,
        ),
    ],
)
def test_live_endpoints_smoke(
    test_client: TestClient,
    path: str,
    expected_count: int,
) -> None:
    response = test_client.get(path)

    assert response.status_code == 200
    assert len(response.json()["value"]) == expected_count


def test_sync_and_live_indicators_smoke(test_client: TestClient) -> None:
    sync_response = test_client.post("/api/powerbi/monitoring/sync?refresh_top=2")
    assert sync_response.status_code == 200
    assert sync_response.json()["counts"] == {
        "workspaces": 1,
        "datasets": 1,
        "refreshes": 2,
        "incidents": 3,
    }

    indicators_response = test_client.get(
        "/api/powerbi/monitoring/indicators?live=true&refresh_top=2"
    )
    assert indicators_response.status_code == 200

    indicator_payload = indicators_response.json()
    assert indicator_payload["totals"]["refreshes"] == 2
    assert indicator_payload["totals"]["failedRefreshes"] == 2
    assert indicator_payload["incidents"]["byGateway"] == [
        {"gatewayId": "gateway-1", "count": 3}
    ]


def test_offline_endpoints_return_empty_results_for_empty_storage(
    empty_test_client: TestClient,
) -> None:
    workspaces = empty_test_client.get("/api/powerbi/storage/workspaces")
    reports = empty_test_client.get("/api/powerbi/storage/reports")
    datasets = empty_test_client.get("/api/powerbi/storage/datasets")
    refreshes = empty_test_client.get("/api/powerbi/storage/refreshes?limit=12")
    incidents = empty_test_client.get("/api/powerbi/storage/incidents?limit=30")
    indicators = empty_test_client.get("/api/powerbi/monitoring/indicators?live=false")

    assert workspaces.json() == {"value": []}
    assert reports.json() == {"value": []}
    assert datasets.json() == {"value": []}
    assert refreshes.json() == {"value": []}
    assert incidents.json() == {"value": []}
    assert indicators.json()["totals"] == {
        "refreshes": 0,
        "successfulRefreshes": 0,
        "failedRefreshes": 0,
        "inProgressRefreshes": 0,
        "incidents": 0,
        "delayedRefreshes": 0,
        "durationAnomalies": 0,
    }


@pytest.mark.parametrize(
    "path",
    [
        "/api/powerbi/workspaces/missing-workspace/datasets",
        "/api/powerbi/workspaces/missing-workspace/datasets/dataset-1/refreshes",
    ],
)
def test_invalid_workspace_returns_404(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    with install_test_doubles(monkeypatch) as client:
        response = client.get(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "Workspace not found."}


def test_invalid_dataset_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    with install_test_doubles(monkeypatch) as client:
        response = client.get(
            "/api/powerbi/workspaces/workspace-1/datasets/missing-dataset/refreshes"
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Dataset not found."}


def test_upstream_auth_error_is_returned_with_original_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_error = build_http_error(
        401,
        {
            "error": {
                "code": "PowerBINotAuthorizedException",
                "message": "Access denied to the requested workspace.",
            }
        },
    )
    with install_test_doubles(
        monkeypatch,
        client=ErroringPowerBIClient(auth_error),
    ) as client:
        response = client.get("/api/powerbi/workspaces")

    assert response.status_code == 401
    assert response.json() == {
        "detail": {
            "error": {
                "code": "PowerBINotAuthorizedException",
                "message": "Access denied to the requested workspace.",
            }
        }
    }


def test_upstream_request_exception_returns_502(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_error = requests.RequestException("network unavailable")
    with install_test_doubles(
        monkeypatch,
        client=ErroringPowerBIClient(request_error),
    ) as client:
        response = client.get("/api/powerbi/workspaces")

    assert response.status_code == 502
    assert response.json() == {"detail": "network unavailable"}
