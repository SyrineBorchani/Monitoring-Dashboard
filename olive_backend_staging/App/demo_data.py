from copy import deepcopy
from typing import Any, Dict, List, Optional

from App.analytics import derive_incidents, summarize_monitoring


DEMO_WORKSPACES: List[Dict[str, Any]] = [
    {
        "id": "ws-finance",
        "name": "Pilotage Finance Executif",
        "type": "Workspace",
        "isReadOnly": False,
        "isOnDedicatedCapacity": True,
        "capacityId": "capacity-east-01",
        "defaultDatasetStorageFormat": "Large",
        "workspaceId": "ws-finance",
        "workspaceName": "Pilotage Finance Executif",
        "workspaceType": "Workspace",
        "capacityMode": "Dedicated",
    },
    {
        "id": "ws-ops",
        "name": "Centre de Supervision Operations",
        "type": "Workspace",
        "isReadOnly": False,
        "isOnDedicatedCapacity": False,
        "capacityId": None,
        "defaultDatasetStorageFormat": "Small",
        "workspaceId": "ws-ops",
        "workspaceName": "Centre de Supervision Operations",
        "workspaceType": "Workspace",
        "capacityMode": "Shared",
    },
]

DEMO_REPORTS: List[Dict[str, Any]] = [
    {
        "id": "report-finance-exec",
        "name": "Vue finance executive",
        "datasetId": "ds-cashflow",
        "webUrl": "https://app.powerbi.com/groups/ws-finance/reports/report-finance-exec",
        "embedUrl": "https://app.powerbi.com/reportEmbed?reportId=report-finance-exec",
        "workspaceId": "ws-finance",
        "workspaceName": "Pilotage Finance Executif",
    },
    {
        "id": "report-ops-command",
        "name": "Suivi des SLA operations",
        "datasetId": "ds-sla",
        "webUrl": "https://app.powerbi.com/groups/ws-ops/reports/report-ops-command",
        "embedUrl": "https://app.powerbi.com/reportEmbed?reportId=report-ops-command",
        "workspaceId": "ws-ops",
        "workspaceName": "Centre de Supervision Operations",
    },
]

DEMO_DATASETS: List[Dict[str, Any]] = [
    {
        "id": "ds-cashflow",
        "name": "Tresorerie quotidienne",
        "configuredBy": "finance.bi@olivesoft.example",
        "isRefreshable": True,
        "isOnPremGatewayRequired": True,
        "datasetId": "ds-cashflow",
        "datasetName": "Tresorerie quotidienne",
        "workspaceId": "ws-finance",
        "workspaceName": "Pilotage Finance Executif",
        "owner": "finance.bi@olivesoft.example",
        "capacityId": "capacity-east-01",
        "capacityMode": "Dedicated",
        "gatewayRequired": True,
        "gatewayIds": ["gw-finance-primary"],
        "primaryGatewayId": "gw-finance-primary",
        "dataSources": [
            {
                "datasourceType": "Sql",
                "gatewayId": "gw-finance-primary",
                "sourceSummary": "sql-prod-01 | FinanceDW",
            }
        ],
        "dataSourceTypes": ["Sql"],
        "dataSourceSummary": ["sql-prod-01 | FinanceDW"],
    },
    {
        "id": "ds-revenue",
        "name": "Modele previsionnel des revenus",
        "configuredBy": "fpanda@olivesoft.example",
        "isRefreshable": True,
        "isOnPremGatewayRequired": False,
        "datasetId": "ds-revenue",
        "datasetName": "Modele previsionnel des revenus",
        "workspaceId": "ws-finance",
        "workspaceName": "Pilotage Finance Executif",
        "owner": "fpanda@olivesoft.example",
        "capacityId": "capacity-east-01",
        "capacityMode": "Dedicated",
        "gatewayRequired": False,
        "gatewayIds": [],
        "primaryGatewayId": None,
        "dataSources": [
            {
                "datasourceType": "AzureSql",
                "gatewayId": None,
                "sourceSummary": "azure-sql-finance | Forecasting",
            }
        ],
        "dataSourceTypes": ["AzureSql"],
        "dataSourceSummary": ["azure-sql-finance | Forecasting"],
    },
    {
        "id": "ds-sla",
        "name": "Suivi des SLA support",
        "configuredBy": "ops.monitoring@olivesoft.example",
        "isRefreshable": True,
        "isOnPremGatewayRequired": True,
        "datasetId": "ds-sla",
        "datasetName": "Suivi des SLA support",
        "workspaceId": "ws-ops",
        "workspaceName": "Centre de Supervision Operations",
        "owner": "ops.monitoring@olivesoft.example",
        "capacityId": None,
        "capacityMode": "Shared",
        "gatewayRequired": True,
        "gatewayIds": ["gw-ops-primary"],
        "primaryGatewayId": "gw-ops-primary",
        "dataSources": [
            {
                "datasourceType": "PostgreSQL",
                "gatewayId": "gw-ops-primary",
                "sourceSummary": "ops-db-02 | support_metrics",
            }
        ],
        "dataSourceTypes": ["PostgreSQL"],
        "dataSourceSummary": ["ops-db-02 | support_metrics"],
    },
    {
        "id": "ds-inventory",
        "name": "Suivi du vieillissement des stocks",
        "configuredBy": "supply.chain@olivesoft.example",
        "isRefreshable": True,
        "isOnPremGatewayRequired": True,
        "datasetId": "ds-inventory",
        "datasetName": "Suivi du vieillissement des stocks",
        "workspaceId": "ws-ops",
        "workspaceName": "Centre de Supervision Operations",
        "owner": "supply.chain@olivesoft.example",
        "capacityId": None,
        "capacityMode": "Shared",
        "gatewayRequired": True,
        "gatewayIds": ["gw-ops-primary"],
        "primaryGatewayId": "gw-ops-primary",
        "dataSources": [
            {
                "datasourceType": "Oracle",
                "gatewayId": "gw-ops-primary",
                "sourceSummary": "oracle-erp-01 | inventory",
            }
        ],
        "dataSourceTypes": ["Oracle"],
        "dataSourceSummary": ["oracle-erp-01 | inventory"],
    },
]

