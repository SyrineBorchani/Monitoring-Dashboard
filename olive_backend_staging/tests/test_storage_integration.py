from __future__ import annotations

from copy import deepcopy

from App.storage import PowerBIStorage
from tests.support import build_seed_snapshot


def test_storage_round_trip_persists_and_reads_monitoring_entities(db_session) -> None:
    snapshot = build_seed_snapshot()
    storage = PowerBIStorage(db_session)
    workspace_id = snapshot["workspaces"][0]["workspaceId"]
    dataset_id = snapshot["datasets"][0]["datasetId"]

    storage.upsert_workspaces(snapshot["workspaces"])
    storage.upsert_reports(workspace_id, snapshot["reports"])
    storage.upsert_datasets(workspace_id, snapshot["datasets"])
    storage.upsert_refresh_history(workspace_id, dataset_id, snapshot["refreshes"])
    storage.replace_incidents(workspace_id, dataset_id, snapshot["incidents"])

    assert storage.get_workspaces() == snapshot["workspaces"]
    assert storage.get_reports() == snapshot["reports"]
    assert storage.get_datasets() == snapshot["datasets"]
    assert storage.get_refresh_history(limit=10) == snapshot["refreshes"]
    assert storage.get_incidents(limit=10) == snapshot["incidents"]


def test_upsert_refresh_history_updates_existing_request(db_session) -> None:
    snapshot = build_seed_snapshot()
    storage = PowerBIStorage(db_session)
    workspace_id = snapshot["workspaces"][0]["workspaceId"]
    dataset_id = snapshot["datasets"][0]["datasetId"]

    storage.upsert_refresh_history(workspace_id, dataset_id, [snapshot["refreshes"][0]])

    updated_refresh = deepcopy(snapshot["refreshes"][0])
    updated_refresh["status"] = "Completed"
    updated_refresh["errorCode"] = None
    updated_refresh["errorMessage"] = None
    updated_refresh["endTime"] = "2026-08-04T08:40:00Z"

    storage.upsert_refresh_history(workspace_id, dataset_id, [updated_refresh])

    stored_refreshes = storage.get_refresh_history(limit=10)
    assert len(stored_refreshes) == 1
    assert stored_refreshes[0]["requestId"] == "refresh-2"
    assert stored_refreshes[0]["status"] == "Completed"
    assert stored_refreshes[0]["endTime"] == "2026-08-04T08:40:00Z"


def test_replace_incidents_replaces_only_the_target_dataset(db_session) -> None:
    storage = PowerBIStorage(db_session)

    storage.replace_incidents(
        "workspace-1",
        "dataset-1",
        [
            {
                "incidentId": "dataset-1-old",
                "workspaceId": "workspace-1",
                "datasetId": "dataset-1",
                "refreshId": "refresh-1",
                "incidentType": "FailedRefresh",
                "severity": "Haute",
                "suspectedCause": "Gateway",
                "recommendation": "Check gateway.",
                "detectedAt": "2026-08-04T08:42:00Z",
            }
        ],
    )
    storage.replace_incidents(
        "workspace-1",
        "dataset-2",
        [
            {
                "incidentId": "dataset-2-still-there",
                "workspaceId": "workspace-1",
                "datasetId": "dataset-2",
                "refreshId": "refresh-2",
                "incidentType": "FailedRefresh",
                "severity": "Haute",
                "suspectedCause": "Credentials",
                "recommendation": "Refresh credentials.",
                "detectedAt": "2026-08-04T09:00:00Z",
            }
        ],
    )

    storage.replace_incidents(
        "workspace-1",
        "dataset-1",
        [
            {
                "incidentId": "dataset-1-new",
                "workspaceId": "workspace-1",
                "datasetId": "dataset-1",
                "refreshId": "refresh-3",
                "incidentType": "ConsecutiveFailures",
                "severity": "Haute",
                "suspectedCause": "Gateway",
                "recommendation": "Escalate repeated failures.",
                "detectedAt": "2026-08-04T10:00:00Z",
            }
        ],
    )

    dataset_1_incidents = storage.get_incidents(dataset_id="dataset-1", limit=10)
    dataset_2_incidents = storage.get_incidents(dataset_id="dataset-2", limit=10)

    assert dataset_1_incidents == [
        {
            "incidentId": "dataset-1-new",
            "workspaceId": "workspace-1",
            "datasetId": "dataset-1",
            "refreshId": "refresh-3",
            "incidentType": "ConsecutiveFailures",
            "severity": "Haute",
            "suspectedCause": "Gateway",
            "recommendation": "Escalate repeated failures.",
            "detectedAt": "2026-08-04T10:00:00Z",
        }
    ]
    assert dataset_2_incidents == [
        {
            "incidentId": "dataset-2-still-there",
            "workspaceId": "workspace-1",
            "datasetId": "dataset-2",
            "refreshId": "refresh-2",
            "incidentType": "FailedRefresh",
            "severity": "Haute",
            "suspectedCause": "Credentials",
            "recommendation": "Refresh credentials.",
            "detectedAt": "2026-08-04T09:00:00Z",
        }
    ]
