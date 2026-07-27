from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
import requests

from App.analytics import (
    build_dataset_record,
    build_datasource_record,
    build_refresh_record,
    build_workspace_record,
    derive_incidents,
    summarize_monitoring,
)
from App.config import is_demo_mode
from App.database import get_db_session
from App.demo_data import (
    get_demo_datasets,
    get_demo_incidents,
    get_demo_indicators,
    get_demo_mode_payload,
    get_demo_refreshes,
    get_demo_reports,
    get_demo_snapshot,
    get_demo_workspaces,
)
from App.powerbi_client import get_powerbi_client
from App.storage import PowerBIStorage


router = APIRouter(prefix="/api/powerbi", tags=["powerbi"])


def _raise_api_error(error: requests.HTTPError) -> None:
    response = error.response
    detail = "Power BI API request failed."

    if response is not None:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text or detail
        raise HTTPException(status_code=response.status_code, detail=detail) from error

    raise HTTPException(status_code=502, detail=detail) from error


def _client():
    return get_powerbi_client()


def _storage() -> PowerBIStorage:
    return PowerBIStorage(get_db_session())


def _mode_payload() -> Dict[str, Any]:
    if is_demo_mode():
        return get_demo_mode_payload()
    return {
        "mode": "live",
        "title": "Environnement connecte",
        "description": (
            "Le dashboard interroge les APIs Power BI et historise les donnees dans la "
            "base PostgreSQL configuree."
        ),
    }


def _fetch_live_workspaces(storage: PowerBIStorage) -> List[Dict[str, Any]]:
    workspaces = [
        build_workspace_record(item)
        for item in _client().list_workspaces()
    ]
    storage.upsert_workspaces(workspaces)
    return workspaces


def _find_workspace(storage: PowerBIStorage, workspace_id: str) -> Dict[str, Any]:
    workspaces = _fetch_live_workspaces(storage)
    for workspace in workspaces:
        if workspace["workspaceId"] == workspace_id:
            return workspace
    raise HTTPException(status_code=404, detail="Workspace not found.")


