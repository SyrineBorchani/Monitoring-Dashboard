from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict, List, Tuple

import requests
from fastapi.testclient import TestClient

from App.analytics import (
    build_dataset_record,
    build_datasource_record,
    build_refresh_record,
    build_workspace_record,
    derive_incidents,
)


WORKSPACE_RAW = {
    "id": "workspace-1",
    "name": "Syrine",
    "type": "Workspace",
    "isReadOnly": False,
    "isOnDedicatedCapacity": False,
}

REPORT_RAW = {
    "id": "report-1",
    "name": "Operations Overview",
    "datasetId": "dataset-1",
    "webUrl": "https://app.powerbi.com/report-1",
    "embedUrl": "https://app.powerbi.com/embed/report-1",
}

DATASET_RAW = {
    "id": "dataset-1",
    "name": "report",
    "configuredBy": "ops@olivesoft.example",
    "isRefreshable": True,
    "isOnPremGatewayRequired": True,
}

DATASOURCE_RAW = {
    "datasourceType": "File",
    "gatewayId": "gateway-1",
    "connectionDetails": {
        "path": r"C:\Data\report.xlsx",
    },
}

REFRESH_HISTORY_RAW = [
    {
        "requestId": "refresh-2",
        "status": "Failed",
        "refreshType": "Scheduled",
        "startTime": "2026-08-04T08:30:00Z",
        "endTime": "2026-08-04T08:42:00Z",
        "refreshAttempts": [
            {
                "serviceExceptionJson": json.dumps(
                    {
                        "errorCode": "GatewayTimeout",
                        "errorMessage": "Gateway timeout while reading the source.",
                    }
                )
            }
        ],
    },
    {
        "requestId": "refresh-1",
        "status": "Failed",
        "refreshType": "Scheduled",
        "startTime": "2026-08-04T06:00:00Z",
        "endTime": "2026-08-04T06:10:00Z",
        "refreshAttempts": [
            {
                "serviceExceptionJson": json.dumps(
                    {
                        "errorCode": "GatewayTimeout",
                        "errorMessage": "Gateway timeout while reading the source.",
                    }
                )
            }
        ],
    },
]


def build_empty_snapshot() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "workspaces": [],
        "reports": [],
        "datasets": [],
        "refreshes": [],
        "incidents": [],
    }


def build_seed_snapshot() -> Dict[str, List[Dict[str, Any]]]:
    workspace = build_workspace_record(deepcopy(WORKSPACE_RAW))
    datasources = [build_datasource_record(deepcopy(DATASOURCE_RAW))]
    dataset = build_dataset_record(deepcopy(DATASET_RAW), workspace, datasources)
    refreshes = [
        build_refresh_record(deepcopy(item), workspace, dataset)
        for item in REFRESH_HISTORY_RAW
    ]
    incidents = derive_incidents(refreshes)
    report = {
        **deepcopy(REPORT_RAW),
        "workspaceId": workspace["workspaceId"],
        "workspaceName": workspace["workspaceName"],
    }
    return {
        "workspaces": [workspace],
        "reports": [report],
        "datasets": [dataset],
        "refreshes": refreshes,
        "incidents": incidents,
    }


class FakeDb:
    def close(self) -> None:
        return None


