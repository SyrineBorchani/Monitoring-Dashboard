from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from App import analytics
from App.analytics import (
    _connection_summary,
    _extract_error_details,
    build_dataset_record,
    build_datasource_record,
    build_report_record,
    build_refresh_record,
    build_workspace_record,
    derive_incidents,
    parse_datetime,
    summarize_monitoring,
)
from tests.support import (
    DATASOURCE_RAW,
    DATASET_RAW,
    REFRESH_HISTORY_RAW,
    WORKSPACE_RAW,
    build_seed_snapshot,
)


def _build_context():
    workspace = build_workspace_record(deepcopy(WORKSPACE_RAW))
    datasources = [build_datasource_record(deepcopy(DATASOURCE_RAW))]
    dataset = build_dataset_record(deepcopy(DATASET_RAW), workspace, datasources)
    return workspace, dataset


def test_parse_datetime_supports_zulu_timestamps_and_invalid_values() -> None:
    parsed = parse_datetime("2026-08-04T08:30:00Z")
    assert parsed == datetime(2026, 8, 4, 8, 30, tzinfo=timezone.utc)

    assert parse_datetime(None) is None

    with pytest.raises(ValueError):
        parse_datetime("not-a-timestamp")


@pytest.mark.parametrize(
    ("raw_exception", "expected"),
    [
        (
            {"errorCode": "GatewayTimeout", "errorMessage": "Gateway timeout"},
            ("GatewayTimeout", "Gateway timeout"),
        ),
        (
            json.dumps({"code": "Unauthorized", "message": "Token expired"}),
            ("Unauthorized", "Token expired"),
        ),
        ("plain text failure", (None, "plain text failure")),
        (None, (None, None)),
    ],
)
def test_extract_error_details_handles_dict_json_and_plain_text(
    raw_exception,
    expected,
) -> None:
    assert _extract_error_details(raw_exception) == expected


def test_connection_summary_prefers_human_readable_connection_fields() -> None:
    summary = _connection_summary(
        {
            "server": "db01",
            "database": "finance",
            "path": r"C:\Data\report.xlsx",
        }
    )
    assert summary == r"db01 | finance | C:\Data\report.xlsx"

    fallback = _connection_summary({"region": "eu-west", "port": 5432})
    assert fallback == "region=eu-west, port=5432"


def test_build_dataset_record_collects_gateway_and_datasource_metadata() -> None:
    workspace = build_workspace_record(deepcopy(WORKSPACE_RAW))
    datasources = [
        build_datasource_record(deepcopy(DATASOURCE_RAW)),
        build_datasource_record(
            {
                "datasourceType": "SQL",
                "gatewayId": "gateway-2",
                "connectionDetails": {
                    "server": "sql01",
                    "database": "warehouse",
                },
            }
        ),
    ]

    dataset = build_dataset_record(deepcopy(DATASET_RAW), workspace, datasources)

    assert dataset["datasetId"] == "dataset-1"
    assert dataset["workspaceId"] == "workspace-1"
    assert dataset["gatewayIds"] == ["gateway-1", "gateway-2"]
    assert dataset["primaryGatewayId"] == "gateway-1"
    assert dataset["dataSourceTypes"] == ["File", "SQL"]
    assert dataset["dataSourceSummary"] == [
        r"C:\Data\report.xlsx",
        "sql01 | warehouse",
    ]


def test_build_report_record_normalizes_workspace_and_view_count() -> None:
    workspace = build_workspace_record(deepcopy(WORKSPACE_RAW))

    report = build_report_record(
        {
            "id": "report-1",
            "name": "Operations Overview",
            "datasetId": "dataset-1",
            "usageMetrics": {"views": "42"},
        },
        workspace,
    )

    assert report["reportId"] == "report-1"
    assert report["reportName"] == "Operations Overview"
    assert report["workspaceId"] == "workspace-1"
    assert report["workspaceName"] == "Syrine"
    assert report["viewCount"] == 42


def test_build_refresh_record_uses_refresh_attempt_errors_and_computes_duration() -> None:
    workspace, dataset = _build_context()

    refresh = build_refresh_record(
        deepcopy(REFRESH_HISTORY_RAW[0]),
        workspace,
        dataset,
    )

    assert refresh["refreshId"] == "refresh-2"
    assert refresh["durationSeconds"] == 720.0
    assert refresh["durationMinutes"] == 12.0
    assert refresh["errorCode"] == "GatewayTimeout"
    assert refresh["errorMessage"] == "Gateway timeout while reading the source."
    assert refresh["refreshAttemptCount"] == 1
    assert refresh["isDelayed"] is False


