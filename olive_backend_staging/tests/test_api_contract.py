from __future__ import annotations

import pytest
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

    assert response.status_code == 503
    assert response.json() == {"detail": "powerbi unavailable"}


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