class FakeStorage:
    def __init__(self, seed: Dict[str, List[Dict[str, Any]]]) -> None:
        self.db = FakeDb()
        self._workspaces: Dict[str, Dict[str, Any]] = {}
        self._reports: Dict[str, Dict[str, Any]] = {}
        self._datasets: Dict[str, Dict[str, Any]] = {}
        self._refreshes: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        self._incidents: Dict[str, Dict[str, Any]] = {}

        self.upsert_workspaces(seed["workspaces"])
        for report in seed["reports"]:
            self._reports[report["id"]] = deepcopy(report)
        if seed["workspaces"] and seed["datasets"]:
            self.upsert_datasets(seed["workspaces"][0]["workspaceId"], seed["datasets"])
            self.upsert_refresh_history(
                seed["workspaces"][0]["workspaceId"],
                seed["datasets"][0]["datasetId"],
                seed["refreshes"],
            )
            self.replace_incidents(
                seed["workspaces"][0]["workspaceId"],
                seed["datasets"][0]["datasetId"],
                seed["incidents"],
            )

    def upsert_workspaces(self, workspaces: List[Dict[str, Any]]) -> None:
        for workspace in workspaces:
            self._workspaces[workspace["workspaceId"]] = deepcopy(workspace)

    def upsert_reports(self, workspace_id: str, reports: List[Dict[str, Any]]) -> None:
        workspace = self._workspaces.get(workspace_id, {})
        for report in reports:
            self._reports[report["id"]] = {
                **deepcopy(report),
                "workspaceId": workspace_id,
                "workspaceName": workspace.get("workspaceName"),
            }

    def upsert_datasets(
        self,
        workspace_id: str,
        datasets: List[Dict[str, Any]],
    ) -> None:
        for dataset in datasets:
            payload = deepcopy(dataset)
            payload["workspaceId"] = workspace_id
            self._datasets[payload["datasetId"]] = payload

    def upsert_refresh_history(
        self,
        workspace_id: str,
        dataset_id: str,
        refresh_history: List[Dict[str, Any]],
    ) -> None:
        for refresh in refresh_history:
            payload = deepcopy(refresh)
            key = (
                workspace_id,
                dataset_id,
                payload.get("requestId") or payload["refreshId"],
            )
            self._refreshes[key] = payload

    def replace_incidents(
        self,
        workspace_id: str,
        dataset_id: str,
        incidents: List[Dict[str, Any]],
    ) -> None:
        self._incidents = {
            incident_id: incident
            for incident_id, incident in self._incidents.items()
            if not (
                incident["workspaceId"] == workspace_id
                and incident["datasetId"] == dataset_id
            )
        }
        for incident in incidents:
            self._incidents[incident["incidentId"]] = deepcopy(incident)

    def get_workspaces(self) -> List[Dict[str, Any]]:
        return sorted(
            (deepcopy(item) for item in self._workspaces.values()),
            key=lambda item: item.get("workspaceName") or "",
        )

    def get_reports(self) -> List[Dict[str, Any]]:
        return sorted(
            (deepcopy(item) for item in self._reports.values()),
            key=lambda item: item.get("name") or "",
        )

    def get_datasets(self) -> List[Dict[str, Any]]:
        return sorted(
            (deepcopy(item) for item in self._datasets.values()),
            key=lambda item: item.get("datasetName") or "",
        )

    def get_refresh_history(
        self,
        workspace_id: str | None = None,
        dataset_id: str | None = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        refreshes = list(self._refreshes.values())
        if workspace_id:
            refreshes = [
                item for item in refreshes if item.get("workspaceId") == workspace_id
            ]
        if dataset_id:
            refreshes = [
                item for item in refreshes if item.get("datasetId") == dataset_id
            ]
        refreshes.sort(key=lambda item: item.get("startTime") or "", reverse=True)
        return [deepcopy(item) for item in refreshes[:limit]]

    def get_incidents(
        self,
        workspace_id: str | None = None,
        dataset_id: str | None = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        incidents = list(self._incidents.values())
        if workspace_id:
            incidents = [
                item for item in incidents if item.get("workspaceId") == workspace_id
            ]
        if dataset_id:
            incidents = [
                item for item in incidents if item.get("datasetId") == dataset_id
            ]
        incidents.sort(key=lambda item: item.get("detectedAt") or "", reverse=True)
        return [deepcopy(item) for item in incidents[:limit]]


class FakePowerBIClient:
    def list_workspaces(self) -> List[Dict[str, Any]]:
        return [deepcopy(WORKSPACE_RAW)]

    def list_workspace_reports(self, workspace_id: str) -> List[Dict[str, Any]]:
        assert workspace_id == WORKSPACE_RAW["id"]
        return [deepcopy(REPORT_RAW)]

    def list_workspace_datasets(self, workspace_id: str) -> List[Dict[str, Any]]:
        assert workspace_id == WORKSPACE_RAW["id"]
        return [deepcopy(DATASET_RAW)]

    def list_dataset_datasources(
        self,
        workspace_id: str,
        dataset_id: str,
    ) -> List[Dict[str, Any]]:
        assert workspace_id == WORKSPACE_RAW["id"]
        assert dataset_id == DATASET_RAW["id"]
        return [deepcopy(DATASOURCE_RAW)]

    def list_dataset_refresh_history(
        self,
        workspace_id: str,
        dataset_id: str,
        top: int = 10,
    ) -> List[Dict[str, Any]]:
        assert workspace_id == WORKSPACE_RAW["id"]
        assert dataset_id == DATASET_RAW["id"]
        return [deepcopy(item) for item in REFRESH_HISTORY_RAW[:top]]


class ErroringPowerBIClient:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def list_workspaces(self) -> List[Dict[str, Any]]:
        raise self.error


def install_test_doubles(
    monkeypatch: Any,
    *,
    seed: Dict[str, List[Dict[str, Any]]] | None = None,
    client: Any | None = None,
) -> TestClient:
    from App import main
    from App.routes import powerbi

    storage = FakeStorage(seed or build_seed_snapshot())

    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(powerbi, "_storage", lambda: storage)
    monkeypatch.setattr(powerbi, "_client", lambda: client or FakePowerBIClient())

    return TestClient(main.app)


def build_http_error(
    status_code: int,
    payload: Dict[str, Any] | None = None,
    *,
    text_body: str | None = None,
    content_type: str = "application/json",
) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    response.headers["Content-Type"] = content_type

    if payload is not None:
        response._content = json.dumps(payload).encode("utf-8")
    elif text_body is not None:
        response._content = text_body.encode("utf-8")
    else:
        response._content = b""

    return requests.HTTPError(response=response)