DEMO_REFRESHES: List[Dict[str, Any]] = [
    {
        "requestId": "refresh-001",
        "status": "Completed",
        "refreshType": "ViaApi",
        "startTime": "2026-07-24T06:00:00Z",
        "endTime": "2026-07-24T06:12:00Z",
        "refreshId": "refresh-001",
        "workspaceId": "ws-finance",
        "workspaceName": "Pilotage Finance Executif",
        "datasetId": "ds-cashflow",
        "datasetName": "Tresorerie quotidienne",
        "capacityId": "capacity-east-01",
        "gatewayIds": ["gw-finance-primary"],
        "dataSourceTypes": ["Sql"],
        "durationSeconds": 720.0,
        "durationMinutes": 12.0,
        "errorCode": None,
        "errorMessage": None,
        "refreshAttemptCount": 1,
        "isDelayed": False,
    },
    {
        "requestId": "refresh-002",
        "status": "Completed",
        "refreshType": "Scheduled",
        "startTime": "2026-07-24T03:00:00Z",
        "endTime": "2026-07-24T03:09:00Z",
        "refreshId": "refresh-002",
        "workspaceId": "ws-finance",
        "workspaceName": "Pilotage Finance Executif",
        "datasetId": "ds-cashflow",
        "datasetName": "Tresorerie quotidienne",
        "capacityId": "capacity-east-01",
        "gatewayIds": ["gw-finance-primary"],
        "dataSourceTypes": ["Sql"],
        "durationSeconds": 540.0,
        "durationMinutes": 9.0,
        "errorCode": None,
        "errorMessage": None,
        "refreshAttemptCount": 1,
        "isDelayed": False,
    },
    {
        "requestId": "refresh-003",
        "status": "Failed",
        "refreshType": "Scheduled",
        "startTime": "2026-07-23T23:10:00Z",
        "endTime": "2026-07-24T00:42:00Z",
        "refreshId": "refresh-003",
        "workspaceId": "ws-finance",
        "workspaceName": "Pilotage Finance Executif",
        "datasetId": "ds-cashflow",
        "datasetName": "Tresorerie quotidienne",
        "capacityId": "capacity-east-01",
        "gatewayIds": ["gw-finance-primary"],
        "dataSourceTypes": ["Sql"],
        "durationSeconds": 5520.0,
        "durationMinutes": 92.0,
        "errorCode": "DM_GWPipeline_Gateway_MashupDataAccessError",
        "errorMessage": "Gateway en timeout pendant la lecture de la source FinanceDW.",
        "refreshAttemptCount": 2,
        "isDelayed": True,
    },
    {
        "requestId": "refresh-004",
        "status": "Completed",
        "refreshType": "Scheduled",
        "startTime": "2026-07-24T05:30:00Z",
        "endTime": "2026-07-24T05:36:00Z",
        "refreshId": "refresh-004",
        "workspaceId": "ws-finance",
        "workspaceName": "Pilotage Finance Executif",
        "datasetId": "ds-revenue",
        "datasetName": "Modele previsionnel des revenus",
        "capacityId": "capacity-east-01",
        "gatewayIds": [],
        "dataSourceTypes": ["AzureSql"],
        "durationSeconds": 360.0,
        "durationMinutes": 6.0,
        "errorCode": None,
        "errorMessage": None,
        "refreshAttemptCount": 1,
        "isDelayed": False,
    },
    {
        "requestId": "refresh-005",
        "status": "Failed",
        "refreshType": "OnDemand",
        "startTime": "2026-07-24T01:20:00Z",
        "endTime": "2026-07-24T01:24:00Z",
        "refreshId": "refresh-005",
        "workspaceId": "ws-finance",
        "workspaceName": "Pilotage Finance Executif",
        "datasetId": "ds-revenue",
        "datasetName": "Modele previsionnel des revenus",
        "capacityId": "capacity-east-01",
        "gatewayIds": [],
        "dataSourceTypes": ["AzureSql"],
        "durationSeconds": 240.0,
        "durationMinutes": 4.0,
        "errorCode": "InvalidCredentials",
        "errorMessage": "Les credentials du dataset ont expire pour la source de prevision.",
        "refreshAttemptCount": 1,
        "isDelayed": False,
    },
    {
        "requestId": "refresh-006",
        "status": "Completed",
        "refreshType": "Scheduled",
        "startTime": "2026-07-24T04:15:00Z",
        "endTime": "2026-07-24T04:38:00Z",
        "refreshId": "refresh-006",
        "workspaceId": "ws-ops",
        "workspaceName": "Centre de Supervision Operations",
        "datasetId": "ds-sla",
        "datasetName": "Suivi des SLA support",
        "capacityId": None,
        "gatewayIds": ["gw-ops-primary"],
        "dataSourceTypes": ["PostgreSQL"],
        "durationSeconds": 1380.0,
        "durationMinutes": 23.0,
        "errorCode": None,
        "errorMessage": None,
        "refreshAttemptCount": 1,
        "isDelayed": False,
    },
    {
        "requestId": "refresh-007",
        "status": "Completed",
        "refreshType": "Scheduled",
        "startTime": "2026-07-23T22:00:00Z",
        "endTime": "2026-07-23T23:40:00Z",
        "refreshId": "refresh-007",
        "workspaceId": "ws-ops",
        "workspaceName": "Centre de Supervision Operations",
        "datasetId": "ds-sla",
        "datasetName": "Suivi des SLA support",
        "capacityId": None,
        "gatewayIds": ["gw-ops-primary"],
        "dataSourceTypes": ["PostgreSQL"],
        "durationSeconds": 6000.0,
        "durationMinutes": 100.0,
        "errorCode": None,
        "errorMessage": None,
        "refreshAttemptCount": 1,
        "isDelayed": True,
    },
    {
        "requestId": "refresh-008",
        "status": "Failed",
        "refreshType": "Scheduled",
        "startTime": "2026-07-24T00:30:00Z",
        "endTime": "2026-07-24T00:39:00Z",
        "refreshId": "refresh-008",
        "workspaceId": "ws-ops",
        "workspaceName": "Centre de Supervision Operations",
        "datasetId": "ds-inventory",
        "datasetName": "Suivi du vieillissement des stocks",
        "capacityId": None,
        "gatewayIds": ["gw-ops-primary"],
        "dataSourceTypes": ["Oracle"],
        "durationSeconds": 540.0,
        "durationMinutes": 9.0,
        "errorCode": "CapacityLimitExceeded",
        "errorMessage": "La capacite partagee etait saturee pendant l'execution du refresh.",
        "refreshAttemptCount": 3,
        "isDelayed": False,
    },
    {
        "requestId": "refresh-009",
        "status": "Completed",
        "refreshType": "Scheduled",
        "startTime": "2026-07-23T18:00:00Z",
        "endTime": "2026-07-23T18:07:00Z",
        "refreshId": "refresh-009",
        "workspaceId": "ws-ops",
        "workspaceName": "Centre de Supervision Operations",
        "datasetId": "ds-inventory",
        "datasetName": "Suivi du vieillissement des stocks",
        "capacityId": None,
        "gatewayIds": ["gw-ops-primary"],
        "dataSourceTypes": ["Oracle"],
        "durationSeconds": 420.0,
        "durationMinutes": 7.0,
        "errorCode": None,
        "errorMessage": None,
        "refreshAttemptCount": 1,
        "isDelayed": False,
    },
    {
        "requestId": "refresh-010",
        "status": "Unknown",
        "refreshType": "Scheduled",
        "startTime": "2026-07-24T07:10:00Z",
        "endTime": None,
        "refreshId": "refresh-010",
        "workspaceId": "ws-ops",
        "workspaceName": "Centre de Supervision Operations",
        "datasetId": "ds-inventory",
        "datasetName": "Suivi du vieillissement des stocks",
        "capacityId": None,
        "gatewayIds": ["gw-ops-primary"],
        "dataSourceTypes": ["Oracle"],
        "durationSeconds": 900.0,
        "durationMinutes": 15.0,
        "errorCode": None,
        "errorMessage": None,
        "refreshAttemptCount": 1,
        "isDelayed": False,
    },
]