def _fetch_live_datasets(
    storage: PowerBIStorage,
    workspaces: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    workspaces = workspaces or _fetch_live_workspaces(storage)
    all_datasets: List[Dict[str, Any]] = []

    for workspace in workspaces:
        workspace_id = workspace["workspaceId"]
        datasets = []
        for raw_dataset in _client().list_workspace_datasets(workspace_id):
            datasources = [
                build_datasource_record(item)
                for item in _client().list_dataset_datasources(
                    workspace_id,
                    raw_dataset["id"],
                )
            ]
            datasets.append(build_dataset_record(raw_dataset, workspace, datasources))
        storage.upsert_datasets(workspace_id, datasets)
        all_datasets.extend(datasets)

    return all_datasets


def _fetch_live_refreshes(
    storage: PowerBIStorage,
    datasets: List[Dict[str, Any]],
    refresh_top: int,
) -> List[Dict[str, Any]]:
    refreshes: List[Dict[str, Any]] = []

    for dataset in datasets:
        workspace = {
            "workspaceId": dataset["workspaceId"],
            "workspaceName": dataset.get("workspaceName"),
        }
        raw_refreshes = _client().list_dataset_refresh_history(
            dataset["workspaceId"],
            dataset["datasetId"],
            top=refresh_top,
        )
        normalized_refreshes = [
            build_refresh_record(item, workspace, dataset)
            for item in raw_refreshes
        ]
        storage.upsert_refresh_history(
            dataset["workspaceId"],
            dataset["datasetId"],
            normalized_refreshes,
        )
        dataset_incidents = derive_incidents(normalized_refreshes)
        storage.replace_incidents(
            dataset["workspaceId"],
            dataset["datasetId"],
            dataset_incidents,
        )
        refreshes.extend(normalized_refreshes)

    return refreshes


def _sync_monitoring_snapshot(
    storage: PowerBIStorage,
    refresh_top: int,
) -> Dict[str, Any]:
    workspaces = _fetch_live_workspaces(storage)
    datasets = _fetch_live_datasets(storage, workspaces)
    refreshes = _fetch_live_refreshes(storage, datasets, refresh_top)
    incidents = storage.get_incidents(limit=5000)
    return {
        "workspaces": workspaces,
        "datasets": datasets,
        "refreshes": refreshes,
        "incidents": incidents,
    }


@router.get("/mode")
def get_operating_mode():
    return _mode_payload()


@router.get("/workspaces")
def get_workspaces():
    if is_demo_mode():
        return {"value": get_demo_workspaces()}
    storage = _storage()
    try:
        return {"value": _fetch_live_workspaces(storage)}
    except requests.HTTPError as error:
        _raise_api_error(error)
    except requests.RequestException as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        storage.db.close()


@router.get("/reports")
def get_reports():
    if is_demo_mode():
        return {"value": get_demo_reports()}
    storage = _storage()
    try:
        workspaces = _fetch_live_workspaces(storage)
        reports: List[Dict[str, Any]] = []
        for workspace in workspaces:
            workspace_reports = _client().list_workspace_reports(workspace["workspaceId"])
            storage.upsert_reports(workspace["workspaceId"], workspace_reports)
            reports.extend(
                [
                    {
                        **report,
                        "workspaceId": workspace["workspaceId"],
                        "workspaceName": workspace.get("workspaceName"),
                    }
                    for report in workspace_reports
                ]
            )
        return {"value": reports}
    except requests.HTTPError as error:
        _raise_api_error(error)
    except requests.RequestException as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        storage.db.close()


@router.get("/datasets")
def get_datasets():
    if is_demo_mode():
        return {"value": get_demo_datasets()}
    storage = _storage()
    try:
        return {"value": _fetch_live_datasets(storage)}
    except requests.HTTPError as error:
        _raise_api_error(error)
    except requests.RequestException as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        storage.db.close()


@router.get("/refreshes")
def get_refreshes(
    refresh_top: int = Query(default=10, ge=1, le=100),
):
    if is_demo_mode():
        return {"value": get_demo_refreshes(limit=refresh_top * len(get_demo_datasets()))}
    storage = _storage()
    try:
        datasets = _fetch_live_datasets(storage)
        return {
            "value": _fetch_live_refreshes(storage, datasets, refresh_top),
        }
    except requests.HTTPError as error:
        _raise_api_error(error)
    except requests.RequestException as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        storage.db.close()


@router.get("/incidents")
def get_incidents(
    refresh_top: int = Query(default=10, ge=1, le=100),
):
    if is_demo_mode():
        _ = refresh_top
        return {"value": get_demo_incidents()}
    storage = _storage()
    try:
        _sync_monitoring_snapshot(storage, refresh_top)
        return {"value": storage.get_incidents(limit=5000)}
    except requests.HTTPError as error:
        _raise_api_error(error)
    except requests.RequestException as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        storage.db.close()


@router.get("/workspaces/{workspace_id}/reports")
def get_workspace_reports(workspace_id: str):
    if is_demo_mode():
        reports = get_demo_reports(workspace_id=workspace_id)
        if not reports:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        return {"value": reports}
    storage = _storage()
    try:
        reports = _client().list_workspace_reports(workspace_id)
        storage.upsert_reports(workspace_id, reports)
        return {"value": reports}
    except requests.HTTPError as error:
        _raise_api_error(error)
    except requests.RequestException as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        storage.db.close()


@router.get("/workspaces/{workspace_id}/datasets")
def get_workspace_datasets(workspace_id: str):
    if is_demo_mode():
        datasets = get_demo_datasets(workspace_id=workspace_id)
        if not datasets:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        return {"value": datasets}
    storage = _storage()
    try:
        workspace = _find_workspace(storage, workspace_id)
        datasets = []
        for raw_dataset in _client().list_workspace_datasets(workspace_id):
            datasources = [
                build_datasource_record(item)
                for item in _client().list_dataset_datasources(
                    workspace_id,
                    raw_dataset["id"],
                )
            ]
            datasets.append(build_dataset_record(raw_dataset, workspace, datasources))
        storage.upsert_datasets(workspace_id, datasets)
        return {"value": datasets}
    except requests.HTTPError as error:
        _raise_api_error(error)
    except requests.RequestException as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        storage.db.close()


@router.get("/workspaces/{workspace_id}/datasets/{dataset_id}/refreshes")
def get_dataset_refresh_history(
    workspace_id: str,
    dataset_id: str,
    top: int = Query(default=10, ge=1, le=100),
):
    if is_demo_mode():
        refreshes = get_demo_refreshes(
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            limit=top,
        )
        if not refreshes:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        return {"value": refreshes}
    storage = _storage()
    try:
        workspace = _find_workspace(storage, workspace_id)
        dataset_payload = None
        for item in _fetch_live_datasets(storage, [workspace]):
            if item["datasetId"] == dataset_id:
                dataset_payload = item
                break
        if dataset_payload is None:
            raise HTTPException(status_code=404, detail="Dataset not found.")

        refresh_history = [
            build_refresh_record(item, workspace, dataset_payload)
            for item in _client().list_dataset_refresh_history(
                workspace_id,
                dataset_id,
                top=top,
            )
        ]
        storage.upsert_refresh_history(workspace_id, dataset_id, refresh_history)
        storage.replace_incidents(
            workspace_id,
            dataset_id,
            derive_incidents(refresh_history),
        )
        return {"value": refresh_history}
    except requests.HTTPError as error:
        _raise_api_error(error)
    except requests.RequestException as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        storage.db.close()


@router.post("/monitoring/sync")
def sync_monitoring_snapshot(
    refresh_top: int = Query(default=10, ge=1, le=100),
):
    if is_demo_mode():
        snapshot = get_demo_snapshot(refresh_top=refresh_top)
        return {
            "message": "Le snapshot de demonstration a ete regenere.",
            "counts": {
                "workspaces": len(snapshot["workspaces"]),
                "datasets": len(snapshot["datasets"]),
                "refreshes": len(snapshot["refreshes"]),
                "incidents": len(snapshot["incidents"]),
            },
        }
    storage = _storage()
    try:
        snapshot = _sync_monitoring_snapshot(storage, refresh_top)
        return {
            "message": "Le snapshot de monitoring a ete synchronise.",
            "counts": {
                "workspaces": len(snapshot["workspaces"]),
                "datasets": len(snapshot["datasets"]),
                "refreshes": len(snapshot["refreshes"]),
                "incidents": len(snapshot["incidents"]),
            },
        }
    except requests.HTTPError as error:
        _raise_api_error(error)
    except requests.RequestException as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        storage.db.close()


@router.get("/monitoring/indicators")
def get_monitoring_indicators(
    live: bool = Query(default=False),
    refresh_top: int = Query(default=10, ge=1, le=100),
):
    if is_demo_mode():
        _ = live
        _ = refresh_top
        return get_demo_indicators()
    storage = _storage()
    try:
        if live:
            snapshot = _sync_monitoring_snapshot(storage, refresh_top)
            refreshes = snapshot["refreshes"]
            incidents = snapshot["incidents"]
        else:
            refreshes = storage.get_refresh_history(limit=5000)
            incidents = storage.get_incidents(limit=5000)
        return summarize_monitoring(refreshes, incidents)
    except requests.HTTPError as error:
        _raise_api_error(error)
    except requests.RequestException as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        storage.db.close()


@router.get("/storage/workspaces")
def get_stored_workspaces():
    if is_demo_mode():
        return {"value": get_demo_workspaces()}
    storage = _storage()
    try:
        return {"value": storage.get_workspaces()}
    finally:
        storage.db.close()


@router.get("/storage/reports")
def get_stored_reports():
    if is_demo_mode():
        return {"value": get_demo_reports()}
    storage = _storage()
    try:
        return {"value": storage.get_reports()}
    finally:
        storage.db.close()


@router.get("/storage/datasets")
def get_stored_datasets():
    if is_demo_mode():
        return {"value": get_demo_datasets()}
    storage = _storage()
    try:
        return {"value": storage.get_datasets()}
    finally:
        storage.db.close()


@router.get("/storage/refreshes")
def get_stored_refresh_history(
    workspace_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=5000),
):
    if is_demo_mode():
        return {
            "value": get_demo_refreshes(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                limit=limit,
            )
        }
    storage = _storage()
    try:
        return {
            "value": storage.get_refresh_history(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                limit=limit,
            )
        }
    finally:
        storage.db.close()


@router.get("/storage/incidents")
def get_stored_incidents(
    workspace_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=5000),
):
    if is_demo_mode():
        return {
            "value": get_demo_incidents(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                limit=limit,
            )
        }
    storage = _storage()
    try:
        return {
            "value": storage.get_incidents(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                limit=limit,
            )
        }
    finally:
        storage.db.close()