def test_build_refresh_record_marks_in_progress_refreshes_as_delayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, dataset = _build_context()
    monkeypatch.setattr(
        analytics,
        "_now_utc",
        lambda: datetime(2026, 8, 4, 10, 45, tzinfo=timezone.utc),
    )

    refresh = build_refresh_record(
        {
            "requestId": "refresh-pending",
            "status": "Unknown",
            "refreshType": "Scheduled",
            "startTime": "2026-08-04T09:00:00Z",
            "refreshAttempts": [],
        },
        workspace,
        dataset,
    )

    assert refresh["durationSeconds"] == 6300.0
    assert refresh["isDelayed"] is True


def test_derive_incidents_emits_failed_and_consecutive_failure_incidents() -> None:
    workspace, dataset = _build_context()
    refreshes = [
        build_refresh_record(deepcopy(item), workspace, dataset)
        for item in REFRESH_HISTORY_RAW
    ]

    incidents = derive_incidents(refreshes)
    incident_types = [item["incidentType"] for item in incidents]

    assert incident_types.count("FailedRefresh") == 2
    assert incident_types.count("ConsecutiveFailures") == 1


def test_derive_incidents_emits_delayed_anomaly_and_not_executed_incidents() -> None:
    workspace, dataset = _build_context()
    refreshes = [
        build_refresh_record(
            {
                "requestId": "baseline-completed",
                "status": "Completed",
                "refreshType": "Scheduled",
                "startTime": "2026-08-04T00:00:00Z",
                "endTime": "2026-08-04T00:05:00Z",
            },
            workspace,
            dataset,
        ),
        build_refresh_record(
            {
                "requestId": "anomaly-completed",
                "status": "Completed",
                "refreshType": "Scheduled",
                "startTime": "2026-08-04T02:00:00Z",
                "endTime": "2026-08-04T02:16:40Z",
            },
            workspace,
            dataset,
        ),
        {
            **build_refresh_record(
                {
                    "requestId": "pending-scheduled",
                    "status": "Unknown",
                    "refreshType": "Scheduled",
                    "startTime": "2026-08-04T03:00:00Z",
                },
                workspace,
                dataset,
            ),
            "durationSeconds": 4000.0,
            "isDelayed": True,
        },
    ]

    incidents = derive_incidents(refreshes)
    incident_types = {item["incidentType"] for item in incidents}

    assert "DurationAnomaly" in incident_types
    assert "DelayedRefresh" in incident_types
    assert "RefreshNotExecuted" in incident_types


def test_summarize_monitoring_aggregates_counts_and_breakdowns() -> None:
    workspace, dataset = _build_context()
    refreshes = [
        build_refresh_record(deepcopy(item), workspace, dataset)
        for item in REFRESH_HISTORY_RAW
    ]
    incidents = derive_incidents(refreshes)

    summary = summarize_monitoring(refreshes, incidents)

    assert summary["totals"] == {
        "refreshes": 2,
        "successfulRefreshes": 0,
        "failedRefreshes": 2,
        "inProgressRefreshes": 0,
        "incidents": 3,
        "delayedRefreshes": 0,
        "durationAnomalies": 0,
    }
    assert summary["rates"] == {"successRate": 0.0, "failureRate": 1.0}
    assert summary["datasets"]["mostFailures"] == [
        {
            "datasetId": "dataset-1",
            "datasetName": "report",
            "failureCount": 2,
        }
    ]
    assert summary["incidents"]["byGateway"] == [{"gatewayId": "gateway-1", "count": 3}]
    assert summary["incidents"]["byDataSource"] == [
        {"datasourceType": "File", "count": 3}
    ]


def test_summarize_monitoring_includes_refresh_trends() -> None:
    workspace, dataset = _build_context()
    refreshes = [
        build_refresh_record(deepcopy(item), workspace, dataset)
        for item in REFRESH_HISTORY_RAW
    ]
    incidents = derive_incidents(refreshes)

    summary = summarize_monitoring(refreshes, incidents, [dataset])

    assert summary["trends"]["refreshTimeline"][0]["datasetName"] == "report"
    assert summary["trends"]["dailyRefreshPerformance"][0]["date"] == "2026-08-04"


def test_summarize_monitoring_includes_fabric_inventory_and_procedures() -> None:
    snapshot = build_seed_snapshot()

    summary = summarize_monitoring(
        snapshot["refreshes"],
        snapshot["incidents"],
        snapshot["datasets"],
        snapshot["fabricItems"],
        snapshot["fabricExecutions"],
        snapshot["fabricSqlExecutions"],
    )

    assert summary["fabric"]["inventory"] == {
        "totalItems": 2,
        "warehouseCount": 1,
        "lakehouseCount": 1,
        "sqlEnabledItems": 2,
    }
    assert summary["fabric"]["executions"]["failed"] == 1
    assert summary["fabric"]["procedures"]["storedProcedureExecutionCount"] == 1
    assert summary["fabric"]["procedures"]["slowestStoredProcedures"][0]["procedureName"] == (
        "dbo.RefreshFinanceSnapshot"
    )