def _clone(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return deepcopy(items)


def get_demo_workspaces() -> List[Dict[str, Any]]:
    return _clone(DEMO_WORKSPACES)


def get_demo_reports(workspace_id: Optional[str] = None) -> List[Dict[str, Any]]:
    reports = _clone(DEMO_REPORTS)
    if workspace_id:
        reports = [item for item in reports if item["workspaceId"] == workspace_id]
    return reports


def get_demo_datasets(workspace_id: Optional[str] = None) -> List[Dict[str, Any]]:
    datasets = _clone(DEMO_DATASETS)
    if workspace_id:
        datasets = [item for item in datasets if item["workspaceId"] == workspace_id]
    return datasets


def get_demo_refreshes(
    workspace_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    refreshes = _clone(DEMO_REFRESHES)
    if workspace_id:
        refreshes = [item for item in refreshes if item["workspaceId"] == workspace_id]
    if dataset_id:
        refreshes = [item for item in refreshes if item["datasetId"] == dataset_id]
    refreshes.sort(key=lambda item: item.get("startTime") or "", reverse=True)
    if limit is not None:
        refreshes = refreshes[:limit]
    return refreshes


def get_demo_incidents(
    workspace_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    incidents = derive_incidents(get_demo_refreshes(workspace_id=workspace_id, dataset_id=dataset_id))
    incidents.sort(key=lambda item: item.get("detectedAt") or "", reverse=True)
    if limit is not None:
        incidents = incidents[:limit]
    return incidents


def get_demo_indicators() -> Dict[str, Any]:
    refreshes = get_demo_refreshes()
    incidents = derive_incidents(refreshes)
    return summarize_monitoring(refreshes, incidents)


def get_demo_snapshot(refresh_top: int = 10) -> Dict[str, Any]:
    return {
        "workspaces": get_demo_workspaces(),
        "reports": get_demo_reports(),
        "datasets": get_demo_datasets(),
        "refreshes": get_demo_refreshes(limit=refresh_top * len(DEMO_DATASETS)),
        "incidents": get_demo_incidents(),
    }


def get_demo_mode_payload() -> Dict[str, Any]:
    snapshot = get_demo_snapshot()
    return {
        "mode": "demo",
        "title": "Preuve de concept",
        "description": (
            "Le dashboard utilise un jeu de donnees de demonstration afin de valider "
            "l'experience complete sans credentials Power BI ni base PostgreSQL."
        ),
        "counts": {
            "workspaces": len(snapshot["workspaces"]),
            "reports": len(snapshot["reports"]),
            "datasets": len(snapshot["datasets"]),
            "refreshes": len(snapshot["refreshes"]),
            "incidents": len(snapshot["incidents"]),
        },
    }
