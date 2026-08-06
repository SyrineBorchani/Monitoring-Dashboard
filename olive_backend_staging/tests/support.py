from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import requests
from fastapi.testclient import TestClient

from App.analytics import (
    build_dataset_record,
    build_datasource_record,
    build_fabric_execution_record,
    build_fabric_item_record,
    build_report_record,
    build_fabric_sql_execution_record,
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
    "viewCount": 128,
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

FABRIC_WAREHOUSE_RAW = {
    "id": "warehouse-1",
    "displayName": "Finance Warehouse",
    "description": "Warehouse de production",
    "type": "Warehouse",
    "workspaceId": "workspace-1",
    "properties": {
        "connectionString": "finance-warehouse.fabric.microsoft.com",
        "createdDate": "2026-08-01T08:00:00Z",
        "lastUpdatedTime": "2026-08-04T08:00:00Z",
        "collationType": "Latin1_General_100_CI_AS_KS_WS_SC_UTF8",
    },
}

FABRIC_LAKEHOUSE_RAW = {
    "id": "lakehouse-1",
    "displayName": "Operations Lakehouse",
    "description": "Lakehouse des operations",
    "type": "Lakehouse",
    "workspaceId": "workspace-1",
    "properties": {
        "oneLakeTablesPath": "https://onelake.fabric.microsoft.com/workspace-1/lakehouse-1/Tables",
        "oneLakeFilesPath": "https://onelake.fabric.microsoft.com/workspace-1/lakehouse-1/Files",
        "sqlEndpointProperties": {
            "id": "sql-endpoint-1",
            "connectionString": "operations-lakehouse.fabric.microsoft.com",
            "provisioningStatus": "Success",
        },
    },
}

FABRIC_EXECUTIONS_RAW = {
    "warehouse-1": [
        {
            "id": "warehouse-exec-1",
            "itemId": "warehouse-1",
            "jobType": "DefaultJob",
            "invokeType": "Manual",
            "status": "Completed",
            "startTimeUtc": "2026-08-04T08:00:00Z",
            "endTimeUtc": "2026-08-04T08:12:00Z",
            "failureReason": None,
        }
    ],
    "lakehouse-1": [
        {
            "id": "lakehouse-exec-1",
            "itemId": "lakehouse-1",
            "jobType": "DefaultJob",
            "invokeType": "Scheduled",
            "status": "Failed",
            "startTimeUtc": "2026-08-04T09:00:00Z",
            "endTimeUtc": "2026-08-04T09:18:00Z",
            "failureReason": {"message": "Pipeline failed."},
        }
    ],
}

FABRIC_SQL_EXECUTIONS_RAW = {
    "warehouse-1": [
        {
            "distributed_statement_id": "sql-exec-1",
            "database_name": "Finance Warehouse",
            "submit_time": "2026-08-04T08:00:00Z",
            "start_time": "2026-08-04T08:00:05Z",
            "end_time": "2026-08-04T08:03:05Z",
            "statement_type": "EXECUTE",
            "total_elapsed_time_ms": 180000,
            "status": "Succeeded",
            "login_name": "service-principal",
            "command": "EXEC dbo.RefreshFinanceSnapshot",
            "error_code": 0,
        }
    ],
    "lakehouse-1": [],
}


def build_empty_snapshot() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "workspaces": [],
        "reports": [],
        "datasets": [],
        "refreshes": [],
        "incidents": [],
        "fabricItems": [],
        "fabricExecutions": [],
        "fabricSqlExecutions": [],
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
    report = build_report_record(deepcopy(REPORT_RAW), workspace)
    fabric_items = [
        build_fabric_item_record(deepcopy(FABRIC_WAREHOUSE_RAW), workspace, "Warehouse"),
        build_fabric_item_record(deepcopy(FABRIC_LAKEHOUSE_RAW), workspace, "Lakehouse"),
    ]
    item_lookup = {item["itemId"]: item for item in fabric_items}
    fabric_executions = []
    for item_id, rows in FABRIC_EXECUTIONS_RAW.items():
        for row in rows:
            fabric_executions.append(
                build_fabric_execution_record(deepcopy(row), item_lookup[item_id])
            )
    fabric_sql_executions = []
    for item_id, rows in FABRIC_SQL_EXECUTIONS_RAW.items():
        for row in rows:
            fabric_sql_executions.append(
                build_fabric_sql_execution_record(deepcopy(row), item_lookup[item_id])
            )
    return {
        "workspaces": [workspace],
        "reports": [report],
        "datasets": [dataset],
        "refreshes": refreshes,
        "incidents": incidents,
        "fabricItems": fabric_items,
        "fabricExecutions": fabric_executions,
        "fabricSqlExecutions": fabric_sql_executions,
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
        self._fabric_items: Dict[str, Dict[str, Any]] = {}
        self._fabric_executions: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._fabric_sql_executions: Dict[Tuple[str, str], Dict[str, Any]] = {}

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
        self.upsert_fabric_items(seed.get("fabricItems", []))
        for item in seed.get("fabricItems", []):
            self.upsert_fabric_executions(
                item["itemId"],
                [
                    execution
                    for execution in seed.get("fabricExecutions", [])
                    if execution.get("itemId") == item["itemId"]
                ],
            )
            self.upsert_fabric_sql_executions(
                item["itemId"],
                [
                    execution
                    for execution in seed.get("fabricSqlExecutions", [])
                    if execution.get("itemId") == item["itemId"]
                ],
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

    def upsert_fabric_items(self, fabric_items: List[Dict[str, Any]]) -> None:
        for item in fabric_items:
            self._fabric_items[item["itemId"]] = deepcopy(item)

    def upsert_fabric_executions(
        self,
        item_id: str,
        fabric_executions: List[Dict[str, Any]],
    ) -> None:
        for execution in fabric_executions:
            self._fabric_executions[(item_id, execution["executionId"])] = deepcopy(execution)

    def upsert_fabric_sql_executions(
        self,
        item_id: str,
        sql_executions: List[Dict[str, Any]],
    ) -> None:
        for execution in sql_executions:
            self._fabric_sql_executions[(item_id, execution["queryId"])] = deepcopy(execution)

    def get_fabric_items(
        self,
        workspace_id: str | None = None,
        item_type: str | None = None,
    ) -> List[Dict[str, Any]]:
        items = list(self._fabric_items.values())
        if workspace_id:
            items = [item for item in items if item.get("workspaceId") == workspace_id]
        if item_type:
            items = [item for item in items if item.get("itemType") == item_type]
        items.sort(key=lambda item: (item.get("itemType") or "", item.get("itemName") or ""))
        return [deepcopy(item) for item in items]

    def get_fabric_executions(
        self,
        workspace_id: str | None = None,
        item_id: str | None = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        executions = list(self._fabric_executions.values())
        if workspace_id:
            executions = [item for item in executions if item.get("workspaceId") == workspace_id]
        if item_id:
            executions = [item for item in executions if item.get("itemId") == item_id]
        executions.sort(key=lambda item: item.get("startTimeUtc") or "", reverse=True)
        return [deepcopy(item) for item in executions[:limit]]

    def get_fabric_sql_executions(
        self,
        workspace_id: str | None = None,
        item_id: str | None = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        executions = list(self._fabric_sql_executions.values())
        if workspace_id:
            executions = [item for item in executions if item.get("workspaceId") == workspace_id]
        if item_id:
            executions = [item for item in executions if item.get("itemId") == item_id]
        executions.sort(key=lambda item: item.get("startTime") or "", reverse=True)
        return [deepcopy(item) for item in executions[:limit]]

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

    def list_workspace_warehouses(self, workspace_id: str) -> List[Dict[str, Any]]:
        assert workspace_id == WORKSPACE_RAW["id"]
        return [deepcopy(FABRIC_WAREHOUSE_RAW)]

    def list_workspace_lakehouses(self, workspace_id: str) -> List[Dict[str, Any]]:
        assert workspace_id == WORKSPACE_RAW["id"]
        return [deepcopy(FABRIC_LAKEHOUSE_RAW)]

    def get_lakehouse(self, workspace_id: str, lakehouse_id: str) -> Dict[str, Any]:
        assert workspace_id == WORKSPACE_RAW["id"]
        assert lakehouse_id == FABRIC_LAKEHOUSE_RAW["id"]
        return deepcopy(FABRIC_LAKEHOUSE_RAW)

    def get_warehouse_connection_string(
        self,
        workspace_id: str,
        warehouse_id: str,
    ) -> str:
        assert workspace_id == WORKSPACE_RAW["id"]
        assert warehouse_id == FABRIC_WAREHOUSE_RAW["id"]
        return FABRIC_WAREHOUSE_RAW["properties"]["connectionString"]

    def list_item_job_instances(self, workspace_id: str, item_id: str) -> List[Dict[str, Any]]:
        assert workspace_id == WORKSPACE_RAW["id"]
        return [deepcopy(item) for item in FABRIC_EXECUTIONS_RAW.get(item_id, [])]


class ErroringPowerBIClient:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def list_workspaces(self) -> List[Dict[str, Any]]:
        raise self.error


class FakeFabricSQLCollector:
    def collect_item_queries(
        self,
        fabric_items: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        return {
            item["itemId"]: [
                deepcopy(query)
                for query in FABRIC_SQL_EXECUTIONS_RAW.get(item["itemId"], [])
            ]
            for item in fabric_items
        }

    def collect_item_queries_from_payload(
        self,
        fabric_items: List[Dict[str, Any]],
        payload: Any,
    ) -> Dict[str, List[Dict[str, Any]]]:
        return self.collect_item_queries(fabric_items)


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
    monkeypatch.setattr(main, "check_database_connection", lambda: (True, None))
    monkeypatch.setattr(
        main,
        "check_external_dependencies",
        lambda: {
            "entra": {"status": "ok"},
            "powerbi": {"status": "ok", "workspaceCount": 1},
        },
    )
    monkeypatch.setattr(powerbi, "_storage", lambda: storage)
    monkeypatch.setattr(powerbi, "_client", lambda: client or FakePowerBIClient())
    monkeypatch.setattr(powerbi, "_fabric_sql_collector", lambda: FakeFabricSQLCollector())

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

